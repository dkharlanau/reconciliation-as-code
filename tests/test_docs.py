import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHOR_FOOTER = """## About the author

Created and maintained by **Dzmitryi Kharlanau**, an SAP consultant and system analyst working across enterprise architecture, data, integration, operations, and practical AI.

- [Website and knowledge base](https://dkharlanau.github.io/)
- [LinkedIn](https://www.linkedin.com/in/dkharlanau/)"""


class DocumentationContractTests(unittest.TestCase):
    def test_local_markdown_links_resolve(self) -> None:
        missing: list[str] = []
        for markdown in ROOT.rglob("*.md"):
            if any(part.startswith(".") for part in markdown.relative_to(ROOT).parts):
                continue
            text = markdown.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_text = target.split("#", 1)[0]
                if not path_text:
                    continue
                resolved = (markdown.parent / path_text).resolve()
                if not resolved.exists():
                    missing.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual([], missing)

    def test_agent_manifest_uses_real_cli_entrypoints(self) -> None:
        manifest = json.loads((ROOT / "docs" / "agent-manifest.json").read_text(encoding="utf-8"))
        commands = [item["command"] for item in manifest["entrypoints"]]
        self.assertTrue(any(command.startswith("rac inspect ") for command in commands))
        self.assertTrue(any(command.startswith("rac validate ") for command in commands))
        self.assertTrue(any(command.startswith("rac run ") for command in commands))
        self.assertTrue(any(command.startswith("rac pipeline ") for command in commands))
        self.assertTrue(any(command.startswith("rac diff ") for command in commands))
        self.assertFalse(any("rulepack" in command for command in commands))

    def test_public_agent_paths_exist(self) -> None:
        for path in ("README.md", "docs/index.md", "docs/agent-manifest.json"):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_readme_ends_with_exact_author_footer_and_suite_guide(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").rstrip()
        self.assertTrue(readme.endswith(AUTHOR_FOOTER))
        self.assertEqual(1, readme.count("## About the author"))
        self.assertIn("docs/as-code-suite.md", readme)
        for repository in ("decision-tables-as-code", "mapping-as-code", "interface-as-code", "process-as-code"):
            self.assertIn(f"https://github.com/dkharlanau/{repository}", readme)

    def test_agent_manifest_navigates_the_core_suite(self) -> None:
        manifest = json.loads((ROOT / "docs" / "agent-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"decision-tables-as-code", "mapping-as-code", "interface-as-code", "process-as-code"},
            {item["product"] for item in manifest["related"]},
        )


if __name__ == "__main__":
    unittest.main()
