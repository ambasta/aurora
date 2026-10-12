#!/usr/bin/env python3
"""Account for test sources through registered Meson tests and reviewed edges.

Only targets reached from registered commands/dependencies contribute sources.
The small JSON map distinguishes child execution, imported/included helpers,
semantic variants, optional suites and supplemental routes. Comments and filename mentions are
not execution edges. Registration is not a result: final-source full and the
emulator gates remain required.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    "tests/*.py",
    "tests/*.cpp",
    "tests/compiler/*.py",
    "tests/compiler/*.cpp",
    "tests/modules/*.cpp",
    "scripts/*test*.sh",
)
# Only semantic selections, not interpreter flags, output paths or tool identities.
SELECTIONS = {
    "--profile",
    "--smoke",
    "--quick",
    "--cap-only",
    "--self-test",
    "--receiver-bound",
    "--stack-guards",
    "--mutation-controls",
}


def discovered(root):
    return {path.relative_to(root).as_posix() for pattern in PATTERNS for path in root.glob(pattern)}


def exceptions(inventory):
    listed = {}
    for reason, paths in inventory["exceptions"].items():
        if not reason or not paths:
            raise ValueError("every exception group needs a reason and at least one path")
        for path in paths:
            if path in listed:
                raise ValueError("exception listed twice: " + path)
            listed[path] = reason
    return listed


def command_paths(test, build):
    workdir = Path(test.get("workdir") or build)
    return {(workdir / argument).resolve() for argument in test["cmd"] if not argument.startswith("-")}


def named_sources(root, build, tests, targets):
    """Follow registered commands, target IDs and generated-source dependencies."""
    by_id = {target["id"]: target for target in targets}
    by_output = {
        str((build / output).resolve()): target["id"] for target in targets for output in target.get("filename", [])
    }
    paths = {path for test in tests for path in command_paths(test, build)}
    pending = [dependency for test in tests for dependency in test.get("depends", [])]
    pending += [by_output[str(path)] for path in paths if str(path) in by_output]
    reached = set()
    while pending:
        identity = pending.pop()
        if identity in reached:
            continue
        if identity not in by_id:
            raise ValueError("unknown registered target dependency: " + identity)
        reached.add(identity)
        target = by_id[identity]
        pending.extend(target.get("depends", []))
        for group in target.get("target_sources", []):
            for source in group.get("sources", []) + group.get("generated_sources", []):
                path = (build / source).resolve()
                paths.add(path)
                if str(path) in by_output:
                    pending.append(by_output[str(path)])
    return {
        path.relative_to(root).as_posix()
        for path in paths
        if path.is_relative_to(root) and not path.is_relative_to(build) and path.is_file()
    }


def covered(direct, inventory):
    """Follow only reviewed child execution and helper edges, never source text."""
    result, pending = set(direct), list(direct)
    while pending:
        owner = pending.pop()
        for path in inventory["executed"].get(owner, []) + inventory["helpers"].get(owner, []):
            if path not in result:
                result.add(path)
                pending.append(path)
    return result


def selection(arguments):
    selected = {}
    for index, argument in enumerate(arguments):
        flag, separator, value = argument.partition("=")
        if flag not in SELECTIONS:
            continue
        if flag in selected:
            raise ValueError("duplicate semantic selection: " + flag)
        if flag == "--profile":
            value = value if separator else arguments[index + 1] if index + 1 < len(arguments) else ""
            if not value or value.startswith("-"):
                raise ValueError("missing profile selection")
        elif separator:
            raise ValueError("unexpected semantic selection value: " + argument)
        selected[flag] = value if flag == "--profile" else True
    return selected


def check(root, tests=None, targets=None, build=None):
    inventory = json.loads((root / "tests/test-inventory.json").read_text())
    found, listed = discovered(root), exceptions(inventory)
    stale = sorted(set(listed) - found)
    if stale:
        raise ValueError("listed exceptions no longer exist: " + ", ".join(stale))
    for kind in ("executed", "helpers"):
        for owner, children in inventory[kind].items():
            for path in [owner, *children]:
                if not (root / path).is_file():
                    raise ValueError("stale " + kind + " edge: " + path)
    optional = {name: (suite, path) for suite, routes in inventory["optional"].items() for name, path in routes.items()}
    optional_sources = {path for _, path in optional.values()}
    if optional_sources - found:
        raise ValueError("optional sources no longer exist: " + ", ".join(sorted(optional_sources - found)))
    if tests is None:
        return dict(sources=len(found), exceptions=len(listed), optional_sources=len(optional_sources))
    full = [test for test in tests if any(s.rsplit(":", 1)[-1] == "full" for s in test["suite"])]
    absent = sorted(test["name"] for test in tests if test not in full and test["name"] not in optional)
    if absent:
        raise ValueError("registered tests outside the full suite: " + ", ".join(absent))
    by_name = {test["name"]: test for test in tests}
    for suite, routes in inventory["optional"].items():
        enabled = set(routes) & set(by_name)
        if enabled and enabled != set(routes):
            raise ValueError("incomplete optional suite: " + suite)
        for name in enabled:
            test = by_name[name]
            if {s.rsplit(":", 1)[-1] for s in test["suite"]} != {suite}:
                raise ValueError("optional test in wrong suite: " + name)
            if routes[name] not in named_sources(root, build, [test], targets):
                raise ValueError("missing optional execution route: " + name)
    for name, (source, modes) in inventory["variants"].items():
        test = by_name.get(name)
        if test is None or (root / source).resolve() not in command_paths(test, build):
            raise ValueError("missing semantic variant: " + name)
        if selection(test["cmd"]) != selection(modes):
            raise ValueError("semantic variant selection changed: " + name)
    direct = named_sources(root, build, full, targets)
    run = covered(direct, inventory)
    missing = sorted(found - run - set(listed) - optional_sources)
    if missing:
        raise ValueError("test sources with no registered execution/helper route: " + ", ".join(missing))
    redundant = sorted(set(listed) & run)
    if redundant:
        raise ValueError("listed exceptions that Meson now covers; remove them: " + ", ".join(redundant))
    return dict(
        sources=len(found),
        direct=len(found & direct),
        indirect=len(found & (run - direct)),
        exceptions=len(listed),
        tests=len(full),
        optional_sources=len(optional_sources),
        optional_tests=len(tests) - len(full),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meson-info", type=Path, help="intro-tests.json of a configured build")
    args = parser.parse_args()
    if args.meson_info is None:
        print("Inventory exceptions:", json.dumps(check(ROOT), sort_keys=True))
        return
    info = args.meson_info.resolve().parent
    tests = json.loads((info / "intro-tests.json").read_text())
    targets = json.loads((info / "intro-targets.json").read_text())
    print("Test inventory:", json.dumps(check(ROOT, tests, targets, info.parent), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit("FAIL: " + str(error))
