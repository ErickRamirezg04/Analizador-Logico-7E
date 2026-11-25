import json
import tempfile
import unittest
from pathlib import Path

import logic_engine as logic
import storage


class LogicEngineTests(unittest.TestCase):
    def test_implicit_conditional_example(self):
        node, normalized, warnings = logic.parse_formula("Si nos dejan nos vamos a querer toda la vida")
        self.assertIsInstance(node, logic.Binary)
        self.assertEqual(node.op, "IMP")
        self.assertEqual(logic.atoms_in(node), ["nos dejan", "nos vamos a querer toda la vida"])
        self.assertTrue(warnings)
        self.assertIn("->", normalized)

    def test_explicit_conditional_has_no_heuristic_warning(self):
        node, _, warnings = logic.parse_formula("Si nos dejan, entonces nos vamos a querer toda la vida")
        self.assertEqual(node.op, "IMP")
        self.assertEqual(warnings, [])

    def test_biconditional_and_precedence(self):
        node, _, _ = logic.parse_formula("p y q si y solo si r")
        self.assertIsInstance(node, logic.Binary)
        self.assertEqual(node.op, "IFF")
        self.assertEqual(node.left.op, "AND")
        accented, _, _ = logic.parse_formula("p si y sólo si q")
        self.assertEqual(accented.op, "IFF")
        only_if, _, _ = logic.parse_formula("p sólo si q")
        self.assertEqual(only_if.op, "IMP")

    def test_truth_tables_for_tautology_and_contradiction(self):
        tautology, _, _ = logic.parse_formula("p o no p")
        contradiction, _, _ = logic.parse_formula("p y no p")
        self.assertTrue(all(row["Fórmula"] == "V" for row in logic.truth_table(tautology, {"p": "x[1]"})))
        self.assertTrue(all(row["Fórmula"] == "F" for row in logic.truth_table(contradiction, {"p": "x[1]"})))

    def test_tableau_checks_validity(self):
        node, _, _ = logic.parse_formula("p -> p")
        result = logic.tableau(node, {"p": "x[1]"}, root_truth=False)
        self.assertEqual(result["classification"], "válida")
        self.assertEqual(result["open_branches"], 0)
        self.assertGreater(result["closed_branches"], 0)

    def test_conditional_with_siempres_y_cuando_constraint(self):
        text = (
            "Si el sensor infrarrojo detecta un obstáculo y el servomotor está activo, "
            "entonces el robot móvil girará a la izquierda o se detendrá por completo, "
            "siempre y cuando no exista una falla crítica de alimentación"
        )
        node, rewritten, warnings = logic.parse_formula(text)
        self.assertIsInstance(node, logic.Binary)
        self.assertEqual(node.op, "IMP")
        self.assertEqual(node.left.op, "AND")
        self.assertEqual(node.left.left.op, "AND")
        self.assertEqual(node.left.right.__class__.__name__, "Not")
        self.assertEqual(node.right.op, "OR")
        self.assertEqual(
            logic.atoms_in(node),
            [
                "el sensor infrarrojo detecta un obstáculo",
                "el servomotor está activo",
                "exista una falla crítica de alimentación",
                "el robot móvil girará a la izquierda",
                "se detendrá por completo",
            ],
        )
        self.assertIn("siempre y cuando", " ".join(warnings))
        self.assertIn("->", rewritten)
        rows = logic.truth_table(node, {atom: f"x[{i+1}]" for i, atom in enumerate(logic.atoms_in(node))})
        self.assertEqual(len(rows), 32)
        self.assertEqual(sum(row["Fórmula"] == "F" for row in rows), 1)

    def test_intra_clause_no_after_subject_is_parsed_as_logical_negation(self):
        text = (
            "El sistema operativo asigna memoria RAM de alta velocidad y el proceso principal "
            "se ejecuta de forma fluida, pero al mismo tiempo el proceso principal "
            "no se ejecuta de forma fluida"
        )
        node, _, warnings = logic.parse_formula(text)
        self.assertEqual(logic.atoms_in(node), [
            "el sistema operativo asigna memoria ram de alta velocidad",
            "el proceso principal se ejecuta de forma fluida",
        ])
        self.assertEqual(node.op, "AND")
        self.assertEqual(node.right.__class__.__name__, "Not")
        self.assertEqual(node.right.child.text, "el proceso principal se ejecuta de forma fluida")
        self.assertTrue(any("pero al mismo tiempo" in warning for warning in warnings))
        result = logic.tableau(node, {atom: f"x[{i+1}]" for i, atom in enumerate(logic.atoms_in(node))})
        self.assertEqual(result["classification"], "insatisfacible")
        self.assertEqual(result["open_branches"], 0)
        self.assertGreater(result["closed_branches"], 0)

    def test_multi_sentence_text_is_explicitly_conjoined(self):
        node, _, warnings = logic.parse_formula("llueve. llevo paraguas.")
        self.assertEqual(node.op, "AND")
        self.assertEqual(logic.atoms_in(node), ["llueve", "llevo paraguas"])
        self.assertTrue(any("oraciones" in warning for warning in warnings))

    def test_database_deduplicates_atoms_and_manual_formulas(self):
        with tempfile.TemporaryDirectory() as folder:
            old_path = storage.DB_PATH
            try:
                storage.DB_PATH = Path(folder) / "test.sqlite"
                storage.init_db()
                first, first_normalized, _ = logic.parse_formula("Es de día")
                second, second_normalized, _ = logic.parse_formula("ES DE DÍA.")
                first_labels = storage.ensure_atoms(first)
                second_labels = storage.ensure_atoms(second)
                self.assertEqual(first_labels, second_labels)
                self.assertEqual(storage.counts()["propositions"], 1)
                self.assertTrue(storage.add_manual_statement("Es de día", first_normalized, first)[0])
                self.assertFalse(storage.add_manual_statement("ES DE DÍA.", second_normalized, second)[0])
                self.assertEqual(len(storage.list_manual_statements()), 1)
            finally:
                storage.DB_PATH = old_path


if __name__ == "__main__":
    unittest.main(verbosity=2)
