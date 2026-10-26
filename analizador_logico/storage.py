"""Persistencia SQLite para el Analizador Lógico.

Conserva los textos originales, fórmulas serializadas, reglas derivadas y la
relación entre cada análisis y los átomos estables x[id]. Incluye migraciones
compatibles con bases de datos creadas por versiones anteriores.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from logic_engine import (
    Formula,
    atoms_in,
    extract_rules,
    formula_to_dict,
    formula_from_dict,
    normalize_text,
    tokenize_for_display,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LOGIC_ANALYZER_DB", str(BASE_DIR / "analizador_logico.db")))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _ensure_columns(conn: sqlite3.Connection, table: str, declarations: dict[str, str]) -> None:
    present = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, declaration in declarations.items():
        if name not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS propositions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical TEXT NOT NULL UNIQUE,
                phrase TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                original_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                formula_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                objective TEXT NOT NULL DEFAULT 'satisfacibilidad',
                warnings_json TEXT NOT NULL DEFAULT '[]',
                tokens_json TEXT NOT NULL DEFAULT '[]',
                inference_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS manual_statements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                formula_json TEXT NOT NULL,
                formula_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analysis_propositions (
                analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                proposition_id INTEGER NOT NULL REFERENCES propositions(id),
                position INTEGER NOT NULL,
                variable TEXT NOT NULL,
                PRIMARY KEY (analysis_id, proposition_id),
                UNIQUE (analysis_id, position)
            );
            CREATE TABLE IF NOT EXISTS analysis_rules (
                analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                rule_order INTEGER NOT NULL,
                rule_label TEXT NOT NULL,
                left_operand TEXT NOT NULL,
                connector TEXT NOT NULL,
                right_operand TEXT NOT NULL,
                rule_type TEXT NOT NULL,
                result_formula TEXT NOT NULL,
                PRIMARY KEY (analysis_id, rule_order)
            );
            """
        )
        # Migración idempotente para archivos SQLite de las versiones anteriores.
        _ensure_columns(conn, "analyses", {
            "objective": "TEXT NOT NULL DEFAULT 'satisfacibilidad'",
            "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
            "tokens_json": "TEXT NOT NULL DEFAULT '[]'",
            "inference_json": "TEXT NOT NULL DEFAULT '{}'",
        })
    # Backfill de datos relacionales una sola vez al actualizar desde una base anterior.
    # Solo completa relaciones ausentes; no cambia textos ni fórmulas guardadas.
    if schema_version < 1:
        _backfill_legacy_analysis_relations()
        with connect() as conn:
            conn.execute("PRAGMA user_version = 1")


def ensure_atoms(node: Formula) -> dict[str, str]:
    """Registra átomos nuevos y devuelve el identificador estable x[id] de cada uno."""
    labels: dict[str, str] = {}
    with connect() as conn:
        for key in atoms_in(node):
            conn.execute(
                "INSERT OR IGNORE INTO propositions(canonical, phrase, created_at) VALUES (?, ?, ?)",
                (key, key, now_iso()),
            )
            row = conn.execute("SELECT id FROM propositions WHERE canonical = ?", (key,)).fetchone()
            if row is None:
                raise RuntimeError(f"No se pudo registrar la proposición: {key}")
            labels[key] = f"x[{row['id']}]"
    return labels


def atom_rows_for_formula(node: Formula) -> list[dict[str, Any]]:
    keys = atoms_in(node)
    if not keys:
        return []
    placeholders = ",".join("?" for _ in keys)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT id, canonical, phrase, created_at FROM propositions WHERE canonical IN ({placeholders})",
            keys,
        ).fetchall()
    by_key = {row["canonical"]: row for row in rows}
    return [
        {
            "Variable": f"x[{by_key[key]['id']}]",
            "Proposición": by_key[key]["phrase"],
            "Clave normalizada": by_key[key]["canonical"],
            "ID persistente": by_key[key]["id"],
        }
        for key in keys
    ]


