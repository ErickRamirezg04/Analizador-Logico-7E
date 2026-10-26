"""Interfaz de escritorio del Analizador de Lógica Proposicional.

Aplicación de escritorio con CustomTkinter. El motor lógico y la persistencia
SQLite se mantienen en logic_engine.py y storage.py, respectivamente.
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import tkinter as tk
from tkinter import messagebox, ttk, filedialog

try:
    import customtkinter as ctk
except ImportError as exc:  # Mensaje claro cuando la dependencia aún no se instaló.
    raise SystemExit(
        "No se encontró CustomTkinter. En VS Code, ejecuta la tarea "
        "'Analizador lógico: instalar dependencias' o ejecuta "
        "python -m pip install -r requirements.txt."
    ) from exc

from logic_engine import (
    Atom,
    Binary,
    Not,
    atoms_in,
    combine_with_and,
    extract_rules,
    format_formula,
    formula_from_dict,
    normalize_text,
    parse_formula,
    strip_entry_label,
    tableau,
    tokenize_for_display,
    truth_table,
)
from inference_engine import forward_chain, forward_chain_from_text
from storage import (
    DB_PATH,
    add_manual_statement,
    all_atom_rows,
    atom_rows_for_formula,
    clear_all_data as clear_persisted_data,
    counts,
    delete_manual_statement,
    ensure_atoms,
    get_analysis,
    init_db,
    list_analyses,
    list_manual_statements,
    save_analysis,
    update_analysis_details,
)

BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"

# Paleta de escritorio: azul profundo, fondos oscuros y acento cian.
BG = "#0B1120"
SIDEBAR = "#111B2E"
PANEL = "#151F33"
PANEL_ALT = "#1B2941"
ACCENT = "#38BDF8"
ACCENT_HOVER = "#0EA5E9"
TEXT = "#E5EDF7"
MUTED = "#9AAAC0"
GREEN = "#34D399"
RED = "#FB7185"
AMBER = "#FBBF24"

TOKEN_COLUMNS = ["Posición", "Token", "Tipo"]
PROP_COLUMNS = ["Variable", "Proposición", "Clave normalizada", "ID persistente"]
RULE_COLUMNS = ["Regla", "Operando izquierdo", "Conector", "Operando derecho", "Tipo", "Subfórmula resultante"]
TABLEAU_COLUMNS = ["Nodo", "Padre", "Rama", "Fórmula / nodo", "Regla aplicada", "Estado"]


def _classify_truth(rows: list[dict[str, Any]]) -> str:
    values = [row.get("Fórmula") for row in rows]
    if values and all(value == "V" for value in values):
        return "Tautología: verdadera para todas las valuaciones."
    if values and all(value == "F" for value in values):
        return "Contradicción: falsa para todas las valuaciones."
    return "Contingencia: el valor depende de la valuación de sus átomos."


def _write_csv(filename: str, rows: list[dict[str, Any]], columns: list[str] | None = None) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / filename
    if columns is None:
        columns = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if columns:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return path


def _safe_prefix(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_")
    return value[:48] or "analisis"


def _semantic_tree_text(rows: list[dict[str, Any]], max_nodes: int = 300) -> str:
    """Convierte los nodos Padre→Hijo del tableau en una vista de árbol ASCII."""
    if not rows:
        return "El tableau no produjo nodos."
    by_id = {int(row["Nodo"]): row for row in rows if str(row.get("Nodo", "")).isdigit()}
    children: dict[int, list[int]] = {}
    roots: list[int] = []
    for node_id, row in by_id.items():
        parent = row.get("Padre")
        if isinstance(parent, int) and parent in by_id:
            children.setdefault(parent, []).append(node_id)
        else:
            roots.append(node_id)
    for child_ids in children.values():
        child_ids.sort()
    roots.sort()
    output = ["LEYENDA  T = verdadera · F = falsa · * = rama cerrada", ""]
    stack: list[tuple[int, str, bool]] = [(root, "", True) for root in reversed(roots)]
    emitted = 0
    while stack and emitted < max_nodes:
        node_id, prefix, is_last = stack.pop()
        row = by_id[node_id]
        symbol = "└── " if is_last else "├── "
        label = f"#{node_id} {row.get('Fórmula / nodo', '')}"
        rule = row.get("Regla aplicada")
        status = row.get("Estado")
        if rule and rule != "—":
            label += f"  [{rule}]"
        if status:
            label += f"  ‹{status}›"
        output.append(prefix + symbol + label)
        emitted += 1
        descendants = children.get(node_id, [])
        child_prefix = prefix + ("    " if is_last else "│   ")
        for index in range(len(descendants) - 1, -1, -1):
            stack.append((descendants[index], child_prefix, index == len(descendants) - 1))
    if len(by_id) > emitted:
        output.extend(["", f"Vista limitada a {emitted} de {len(by_id)} nodos. Consulta el CSV completo en exports/."])
    return "\n".join(output)


class LogicAnalyzerApp(ctk.CTk):
    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("Analizador lógico | Sistemas Expertos")
        self.geometry("1440x900")
        self.minsize(1120, 720)
        self.configure(fg_color=BG)

        try:
            init_db()
        except Exception as exc:
            messagebox.showerror(
                "Error de base de datos",
                f"No se pudo inicializar SQLite en:\n{DB_PATH}\n\nDetalle: {exc}\n\nVerifica los permisos de escritura de la carpeta.",
            )
            self.after(100, self.destroy)
            return

        self.objective_var = tk.StringVar(value="Satisfacibilidad")
        self.current_result: dict[str, Any] | None = None
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._setup_ttk_style()
        self._build_shell()
        self._build_pages()
        self.navigate("analysis")
        self.refresh_stats()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------- App shell -----------------------------
    def _setup_ttk_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Logic.Treeview",
            background=PANEL,
            foreground=TEXT,
            fieldbackground=PANEL,
            borderwidth=0,
            rowheight=30,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Logic.Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padding=(8, 8),
        )
        style.map("Logic.Treeview", background=[("selected", "#075985")], foreground=[("selected", "#FFFFFF")])
        style.map("Logic.Treeview.Heading", background=[("active", "#263956")])
        style.configure("Logic.Vertical.TScrollbar", background=PANEL_ALT, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT)
        style.configure("Logic.Horizontal.TScrollbar", background=PANEL_ALT, troughcolor=BG, bordercolor=BG, arrowcolor=TEXT)

    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=246, corner_radius=0, fg_color=SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(8, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(25, 25))
        logo = ctk.CTkLabel(brand, text="∴", font=ctk.CTkFont(family="Segoe UI", size=36, weight="bold"), text_color=ACCENT)
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(brand, text="LÓGICA LAB", font=ctk.CTkFont(size=17, weight="bold"), text_color=TEXT).grid(row=0, column=1, sticky="sw")
        ctk.CTkLabel(brand, text="Sistemas Expertos", font=ctk.CTkFont(size=11), text_color=MUTED).grid(row=1, column=1, sticky="nw")

        ctk.CTkLabel(self.sidebar, text="ESPACIO DE TRABAJO", text_color="#7285A2", font=ctk.CTkFont(size=10, weight="bold")).grid(row=1, column=0, sticky="w", padx=20, pady=(0, 8))
        nav_items = [
            ("analysis", "⌕", "Analizar texto"),
            ("manual", "≡", "Modo manual"),
            ("results", "▦", "Resultados"),
            ("history", "◷", "Historial"),
            ("registry", "▤", "Proposiciones"),
            ("help", "ⓘ", "Guía de uso"),
        ]
        for index, (key, icon, title) in enumerate(nav_items, start=2):
            button = ctk.CTkButton(
                self.sidebar,
                text=f"{icon}    {title}",
                anchor="w",
                height=43,
                corner_radius=9,
                fg_color="transparent",
                hover_color="#22334D",
                text_color=TEXT,
                font=ctk.CTkFont(size=13, weight="normal"),
                command=lambda target=key: self.navigate(target),
            )
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=3)
            self._nav_buttons[key] = button

        ctk.CTkFrame(self.sidebar, height=1, fg_color="#293750").grid(row=9, column=0, sticky="ew", padx=18, pady=(10, 14))
        ctk.CTkLabel(self.sidebar, text="BASE DE DATOS LOCAL", text_color="#7285A2", font=ctk.CTkFont(size=10, weight="bold")).grid(row=10, column=0, sticky="w", padx=20, pady=(0, 10))
        self.stat_props = self._sidebar_stat(11, "Proposiciones únicas", "0")
        self.stat_analyses = self._sidebar_stat(12, "Análisis guardados", "0")
        self.stat_manual = self._sidebar_stat(13, "Entradas manuales", "0")
        ctk.CTkButton(
            self.sidebar,
            text="⌫  Limpieza completa de datos",
            height=36,
            corner_radius=8,
            fg_color="#512637",
            hover_color="#713047",
            text_color="#FFE4E6",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.clear_all_data,
        ).grid(row=14, column=0, sticky="ew", padx=12, pady=(10, 0))
        ctk.CTkLabel(self.sidebar, text="SQLite · Persistencia local", text_color="#7285A2", font=ctk.CTkFont(size=10)).grid(row=15, column=0, sticky="w", padx=20, pady=(8, 12))

        self.main_area = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self.main_area, height=88, fg_color=BG, corner_radius=0)
        self.header.grid(row=0, column=0, sticky="ew", padx=28, pady=(20, 10))
        self.header.grid_columnconfigure(0, weight=1)
        title_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="w")
        self.header_title = ctk.CTkLabel(title_frame, text="Analizar texto", font=ctk.CTkFont(size=25, weight="bold"), text_color=TEXT)
        self.header_title.grid(row=0, column=0, sticky="w")
        self.header_subtitle = ctk.CTkLabel(title_frame, text="Formaliza enunciados y examina su estructura lógica.", font=ctk.CTkFont(size=12), text_color=MUTED)
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        objective_box = ctk.CTkFrame(self.header, fg_color=PANEL, corner_radius=10)
        objective_box.grid(row=0, column=1, rowspan=2, sticky="e", padx=(20, 0))
        ctk.CTkLabel(objective_box, text="OBJETIVO DEL TABLEAU", font=ctk.CTkFont(size=9, weight="bold"), text_color=MUTED).grid(row=0, column=0, padx=12, pady=(8, 0), sticky="w")
        self.objective_menu = ctk.CTkOptionMenu(
            objective_box,
            values=["Satisfacibilidad", "Validez"],
            variable=self.objective_var,
            width=180,
            height=32,
            fg_color="#20304A",
            button_color=ACCENT_HOVER,
            button_hover_color="#0284C7",
            text_color=TEXT,
        )
        self.objective_menu.grid(row=1, column=0, padx=10, pady=(3, 9))
        self.recalculate_button = ctk.CTkButton(
            self.header, text="↻  Recalcular", width=112, height=40,
            fg_color="#20304A", hover_color="#2C4160", text_color=TEXT,
            command=self.recalculate_current,
        )
        self.recalculate_button.grid(row=0, column=2, rowspan=2, padx=(10, 0), sticky="e")

        self.page_host = ctk.CTkFrame(self.main_area, fg_color=BG, corner_radius=0)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

    def _sidebar_stat(self, row: int, caption: str, value: str) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=2)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=caption, text_color=MUTED, font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w")
        label = ctk.CTkLabel(frame, text=value, text_color=TEXT, font=ctk.CTkFont(size=12, weight="bold"))
        label.grid(row=0, column=1, sticky="e")
        return label

    def _build_pages(self) -> None:
        page_specs = {
            "analysis": ("Analizar texto", "Formaliza enunciados y examina su estructura lógica."),
            "manual": ("Modo manual", "Construye un sistema lógico agregando proposiciones una a una."),
            "results": ("Resultados del análisis", "Revisa las tablas y el árbol semántico generado."),
            "history": ("Historial", "Recupera análisis anteriores guardados en SQLite."),
            "registry": ("Registro de proposiciones", "Consulta proposiciones atómicas únicas e identificadores persistentes."),
            "help": ("Guía de uso", "Conectores admitidos, método semántico y límites del sistema."),
        }
        for key, (title, subtitle) in page_specs.items():
            page = ctk.CTkFrame(self.page_host, fg_color=BG, corner_radius=0)
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_columnconfigure(0, weight=1)
            page.grid_rowconfigure(0, weight=0)
            self._pages[key] = page
        self._build_analysis_page()
        self._build_manual_page()
        self._build_results_page()
        self._build_history_page()
        self._build_registry_page()
        self._build_help_page()
        self._page_specs = page_specs

    def navigate(self, page_name: str) -> None:
        if page_name not in self._pages:
            return
        self._pages[page_name].tkraise()
        title, subtitle = self._page_specs[page_name]
        self.header_title.configure(text=title)
        self.header_subtitle.configure(text=subtitle)
        for key, button in self._nav_buttons.items():
            active = key == page_name
            button.configure(
                fg_color="#173653" if active else "transparent",
                text_color=ACCENT if active else TEXT,
                font=ctk.CTkFont(size=13, weight="bold" if active else "normal"),
            )
        if page_name == "manual":
            self.refresh_manual_table()
        elif page_name == "history":
            self.refresh_history_table()
        elif page_name == "registry":
            self.refresh_registry_table()
        elif page_name == "results" and self.current_result is None:
            self._show_empty_results()

    def refresh_stats(self) -> None:
        try:
            stats = counts()
            self.stat_props.configure(text=f"{stats['propositions']:,}")
            self.stat_analyses.configure(text=f"{stats['analyses']:,}")
            self.stat_manual.configure(text=f"{stats['manual']:,}")
        except Exception:
            pass

    def _on_close(self) -> None:
        self.destroy()

    # ------------------------------ Widgets -----------------------------
    def _make_card(self, parent: Any, title: str, subtitle: str | None = None) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=14, border_width=1, border_color="#23324A")
        card.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=15, weight="bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        if subtitle:
            ctk.CTkLabel(header, text=subtitle, font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=860, justify="left").grid(row=1, column=0, sticky="w", pady=(5, 0))
        return card

    def _make_table(
        self,
        parent: Any,
        rows: list[dict[str, Any]],
        columns: list[str] | None = None,
        *,
        height: int = 13,
        on_double_click: Any = None,
    ) -> ttk.Treeview:
        data = list(rows)
        cols = list(columns or (data[0].keys() if data else []))
        if not cols:
            cols = ["Información"]
        wrapper = tk.Frame(parent, bg=PANEL)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(wrapper, columns=cols, show="headings", height=height, style="Logic.Treeview", selectmode="browse")
        for col in cols:
            tree.heading(col, text=col)
            width = 210
            if col.lower() in ("id", "nodo", "padre", "posición", "regla", "rama", "variable"):
                width = 90
            elif col in ("Proposición", "Proposición ingresada", "Texto original", "Fórmula / nodo", "Subfórmula resultante", "Expresión interpretada"):
                width = 260
            elif col in ("Fecha", "Fecha de registro", "Registrada"):
                width = 170
            tree.column(col, width=width, minwidth=80, stretch=True, anchor="w")
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview, style="Logic.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview, style="Logic.Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrapper.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        for index, row in enumerate(data):
            values = ["—" if row.get(col) is None else str(row.get(col, "—")) for col in cols]
            row_id = str(row.get("ID", index))
            # Treeview necesita iid únicos y sencillos, independientemente de los datos del usuario.
            tree.insert("", "end", iid=f"row_{index}_{re.sub('[^a-zA-Z0-9_-]', '_', row_id)}", values=values)
        if on_double_click:
            tree.bind("<Double-1>", on_double_click)
        return tree

    def _clear_container(self, parent: Any) -> None:
        for child in parent.winfo_children():
            child.destroy()

    def _new_textbox(self, parent: Any, *, height: int = 160, font_size: int = 13) -> ctk.CTkTextbox:
        return ctk.CTkTextbox(
            parent,
            height=height,
            fg_color="#0E1728",
            border_color="#2A3B55",
            border_width=1,
            text_color=TEXT,
            corner_radius=10,
            font=ctk.CTkFont(family="Consolas", size=font_size),
            wrap="word",
        )

    # ------------------------------- Pages ------------------------------
    def _build_analysis_page(self) -> None:
        page = self._pages["analysis"]
        page.grid_rowconfigure(1, weight=1)
        intro = ctk.CTkFrame(page, fg_color="transparent")
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(intro, text="De lenguaje natural a lógica proposicional", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(intro, text="Escribe una oración, una fórmula simbólica o varias premisas. Para encadenar reglas, separa cada regla/hecho por una línea o por una oración terminada en punto; el motor derivará conclusiones en la pestaña Encadenamiento.", font=ctk.CTkFont(size=12), text_color=MUTED, wraplength=1000, justify="left").pack(anchor="w", pady=(6, 0))

        card = self._make_card(page, "Entrada de texto", "Admite conectores en español, inglés y notación simbólica. Para condicionales en español, prefiere la forma explícita «si p, entonces q».")
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        self.full_text = self._new_textbox(card, height=300, font_size=14)
        self.full_text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 14))
        self.full_text.insert("1.0", "Si nos dejan, entonces nos vamos a querer toda la vida")

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.analysis_status = ctk.CTkLabel(footer, text="La interpretación del lenguaje natural puede ser ambigua; revisa las advertencias del análisis.", text_color=MUTED, font=ctk.CTkFont(size=11), wraplength=650, justify="left")
        self.analysis_status.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="Limpiar", width=95, fg_color="#263650", hover_color="#344965", command=lambda: self.full_text.delete("1.0", "end")).grid(row=0, column=1, padx=(8, 8))
        ctk.CTkButton(footer, text="Analizar texto  →", width=165, height=40, font=ctk.CTkFont(size=13, weight="bold"), command=self.analyze_full_text).grid(row=0, column=2)

    def _build_manual_page(self) -> None:
        page = self._pages["manual"]
        page.grid_rowconfigure(2, weight=1)
        intro = ctk.CTkFrame(page, fg_color="transparent")
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(intro, text="Construye tu base de conocimiento", font=ctk.CTkFont(size=19, weight="bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(intro, text="Cada entrada se conserva en SQLite. Los duplicados estructurales se detectan y no se agregan por segunda vez.", font=ctk.CTkFont(size=12), text_color=MUTED).pack(anchor="w", pady=(5, 0))

        entry_card = self._make_card(page, "Nueva premisa o regla", "Ejemplos: «tengo tos seca», «Si tengo tos seca entonces tengo un síntoma», «(p y q) -> r».")
        entry_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        entry_card.grid_columnconfigure(0, weight=1)
        self.manual_entry = ctk.CTkEntry(entry_card, height=42, placeholder_text="Escribe una proposición o fórmula lógica…", font=ctk.CTkFont(size=13))
        self.manual_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))
        self.manual_entry.bind("<Return>", lambda _event: self.add_manual())
        controls = ctk.CTkFrame(entry_card, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        ctk.CTkButton(controls, text="＋ Agregar al sistema y analizar todo", command=self.add_manual, height=38).pack(side="left")
        ctk.CTkButton(controls, text="Reanalizar sistema completo", command=self.analyze_manual_system, height=38, fg_color="#174B66", hover_color="#126080").pack(side="left", padx=(10, 0))
        ctk.CTkButton(controls, text="Eliminar seleccionada", command=self.delete_manual, height=38, fg_color="#512637", hover_color="#713047").pack(side="right")

        list_card = self._make_card(page, "Premisas y reglas guardadas", "Doble clic o «Reanalizar sistema completo» analiza todas las entradas almacenadas, no solo una.")
        list_card.grid(row=2, column=0, sticky="nsew")
        list_card.grid_rowconfigure(1, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        self.manual_table_host = ctk.CTkFrame(list_card, fg_color="transparent")
        self.manual_table_host.grid(row=1, column=0, sticky="nsew")
        list_card.grid_rowconfigure(1, weight=1)

    def _build_results_page(self) -> None:
        page = self._pages["results"]
        page.grid_rowconfigure(0, weight=1)
        page.grid_columnconfigure(0, weight=1)
        self.results_outer = ctk.CTkFrame(page, fg_color="transparent")
        self.results_outer.grid(row=0, column=0, sticky="nsew")
        self.results_outer.grid_rowconfigure(0, weight=1)
        self.results_outer.grid_columnconfigure(0, weight=1)
        self._show_empty_results()

    def _build_history_page(self) -> None:
        page = self._pages["history"]
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(toolbar, text="El historial se conserva aunque cierres la aplicación.", text_color=MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkButton(toolbar, text="↻ Actualizar", width=110, command=self.refresh_history_table).pack(side="right")
        card = self._make_card(page, "Análisis recientes", "Selecciona un análisis y pulsa «Abrir análisis» o haz doble clic en la fila.")
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.history_table_host = ctk.CTkFrame(card, fg_color="transparent")
        self.history_table_host.grid(row=1, column=0, sticky="nsew")
        buttonbar = ctk.CTkFrame(card, fg_color="transparent")
        buttonbar.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 16))
        ctk.CTkButton(buttonbar, text="Abrir análisis seleccionado", command=self.open_selected_history, height=38).pack(side="left")

    def _build_registry_page(self) -> None:
        page = self._pages["registry"]
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        toolbar = ctk.CTkFrame(page, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.registry_search_var = tk.StringVar()
        self.registry_search = ctk.CTkEntry(toolbar, textvariable=self.registry_search_var, placeholder_text="Filtrar por proposición o variable…", width=330, height=38)
        self.registry_search.pack(side="left")
        self.registry_search.bind("<KeyRelease>", lambda _event: self.refresh_registry_table())
        ctk.CTkButton(toolbar, text="Exportar CSV", command=self.export_registry, width=120, height=38).pack(side="right")
        ctk.CTkButton(toolbar, text="↻ Actualizar", command=self.refresh_registry_table, width=110, height=38).pack(side="right", padx=(0, 8))
        card = self._make_card(page, "Registro global de átomos", "Cada proposición atómica normalizada conserva su identificador x[id], incluso si eliminas una entrada del modo manual.")
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        self.registry_table_host = ctk.CTkFrame(card, fg_color="transparent")
        self.registry_table_host.grid(row=1, column=0, sticky="nsew")
        self.registry_count_label = ctk.CTkLabel(card, text="", text_color=MUTED, font=ctk.CTkFont(size=11))
        self.registry_count_label.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 14))

    def _build_help_page(self) -> None:
        page = self._pages["help"]
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)
        scroller = ctk.CTkScrollableFrame(page, fg_color=BG, corner_radius=0)
        scroller.grid(row=0, column=0, sticky="nsew")
        scroller.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(scroller, text="Conectores admitidos", font=ctk.CTkFont(size=19, weight="bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", pady=(2, 12))
        connectors = [
            ("Negación", "no p · not p · ¬p · ~p", "¬", "Invierte el valor de verdad de una fórmula."),
            ("Conjunción", "p y q · p and q · p ∧ q · p & q", "∧", "Es verdadera solo cuando ambos operandos son verdaderos."),
            ("Disyunción inclusiva", "p o q · p or q · p ∨ q", "∨", "Es verdadera cuando al menos uno de los operandos es verdadero."),
            ("Condicional", "si p entonces q · if p then q · p -> q · p => q", "→", "Solo es falso cuando el antecedente es verdadero y el consecuente falso."),
            ("Bicondicional", "p si y solo si q · p iff q · p <-> q", "↔", "Es verdadero cuando ambos operandos tienen el mismo valor de verdad."),
        ]
        for row_index, (name, forms, symbol, description) in enumerate(connectors, start=1):
            card = ctk.CTkFrame(scroller, fg_color=PANEL, corner_radius=12)
            card.grid(row=row_index, column=0, sticky="ew", pady=5)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=symbol, font=ctk.CTkFont(size=25, weight="bold"), text_color=ACCENT, width=55).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=13)
            ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT).grid(row=0, column=1, sticky="w", pady=(12, 2))
            ctk.CTkLabel(card, text=forms, font=ctk.CTkFont(family="Consolas", size=11), text_color=ACCENT).grid(row=1, column=1, sticky="w", pady=(0, 3))
            ctk.CTkLabel(card, text=description, font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=800, justify="left").grid(row=2, column=1, sticky="w", pady=(0, 12))

        notes = self._make_card(scroller, "Cómo interpretar el resultado", "")
        notes.grid(row=6, column=0, sticky="ew", pady=(16, 8))
        body = ctk.CTkLabel(
            notes,
            text=(
                "• El parser es recursivo y admite fórmulas anidadas con paréntesis.\n"
                "• Precedencia: ¬, ∧, ∨, →, ↔. Usa paréntesis si el alcance puede ser ambiguo.\n"
                "• Satisfacibilidad: se inicia con T φ. Una rama abierta representa un modelo.\n"
                "• Validez: se inicia con F φ. Si todas las ramas cierran, φ es válida.\n"
                "• Para un argumento H → C, buscar un contraejemplo equivale a evaluar H ∧ ¬C.\n"
                "• SQLite guarda el historial, el texto original, las reglas y su relación con los átomos.\n"
                "• Tanto el modo manual como el análisis de texto aplican encadenamiento hacia adelante a reglas A → B y hechos disponibles. En el modo texto, separa premisas por líneas o por frases terminadas en punto.\n"
                "• La inferencia explica qué regla y antecedentes produjeron cada conclusión; no es diagnóstico clínico.\n"
                "• El lenguaje natural puede ser ambiguo. Revisa advertencias y confirma la segmentación.\n"
                "• La tabla de verdad tiene un límite de 12 átomos y el tableau un límite de nodos."
            ),
            text_color=TEXT, font=ctk.CTkFont(size=12), justify="left", anchor="w", wraplength=1000,
        )
        body.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))

    def _format_inference_report(self, inference: dict[str, Any]) -> str:
        if not inference:
            return (
                "No hay un encadenamiento guardado para este análisis.\n\n"
                "En Analizar texto, coloca cada regla y cada hecho en una línea o sepáralos con punto. "
                "En Modo manual, agrega las entradas una por una; ambos modos utilizan el mismo motor de reglas."
            )
        lines = [
            "MOTOR DE INFERENCIA · ENCADENAMIENTO HACIA ADELANTE",
            "=" * 62,
            str(inference.get("status", "Sin estado")),
            f"Reglas condicionales detectadas: {inference.get('rules_count', 0)}",
            "",
            "HECHOS Y CONCLUSIONES",
            "-" * 62,
        ]
        initial_facts = inference.get("initial_facts", [])
        if initial_facts:
            for fact in initial_facts:
                lines.append(f"[{fact.get('Tipo', 'Hecho')}] {fact.get('Proposición', '')}")
                origin = fact.get("Origen", "")
                justification = fact.get("Justificación", "")
                if origin:
                    lines.append(f"    Origen: {origin}")
                if justification and justification != "Premisa proporcionada por el usuario":
                    lines.append(f"    Justificación: {justification}")
        else:
            lines.append("No se extrajeron hechos atómicos iniciales.")
        lines.extend(["", "TRAZA DE INFERENCIA", "-" * 62])
        derivations = inference.get("derivations", [])
        if derivations:
            for row in derivations:
                lines.extend([
                    f"Paso {row.get('Paso')}: {row.get('Regla')}",
                    f"    Regla: {row.get('Regla ingresada')}",
                    f"    Antecedente demostrado: {row.get('Antecedente demostrado')}",
                    f"    Hechos utilizados: {row.get('Hechos utilizados')}",
                    f"    ⇒ Conclusión: {row.get('Conclusión')}",
                    "",
                ])
        else:
            lines.append("No se activó ninguna regla con los hechos actuales.")
        lines.extend(["CONCLUSIONES NUEVAS", "-" * 62])
        conclusions = inference.get("conclusions", [])
        lines.extend([f"• {item}" for item in conclusions] if conclusions else ["No se derivaron conclusiones nuevas."])
        conflicts = inference.get("conflicts", [])
        if conflicts:
            lines.extend(["", "CONFLICTOS DETECTADOS", "-" * 62])
            lines.extend(f"• {atom} y ¬{atom}" for atom in conflicts)
        warnings = inference.get("warnings", [])
        if warnings:
            lines.extend(["", "ADVERTENCIAS", "-" * 62])
            lines.extend(f"• {warning}" for warning in warnings)
        lines.extend([
            "",
            "ALCANCE",
            "-" * 62,
            str(inference.get("method", "")),
            "Las conclusiones dependen de las premisas ingresadas y de la formalización; no constituyen diagnóstico clínico.",
        ])
        return "\n".join(lines)

    def clear_all_data(self) -> None:
        confirmed = messagebox.askyesno(
            "Confirmar limpieza completa",
            "Esta acción eliminará permanentemente de la base local:\n\n"
            "• Todas las proposiciones e identificadores guardados.\n"
            "• Todas las reglas asociadas a análisis.\n"
            "• Todas las premisas/reglas del modo manual.\n"
            "• El historial y los datos de inferencia.\n"
            "• Los archivos CSV dentro de exports/.\n\n"
            "No se puede deshacer. ¿Deseas continuar?",
            icon="warning",
            default=messagebox.NO,
        )
        if not confirmed:
            return
        try:
            removed = clear_persisted_data()
            removed_csv = 0
            if EXPORT_DIR.exists():
                for item in EXPORT_DIR.iterdir():
                    if item.is_file() and item.suffix.lower() == ".csv":
                        item.unlink()
                        removed_csv += 1
            self.current_result = None
            if hasattr(self, "full_text"):
                self.full_text.delete("1.0", "end")
            if hasattr(self, "manual_entry"):
                self.manual_entry.delete(0, "end")
            if hasattr(self, "registry_search_var"):
                self.registry_search_var.set("")
            self.refresh_stats()
            self.refresh_manual_table()
            self.refresh_history_table()
            self.refresh_registry_table()
            self._show_empty_results()
            self.navigate("analysis")
            messagebox.showinfo(
                "Limpieza completada",
                "La base de conocimiento quedó vacía.\n\n"
                f"Proposiciones eliminadas: {removed['propositions']}\n"
                f"Análisis eliminados: {removed['analyses']}\n"
                f"Entradas manuales eliminadas: {removed['manual']}\n"
                f"Reglas asociadas eliminadas: {removed['rules']}\n"
                f"CSV eliminados: {removed_csv}",
            )
        except Exception as exc:
            messagebox.showerror("No se pudo completar la limpieza", str(exc))

    # ---------------------------- Core actions --------------------------
    def _current_objective(self) -> str:
        return "validez" if self.objective_var.get().strip().lower() == "validez" else "satisfacibilidad"

    def analyze_full_text(self) -> None:
        original = self.full_text.get("1.0", "end").strip()
        if not original:
            messagebox.showwarning("Falta texto", "Escribe una oración o fórmula antes de analizar.")
            return
        try:
            node, rewritten, warnings = parse_formula(original)
            ensure_atoms(node)
            # Además del tableau sobre la fórmula completa, el modo de texto
            # separa sus enunciados y los entrega al mismo motor de reglas que
            # utiliza el modo manual. Así puede derivar conclusiones de una base
            # formada por reglas y hechos capturados en un único cuadro.
            inference = forward_chain_from_text(original)
            warnings.extend(inference.get("warnings", []))
            warnings = list(dict.fromkeys(warnings))
            objective = self._current_objective()
            record_id = save_analysis(
                "texto_completo", original, rewritten, node,
                objective=objective, warnings=warnings, inference=inference,
            )
            self._build_result(
                original, rewritten, warnings, node, objective, record_id,
                inference_result=inference,
            )
            self.refresh_stats()
            self.navigate("results")
        except (ValueError, RecursionError, RuntimeError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo analizar", str(exc))

    def add_manual(self) -> None:
        original = self.manual_entry.get().strip()
        if not original:
            messagebox.showwarning("Falta premisa o regla", "Escribe un hecho o una regla lógica.")
            return
        try:
            node, rewritten, _warnings = parse_formula(strip_entry_label(original))
            ensure_atoms(node)
            inserted, statement_id = add_manual_statement(original, rewritten, node)
            if not inserted:
                self.refresh_manual_table()
                self.refresh_stats()
                messagebox.showinfo(
                    "Duplicado detectado",
                    f"La fórmula ya existe en el sistema manual (ID {statement_id}).\nNo se agregó una segunda entrada.",
                )
                # Aunque el alta sea duplicada, vuelve a analizar el sistema que ya existe.
                self.analyze_manual_system()
                return
            self.manual_entry.delete(0, "end")
            self.refresh_manual_table()
            self.refresh_stats()
            # La entrada nueva no se analiza aisladamente: se recalcula la base completa.
            self.analyze_manual_system()
        except (ValueError, RecursionError, RuntimeError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo agregar", str(exc))

    def analyze_manual_system(self) -> None:
        records = list_manual_statements()
        if not records:
            messagebox.showinfo("Sistema vacío", "Agrega al menos una premisa o regla en el modo manual.")
            return
        try:
            nodes: list[Any] = []
            inference_premises: list[dict[str, Any]] = []
            warnings: list[str] = []
            for record in records:
                node = formula_from_dict(json.loads(record["formula_json"]))
                nodes.append(node)
                inference_premises.append({
                    "id": record["id"],
                    "original_text": record["original_text"],
                    "node": node,
                })
                try:
                    _, _, item_warnings = parse_formula(strip_entry_label(record["original_text"]))
                    warnings.extend(item_warnings)
                except (ValueError, RecursionError):
                    warnings.append(f"No se pudieron revisar las advertencias de la entrada #{record['id']}.")

            combined = combine_with_and(nodes)
            labels = ensure_atoms(combined)
            original = "\n".join(record["original_text"] for record in records)
            rewritten = format_formula(combined, labels)
            inference = forward_chain(inference_premises)
            warnings.extend(inference.get("warnings", []))
            objective = "satisfacibilidad"
            self.objective_var.set("Satisfacibilidad")
            record_id = save_analysis(
                "consistencia_sistema_manual", original, rewritten, combined,
                objective=objective, warnings=warnings, inference=inference,
            )
            self._build_result(
                original, rewritten, warnings, combined, objective, record_id,
                inference_result=inference,
            )
            self.refresh_stats()
            self.refresh_manual_table()
            self.navigate("results")
        except (ValueError, RecursionError, RuntimeError, OSError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo analizar el sistema", str(exc))

    def _build_result(
        self,
        original_text: str,
        rewritten_text: str,
        warnings: list[str],
        node: Any,
        objective: str,
        record_id: int | str,
        *,
        prefix: str | None = None,
        inference_result: dict[str, Any] | None = None,
        stored_record: dict[str, Any] | None = None,
    ) -> None:
        labels = ensure_atoms(node)
        formula = format_formula(node, labels)
        token_rows = tokenize_for_display(normalize_text(original_text))
        rule_rows = extract_rules(node, labels)

        # Cuando se abre el historial, usa los tokens, reglas y advertencias que se
        # guardaron con ese análisis. Esto evita depender de volver a introducir texto.
        if stored_record:
            try:
                stored_tokens = json.loads(stored_record.get("tokens_json") or "[]")
                if stored_tokens:
                    token_rows = stored_tokens
            except (TypeError, json.JSONDecodeError):
                pass
            stored_rules = stored_record.get("saved_rules") or []
            if stored_rules:
                rule_rows = stored_rules
            try:
                saved_warnings = json.loads(stored_record.get("warnings_json") or "[]")
                if isinstance(saved_warnings, list) and saved_warnings:
                    warnings = saved_warnings
            except (TypeError, json.JSONDecodeError):
                pass
            if inference_result is None:
                try:
                    loaded_inference = json.loads(stored_record.get("inference_json") or "{}")
                    inference_result = loaded_inference if isinstance(loaded_inference, dict) else {}
                except (TypeError, json.JSONDecodeError):
                    inference_result = {}

        inference_result = inference_result or {}
        proposition_rows = atom_rows_for_formula(node)
        errors: list[str] = []
        try:
            truth_rows = truth_table(node, labels)
            truth_classification = _classify_truth(truth_rows)
        except (ValueError, RecursionError) as exc:
            truth_rows = []
            truth_classification = f"No se pudo completar la tabla de verdad: {exc}"
            errors.append(truth_classification)
        try:
            tableau_result = tableau(node, labels, root_truth=(objective.lower() != "validez"))
            tableau_rows = tableau_result.get("rows", [])
            model_rows = tableau_result.get("open_models", [])
            tableau_classification = tableau_result.get("classification", "incompleto")
            closed_branches = tableau_result.get("closed_branches", 0)
            open_branches = tableau_result.get("open_branches", 0)
        except (ValueError, RecursionError, RuntimeError) as exc:
            tableau_result = {}
            tableau_rows = []
            model_rows = []
            tableau_classification = f"No se pudo completar el tableau: {exc}"
            closed_branches = open_branches = 0
            errors.append(tableau_classification)

        output_prefix = prefix or f"analisis_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        outputs: list[Path] = []
        try:
            outputs.extend([
                _write_csv(f"{output_prefix}_tokenizacion.csv", token_rows, TOKEN_COLUMNS),
                _write_csv(f"{output_prefix}_proposiciones.csv", proposition_rows, PROP_COLUMNS),
                _write_csv(f"{output_prefix}_reglas.csv", rule_rows, RULE_COLUMNS),
            ])
            if truth_rows:
                outputs.append(_write_csv(f"{output_prefix}_tabla_verdad.csv", truth_rows))
            if tableau_rows:
                outputs.append(_write_csv(f"{output_prefix}_arbol_semantico.csv", tableau_rows, TABLEAU_COLUMNS))
            if model_rows:
                outputs.append(_write_csv(f"{output_prefix}_modelos_abiertos.csv", model_rows))
            if inference_result:
                if inference_result.get("initial_facts"):
                    outputs.append(_write_csv(f"{output_prefix}_hechos_y_conclusiones.csv", inference_result["initial_facts"]))
                if inference_result.get("derivations"):
                    outputs.append(_write_csv(f"{output_prefix}_encadenamiento.csv", inference_result["derivations"]))
        except (OSError, ValueError) as exc:
            errors.append(f"No se pudieron exportar todos los CSV: {exc}")

        self.current_result = {
            "original_text": original_text,
            "rewritten_text": rewritten_text,
            "warnings": list(warnings),
            "node": node,
            "objective": objective,
            "record_id": record_id,
            "formula": formula,
            "tokens": token_rows,
            "propositions": proposition_rows,
            "rules": rule_rows,
            "truth_rows": truth_rows,
            "truth_classification": truth_classification,
            "tableau_result": tableau_result,
            "tableau_rows": tableau_rows,
            "tableau_classification": tableau_classification,
            "closed_branches": closed_branches,
            "open_branches": open_branches,
            "models": model_rows,
            "inference": inference_result,
            "outputs": outputs,
            "errors": errors,
        }
        if isinstance(record_id, int):
            try:
                update_analysis_details(
                    record_id,
                    objective=objective,
                    warnings=list(warnings),
                    tokens=token_rows,
                    inference=inference_result,
                    node=node,
                    rules=rule_rows,
                )
            except Exception:
                errors.append("El análisis se mostró, pero no se pudieron actualizar sus detalles persistidos.")
        self._render_result()

    def recalculate_current(self) -> None:
        if not self.current_result:
            messagebox.showinfo("Sin análisis", "Primero analiza una oración o abre un análisis del historial.")
            return
        current = self.current_result
        self._build_result(
            current["original_text"], current["rewritten_text"], current["warnings"], current["node"],
            self._current_objective(), current["record_id"],
            inference_result=current.get("inference", {}),
        )
        self.navigate("results")

    # ------------------------------ Results -----------------------------
    def _show_empty_results(self) -> None:
        self._clear_container(self.results_outer)
        frame = ctk.CTkFrame(self.results_outer, fg_color=PANEL, corner_radius=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.grid(row=0, column=0, sticky="nsew", padx=30, pady=45)
        ctk.CTkLabel(inner, text="▦", font=ctk.CTkFont(size=48), text_color=ACCENT).pack(pady=(25, 12))
        ctk.CTkLabel(inner, text="Tus resultados aparecerán aquí", font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT).pack()
        ctk.CTkLabel(inner, text="Analiza un texto o agrega una proposición en el modo manual para ver la tokenización, las reglas y el tableau semántico.", text_color=MUTED, wraplength=580, justify="center", font=ctk.CTkFont(size=12)).pack(pady=(10, 24))
        ctk.CTkButton(inner, text="Ir a analizar texto", command=lambda: self.navigate("analysis"), height=40).pack()

    def _render_result(self) -> None:
        result = self.current_result
        if result is None:
            self._show_empty_results()
            return
        self._clear_container(self.results_outer)
        page = ctk.CTkFrame(self.results_outer, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)

        summary = ctk.CTkFrame(page, fg_color=PANEL, corner_radius=14, border_width=1, border_color="#23324A")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        summary.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(summary, text=f"ANÁLISIS #{result['record_id']}  ·  {result['objective'].upper()}", text_color=ACCENT, font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 5))
        ctk.CTkLabel(summary, text=result["formula"], text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=22, weight="bold"), wraplength=1050, justify="left").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 8))
        ctk.CTkLabel(summary, text=f"Original: {result['original_text']}", text_color=MUTED, font=ctk.CTkFont(size=11), wraplength=1050, justify="left").grid(row=2, column=0, sticky="w", padx=18, pady=(0, 10))
        statstrip = ctk.CTkFrame(summary, fg_color="transparent")
        statstrip.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 14))
        quick_stats = [
            ("ÁTOMOS", str(len(atoms_in(result["node"]))), ACCENT),
            ("REGLAS", str(len(result["rules"])), TEXT),
            ("RAMAS CERRADAS", str(result["closed_branches"]), RED),
            ("RAMAS ABIERTAS", str(result["open_branches"]), GREEN),
        ]
        for index, (label, value, color) in enumerate(quick_stats):
            tile = ctk.CTkFrame(statstrip, fg_color=PANEL_ALT, corner_radius=8)
            tile.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0), ipadx=12, ipady=7)
            statstrip.grid_columnconfigure(index, weight=1)
            ctk.CTkLabel(tile, text=label, text_color=MUTED, font=ctk.CTkFont(size=9, weight="bold")).pack(anchor="w", padx=10, pady=(4, 1))
            ctk.CTkLabel(tile, text=value, text_color=color, font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=10, pady=(0, 4))

        tabs = ctk.CTkTabview(page, fg_color=PANEL, segmented_button_fg_color=PANEL_ALT, segmented_button_selected_color="#075985", segmented_button_selected_hover_color="#0369A1", segmented_button_unselected_color=PANEL_ALT, segmented_button_unselected_hover_color="#2C4160", text_color=TEXT)
        tabs.grid(row=1, column=0, sticky="nsew")
        tab_names = ["Resumen", "Encadenamiento", "Tokenización", "Proposiciones", "Reglas", "Tabla de verdad", "Árbol semántico", "Nodos tableau", "Modelos"]
        for name in tab_names:
            tabs.add(name)
        tab_frames = {name: tabs.tab(name) for name in tab_names}
        for frame in tab_frames.values():
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)

        # Resumen: advertencias, clasificación, estado del tableau y archivos.
        summary_tab = tab_frames["Resumen"]
        summary_tab.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(summary_tab, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        left.grid_columnconfigure(0, weight=1)
        truth_color = GREEN if result["truth_classification"].startswith("Tautología") else (RED if result["truth_classification"].startswith("Contradicción") else ACCENT)
        ctk.CTkLabel(left, text="TABLA DE VERDAD", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text=result["truth_classification"], text_color=truth_color, font=ctk.CTkFont(size=13, weight="bold"), wraplength=940, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 14))
        ctk.CTkLabel(left, text="TABLEAU SEMÁNTICO", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(row=2, column=0, sticky="w")
        class_text = self._tableau_explanation(result)
        ctk.CTkLabel(left, text=class_text, text_color=TEXT, font=ctk.CTkFont(size=12), wraplength=950, justify="left").grid(row=3, column=0, sticky="w", pady=(4, 12))
        ctk.CTkLabel(left, text="ADVERTENCIAS DE INTERPRETACIÓN", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(row=4, column=0, sticky="w")
        warnings_box = self._new_textbox(left, height=105, font_size=11)
        warnings_box.grid(row=5, column=0, sticky="ew", pady=(5, 12))
        warning_text = "\n".join(f"• {w}" for w in result["warnings"]) or "No se generaron advertencias para esta entrada."
        warnings_box.insert("1.0", warning_text)
        warnings_box.configure(state="disabled")
        if result["errors"]:
            ctk.CTkLabel(left, text="\n".join(result["errors"]), text_color=AMBER, wraplength=950, justify="left").grid(row=6, column=0, sticky="w", pady=(0, 8))
        next_row = 7
        inference_summary = result.get("inference") or {}
        if inference_summary:
            ctk.CTkLabel(left, text="MOTOR DE INFERENCIA", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(row=next_row, column=0, sticky="w", pady=(0, 3))
            next_row += 1
            conclusion_text = ", ".join(inference_summary.get("conclusions", [])) or "Sin conclusiones nuevas."
            ctk.CTkLabel(
                left,
                text=f"{inference_summary.get('status', '')}\nConclusiones: {conclusion_text}",
                text_color=GREEN if inference_summary.get("conclusions") else TEXT,
                font=ctk.CTkFont(size=12, weight="bold"), wraplength=960, justify="left",
            ).grid(row=next_row, column=0, sticky="w", pady=(0, 9))
            next_row += 1
        export_names = "   ·   ".join(path.name for path in result["outputs"])
        ctk.CTkLabel(left, text=f"CSV exportados a exports/: {export_names or 'ninguno'}", text_color=MUTED, font=ctk.CTkFont(size=10), wraplength=980, justify="left").grid(row=next_row, column=0, sticky="w", pady=(0, 6))
        next_row += 1
        ctk.CTkButton(left, text="Abrir carpeta de exportaciones", command=self.open_exports_folder, fg_color="#263650", hover_color="#344965", height=34).grid(row=next_row, column=0, sticky="w", pady=(3, 10))

        inference_box = ctk.CTkTextbox(
            tab_frames["Encadenamiento"], fg_color="#0E1728", text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12), wrap="word",
        )
        inference_box.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        inference_box.insert("1.0", self._format_inference_report(result.get("inference", {})))
        inference_box.configure(state="disabled")

        self._populate_table_tab(tab_frames["Tokenización"], result["tokens"], TOKEN_COLUMNS)
        self._populate_table_tab(tab_frames["Proposiciones"], result["propositions"], PROP_COLUMNS)
        self._populate_table_tab(tab_frames["Reglas"], result["rules"], RULE_COLUMNS)
        truth_columns = list(result["truth_rows"][0].keys()) if result["truth_rows"] else ["Resultado"]
        self._populate_table_tab(tab_frames["Tabla de verdad"], result["truth_rows"], truth_columns, empty_text=result["truth_classification"])
        tree_box = ctk.CTkTextbox(tab_frames["Árbol semántico"], fg_color="#0E1728", text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=11), wrap="none")
        tree_box.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        tree_box.insert("1.0", _semantic_tree_text(result["tableau_rows"]))
        tree_box.configure(state="disabled")
        self._populate_table_tab(tab_frames["Nodos tableau"], result["tableau_rows"], TABLEAU_COLUMNS)
        model_columns = list(result["models"][0].keys()) if result["models"] else ["Modelos"]
        self._populate_table_tab(tab_frames["Modelos"], result["models"], model_columns, empty_text="No se encontraron modelos abiertos para el objetivo seleccionado.")

    def _populate_table_tab(self, parent: Any, rows: list[dict[str, Any]], columns: list[str], empty_text: str = "No hay filas para mostrar.") -> None:
        self._clear_container(parent)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        if not rows:
            ctk.CTkLabel(parent, text=empty_text, text_color=MUTED, wraplength=850, justify="left").grid(row=0, column=0, sticky="nw", padx=18, pady=20)
            return
        self._make_table(parent, rows, columns, height=15)

    def _tableau_explanation(self, result: dict[str, Any]) -> str:
        classification = str(result["tableau_classification"])
        objective = result["objective"].lower()
        if classification == "satisfacible":
            return "La fórmula es satisfacible: existe al menos una rama abierta que representa un modelo."
        if classification == "insatisfacible":
            return "La fórmula es insatisfacible: todas las ramas del tableau se cerraron por contradicción."
        if classification == "válida":
            return "La fórmula es válida: el tableau iniciado con F φ cierra todas sus ramas; no existe contraejemplo."
        if classification.startswith("no válida"):
            return "La fórmula no es válida: existe una rama abierta que representa un contraejemplo."
        return f"Clasificación: {classification}. Ramas abiertas: {result['open_branches']}; cerradas: {result['closed_branches']}."

    # ---------------------------- Manual mode ---------------------------
    def refresh_manual_table(self) -> None:
        if not hasattr(self, "manual_table_host"):
            return
        self._clear_container(self.manual_table_host)
        records = list_manual_statements()
        rows: list[dict[str, Any]] = []
        for record in records:
            try:
                node = formula_from_dict(json.loads(record["formula_json"]))
                if isinstance(node, Binary) and node.op == "IMP":
                    kind = "Regla condicional"
                elif isinstance(node, Atom):
                    kind = "Hecho atómico"
                elif isinstance(node, Not) and isinstance(node.child, Atom):
                    kind = "Hecho negado"
                else:
                    kind = "Premisa compuesta"
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                kind = "No clasificado"
            rows.append({
                "ID": record["id"],
                "Tipo": kind,
                "Premisa / regla ingresada": record["original_text"],
                "Expresión interpretada": record["normalized_text"],
                "Fecha de registro": record["created_at"],
            })
        self.manual_tree = self._make_table(
            self.manual_table_host, rows,
            ["ID", "Tipo", "Premisa / regla ingresada", "Expresión interpretada", "Fecha de registro"],
            height=11,
            on_double_click=lambda _event: self.open_selected_manual(),
        )

    def open_selected_manual(self) -> None:
        # El análisis manual siempre abarca todas las premisas y reglas persistidas.
        self.analyze_manual_system()

    def delete_manual(self) -> None:
        tree = getattr(self, "manual_tree", None)
        selected = tree.selection() if tree else ()
        if not selected:
            messagebox.showinfo("Selecciona una entrada", "Selecciona una proposición de la tabla antes de eliminarla.")
            return
        values = tree.item(selected[0], "values")
        statement_id = int(values[0])
        if not messagebox.askyesno("Confirmar eliminación", f"¿Eliminar la entrada manual #{statement_id}?\n\nEl registro global de átomos se conserva para mantener los identificadores estables."):
            return
        if delete_manual_statement(statement_id):
            self.refresh_manual_table()
            self.refresh_stats()
            remaining = list_manual_statements()
            if remaining:
                self.analyze_manual_system()
            else:
                self.current_result = None
                self._show_empty_results()
                self.navigate("manual")
            messagebox.showinfo("Entrada eliminada", "La entrada se eliminó del conjunto manual y el sistema restante se actualizó.")

    # ------------------------------ History -----------------------------
    def refresh_history_table(self) -> None:
        if not hasattr(self, "history_table_host"):
            return
        self._clear_container(self.history_table_host)
        records = list_analyses(500)
        rows = [{"ID": r["id"], "Modo": r["mode"], "Texto original": r["original_text"], "Expresión interpretada": r["normalized_text"], "Fecha": r["created_at"]} for r in records]
        self.history_tree = self._make_table(self.history_table_host, rows, ["ID", "Modo", "Texto original", "Expresión interpretada", "Fecha"], height=15, on_double_click=lambda _event: self.open_selected_history())

    def open_selected_history(self) -> None:
        tree = getattr(self, "history_tree", None)
        selected = tree.selection() if tree else ()
        if not selected:
            messagebox.showinfo("Selecciona un análisis", "Selecciona un análisis del historial primero.")
            return
        values = tree.item(selected[0], "values")
        if not values:
            return
        try:
            analysis_id = int(values[0])
        except (TypeError, ValueError):
            messagebox.showerror("Identificador inválido", "No se pudo leer el ID del análisis seleccionado.")
            return
        record = get_analysis(analysis_id)
        if not record:
            messagebox.showerror("No encontrado", "El análisis ya no está disponible en la base de datos.")
            return
        try:
            node = formula_from_dict(json.loads(record["formula_json"]))
            try:
                warnings = json.loads(record.get("warnings_json") or "[]")
                if not isinstance(warnings, list):
                    warnings = []
                if not warnings:
                    _, _, inferred_warnings = parse_formula(record["original_text"])
                    warnings = inferred_warnings
            except (TypeError, json.JSONDecodeError):
                _, _, warnings = parse_formula(record["original_text"])
            objective = str(record.get("objective") or "satisfacibilidad")
            self.objective_var.set("Validez" if objective.lower() == "validez" else "Satisfacibilidad")
            self._build_result(
                record["original_text"], record["normalized_text"], warnings, node,
                objective, int(record["id"]), stored_record=record,
            )
            self.navigate("results")
        except (ValueError, RecursionError, KeyError, TypeError) as exc:
            messagebox.showerror("No se pudo recuperar el análisis", str(exc))

    # ------------------------------ Registry ----------------------------
    def refresh_registry_table(self) -> None:
        if not hasattr(self, "registry_table_host"):
            return
        self._clear_container(self.registry_table_host)
        rows = all_atom_rows()
        query = self.registry_search_var.get().strip().casefold() if hasattr(self, "registry_search_var") else ""
        if query:
            rows = [row for row in rows if query in str(row.get("Proposición", "")).casefold() or query in str(row.get("Variable", "")).casefold() or query in str(row.get("Clave normalizada", "")).casefold()]
        self.registry_tree = self._make_table(self.registry_table_host, rows, ["Variable", "Proposición", "Clave normalizada", "Registrada"], height=16)
        self.registry_count_label.configure(text=f"{len(rows):,} registros visibles" + (" (filtro aplicado)" if query else ""))

    def export_registry(self) -> None:
        rows = all_atom_rows()
        if not rows:
            messagebox.showinfo("Registro vacío", "Todavía no existen proposiciones atómicas registradas.")
            return
        default_path = EXPORT_DIR / "registro_global_proposiciones.csv"
        chosen = filedialog.asksaveasfilename(
            title="Exportar registro de proposiciones",
            defaultextension=".csv",
            initialdir=str(EXPORT_DIR if EXPORT_DIR.exists() else BASE_DIR),
            initialfile=default_path.name,
            filetypes=[("Archivo CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if not chosen:
            return
        try:
            path = Path(chosen)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            messagebox.showinfo("Exportación completada", f"Se exportaron {len(rows)} proposiciones a:\n{path}")
        except OSError as exc:
            messagebox.showerror("Error de exportación", str(exc))

    # ------------------------------- Help -------------------------------
    def open_exports_folder(self) -> None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            import os
            import subprocess
            if __import__("sys").platform.startswith("win"):
                os.startfile(str(EXPORT_DIR))  # type: ignore[attr-defined]
            elif __import__("sys").platform == "darwin":
                subprocess.Popen(["open", str(EXPORT_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(EXPORT_DIR)])
        except Exception as exc:
            messagebox.showinfo("Carpeta de exportaciones", f"Los CSV se guardan en:\n{EXPORT_DIR}\n\nNo se pudo abrir automáticamente: {exc}")


def main() -> int:
    app = LogicAnalyzerApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
