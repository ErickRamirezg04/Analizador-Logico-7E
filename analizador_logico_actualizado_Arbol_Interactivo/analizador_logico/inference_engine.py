"""Encadenamiento hacia adelante para bases de conocimiento proposicionales.

El motor es explicable: solo deriva literales cuando una regla A -> B tiene un
antecedente demostrado por hechos disponibles. Para reglas Horn frecuentes,
como (p AND q) -> r, aplica modus ponens generalizado.
"""
from __future__ import annotations

from typing import Any, Iterable

from logic_engine import (Atom, Binary, Formula, Not, canonical_atom, formula_key, format_formula, parse_formula, split_text_statements, strip_entry_label)


def _flatten_and(node: Formula) -> list[Formula]:
    if isinstance(node, Binary) and node.op == "AND":
        return _flatten_and(node.left) + _flatten_and(node.right)
    return [node]


def _literal(node: Formula) -> tuple[str, bool] | None:
    if isinstance(node, Atom):
        return canonical_atom(node.text), True
    if isinstance(node, Not) and isinstance(node.child, Atom):
        return canonical_atom(node.child.text), False
    return None


def forward_chain_from_text(text: str, *, max_steps: int = 10000) -> dict[str, Any]:
    """Analiza reglas y hechos escritos en un único cuadro de texto.

    Separa enunciados por líneas, puntos de cierre o punto y coma, formaliza cada
    uno y ejecuta el mismo motor de encadenamiento que utiliza el modo manual.
    """
    premises: list[dict[str, Any]] = []
    parse_warnings: list[str] = []
    for index, statement in enumerate(split_text_statements(text), start=1):
        content = strip_entry_label(statement)
        if not content:
            continue
        node, _rewritten, warnings = parse_formula(content)
        premises.append({
            "id": index,
            "original_text": statement,
            "node": node,
        })
        parse_warnings.extend(warnings)

    if not premises:
        return {
            "status": "No se detectaron enunciados para el encadenamiento.",
            "initial_facts": [], "facts": [], "derivations": [], "conclusions": [],
            "conflicts": [], "rules_count": 0, "warnings": [],
            "method": "Encadenamiento hacia adelante.", "input_statements": [],
        }

    result = forward_chain(premises, max_steps=max_steps)
    result["warnings"] = list(dict.fromkeys(parse_warnings + result.get("warnings", [])))
    result["input_statements"] = [item["original_text"] for item in premises]
    result["input_statement_count"] = len(premises)
    if len(premises) > 1:
        result["status"] = f"Se analizaron {len(premises)} enunciados. {result['status']}"
    return result