def _replace_analysis_relations(
    conn: sqlite3.Connection,
    analysis_id: int,
    node: Formula,
    labels: dict[str, str],
    rules: list[dict[str, Any]],
) -> None:
    conn.execute("DELETE FROM analysis_propositions WHERE analysis_id = ?", (analysis_id,))
    conn.execute("DELETE FROM analysis_rules WHERE analysis_id = ?", (analysis_id,))
    atom_keys = atoms_in(node)
    if atom_keys:
        placeholders = ",".join("?" for _ in atom_keys)
        rows = conn.execute(
            f"SELECT id, canonical FROM propositions WHERE canonical IN ({placeholders})", atom_keys
        ).fetchall()
        ids = {str(row["canonical"]): int(row["id"]) for row in rows}
        for position, atom in enumerate(atom_keys, start=1):
            if atom in ids:
                conn.execute(
                    "INSERT INTO analysis_propositions(analysis_id, proposition_id, position, variable) VALUES (?, ?, ?, ?)",
                    (analysis_id, ids[atom], position, labels.get(atom, f"x[{ids[atom]}]")),
                )
    for index, rule in enumerate(rules, start=1):
        conn.execute(
            """INSERT INTO analysis_rules(
                analysis_id, rule_order, rule_label, left_operand, connector,
                right_operand, rule_type, result_formula
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis_id,
                index,
                str(rule.get("Regla", f"R{index}")),
                str(rule.get("Operando izquierdo", "—")),
                str(rule.get("Conector", "—")),
                str(rule.get("Operando derecho", "—")),
                str(rule.get("Tipo", "—")),
                str(rule.get("Subfórmula resultante", "—")),
            ),
        )


def _backfill_legacy_analysis_relations() -> None:
    with connect() as conn:
        rows = [dict(row) for row in conn.execute(
            """SELECT a.id, a.original_text, a.formula_json, a.tokens_json,
                      (SELECT COUNT(*) FROM analysis_propositions ap WHERE ap.analysis_id = a.id) AS proposition_links,
                      (SELECT COUNT(*) FROM analysis_rules ar WHERE ar.analysis_id = a.id) AS stored_rules
               FROM analyses a ORDER BY a.id"""
        ).fetchall()]
    for row in rows:
        try:
            node = formula_from_dict(json.loads(row["formula_json"]))
            labels = ensure_atoms(node)
            rules = extract_rules(node, labels)
            atom_count = len(atoms_in(node))
            needs_links = int(row["proposition_links"]) < atom_count
            needs_rules = int(row["stored_rules"]) < len(rules)
            tokens = json.loads(row.get("tokens_json") or "[]")
            if needs_links or needs_rules:
                with connect() as conn:
                    _replace_analysis_relations(conn, int(row["id"]), node, labels, rules)
            if not tokens:
                tokens = tokenize_for_display(normalize_text(str(row["original_text"])))
                with connect() as conn:
                    conn.execute(
                        "UPDATE analyses SET tokens_json = ? WHERE id = ?",
                        (json.dumps(tokens, ensure_ascii=False), int(row["id"])),
                    )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, sqlite3.Error):
            # Un análisis histórico corrupto no debe impedir el arranque de la app.
            continue


def save_analysis(
    mode: str,
    original_text: str,
    normalized_text: str,
    node: Formula,
    *,
    objective: str = "satisfacibilidad",
    warnings: list[str] | None = None,
    inference: dict[str, Any] | None = None,
) -> int:
    """Guarda texto, fórmula, objetivo, advertencias, tokens, átomos vinculados y reglas."""
    labels = ensure_atoms(node)
    rules = extract_rules(node, labels)
    tokens = tokenize_for_display(normalize_text(original_text))
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO analyses(
                mode, original_text, normalized_text, formula_json, created_at,
                objective, warnings_json, tokens_json, inference_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mode,
                original_text,
                normalized_text,
                json.dumps(formula_to_dict(node), ensure_ascii=False),
                now_iso(),
                objective,
                json.dumps(warnings or [], ensure_ascii=False),
                json.dumps(tokens, ensure_ascii=False),
                json.dumps(inference or {}, ensure_ascii=False),
            ),
        )
        analysis_id = int(cur.lastrowid)
        _replace_analysis_relations(conn, analysis_id, node, labels, rules)
        return analysis_id


def update_analysis_details(
    analysis_id: int,
    *,
    objective: str,
    warnings: list[str],
    tokens: list[dict[str, Any]],
    inference: dict[str, Any] | None = None,
    node: Formula | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> None:
    labels = ensure_atoms(node) if node is not None else {}
    with connect() as conn:
        conn.execute(
            "UPDATE analyses SET objective = ?, warnings_json = ?, tokens_json = ?, inference_json = ? WHERE id = ?",
            (
                objective,
                json.dumps(warnings, ensure_ascii=False),
                json.dumps(tokens, ensure_ascii=False),
                json.dumps(inference or {}, ensure_ascii=False),
                analysis_id,
            ),
        )
        if node is not None and rules is not None:
            _replace_analysis_relations(conn, analysis_id, node, labels, rules)


def list_analyses(limit: int = 25) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, mode, original_text, normalized_text, formula_json, created_at,
                      objective, warnings_json, tokens_json, inference_json
               FROM analyses ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_analysis(analysis_id: int) -> dict[str, Any] | None:
    """Recupera un análisis con reglas y átomos vinculados persistidos."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["saved_rules"] = [dict(item) for item in conn.execute(
            """SELECT rule_label AS 'Regla', left_operand AS 'Operando izquierdo',
                      connector AS 'Conector', right_operand AS 'Operando derecho',
                      rule_type AS 'Tipo', result_formula AS 'Subfórmula resultante'
               FROM analysis_rules WHERE analysis_id = ? ORDER BY rule_order""",
            (analysis_id,),
        ).fetchall()]
        record["saved_propositions"] = [dict(item) for item in conn.execute(
            """SELECT p.id, p.canonical, p.phrase, ap.position, ap.variable
               FROM analysis_propositions ap JOIN propositions p ON p.id = ap.proposition_id
               WHERE ap.analysis_id = ? ORDER BY ap.position""",
            (analysis_id,),
        ).fetchall()]
        return record


