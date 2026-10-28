"""Pruebas de estructura y exportación del árbol visual del tableau."""
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

import logic_engine as logic
from tableau_visualizer import (
    STYLES,
    build_tableau_layout,
    export_tableau_png,
    export_tableau_svg,
)


class TableauVisualizerTests(unittest.TestCase):
    def _mixed_tableau(self):
        # (p -> q) AND p genera una rama que cierra y otra que permanece abierta.
        formula, _, _ = logic.parse_formula("(p -> q) y p")
        labels = {atom: f"x[{index + 1}]" for index, atom in enumerate(logic.atoms_in(formula))}
        result = logic.tableau(formula, labels)
        layout = build_tableau_layout(
            result["rows"],
            title="Árbol de prueba",
            subtitle=f"{result['classification']} · abiertas={result['open_branches']} · cerradas={result['closed_branches']}",
        )
        return result, layout

    def test_layout_covers_all_tableau_nodes_and_connections(self):
        result, layout = self._mixed_tableau()
        self.assertEqual(len(layout["nodes"]), len(result["rows"]))
        self.assertEqual(len(layout["edges"]), len(layout["nodes"]) - 1)
        self.assertGreater(layout["width"], 700)
        self.assertGreater(layout["height"], 500)
        styles = {node["style"] for node in layout["nodes"].values()}
        self.assertIn("closed", styles)
        self.assertIn("open", styles)
        self.assertEqual(STYLES["closed"]["outline"], "#FB7185")
        self.assertEqual(STYLES["open"]["outline"], "#34D399")

    def test_svg_export_is_valid_and_contains_branch_labels(self):
        _, layout = self._mixed_tableau()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = export_tableau_svg(Path(temp_dir) / "tree.svg", layout)
            root = ET.parse(output).getroot()
            self.assertTrue(root.tag.endswith("svg"))
            svg_text = output.read_text(encoding="utf-8")
            self.assertIn("Árbol de prueba", svg_text)
            self.assertIn("Rama abierta", svg_text)
            self.assertIn("Rama cerrada", svg_text)
            self.assertIn("Bifurcación", svg_text)

    def test_png_export_is_valid_image(self):
        _, layout = self._mixed_tableau()
        with tempfile.TemporaryDirectory() as temp_dir:
            output, scale = export_tableau_png(Path(temp_dir) / "tree.png", layout)
            with Image.open(output) as image:
                self.assertEqual(image.format, "PNG")
                self.assertGreater(image.width, 300)
                self.assertGreater(image.height, 300)
            self.assertGreater(scale, 0)
            self.assertLessEqual(scale, 1)

    def test_empty_tableau_has_a_renderable_layout(self):
        layout = build_tableau_layout([])
        self.assertTrue(layout["empty"])
        self.assertEqual(layout["nodes"], {})
        self.assertGreater(layout["width"], 0)
        with tempfile.TemporaryDirectory() as temp_dir:
            output = export_tableau_svg(Path(temp_dir) / "empty.svg", layout)
            self.assertTrue(output.exists())
            self.assertIn("El tableau no produjo nodos", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
