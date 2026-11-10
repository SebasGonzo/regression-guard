"""Node, Vitest and Jest adapters; scripts are resolved as data, never shell commands."""
from __future__ import annotations

import fnmatch
from functools import lru_cache
import re
import shutil
from pathlib import Path

from .base import Context, Plan, apply_fallback
from ..dependencies import JS_SUFFIXES, closure, graph
from ..execution import execute_files, json_value
from ..process import invoke
from ..project import local_path
from ..scripts import Script, resolve


def pattern_matches(path: str, pattern: str) -> bool:
    brace = re.search(r"\{([^{}]+)\}", pattern)
    if brace:
        values = brace.group(1).split(",")
        if len(values) > 32:
            return False
        return any(pattern_matches(path, pattern[:brace.start()] + item + pattern[brace.end():])
                   for item in values)
    parts = path.removeprefix("./").split("/")
    pats = pattern.removeprefix("./").split("/")
    @lru_cache(maxsize=None)
    def match(i, j):
        if j == len(pats):
            return i == len(parts)
        if pats[j] == "**":
            return match(i, j + 1) or (i < len(parts) and match(i + 1, j))
        return i < len(parts) and fnmatch.fnmatchcase(parts[i], pats[j]) and match(i + 1, j + 1)
    return match(0, 0)


def under(file: str, directory: str) -> bool:
    return directory == "." or file.startswith(directory.rstrip("/") + "/")


def specifications(context: Context) -> list[dict]:
    if hasattr(context, "_specifications"):
        return context._specifications
    found = []
    for package in context.packages:
        directory, data = package["directory"], package["data"]
        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            scripts = {}
        primary_error = ""
        for name in scripts:
            if name != "test" and not name.startswith("test:"):
                continue
            try:
                spec = resolve(scripts, name)
                key = (directory, spec.runner, tuple(spec.options), tuple(spec.patterns))
                if not any(item["key"] == key for item in found):
                    found.append({"key": key, "directory": directory, "spec": spec,
                                  "manager": package["manager"], "script": name})
            except ValueError as exc:
                if name == "test":
                    primary_error = f"Primary test script was not executed: {exc}"
        local = [f for f in context.files if under(f, directory)
                 and not any(other["directory"] != directory
                             and under(other["directory"] + "/", directory)
                             and under(f, other["directory"])
                             for other in context.packages)]
        config_names = {Path(f).name for f in local}
        text_markers = set()
        for file in local:
            if Path(file).suffix in JS_SUFFIXES and re.search(r"(?:test|spec)[._-]", Path(file).name):
                try:
                    text = (context.repo / file).read_text(encoding="utf-8")
                    if re.search(r"""["']node:test["']""", text):
                        text_markers.add("node:test")
                    if re.search(r"""["']vitest["']""", text):
                        text_markers.add("vitest")
                    if re.search(r"""["']@jest/globals["']""", text):
                        text_markers.add("jest")
                except (OSError, UnicodeError):
                    pass
        declared = set(data.get("dependencies", {})) | set(data.get("devDependencies", {}))
        framework_dependencies = declared & {"vitest", "jest"}
        if len(framework_dependencies) == 1 and any(
                re.search(r"\.(?:test|spec)\.[^.]+$", p) for p in local):
            text_markers.update(framework_dependencies)
        if any(re.match(r"vitest\.config\.", n) for n in config_names):
            text_markers.add("vitest")
        if data.get("jest") or any(re.match(r"jest\.config\.", n) for n in config_names):
            text_markers.add("jest")
        for runner in sorted(text_markers):
            if not any(x["directory"] == directory and x["spec"].runner == runner for x in found):
                found.append({"key": (directory, runner, (), ()), "directory": directory,
                              "spec": Script(runner), "manager": package["manager"], "script": "conventions"})
        if primary_error:
            context.limitations.append(f"{directory}/package.json: {primary_error}")
    # Node projects may deliberately have no package.json.
    if not context.packages:
        for file in context.files:
            if Path(file).suffix in JS_SUFFIXES:
                try:
                    if re.search(r"""["']node:test["']""", (context.repo / file).read_text(encoding="utf-8")):
                        found.append({"key": (".", "node:test", (), ()), "directory": ".",
                                      "spec": Script("node:test"), "manager": "none", "script": "conventions"})
                        break
                except (OSError, UnicodeError):
                    pass
    context._specifications = found
    return found