def forward_chain(
    premises: Iterable[dict[str, Any]],
    *,
    max_steps: int = 10000,
) -> dict[str, Any]:
    """Deriva conclusiones a partir de premisas/reglas introducidas manualmente.

    Cada premise debe incluir ``id``, ``original_text`` y ``node`` (AST Formula).
    Reglas admitidas: condicionales cuyo consecuente sea un átomo, su negación o
    una conjunción de dichos literales. Los antecedentes pueden ser conjunciones,
    disyunciones y literales; la conjunción exige que todos los elementos estén
    probados. No realiza diagnóstico clínico.
    """
    items = list(premises)
    positive: set[str] = set()
    negative: set[str] = set()
    literal_sources: dict[tuple[str, bool], str] = {}
    known_formula_keys: set[str] = set()
    known_formula_sources: dict[str, str] = {}
    initial_facts: list[dict[str, Any]] = []
    derivations: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Se consideran hechos los átomos/negaciones y las partes de conjunciones
    # afirmadas. Si una entrada contiene varias premisas unidas por AND, también
    # se extraen de ella las reglas condicionales independientes.
    rules: list[dict[str, Any]] = []
    for position, item in enumerate(items, start=1):
        node: Formula = item["node"]
        source = f"Premisa #{item.get('id', position)}: {item.get('original_text', format_formula(node))}"
        known_formula_keys.add(formula_key(node))
        known_formula_sources.setdefault(formula_key(node), source)
        for asserted in _flatten_and(node):
            if isinstance(asserted, Binary) and asserted.op == "IMP":
                rules.append({
                    "id": item.get("id", position),
                    "label": f"R{len(rules) + 1}",
                    "source": source,
                    "node": asserted,
                    "antecedent": asserted.left,
                    "consequent": asserted.right,
                })
                continue
            asserted_key = formula_key(asserted)
            known_formula_keys.add(asserted_key)
            known_formula_sources.setdefault(asserted_key, source)
            for fact_node in _flatten_and(asserted):
                lit = _literal(fact_node)
                if lit is None:
                    fact_key = formula_key(fact_node)
                    known_formula_keys.add(fact_key)
                    known_formula_sources.setdefault(fact_key, source)
                    continue
                atom, truth = lit
                target = positive if truth else negative
                key = (atom, truth)
                if atom not in target:
                    target.add(atom)
                    literal_sources[key] = source
                    initial_facts.append({
                        "Proposición": ("" if truth else "¬") + atom,
                        "Tipo": "Hecho inicial",
                        "Origen": source,
                        "Justificación": "Premisa proporcionada por el usuario",
                    })

    def prove(node: Formula) -> tuple[bool, list[tuple[str, bool]], str]:
        lit = _literal(node)
        if lit is not None:
            atom, truth = lit
            available = positive if truth else negative
            if atom in available:
                return True, [(atom, truth)], literal_sources.get((atom, truth), "hecho conocido")
            return False, [], ""
        key = formula_key(node)
        if key in known_formula_keys:
            return True, [], known_formula_sources.get(key, "premisa compuesta registrada")
        if isinstance(node, Binary) and node.op == "AND":
            left_ok, left_evidence, left_source = prove(node.left)
            right_ok, right_evidence, right_source = prove(node.right)
            if left_ok and right_ok:
                evidence = left_evidence + right_evidence
                sources = "; ".join(dict.fromkeys(filter(None, [left_source, right_source])))
                return True, evidence, sources
            return False, [], ""
        if isinstance(node, Binary) and node.op == "OR":
            left = prove(node.left)
            if left[0]:
                return left
            return prove(node.right)
        return False, [], ""

    def consequent_literals(node: Formula) -> list[tuple[str, bool]] | None:
        if isinstance(node, Binary) and node.op == "AND":
            left = consequent_literals(node.left)
            right = consequent_literals(node.right)
            if left is None or right is None:
                return None
            return left + right
        lit = _literal(node)
        return [lit] if lit is not None else None

    changed = True
    step = 0
    while changed:
        changed = False
        for rule in rules:
            ok, evidence, source_text = prove(rule["antecedent"])
            if not ok:
                continue
            conclusions = consequent_literals(rule["consequent"])
            if conclusions is None:
                warnings.append(
                    f"{rule['label']} tiene un consecuente complejo que no es una conjunción de literales; "
                    "se conservó como regla lógica, pero el encadenamiento no lo convirtió en un hecho atómico."
                )
                continue
            for atom, truth in conclusions:
                target = positive if truth else negative
                if atom in target:
                    continue
                step += 1
                if step > max_steps:
                    warnings.append(f"El encadenamiento alcanzó el límite preventivo de {max_steps} inferencias.")
                    changed = False
                    break
                target.add(atom)
                literal_sources[(atom, truth)] = f"Inferencia {step} por {rule['label']}"
                inferred = ("" if truth else "¬") + atom
                used = ", ".join(("" if sign else "¬") + name for name, sign in evidence) or source_text or "antecedente registrado"
                derivations.append({
                    "Paso": step,
                    "Regla": rule["label"],
                    "Regla ingresada": rule["source"],
                    "Antecedente demostrado": format_formula(rule["antecedent"]),
                    "Hechos utilizados": used,
                    "Conclusión": inferred,
                })
                initial_facts.append({
                    "Proposición": inferred,
                    "Tipo": "Conclusión derivada",
                    "Origen": rule["label"],
                    "Justificación": f"El antecedente se satisfizo con: {used}",
                })
                changed = True

    conflicts = sorted(positive.intersection(negative))
    facts = [
        {"Proposición": atom, "Valor": "V", "Origen": literal_sources.get((atom, True), "hecho conocido")}
        for atom in sorted(positive)
    ] + [
        {"Proposición": f"¬{atom}", "Valor": "V (negación)" , "Origen": literal_sources.get((atom, False), "hecho conocido")}
        for atom in sorted(negative)
    ]
    conclusions = sorted({row["Conclusión"] for row in derivations})

    if conflicts:
        status = "Inconsistente: se conocen un literal y su negación. Las conclusiones deben revisarse."
    elif conclusions:
        status = f"Encadenamiento completado: se derivaron {len(conclusions)} conclusión(es) nueva(s)."
    elif rules:
        status = "No se derivaron conclusiones nuevas con los hechos actuales; faltan antecedentes o reglas aplicables."
    else:
        status = "No hay reglas condicionales en el conjunto manual; solo se registraron los hechos introducidos."

    return {
        "status": status,
        "initial_facts": initial_facts,
        "facts": facts,
        "derivations": derivations,
        "conclusions": conclusions,
        "conflicts": conflicts,
        "rules_count": len(rules),
        "warnings": list(dict.fromkeys(warnings)),
        "method": "Encadenamiento hacia adelante (modus ponens generalizado para antecedentes demostrables).",
    }
