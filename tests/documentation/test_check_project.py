"""Exercise document acceptance failures on disposable project fixtures."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_project import check  # noqa: E402


class ProjectCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cards = {}
        self.deps = {"P00": []} | {f"G{i:02}": ["P00"] for i in range(15)}
        self.statuses = {task: "planned" for task in self.deps}
        for task in self.deps:
            self.cards[task] = f"tasks/{task}-test.md"
            self.card(task)
        self.write("STATE.md", "---\ncurrent_task: P00\n---\n# State\n")
        self.write("README.md", "[Roadmap](docs/ROADMAP.md)\n![Diagram](assets/test.svg)\n")
        self.write("assets/test.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.write(".obsidian/app.json", "{}")
        self.roadmap()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def card(self, task):
        self.write(self.cards[task], f"---\nid: {task}\nstatus: {self.statuses[task]}\n"
                   f"depends_on: [{', '.join(self.deps[task])}]\n---\n# Task\n")

    def roadmap(self):
        rows = ["---", "current_task: P00", "---", "# Roadmap"]
        for task in self.deps:
            deps = ", ".join(self.deps[task]) or "—"
            rows.append(f"| [{task}](../{self.cards[task]}) | Test | {deps} | {self.statuses[task]} |")
        self.write("docs/ROADMAP.md", "\n".join(rows))

    def assertRejected(self, fragment):
        self.assertTrue(any(fragment in error for error in check(self.root).errors),
                        msg=f"Expected {fragment!r} in {check(self.root).errors}")

    def test_valid_project(self):
        result = check(self.root)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.tasks, 16)

    def test_missing_link(self):
        self.write("README.md", "[missing](absent.md)")
        self.assertRejected("missing link target")

    def test_code_examples_are_not_links(self):
        self.write("README.md", "```md\n[x](absent.md)\n````\n"
                   "~~~\n[y](absent.md)\n~~~\n`[z](absent.md)`\n    [q](absent.md)\n")
        self.assertEqual(check(self.root).errors, [])

    def test_link_escapes_project(self):
        self.write("README.md", "[outside](../outside.md)")
        self.assertRejected("link escapes project")

    def test_unknown_dependency(self):
        self.deps["G00"] = ["X99"]
        self.card("G00")
        self.roadmap()
        self.assertRejected("unknown dependency: X99")

    def test_dependency_cycle(self):
        self.deps["P00"] = ["G00"]
        self.card("P00")
        self.roadmap()
        self.assertRejected("dependency cycle")

    def test_passed_requires_report(self):
        self.statuses["P00"] = "passed"
        self.card("P00")
        self.roadmap()
        self.assertRejected("passed task requires report")

    def test_passed_requires_accepted_predecessor(self):
        self.statuses["G00"] = "passed"
        self.card("G00")
        self.roadmap()
        self.write("evidence/reports/G00.md", "---\ntask: G00\nresult: pass\n---\n")
        self.assertRejected("passed task requires passed dependency: P00")

    def test_empty_template_is_not_pass_report(self):
        self.statuses["P00"] = "passed"
        self.card("P00")
        self.roadmap()
        self.write("evidence/reports/P00.md", "---\ntask: P00\nresult: not_run\n---\n")
        self.assertRejected("report must name this task and result: pass")

    def test_accepted_task(self):
        self.statuses["P00"] = "passed"
        self.card("P00")
        self.roadmap()
        self.write("evidence/reports/P00.md", "---\ntask: P00\nresult: pass\n---\n")
        self.assertEqual(check(self.root).errors, [])

    def test_duplicate_task(self):
        self.write("tasks/duplicate.md", (self.root / self.cards["P00"]).read_text(encoding="utf-8"))
        self.assertRejected("duplicate task ID")

    def test_roadmap_mismatch(self):
        self.statuses["P00"] = "in_progress"
        self.roadmap()
        self.assertRejected("status/dependencies differ from ROADMAP")

    def test_non_ascii_source_path(self):
        self.write("docs/пример.md", "text")
        self.assertRejected("source path must use ASCII")

    def test_invalid_utf8(self):
        (self.root / "README.md").write_bytes(b"\xff")
        self.assertRejected("cannot read UTF-8")

    def test_invalid_json_and_xml(self):
        self.write(".obsidian/app.json", "{")
        self.write("assets/test.svg", "<svg>")
        self.assertRejected("invalid JSON")
        self.assertRejected("invalid XML")

    def test_state_limit(self):
        self.write("STATE.md", "---\ncurrent_task: P00\n---\n" + "x" * 2500)
        self.assertRejected("exceeds 2500")

    def test_private_data_and_caches_are_excluded(self):
        for relative in ("data/runs/capture.md", "evidence/local/notes.md",
                         ".git/config", ".venv/example.md", "__pycache__/cache.md",
                         ".obsidian/workspace.json"):
            self.write(relative, "[broken](absent.md)")
        self.assertEqual(check(self.root).errors, [])


if __name__ == "__main__":
    unittest.main()