class JavaScriptAdapter:
    name = ""
    binary = ""

    def detect(self, context: Context) -> list[Plan]:
        result = []
        for item in specifications(context):
            spec = item["spec"]
            if spec.runner != self.name:
                continue
            plan = Plan(self.name, item["directory"])
            plan.metadata = {"options": spec.options, "patterns": spec.patterns,
                             "package_manager": item["manager"], "script": item["script"]}
            node = shutil.which("node")
            plan.available = bool(node)
            plan.metadata["executable"] = node
            try:
                for value in spec.options[1::2]:
                    local_path(context.repo / plan.directory, value)
            except ValueError as exc:
                plan.available = False
                plan.unknown = True
                plan.limitations.append(str(exc))
            if self.binary:
                executable = context.repo / plan.directory / "node_modules" / self.binary
                plan.available &= executable.is_file() and executable.resolve().is_relative_to(context.repo)
                plan.metadata["binary"] = str(executable)
            if not plan.available:
                plan.unknown = True
                plan.limitations.append(f"{self.name} runner unavailable; install project dependencies explicitly.")
            result.append(plan)
        return result

    def prefix(self, plan: Plan) -> list[str]:
        return [plan.metadata["executable"], *(
            [plan.metadata["binary"]] if self.binary else ["--test", "--test-reporter=tap"])]

    def discover(self, context: Context, plan: Plan) -> list[str]:
        result = []
        for file in context.files:
            if not under(file, plan.directory):
                continue
            relative = Path(file).relative_to(plan.directory).as_posix()
            suffix = Path(file).suffix
            patterns = plan.metadata["patterns"]
            if patterns:
                valid = suffix in JS_SUFFIXES and any(pattern_matches(relative, p) for p in patterns)
            elif self.name == "node:test":
                valid = suffix in {".js", ".mjs", ".cjs"} and (
                    "test" in Path(relative).parts[:-1] or
                    bool(re.match(r"(?:test|test-.+|.+[._-]test)\.(?:js|mjs|cjs)$", Path(file).name)))
            else:
                valid = suffix in JS_SUFFIXES and (
                    bool(re.search(r"\.(?:test|spec)\.[^.]+$", file))
                    or "__tests__" in Path(file).parts)
            if valid:
                result.append(file)
        return sorted(result)

    def native_discovery(self, context: Context, plan: Plan) -> list[str]:
        options = plan.metadata["options"]
        if self.name == "vitest":
            command = self.prefix(plan) + ["list", "--filesOnly", "--json", *options,
                                           *plan.metadata["patterns"]]
        else:
            command = self.prefix(plan) + ["--listTests", "--json", "--runInBand", *options,
                                           *plan.metadata["patterns"]]
        process = invoke(command, context.repo / plan.directory, context.budget)
        plan.metadata.setdefault("discovery_commands", []).append(command)
        if process.timed_out:
            plan.metadata["timed_out"] = True
            raise ValueError("Total budget exhausted during runner discovery.")
        if process.error or process.code:
            raise ValueError(process.error or process.output[-1500:] or "Native discovery failed.")
        values = json_value(process.output, list)
        files = []
        for item in values:
            if not isinstance(item, (str, dict)):
                raise ValueError("Unrecognized native test file entry type.")
            value = item if isinstance(item, str) else item.get("file") or item.get("filepath")
            if not isinstance(value, str):
                raise ValueError("Unrecognized native test file entry.")
            path = Path(value)
            if not path.is_absolute():
                path = context.repo / plan.directory / path
            path = path.resolve()
            if not path.is_relative_to(context.repo) or not path.is_file():
                raise ValueError("Native discovery returned a missing or external test path.")
            files.append(path.relative_to(context.repo).as_posix())
        return sorted(set(files))

    def prepare(self, context: Context, plan: Plan) -> None:
        plan.discovered = self.discover(context, plan)
        if self.binary and context.execute and plan.available:
            try:
                plan.discovered = self.native_discovery(context, plan)
            except (ValueError, OSError, TypeError) as exc:
                plan.available = False
                plan.unknown = True
                plan.limitations.append(f"Cannot verify native discovery: {exc}")
        elif self.binary:
            plan.unknown = True
            plan.limitations.append("Static discovery is provisional; check queries the runner's configuration.")
        if not hasattr(context, "_js_graph"):
            context._js_graph = graph(context.repo, context.files, context.budget)
        edges, problems = context._js_graph
        changed = context.changed
        local_changes = {p for p in changed if under(p, plan.directory)
                         and (Path(p).suffix in JS_SUFFIXES | {".json", ".yaml", ".toml"}
                              or Path(p).name == "yarn.lock")}
        configs = {p for p in local_changes if Path(p).name in {
            "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json",
            ".regression-guard.toml"} or re.match(r"(?:vite|vitest|jest)\.config\.", Path(p).name)}
        for test in plan.discovered:
            reachable = closure(test, edges, direct=context.mode == "fast")
            related = changed & reachable
            if context.mode == "full" or related:
                plan.selected.append(test)
                plan.reasons[test] = (["explicit full mode"] if context.mode == "full" else
                                      [f"static import or changed test: {p}" for p in sorted(related)])
                plan.covered.update(related)
            for item in closure(test, edges):
                if item in problems:
                    plan.unknown = True
                    plan.limitations.extend(problems[item])
        if context.mode == "full" and plan.discovered:
            plan.covered.update(local_changes)
        apply_fallback(context, plan, local_changes - plan.covered)
        if configs - plan.covered:
            plan.limitations.append("Runner/build configuration changed; selective coverage is unknown.")
        if not plan.discovered:
            plan.limitations.append(f"No {self.name} test files discovered.")
        if self.name == "node:test" and any(Path(p).suffix in {".ts", ".tsx", ".jsx", ".mts", ".cts"}
                                          for p in plan.discovered):
            plan.unknown = True
            plan.available = False
            plan.limitations.append("Node adapter does not implicitly install TypeScript/JSX loaders.")

    def run(self, context: Context, plan: Plan):
        def command(test):
            path = str(context.repo / test)
            prefix = self.prefix(plan)
            if self.name == "node:test":
                return [*prefix, path]
            options = plan.metadata["options"]
            if self.name == "vitest":
                return [*prefix, "run", *options, path, "--reporter=json",
                        "--maxWorkers=1", "--no-file-parallelism"]
            return [*prefix, *options, "--runInBand", "--watch=false", "--watchAll=false",
                    "--no-cache", "--json", "--runTestsByPath", path]
        return execute_files(context, plan, command)


class NodeAdapter(JavaScriptAdapter):
    name = "node:test"


class VitestAdapter(JavaScriptAdapter):
    name = "vitest"
    binary = "vitest/vitest.mjs"


class JestAdapter(JavaScriptAdapter):
    name = "jest"
    binary = "jest/bin/jest.js"
