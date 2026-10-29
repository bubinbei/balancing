"""Check repository documents and task bookkeeping; never certify hardware.

Run from any directory: python tools/check_project.py [--root PATH] [--json].
Only the small, flat frontmatter contract used by this project is parsed.
No third-party packages, devices, network access, or repository writes are used.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


EXPECTED_TASKS = {"P00"} | {f"G{i:02}" for i in range(15)}
STATUSES = {"planned", "in_progress", "blocked", "passed"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
             ".mypy_cache", ".ruff_cache", ".trash", "build", "dist", ".west"}
SKIP_PREFIXES = {("data", "runs"), ("evidence", "local"),
                 (".obsidian", "cache"), (".obsidian", "plugins")}
TEXT_SUFFIXES = {"", ".md", ".py", ".json", ".svg", ".xml", ".txt", ".csv",
                 ".toml", ".yaml", ".yml", ".c", ".h", ".cpp", ".hpp",
                 ".rs", ".ini", ".cfg", ".ps1", ".sh", ".cmake", ".dts",
                 ".overlay", ".conf", ".lock"}
LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*(?:<(?P<angle>[^>\n]+)>|"
    r"(?P<plain>(?:\\.|[^\s)])+))"
    r'''(?:\s+(?:"[^"\n]*"|'[^'\n]*'|\([^\)\n]*\)))?\s*\)'''
)


@dataclass
class Result:
    files: int = 0
    links: int = 0
    tasks: int = 0
    errors: list[str] = field(default_factory=list)

    def error(self, path: str, message: str) -> None:
        self.errors.append(f"{path}: {message}")


def metadata(text: str) -> dict[str, str]:
    """Read scalar fields and inline lists, not general YAML."""
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.fullmatch(r"([a-z_]+):\s*(.*?)\s*", line)
        if not match:
            raise ValueError(f"unsupported frontmatter line: {line!r}")
        key, value = match.groups()
        if key in values:
            raise ValueError(f"duplicate frontmatter key: {key}")
        values[key] = value
    return values


def dependencies(value: str) -> list[str]:
    if not re.fullmatch(r"\[\s*(?:[A-Z]\d\d\s*(?:,\s*[A-Z]\d\d\s*)*)?\]", value):
        raise ValueError("depends_on must be an inline list of task IDs")
    items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
    if len(set(items)) != len(items):
        raise ValueError("duplicate dependency")
    return items


def prose(text: str) -> str:
    """Skip fenced/indented code and inline code when checking links."""
    output = []
    fence_char, fence_size = "", 0
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence_char:
            if (marker and marker[1][0] == fence_char
                    and len(marker[1]) >= fence_size and not marker[2].strip()):
                fence_char, fence_size = "", 0
            continue
        if marker:
            fence_char, fence_size = marker[1][0], len(marker[1])
            continue
        if not line.startswith(("    ", "\t")):
            output.append(re.sub(r"(`+).*?\1", "", line))
    return "\n".join(output)


def ignored(parts: tuple[str, ...]) -> bool:
    return any(parts[:len(prefix)] == prefix for prefix in SKIP_PREFIXES)


def source_files(root: Path, result: Result):
    for base, dirs, files in os.walk(root, followlinks=False):
        parent = Path(base)
        kept = []
        for name in sorted(dirs):
            path = parent / name
            parts = path.relative_to(root).parts
            if name in SKIP_DIRS or name.endswith(".egg-info") or ignored(parts):
                continue
            if path.is_symlink():
                result.error(path.relative_to(root).as_posix(), "source symlink is unsupported")
            else:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(files):
            if (name.endswith((".pyc", ".log")) or name in {"Thumbs.db", ".DS_Store"}
                    or (parent.name == ".obsidian" and name.startswith("workspace"))):
                continue
            yield parent / name


def check(root: Path) -> Result:
    root = root.resolve()
    result = Result()
    if not root.is_dir():
        result.error(str(root), "project directory does not exist")
        return result
    documents: dict[str, str] = {}
    for path in source_files(root, result):
        relative = path.relative_to(root).as_posix()
        result.files += 1
        if not relative.isascii():
            result.error(relative, "source path must use ASCII")
        if path.is_symlink():
            result.error(relative, "source symlink is unsupported")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError) as exc:
            result.error(relative, f"cannot read UTF-8: {exc}")
            continue
        if path.suffix.lower() == ".json":
            try:
                json.loads(text)
            except ValueError as exc:
                result.error(relative, f"invalid JSON: {exc}")
        if path.suffix.lower() in {".svg", ".xml"}:
            try:
                ET.fromstring(text)
            except ET.ParseError as exc:
                result.error(relative, f"invalid XML: {exc}")
        if path.suffix.lower() != ".md":
            continue
        documents[relative] = text
        for match in LINK.finditer(prose(text)):
            destination = match["angle"] or match["plain"]
            if destination.startswith("#"):
                continue
            if PureWindowsPath(destination).is_absolute():
                result.error(relative, f"nonportable absolute link: {destination}")
                continue
            if urlsplit(destination).scheme:
                continue
            result.links += 1
            target = (path.parent / unquote(destination.split("#")[0])).resolve()
            if not target.is_relative_to(root):
                result.error(relative, f"link escapes project: {destination}")
            elif not target.exists():
                result.error(relative, f"missing link target: {destination}")

    tasks: dict[str, tuple[str, str, list[str]]] = {}
    for relative, text in documents.items():
        if Path(relative).parent.as_posix() != "tasks":
            continue
        try:
            fields = metadata(text)
            task_id, status = fields["id"], fields["status"]
            deps = dependencies(fields["depends_on"])
            if not re.fullmatch(r"[A-Z]\d\d", task_id):
                raise ValueError("invalid task ID")
            if status not in STATUSES:
                raise ValueError(f"invalid status: {status}")
            if task_id in tasks:
                raise ValueError(f"duplicate task ID: {task_id}")
            tasks[task_id] = (relative, status, deps)
        except (ValueError, KeyError) as exc:
            result.error(relative, f"invalid task: {exc}")
    result.tasks = len(tasks)
    for task_id in sorted(EXPECTED_TASKS - tasks.keys()):
        result.error("tasks", f"missing required task: {task_id}")

    visited: set[str] = set()

    def visit(task_id: str, stack: list[str]) -> None:
        if task_id in stack:
            result.error("tasks", "dependency cycle: " + " -> ".join(stack + [task_id]))
            return
        if task_id in visited:
            return
        relative, status, deps = tasks[task_id]
        for dep in deps:
            if dep not in tasks:
                result.error(relative, f"unknown dependency: {dep}")
            else:
                visit(dep, stack + [task_id])
                if status == "passed" and tasks[dep][1] != "passed":
                    result.error(relative, f"passed task requires passed dependency: {dep}")
        visited.add(task_id)

    for task_id, (relative, status, _) in tasks.items():
        visit(task_id, [])
        if status == "passed":
            report_path = f"evidence/reports/{task_id}.md"
            if report_path not in documents:
                result.error(relative, f"passed task requires report: {report_path}")
            else:
                try:
                    report = metadata(documents[report_path])
                    if report.get("task") != task_id or report.get("result") != "pass":
                        raise ValueError("report must name this task and result: pass")
                except ValueError as exc:
                    result.error(report_path, str(exc))

    state = documents.get("STATE.md", "")
    if len(state) > 2500:
        result.error("STATE.md", f"{len(state)} characters exceeds 2500")
    roadmap = documents.get("docs/ROADMAP.md", "")
    rows = {}
    for line in roadmap.splitlines():
        if not re.match(r"^\| \[[A-Z]\d\d\]", line):
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) != 4:
            result.error("docs/ROADMAP.md", "task table must have four columns")
            continue
        task_id = columns[0][1:4]
        if task_id in rows:
            result.error("docs/ROADMAP.md", f"duplicate task row: {task_id}")
        rows[task_id] = columns
    if rows.keys() != tasks.keys():
        result.error("docs/ROADMAP.md", "task table IDs do not match task cards")
    for task_id, (relative, status, deps) in tasks.items():
        if task_id not in rows:
            continue
        columns = rows[task_id]
        row_deps = [] if columns[2] == "—" else columns[2].split(",")
        if columns[3] != status or [dep.strip() for dep in row_deps] != deps:
            result.error(relative, "status/dependencies differ from ROADMAP")
        if f"../{relative}" not in columns[0]:
            result.error("docs/ROADMAP.md", f"wrong card link for {task_id}")
    try:
        current = metadata(state)["current_task"]
        if current not in tasks:
            result.error("STATE.md", f"unknown current_task: {current}")
        if metadata(roadmap).get("current_task") != current:
            result.error("docs/ROADMAP.md", "current_task differs from STATE")
    except (ValueError, KeyError) as exc:
        result.error("STATE.md / docs/ROADMAP.md", f"invalid context: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = check(args.root)
    if args.as_json:
        print(json.dumps({**vars(result), "ok": not result.errors}, ensure_ascii=False, indent=2))
    else:
        for error in result.errors:
            print(error, file=sys.stderr)
        print(f"{'FAIL' if result.errors else 'OK'}: {result.files} files, "
              f"{result.links} local links, {result.tasks} tasks; "
              f"{len(result.errors)} errors. Documentation checks only.")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
