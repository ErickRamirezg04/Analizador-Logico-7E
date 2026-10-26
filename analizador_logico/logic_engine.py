"""Motor de lógica proposicional para el Analizador Lógico.

Admite fórmulas proposicionales en español/inglés con conectores reconocidos,
además de notación simbólica. La conversión de lenguaje natural es intencionalmente
conservadora: no pretende resolver toda la ambigüedad del lenguaje humano.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import re
import unicodedata
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Árbol sintáctico abstracto (AST)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Atom:
    text: str


@dataclass(frozen=True)
class Not:
    child: "Formula"


@dataclass(frozen=True)
class Binary:
    op: str  # AND, OR, IMP, IFF
    left: "Formula"
    right: "Formula"


Formula = Atom | Not | Binary

OP_SYMBOL = {"AND": "∧", "OR": "∨", "IMP": "→", "IFF": "↔"}
OP_NAMES = {
    "AND": "Conjunción (AND / Y)",
    "OR": "Disyunción (OR / O)",
    "IMP": "Condicional (SI…ENTONCES / →)",
    "IFF": "Bicondicional (SI Y SOLO SI / ↔)",
    "NOT": "Negación (NOT / NO / ¬)",
}


def normalize_text(text: str) -> str:
    """Normaliza Unicode, minúsculas, espacios y puntuación final."""
    text = unicodedata.normalize("NFC", text or "").lower().strip()
    text = re.sub(r"\s+", " ", text)
    # La puntuación final no cambia el valor lógico de la fórmula.
    text = re.sub(r"[.!?¡¿;]+\s*$", "", text).strip()
    return text


def strip_entry_label(text: str) -> str:
    """Quita etiquetas de captura como «Regla 1:» sin alterar el texto que se guarda."""
    return re.sub(
        r"^\s*(?:(?:regla|rule|hecho|fact|premisa|premise|proposición|proposicion)\s*#?\s*\d+)\s*:\s*",
        "",
        text or "",
        count=1,
        flags=re.IGNORECASE,
    ).strip()


def canonical_atom(text: str) -> str:
    """Clave estable para evitar duplicados de proposiciones atómicas."""
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(" \t\r\n.,;:!?¡¿()[]{}\"'“”‘’")
    return text


def preprocess_conditionals(text: str) -> tuple[str, list[str]]:
    """Normaliza conectores discursivos y condiciones subordinadas.

    Ejemplos admitidos:
      - si p entonces q
      - si p, q
      - si nos dejan nos vamos a querer toda la vida (heurística de pronombre)
      - p, pero al mismo tiempo q (se formaliza como p AND q)
      - si p entonces q, siempre y cuando r (se formaliza como (p AND r) -> q)
      - if p then q / provided that / as long as

    La formalización del lenguaje natural tiene límites: ciertas frases se
    convierten según convenciones explícitas y se documentan en advertencias.
    """
    s = normalize_text(text)
    warnings: list[str] = []
    s = re.sub(r"\bno es (?:cierto|verdad) que\b", "no", s)

    # Conectores adversativos discursivos: en lógica proposicional se aproximan
    # mediante conjunción. Eliminar "al mismo tiempo" evita incorporarlo al átomo.
    discourse_patterns = (
        (r"\bpero\s+al\s+mismo\s+tiempo\b", " y ", "pero al mismo tiempo"),
        (r"\bpero\b", " y ", "pero"),
        (r"\bsin\s+embargo\b", " y ", "sin embargo"),
        (r"\bno\s+obstante\b", " y ", "no obstante"),
    )
    for pattern, replacement, phrase in discourse_patterns:
        if re.search(pattern, s, flags=re.I):
            s = re.sub(pattern, replacement, s, flags=re.I)
            warnings.append(
                f"Se interpretó «{phrase}» como conjunción lógica (∧). "
                "El matiz discursivo/adversativo no se representa por separado."
            )

    # Caso explícito: el antecedente y consecuente quedan delimitados.
    m = re.match(r"^(si|if)\s+(.+?)\s+(?:,\s*)?(entonces|then)\s+(.+)$", s, flags=re.I)
    if m:
        antecedent, consequent = m.group(2).strip(" ,"), m.group(4).strip(" ,")
        # Expresiones como "siempre y cuando R" o "provided that R" introducen
        # una condición necesaria adicional. Se incorpora al antecedente: (P ∧ R) -> Q.
        condition_pattern = (
            r",?\s*\b(?:siempre\s+y\s+cuando|siempre\s+que|"
            r"a\s+condici[oó]n\s+de\s+que|con\s+tal\s+de\s+que|"
            r"provided\s+that|as\s+long\s+as)\b\s+(.+)$"
        )
        condition_match = re.search(condition_pattern, consequent, flags=re.I)
        if condition_match:
            condition = condition_match.group(1).strip(" ,.")
            main_consequent = consequent[:condition_match.start()].strip(" ,")
            if condition and main_consequent:
                warnings.append(
                    "Se interpretó la condición «siempre y cuando / provided that» como "
                    "una condición adicional del antecedente: (P ∧ condición) → Q. "
                    "Revisa esta formalización si el alcance de la frase pretendía ser distinto."
                )
                return f"(({antecedent}) y ({condition})) -> ({main_consequent})", warnings
        return f"({antecedent}) -> ({consequent})", warnings

    # Caso con coma: en una oración que comienza con "si", la coma puede
    # delimitar el antecedente aunque se omita "entonces".
    m = re.match(r"^(si|if)\s+(.+?),\s*(?:entonces\s+|then\s+)?(.+)$", s, flags=re.I)
    if m:
        antecedent, consequent = m.group(2).strip(" ,"), m.group(3).strip(" ,")
        if antecedent and consequent:
            return f"({antecedent}) -> ({consequent})", warnings

    # Heurística opcional para ejemplos como "si nos dejan nos vamos...".
    # Se busca el inicio repetido de un sujeto/pronombre después del antecedente.
    pronouns = (
        r"yo|t[uú]|[eé]l|ella|nosotros|nosotras|ustedes|ellos|ellas|"
        r"vosotros|vosotras|nos|me|te|se|i|you|he|she|we|they"
    )
    m = re.match(rf"^(si|if)\s+(.+?)\s+({pronouns})\s+(.+)$", s, flags=re.I)
    if m:
        antecedent, consequent = m.group(2).strip(), (m.group(3) + " " + m.group(4)).strip()
        if antecedent and consequent:
            warnings.append(
                "Se infirió el límite del condicional por la repetición de un pronombre. "
                "Revisa que el antecedente y el consecuente sean los deseados; para evitar "
                "ambigüedad escribe «si … entonces …» o usa paréntesis."
            )
            return f"({antecedent}) -> ({consequent})", warnings

    if re.match(r"^(si|if)\b", s) and "entonces" not in s and "then" not in s:
        warnings.append(
            "La oración comienza con «si/if» pero no se pudo determinar con seguridad "
            "dónde termina el antecedente. Usa «si … entonces …», una coma o paréntesis."
        )
    return s, warnings


# Los patrones compuestos se colocan antes de los conectores de una sola palabra.
_SCAN_RE = re.compile(
    r"<=>|<->|↔|⟷|→|⇒|->|=>|∧|∨|¬|~|&|\|"
    r"|\bsi\s+y\s+s[oó]lo\s+si\b|\bsi\s+s[oó]lo\s+si\b|\bsi\s+solamente\s+si\b"
    r"|\bif\s+and\s+only\s+if\b|\biff\b"
    r"|\bonly\s+if\b|\bs[oó]lo\s+si\b|\bsolamente\s+si\b"
    r"|\b(?:and|y|or|o|not|no|negado|negada|entonces|then|implica|implies)\b"
    r"|[()]|[^\W_]+(?:[-’'][^\W_]+)*|[^\w\s]",
    flags=re.I | re.UNICODE,
)


def _scan_logic_tokens(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    for match in _SCAN_RE.finditer(text):
        raw = match.group(0).strip()
        low = raw.lower()
        if not raw:
            continue
        if low in {"<->", "<=>", "↔", "⟷", "si y solo si", "si y sólo si", "si solo si", "si sólo si", "si solamente si", "if and only if", "iff"}:
            tokens.append(("IFF", raw))
        elif low in {"->", "=>", "→", "⇒", "only if", "solo si", "sólo si", "solamente si", "entonces", "then", "implica", "implies"}:
            tokens.append(("IMP", raw))
        elif low in {"∧", "&", "and", "y"}:
            tokens.append(("AND", raw))
        elif low in {"∨", "|", "or", "o"}:
            tokens.append(("OR", raw))
        elif low in {"¬", "~", "not", "no", "negado", "negada"}:
            tokens.append(("NOT", raw))
        elif raw == "(":
            tokens.append(("LPAREN", raw))
        elif raw == ")":
            tokens.append(("RPAREN", raw))
        elif raw in {",", ".", ";", ":", "!", "?", "¡", "¿", '"', "“", "”", "'", "‘", "’"}:
            # Puntuación sin función lógica: no se trata como átomo.
            continue
        else:
            tokens.append(("WORD", raw))
    return tokens


def tokenize_for_display(text: str) -> list[dict[str, Any]]:
    """Tokenización palabra por palabra; clasifica también conectores de varias palabras."""
    display_tokens = re.findall(
        r"<=>|<->|↔|⟷|→|⇒|->|=>|∧|∨|¬|~|&|\||[()¡¿!?,.;:]|[^\W_]+(?:[-’'][^\W_]+)*",
        text,
        flags=re.I | re.UNICODE,
    )
    connector_map = {
        "and": "Conector AND", "y": "Conector AND", "∧": "Conector AND", "&": "Conector AND",
        "or": "Conector OR", "o": "Conector OR", "∨": "Conector OR", "|": "Conector OR",
        "not": "Negación", "no": "Negación", "¬": "Negación", "~": "Negación",
        "<->": "Bicondicional", "<=>": "Bicondicional", "↔": "Bicondicional", "⟷": "Bicondicional",
        "->": "Condicional", "=>": "Condicional", "→": "Condicional", "⇒": "Condicional",
        "entonces": "Conector condicional", "then": "Conector condicional",
        "si": "Palabra / posible inicio condicional", "if": "Palabra / posible inicio condicional",
        "pero": "Conector AND (adversativo)", "and": "Conector AND", "y": "Conector AND",
    }
    lows = [token.lower() for token in display_tokens]
    categories: list[str | None] = [None] * len(display_tokens)
    multiword = [
        (["siempre", "y", "cuando"], "Condición adicional del condicional"),
        (["pero", "al", "mismo", "tiempo"], "Conjunción con matiz adversativo"),
        (["sin", "embargo"], "Conjunción con matiz adversativo"),
        (["no", "obstante"], "Conjunción con matiz adversativo"),
        (["siempre", "que"], "Condición adicional del condicional"),
        (["a", "condición", "de", "que"], "Condición adicional del condicional"),
        (["con", "tal", "de", "que"], "Condición adicional del condicional"),
        (["provided", "that"], "Condición adicional del condicional"),
        (["as", "long", "as"], "Condición adicional del condicional"),
        (["si", "y", "solo", "si"], "Bicondicional"),
        (["si", "y", "sólo", "si"], "Bicondicional"),
        (["si", "solo", "si"], "Bicondicional"),
        (["si", "sólo", "si"], "Bicondicional"),
        (["si", "solamente", "si"], "Bicondicional"),
        (["if", "and", "only", "if"], "Bicondicional"),
        (["only", "if"], "Condicional"),
        (["solo", "si"], "Condicional"),
        (["sólo", "si"], "Condicional"),
        (["solamente", "si"], "Condicional"),
    ]
    i = 0
    while i < len(lows):
        matched = False
        for phrase, category in multiword:
            size = len(phrase)
            if lows[i:i + size] == phrase:
                for j in range(i, i + size):
                    categories[j] = category
                i += size
                matched = True
                break
        if not matched:
            token = display_tokens[i]
            low = lows[i]
            if low in {"(", ")"}:
                categories[i] = "Agrupación"
            elif low in {",", ".", ";", ":", "!", "?", "¡", "¿"}:
                categories[i] = "Puntuación"
            else:
                categories[i] = connector_map.get(low, "Palabra de proposición")
            i += 1
    return [
        {"Posición": i + 1, "Token": token, "Tipo": categories[i] or "Palabra de proposición"}
        for i, token in enumerate(display_tokens)
    ]


class FormulaParser:
    """Parser recursivo descendente con precedencia proposicional estándar."""
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.i = 0

    def current(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, expected: str | None = None) -> tuple[str, str]:
        tok = self.current()
        if tok is None:
            raise ValueError("La fórmula terminó antes de completar una operación lógica.")
        if expected and tok[0] != expected:
            raise ValueError(f"Se esperaba {expected} y se encontró {tok[1]!r}.")
        self.i += 1
        return tok

    def parse(self) -> Formula:
        if not self.tokens:
            raise ValueError("No se detectó una fórmula. Introduce una oración o expresión lógica.")
        expr = self.parse_iff()
        if self.current() is not None:
            leftover = " ".join(token for _, token in self.tokens[self.i:self.i + 6])
            raise ValueError(f"No se pudo interpretar el fragmento: {leftover!r}. Revisa conectores y paréntesis.")
        return expr

    def parse_iff(self) -> Formula:
        node = self.parse_imp()
        while self.current() and self.current()[0] == "IFF":
            self.take("IFF")
            node = Binary("IFF", node, self.parse_imp())
        return node

    def parse_imp(self) -> Formula:
        node = self.parse_or()
        # La implicación es asociativa por la derecha: p -> q -> r = p -> (q -> r).
        if self.current() and self.current()[0] == "IMP":
            self.take("IMP")
            node = Binary("IMP", node, self.parse_imp())
        return node

    def parse_or(self) -> Formula:
        node = self.parse_and()
        while self.current() and self.current()[0] == "OR":
            self.take("OR")
            node = Binary("OR", node, self.parse_and())
        return node

    def parse_and(self) -> Formula:
        node = self.parse_not()
        while self.current() and self.current()[0] == "AND":
            self.take("AND")
            node = Binary("AND", node, self.parse_not())
        return node

    def parse_not(self) -> Formula:
        if self.current() and self.current()[0] == "NOT":
            self.take("NOT")
            return Not(self.parse_not())
        return self.parse_primary()

    def parse_primary(self) -> Formula:
        tok = self.current()
        if tok is None:
            raise ValueError("Falta una proposición después de un conector lógico.")
        if tok[0] == "LPAREN":
            self.take("LPAREN")
            inner = self.parse_iff()
            self.take("RPAREN")
            return inner
        if tok[0] != "WORD":
            raise ValueError(f"El conector {tok[1]!r} no tiene una proposición a su izquierda o derecha.")
        words: list[str] = []
        while self.current() and self.current()[0] == "WORD":
            words.append(self.take("WORD")[1])

        # En español, la negación gramatical suele aparecer después del sujeto:
        # «el proceso principal NO se ejecuta». Si dejamos "no" como un NOT
        # independiente, el parser cree que el átomo del sujeto terminó y falla
        # ante el fragmento sobrante. En ese contexto, convierte sujeto + predicado
        # en una sola proposición negada, equivalente a ¬(sujeto se ejecuta...).
        # Cuando NOT aparece al inicio del operando (p. ej. «y no llueve»), lo
        # maneja parse_not() como siempre.
        if self.current() and self.current()[0] == "NOT":
            self.take("NOT")
            suffix: list[str] = []
            while self.current() and self.current()[0] == "WORD":
                suffix.append(self.take("WORD")[1])
            if not suffix:
                raise ValueError("La negación aparece después de un sujeto, pero no tiene predicado.")
            phrase = canonical_atom(" ".join(words + suffix))
            if not phrase:
                raise ValueError("Se encontró una proposición vacía después de la negación.")
            return Not(Atom(phrase))

        phrase = canonical_atom(" ".join(words))
        if not phrase:
            raise ValueError("Se encontró una proposición vacía.")
        return Atom(phrase)


def _parse_single_formula(text: str) -> tuple[Formula, str, list[str]]:
    normalized = normalize_text(strip_entry_label(text))
    rewritten, warnings = preprocess_conditionals(normalized)
    rewritten = normalize_text(rewritten)
    tokens = _scan_logic_tokens(rewritten)
    ast = FormulaParser(tokens).parse()
    return ast, rewritten, warnings


def split_text_statements(text: str) -> list[str]:
    """Divide texto por líneas, puntuación de cierre o punto y coma.

    Cada segmento se considera una premisa independiente para análisis de
    conocimiento. Admite viñetas y numeración al inicio de una línea.
    """
    raw = unicodedata.normalize("NFC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    statements: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)", "", line)
        parts = re.split(r";\s*|(?<=[.!?])\s+", line)
        for part in parts:
            part = part.strip()
            if part:
                statements.append(part)
    return statements


def parse_formula(text: str) -> tuple[Formula, str, list[str]]:
    """Devuelve AST, fórmula normalizada y advertencias.

    Varias líneas o frases se interpretan como enunciados independientes unidos
    por conjunción. Es útil tanto para analizar consistencia como para presentar
    todas las premisas en una sola entrada. La segmentación se comunica mediante
    una advertencia porque puntuación y saltos de línea también pueden ser estilo.
    """
    statements = split_text_statements(text)
    if not statements:
        return _parse_single_formula(text)
    if len(statements) == 1:
        return _parse_single_formula(statements[0])

    parsed: list[Formula] = []
    rewritten_parts: list[str] = []
    warnings: list[str] = []
    for statement in statements:
        child, rewritten, child_warnings = _parse_single_formula(statement)
        parsed.append(child)
        rewritten_parts.append(rewritten)
        warnings.extend(child_warnings)
    warnings.append(
        f"Se detectaron {len(parsed)} oraciones/enunciados y se combinaron como conjunción "
        "para analizar el conjunto. Confirma que esta segmentación corresponde al texto."
    )
    return combine_with_and(parsed), " ∧ ".join(f"({part})" for part in rewritten_parts), warnings


# ---------------------------------------------------------------------------
# Serialización, presentación y extracción de reglas/proposiciones
# ---------------------------------------------------------------------------
def formula_to_dict(node: Formula) -> dict[str, Any]:
    if isinstance(node, Atom):
        return {"type": "atom", "text": node.text}
    if isinstance(node, Not):
        return {"type": "not", "child": formula_to_dict(node.child)}
    return {"type": "binary", "op": node.op, "left": formula_to_dict(node.left), "right": formula_to_dict(node.right)}


def formula_from_dict(data: dict[str, Any]) -> Formula:
    kind = data.get("type")
    if kind == "atom":
        return Atom(canonical_atom(str(data["text"])))
    if kind == "not":
        return Not(formula_from_dict(data["child"]))
    if kind == "binary":
        op = str(data["op"])
        if op not in OP_SYMBOL:
            raise ValueError(f"Operador guardado desconocido: {op}")
        return Binary(op, formula_from_dict(data["left"]), formula_from_dict(data["right"]))
    raise ValueError("La fórmula almacenada tiene un formato desconocido.")


def atoms_in(node: Formula) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    def walk(n: Formula) -> None:
        if isinstance(n, Atom):
            key = canonical_atom(n.text)
            if key not in seen:
                seen.add(key)
                found.append(key)
        elif isinstance(n, Not):
            walk(n.child)
        else:
            walk(n.left)
            walk(n.right)
    walk(node)
    return found


def formula_key(node: Formula) -> str:
    """Representación estructural estable para identificar una subfórmula."""
    if isinstance(node, Atom):
        return "A:" + canonical_atom(node.text)
    if isinstance(node, Not):
        return "N(" + formula_key(node.child) + ")"
    return f"{node.op}({formula_key(node.left)},{formula_key(node.right)})"


def format_formula(node: Formula, labels: dict[str, str] | None = None, show_atoms: bool = False) -> str:
    if isinstance(node, Atom):
        key = canonical_atom(node.text)
        if labels and key in labels:
            return labels[key]
        return node.text if show_atoms else node.text
    if isinstance(node, Not):
        child_text = format_formula(node.child, labels, show_atoms)
        return f"¬{child_text}"
    left = format_formula(node.left, labels, show_atoms)
    right = format_formula(node.right, labels, show_atoms)
    return f"({left} {OP_SYMBOL[node.op]} {right})"


def extract_rules(node: Formula, labels: dict[str, str]) -> list[dict[str, str]]:
    """Extrae reglas de abajo hacia arriba: cada nodo compuesto genera una regla."""
    rules: list[dict[str, str]] = []
    def walk(n: Formula) -> None:
        if isinstance(n, Atom):
            return
        if isinstance(n, Not):
            walk(n.child)
            rules.append({
                "Regla": f"R{len(rules) + 1}",
                "Operando izquierdo": format_formula(n.child, labels),
                "Conector": "¬",
                "Operando derecho": "—",
                "Tipo": OP_NAMES["NOT"],
                "Subfórmula resultante": format_formula(n, labels),
            })
            return
        walk(n.left)
        walk(n.right)
        rules.append({
            "Regla": f"R{len(rules) + 1}",
            "Operando izquierdo": format_formula(n.left, labels),
            "Conector": OP_SYMBOL[n.op],
            "Operando derecho": format_formula(n.right, labels),
            "Tipo": OP_NAMES[n.op],
            "Subfórmula resultante": format_formula(n, labels),
        })
    walk(node)
    return rules


def combine_with_and(nodes: list[Formula]) -> Formula:
    if not nodes:
        raise ValueError("No hay proposiciones registradas para combinar.")
    result = nodes[0]
    for node in nodes[1:]:
        result = Binary("AND", result, node)
    return result


# ---------------------------------------------------------------------------
# Tabla de verdad
# ---------------------------------------------------------------------------
def evaluate(node: Formula, assignment: dict[str, bool]) -> bool:
    if isinstance(node, Atom):
        return bool(assignment[canonical_atom(node.text)])
    if isinstance(node, Not):
        return not evaluate(node.child, assignment)
    left, right = evaluate(node.left, assignment), evaluate(node.right, assignment)
    if node.op == "AND":
        return left and right
    if node.op == "OR":
        return left or right
    if node.op == "IMP":
        return (not left) or right
    if node.op == "IFF":
        return left == right
    raise ValueError(f"Operador no soportado: {node.op}")


def truth_table(node: Formula, labels: dict[str, str], max_atoms: int = 12) -> list[dict[str, Any]]:
    atom_keys = atoms_in(node)
    if len(atom_keys) > max_atoms:
        raise ValueError(
            f"La fórmula contiene {len(atom_keys)} proposiciones atómicas. La tabla de verdad "
            f"se limita a {max_atoms} para evitar generar más de {2 ** max_atoms:,} filas."
        )
    rows: list[dict[str, Any]] = []
    for values in product([False, True], repeat=len(atom_keys)):
        assignment = dict(zip(atom_keys, values))
        row: dict[str, Any] = {}
        for key in atom_keys:
            row[labels.get(key, key)] = "V" if assignment[key] else "F"
        row["Fórmula"] = "V" if evaluate(node, assignment) else "F"
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Tableau / árbol semántico con fórmulas con signo T y F
# ---------------------------------------------------------------------------
def signed_decomposition(node: Formula, truth: bool) -> list[list[tuple[Formula, bool]]]:
    """Cada elemento es una rama alternativa; una lista interior conserva la rama."""
    if isinstance(node, Not):
        return [[(node.child, not truth)]]
    if not isinstance(node, Binary):
        return []
    a, b = node.left, node.right
    if node.op == "AND":
        return [[(a, True), (b, True)]] if truth else [[(a, False)], [(b, False)]]
    if node.op == "OR":
        return [[(a, True)], [(b, True)]] if truth else [[(a, False), (b, False)]]
    if node.op == "IMP":
        return [[(a, False)], [(b, True)]] if truth else [[(a, True), (b, False)]]
    if node.op == "IFF":
        if truth:
            return [[(a, True), (b, True)], [(a, False), (b, False)]]
        return [[(a, True), (b, False)], [(a, False), (b, True)]]
    raise ValueError(f"Operador de tableau no soportado: {node.op}")


def tableau(node: Formula, labels: dict[str, str], root_truth: bool = True, max_nodes: int = 700) -> dict[str, Any]:
    """Construye el tableau; limita el tamaño para proteger la interfaz.

    root_truth=True comprueba satisfacibilidad de φ.
    root_truth=False comprueba la satisfacibilidad de ¬φ, equivalente a buscar
    contraejemplos a la validez de φ.
    """
    rows: list[dict[str, Any]] = []
    open_models: list[dict[str, str]] = []
    closed_count = 0
    open_count = 0
    node_counter = 0
    stopped = False

    def add(parent: int | None, branch: str, formula_text: str, rule: str = "", status: str = "") -> int:
        nonlocal node_counter, stopped
        if node_counter >= max_nodes:
            stopped = True
            raise RuntimeError("TABLEAU_LIMIT")
        node_counter += 1
        rows.append({
            "Nodo": node_counter,
            "Padre": parent if parent is not None else "—",
            "Rama": branch,
            "Fórmula / nodo": formula_text,
            "Regla aplicada": rule or "—",
            "Estado": status or "En desarrollo",
        })
        return node_counter

    def signed_text(n: Formula, sign: bool) -> str:
        return ("T " if sign else "F ") + format_formula(n, labels)

    root_id = add(None, "1", signed_text(node, root_truth), "Inicio", "Raíz")

    def expand(
        items: list[tuple[Formula, bool, int]],
        expanded: set[tuple[bool, str]],
        branch: str,
        branch_parent: int,
        depth: int = 0,
    ) -> None:
        nonlocal closed_count, open_count
        if stopped:
            return
        if depth > max_nodes:
            raise RuntimeError("TABLEAU_LIMIT")

        # Una rama cierra si el mismo átomo aparece con ambos signos.
        signs: dict[str, set[bool]] = {}
        for formula, sign, _ in items:
            if isinstance(formula, Atom):
                signs.setdefault(canonical_atom(formula.text), set()).add(sign)
        contradiction = next((key for key, values in signs.items() if len(values) == 2), None)
        if contradiction is not None:
            label = labels.get(contradiction, contradiction)
            add(branch_parent, branch, f"* Cierre: {label} y ¬{label}", "Literal complementario", "Rama cerrada")
            closed_count += 1
            return

        # Estrategia de selección: primero bicondicionales y sus negaciones,
        # después descomposiciones lineales (α), y al final reglas que bifurcan
        # (β). Esta prioridad reduce bifurcaciones prematuras y sigue la pauta
        # didáctica de descomponer ↔ antes que otras conectivas ramificantes.
        candidates: list[tuple[int, int]] = []
        for i, (formula, sign, _) in enumerate(items):
            if isinstance(formula, Atom):
                continue
            key = (sign, formula_key(formula))
            if key in expanded:
                continue
            if isinstance(formula, Not) and isinstance(formula.child, Binary) and formula.child.op == "IFF":
                priority = 0
            elif isinstance(formula, Binary) and formula.op == "IFF":
                priority = 0
            elif isinstance(formula, Not):
                priority = 1
            elif (formula.op == "AND" and sign) or (formula.op == "OR" and not sign) or (formula.op == "IMP" and not sign):
                priority = 1  # reglas α: todas las consecuencias quedan en la misma rama
            else:
                priority = 2  # reglas β: crean ramas alternativas
            candidates.append((priority, i))
        chosen_index = min(candidates)[1] if candidates else None

        if chosen_index is None:
            # Un camino abierto puede dejar átomos sin signo explícito. Para
            # devolver un modelo completo (valuación total), asignamos V por
            # defecto a esos átomos libres; al no imponer restricciones en la
            # rama, esta extensión conserva la satisfacibilidad del camino.
            model: dict[str, str] = {}
            for key in atoms_in(node):
                values = signs.get(key, {True})
                model[labels.get(key, key)] = "V" if True in values else "F"
            model_text = ", ".join(f"{k}={v}" for k, v in model.items()) if model else "sin átomos"
            add(branch_parent, branch, f"Rama abierta: {{{model_text}}}", "Sin fórmulas por expandir", "Rama abierta")
            open_count += 1
            open_models.append(model)
            return

        formula, sign, source_id = items[chosen_index]
        parts = signed_decomposition(formula, sign)
        if not parts:
            new_expanded = set(expanded)
            new_expanded.add((sign, formula_key(formula)))
            expand(items, new_expanded, branch, branch_parent, depth + 1)
            return

        # La fórmula seleccionada queda marcada como utilizada. Las consecuencias
        # se añaden al extremo de la rama, conservando la geometría del tableau.
        selected_label = signed_text(formula, sign)
        source_row = next((r for r in rows if r["Nodo"] == source_id), None)
        if source_row is not None:
            source_row["Regla aplicada"] = f"Descomposición de {selected_label}"
            source_row["Estado"] = "Expandida"

        new_expanded = set(expanded)
        new_expanded.add((sign, formula_key(formula)))
        remaining = items[:chosen_index] + items[chosen_index + 1:]

        if len(parts) == 1:
            next_items = list(remaining)
            current_parent = branch_parent
            for consequence, consequence_sign in parts[0]:
                child_id = add(current_parent, branch, signed_text(consequence, consequence_sign), "Regla α: misma rama")
                next_items.append((consequence, consequence_sign, child_id))
                current_parent = child_id
            expand(next_items, new_expanded, branch, current_parent, depth + 1)
        else:
            split_id = add(branch_parent, branch, f"Bifurcación de {selected_label}", "Regla β: apertura de ramas", "Bifurcación")
            for suffix, alternative in zip(("a", "b"), parts):
                child_branch = f"{branch}.{suffix}"
                branch_marker = add(split_id, child_branch, f"Rama {child_branch}", "Alternativa de la regla β", "Bifurcación")
                next_items = list(remaining)
                current_parent = branch_marker
                for consequence, consequence_sign in alternative:
                    child_id = add(current_parent, child_branch, signed_text(consequence, consequence_sign), "Regla β: alternativa")
                    next_items.append((consequence, consequence_sign, child_id))
                    current_parent = child_id
                expand(next_items, set(new_expanded), child_branch, current_parent, depth + 1)

    try:
        expand([(node, root_truth, root_id)], set(), "1", root_id)
    except RuntimeError as exc:
        if str(exc) != "TABLEAU_LIMIT":
            raise
        stopped = True
        if node_counter < max_nodes + 1:
            node_counter += 1
            rows.append({
                "Nodo": node_counter, "Padre": "—", "Rama": "—",
                "Fórmula / nodo": "Análisis interrumpido por el límite de tamaño",
                "Regla aplicada": "Límite de seguridad", "Estado": "Incompleto",
            })

    if stopped:
        classification = "incompleto"
    elif root_truth:
        classification = "satisfacible" if open_count > 0 else "insatisfacible"
    else:
        classification = "no válida (existe contraejemplo)" if open_count > 0 else "válida"

    return {
        "rows": rows,
        "open_models": open_models,
        "closed_branches": closed_count,
        "open_branches": open_count,
        "classification": classification,
        "complete": not stopped,
        "root_truth": root_truth,
    }
