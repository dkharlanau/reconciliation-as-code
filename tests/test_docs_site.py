import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_docs_site.py"
SPEC = importlib.util.spec_from_file_location("build_docs_site", SCRIPT)
assert SPEC and SPEC.loader
BUILD_DOCS_SITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_DOCS_SITE)


class DocumentationSiteTests(unittest.TestCase):
    def test_site_builds_all_declared_use_cases(self) -> None:
        data = BUILD_DOCS_SITE.load_data()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            BUILD_DOCS_SITE.build(output)
            manifest = json.loads((output / "site-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["use_cases"]), manifest["use_cases"])
            self.assertEqual(len(data["use_cases"]) + 3, manifest["pages"])
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "agent-manifest.json").is_file())
            self.assertTrue((output / "use-cases" / "index.html").is_file())
            self.assertTrue((output / "faq" / "index.html").is_file())
            for item in data["use_cases"]:
                self.assertTrue((output / "use-cases" / item["slug"] / "index.html").is_file())

    def test_builder_refuses_unmarked_nonempty_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            (output / "user-file.txt").write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmarked"):
                BUILD_DOCS_SITE.build(output)
            self.assertEqual("preserve", (output / "user-file.txt").read_text(encoding="utf-8"))

    def test_builder_refuses_repository_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe"):
            BUILD_DOCS_SITE.prepare_output(ROOT)


if __name__ == "__main__":
    unittest.main()
