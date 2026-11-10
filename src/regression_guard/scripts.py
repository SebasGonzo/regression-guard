"""Resolve package-manager aliases as data; never execute npm, pnpm, yarn or a shell."""
from __future__ import annotations

import re
import shlex
from pathlib import Path
from dataclasses import dataclass, field

from .project import local_path


@dataclass
class Script:
    runner: str
    options: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)


def resolve(scripts: dict, name: str = "test", stack: tuple[str, ...] = ()) -> Script:
    if name in stack or len(stack) >= 12:
        raise ValueError("Cyclic or overly deep package script alias.")
    text = scripts.get(name)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"No usable script named {name!r}.")
    if re.search(r"[;&|<>$\x60\r\n\x00]", text):
        raise ValueError("Shell operators, substitutions and environment commands are not allowlisted.")
    try:
        args = shlex.split(text, posix=True)
    except ValueError as exc:
        raise ValueError("Cannot tokenize package script.") from exc
    if not args:
        raise ValueError("Empty package script.")
    if args[0] in {"npm", "pnpm", "yarn"}:
        tail = args[1:]
        if tail and tail[0] == "run":
            tail = tail[1:]
        if not tail or tail[0].startswith("-"):
            raise ValueError("Only local package-script aliases are allowlisted.")
        target, extra = tail[0], tail[1:]
        if extra and extra[0] == "--":
            extra = extra[1:]
        spec = resolve(scripts, target, stack + (name,))
        return validate([spec.runner, *spec.options, *spec.patterns, *extra], normalized=True)
    return validate(args)


def validate(args: list[str], *, normalized: bool = False) -> Script:
    name = args[0]
    tail = args[1:]
    if name == "node":
        if not tail or tail[0] != "--test":
            raise ValueError("Only Node's built-in --test runner is allowlisted.")
        name, tail = "node:test", tail[1:]
    elif name == "node:test" and normalized:
        pass
    elif name == "vitest":
        if tail and tail[0] == "run":
            tail = tail[1:]
    elif name != "jest":
        raise ValueError(f"Runner command is not allowlisted: {name}")
    options, patterns = [], []
    index = 0
    while index < len(tail):
        arg = tail[index]
        if arg == "--":
            index += 1
            continue
        if arg in {"--runInBand", "--run", "--ci"} and name in {"jest", "vitest"}:
            index += 1
            continue
        if arg in {"--config", "-c"} and name in {"jest", "vitest"}:
            if index + 1 >= len(tail):
                raise ValueError("Missing --config path.")
            value = tail[index + 1]
            local_path(Path("."), value)
            options.extend(["--config", value])
            index += 2
            continue
        if arg.startswith("--config=") and name in {"jest", "vitest"}:
            value = arg.split("=", 1)[1]
            local_path(Path("."), value)
            options.extend(["--config", value])
        elif arg.startswith("-"):
            raise ValueError(f"Runner option is not allowlisted: {arg}")
        else:
            if not re.fullmatch(r"[\w ./?*\[\]{}()+@,\-]+", arg):
                raise ValueError(f"Unsupported test path/pattern: {arg!r}")
            local_path(Path("."), arg, pattern=True)
            expansions = 1
            for brace in re.findall(r"\{([^{}]+)\}", arg):
                expansions *= len(brace.split(","))
            if len(arg) > 512 or expansions > 128:
                raise ValueError("Test pattern exceeds the bounded expansion policy.")
            patterns.append(arg)
        index += 1
    return Script(name, options, patterns)
