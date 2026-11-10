"""Conservative local JS imports. This lexer does not execute project configuration."""
from __future__ import annotations

import re
from pathlib import Path

JS_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
ALIASES = ("@/", "~/", "#")


def tokens(source: str) -> tuple[list[tuple[str, str]], list[str]]:
    result, issues = [], []
    pos = 0
    while pos < len(source):
        char = source[pos]
        if char.isspace():
            pos += 1
            continue
        if source.startswith("//", pos):
            end = source.find("\n", pos + 2)
            pos = len(source) if end < 0 else end + 1
            continue
        if source.startswith("/*", pos):
            end = source.find("*/", pos + 2)
            if end < 0:
                issues.append("Unterminated comment.")
                break
            pos = end + 2
            continue
        if char in {"'", '"', "`"}:
            quote, start = char, pos
            pos += 1
            escaped = False
            while pos < len(source):
                if source[pos] == "\\":
                    escaped = True
                    pos += 2
                elif source[pos] == quote:
                    break
                else:
                    pos += 1
            value = source[start + 1:pos]
            if pos >= len(source):
                issues.append("Unterminated string/template.")
            if quote == "`" and "${" in value:
                issues.append("Template expressions require manual dependency review.")
            result.append(("string", value if not escaped else ""))
            if escaped and result and any(t[1] in {"import", "from", "require"} for t in result[-4:]):
                issues.append("Escaped import specifier is not resolved.")
            pos += 1
            continue
        if char == "/":
            previous = result[-1][1] if result else ""
            if not result or previous in {"=", "(", "[", "{", ":", ",", ";", "!", "?", "return", "=>", ")", "}"}:
                # After ) or } regex versus division can be ambiguous without a parser.
                if previous in {")", "}"}:
                    issues.append("Ambiguous slash syntax requires manual dependency review.")
                pos += 1
                in_class = False
                while pos < len(source):
                    if source[pos] == "\\":
                        pos += 2
                        continue
                    if source[pos] == "[":
                        in_class = True
                    elif source[pos] == "]":
                        in_class = False
                    elif source[pos] == "/" and not in_class:
                        pos += 1
                        while pos < len(source) and source[pos].isalpha():
                            pos += 1
                        break
                    pos += 1
                result.append(("regex", ""))
                continue
        if char.isalnum() or char in {"_", "$"}:
            start = pos
            while pos < len(source) and (source[pos].isalnum() or source[pos] in {"_", "$"}):
                pos += 1
            result.append(("word", source[start:pos]))
            continue
        result.append(("punct", char))
        pos += 1
    return result, issues


def imports(path: Path) -> tuple[list[str], list[str]]:
    try:
        stream, issues = tokens(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return [], [f"Cannot inspect imports in {path.name}: {exc}"]
    found = []
    for index, (kind, value) in enumerate(stream):
        if kind != "word" or value not in {"import", "export", "require"}:
            continue
        if index and stream[index - 1][1] == ".":
            continue
        tail = stream[index + 1:]
        if not tail:
            continue
        if value in {"require", "import"} and tail[0][1] == "(":
            if len(tail) > 1 and tail[1][0] == "string" and tail[1][1]:
                found.append(tail[1][1])
            else:
                issues.append("Nonliteral dynamic import/require.")
            continue
        if value == "require" or tail[0][1] == ".":
            continue
        if value == "import" and tail[0][0] == "string":
            found.append(tail[0][1])
            continue
        if tail[0][1] == "type":
            continue
        if value == "export" and tail[0][1] not in {"{", "*"}:
            continue
        for offset, (next_kind, next_value) in enumerate(tail[:100]):
            if next_value == ";":
                break
            if next_kind == "word" and next_value == "from":
                if offset + 1 < len(tail) and tail[offset + 1][0] == "string":
                    found.append(tail[offset + 1][1])
                break
    if any(item.startswith(ALIASES) for item in found):
        issues.append("Unresolved import alias.")
    return found, [f"{path.name}: {issue}" for issue in sorted(set(issues))]


def graph(repo: Path, files: list[str], budget=None) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    known = set(files)
    edges, issues = {}, {}
    for file in files:
        if budget:
            budget.check()
        if Path(file).suffix not in JS_SUFFIXES:
            continue
        dependencies, problems = imports(repo / file)
        edges[file] = set()
        for item in dependencies:
            if not item.startswith("."):
                continue
            candidate = (repo / Path(file).parent / item).resolve()
            if not candidate.is_relative_to(repo):
                problems.append(f"Import leaves repository: {file} -> {item}")
                continue
            rel = candidate.relative_to(repo).as_posix()
            choices = [rel] + [rel + ext for ext in sorted(JS_SUFFIXES | {".json"})]
            choices += [rel + "/index" + ext for ext in sorted(JS_SUFFIXES)]
            if Path(rel).suffix == ".js":
                choices += [str(Path(rel).with_suffix(ext)).replace("\\", "/") for ext in (".ts", ".tsx")]
            match = next((p for p in choices if p in known), None)
            if match:
                edges[file].add(match)
            else:
                problems.append(f"Unresolved local import: {file} -> {item}")
        if problems:
            issues[file] = problems
    return edges, issues


def closure(start: str, edges: dict[str, set[str]], *, direct: bool = False) -> set[str]:
    seen = {start}
    todo = list(edges.get(start, set()))
    while todo:
        item = todo.pop()
        if item in seen:
            continue
        seen.add(item)
        if not direct:
            todo.extend(edges.get(item, set()) - seen)
    return seen