def get_latest_analysis() -> dict[str, Any] | None:
    rows = list_analyses(1)
    return get_analysis(int(rows[0]["id"])) if rows else None


def add_manual_statement(original_text: str, normalized_text: str, node: Formula) -> tuple[bool, int | None]:
    """Inserta una premisa/regla manual; evita fórmulas estructurales duplicadas."""
    from logic_engine import formula_key
    key = formula_key(node)
    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO manual_statements(original_text, normalized_text, formula_json, formula_key, created_at) VALUES (?, ?, ?, ?, ?)",
                (original_text, normalized_text, json.dumps(formula_to_dict(node), ensure_ascii=False), key, now_iso()),
            )
            return True, int(cur.lastrowid)
    except sqlite3.IntegrityError:
        with connect() as conn:
            row = conn.execute("SELECT id FROM manual_statements WHERE formula_key = ?", (key,)).fetchone()
        return False, int(row["id"]) if row else None


def list_manual_statements() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, original_text, normalized_text, formula_json, formula_key, created_at FROM manual_statements ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_manual_statement(statement_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM manual_statements WHERE id = ?", (statement_id,))
        return cur.rowcount > 0


def all_atom_rows(limit: int = 1000000) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, phrase, canonical, created_at FROM propositions ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
    return [
        {
            "Variable": f"x[{row['id']}]",
            "Proposición": row["phrase"],
            "Clave normalizada": row["canonical"],
            "Registrada": row["created_at"],
        }
        for row in rows
    ]


def clear_all_data() -> dict[str, int]:
    """Elimina análisis, relaciones, premisas manuales y átomos; reinicia identificadores."""
    with connect() as conn:
        before = {
            "propositions": int(conn.execute("SELECT COUNT(*) FROM propositions").fetchone()[0]),
            "analyses": int(conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]),
            "manual": int(conn.execute("SELECT COUNT(*) FROM manual_statements").fetchone()[0]),
            "rules": int(conn.execute("SELECT COUNT(*) FROM analysis_rules").fetchone()[0]),
        }
        conn.execute("DELETE FROM analysis_rules")
        conn.execute("DELETE FROM analysis_propositions")
        conn.execute("DELETE FROM analyses")
        conn.execute("DELETE FROM manual_statements")
        conn.execute("DELETE FROM propositions")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('analyses', 'manual_statements', 'propositions')")
        return before


def counts() -> dict[str, int]:
    with connect() as conn:
        return {
            "propositions": int(conn.execute("SELECT COUNT(*) FROM propositions").fetchone()[0]),
            "analyses": int(conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]),
            "manual": int(conn.execute("SELECT COUNT(*) FROM manual_statements").fetchone()[0]),
            "rules": int(conn.execute("SELECT COUNT(*) FROM analysis_rules").fetchone()[0]),
        }
