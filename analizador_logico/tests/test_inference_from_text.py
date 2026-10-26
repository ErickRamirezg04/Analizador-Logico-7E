import json
import tempfile
import unittest
from pathlib import Path

from inference_engine import forward_chain_from_text
import logic_engine as logic
import storage


class FullTextInferenceTests(unittest.TestCase):
    def test_text_mode_derives_conclusion_from_multiline_case(self):
        text = (
            "Regla 1: Si tengo dolor de garganta y tengo tos seca entonces tengo faringitis\n"
            "Tengo dolor de garganta\n"
            "Tengo tos seca"
        )
        result = forward_chain_from_text(text)
        self.assertEqual(result["rules_count"], 1)
        self.assertIn("tengo faringitis", result["conclusions"])
        self.assertEqual(len(result["derivations"]), 1)
        self.assertIn("tengo dolor de garganta", result["derivations"][0]["Hechos utilizados"])
        self.assertIn("tengo tos seca", result["derivations"][0]["Hechos utilizados"])

    def test_text_mode_supports_multi_step_chaining(self):
        text = "Si p entonces q. Si q entonces r. Si r entonces s. p."
        result = forward_chain_from_text(text)
        self.assertEqual(result["rules_count"], 3)
        self.assertEqual(result["conclusions"], ["q", "r", "s"])
        self.assertEqual(len(result["derivations"]), 3)

    def test_text_mode_does_not_infer_when_fact_is_missing(self):
        text = "Si p y q entonces r. p."
        result = forward_chain_from_text(text)
        self.assertEqual(result["rules_count"], 1)
        self.assertEqual(result["conclusions"], [])
        self.assertEqual(len(result["derivations"]), 0)

    def test_formula_with_conjoined_rule_and_fact_can_chain(self):
        result = forward_chain_from_text("p y (p -> q)")
        self.assertIn("q", result["conclusions"])

    def test_parser_combines_newline_separated_premises(self):
        node, _normalized, warnings = logic.parse_formula("Si p entonces q\np")
        self.assertEqual(node.op, "AND")
        self.assertIn("p", logic.atoms_in(node))
        self.assertTrue(any("enunciados" in warning for warning in warnings))

    def test_text_inference_is_saved_and_recovered_with_analysis(self):
        text = "Si p entonces q. p."
        with tempfile.TemporaryDirectory() as folder:
            old_path = storage.DB_PATH
            try:
                storage.DB_PATH = Path(folder) / "inference.sqlite"
                storage.init_db()
                node, normalized, warnings = logic.parse_formula(text)
                inference = forward_chain_from_text(text)
                analysis_id = storage.save_analysis(
                    "texto_completo", text, normalized, node,
                    objective="satisfacibilidad", warnings=warnings, inference=inference,
                )
                restored = storage.get_analysis(analysis_id)
                self.assertIsNotNone(restored)
                restored_inference = json.loads(restored["inference_json"])
                self.assertIn("q", restored_inference["conclusions"])
            finally:
                storage.DB_PATH = old_path


if __name__ == "__main__":
    unittest.main(verbosity=2)
