import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
