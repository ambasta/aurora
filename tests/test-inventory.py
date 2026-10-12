#!/usr/bin/env python3
"""Every test source must run under Meson, or be listed in test-inventory.json.

A source counts as run when a registered test or build target names it, or
when a source that already counts names it (a fixture compiled by its runner,
an imported helper, a wrapped script). The listed exceptions are the routes
outside the Meson `full` graph, each with a reason. Registration is not a
result: final-source `full` and the emulator gates remain required.
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = (
    "tests/*.py",
    "tests/*.cpp",
    "tests/compiler/*.py",
    "tests/compiler/*.cpp",
    "tests/modules/*.cpp",
    "scripts/*test*.sh",
)


# Helpers that may name test sources; they need not be covered themselves.
HELPERS = ("scripts/*.py", "scripts/*.sh")


def discovered(root, patterns=PATTERNS):
    return {path.relative_to(root).as_posix() for pattern in patterns for path in root.glob(pattern)}


def exceptions(root):
    listed = {}
    for reason, paths in json.loads((root / "tests/test-inventory.json").read_text()).items():
        if not reason or not paths:
            raise ValueError("every exception group needs a reason and at least one path")
        for path in paths:
            if path in listed:
                raise ValueError("exception listed twice: " + path)
            listed[path] = reason
    return listed


def named_sources(root, build, tests, targets):
    """Source files that a registered test command or a build target names."""
    candidates = []
    for test in tests:
        workdir = Path(test.get("workdir") or build)
        candidates += [workdir / argument for argument in test["cmd"] if "/" in argument]
    for target in targets:
        for group in target.get("target_sources", []):
            candidates += [Path(source) for source in group.get("sources", []) + group.get("generated_sources", [])]
    names = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path.is_relative_to(root) and not path.is_relative_to(build):
            names.add(path.relative_to(root).as_posix())
    return names


def covered(root, pool, direct):
    """Close over pool files that a covered file names by file name or module name."""
    result, texts = set(direct), {}

    def text(path):
        if path not in texts:
            try:
                texts[path] = (root / path).read_text()
            except (OSError, UnicodeDecodeError):
                texts[path] = ""
        return texts[path]

    pending = True
    while pending:
        pending = False
        for path in sorted(pool - result):
            names = {Path(path).name, Path(path).stem} if path.endswith(".py") else {Path(path).name}
            if any(name in text(other) for other in result for name in names):
                result.add(path)
                pending = True
    return result


def check(root, tests=None, targets=None, build=None):
    found, listed = discovered(root), exceptions(root)
    stale = sorted(set(listed) - found)
    if stale:
        raise ValueError("listed exceptions no longer exist: " + ", ".join(stale))
    if tests is None:
        return dict(sources=len(found), exceptions=len(listed))
    absent = sorted(test["name"] for test in tests if not any(s.rsplit(":", 1)[-1] == "full" for s in test["suite"]))
    if absent:
        raise ValueError("registered tests outside the full suite: " + ", ".join(absent))
    run = covered(root, found | discovered(root, HELPERS), named_sources(root, build, tests, targets))
    missing = sorted(found - run - set(listed))
    if missing:
        raise ValueError("test sources no Meson test runs; register them or list a reason: " + ", ".join(missing))
    redundant = sorted(set(listed) & run)
    if redundant:
        raise ValueError("listed exceptions that Meson now runs; remove them: " + ", ".join(redundant))
    return dict(sources=len(found), run=len(found & run), exceptions=len(listed), tests=len(tests))


def self_test():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        build = root / "build"
        (root / "tests").mkdir()
        build.mkdir()
        (root / "tests/runner.py").write_text("subprocess.run(['g++', 'fixture.cpp'])\n")
        (root / "tests/fixture.cpp").write_text("int main() {}\n")
        (root / "tests/gate.py").write_text("separate\n")
        (root / "tests/test-inventory.json").write_text(json.dumps({"separate gate": ["tests/gate.py"]}))
        runner = dict(name="runner", cmd=["python3", str(root / "tests/runner.py")], suite=["p:full"])
        result = check(root, [runner], [], build)
        if result["run"] != 2 or result["exceptions"] != 1:
            raise ValueError("inventory self-test miscounted coverage")
        for tests, change in (
            ([], None),
            ([dict(runner, suite=["p:dev"])], None),
            ([runner], lambda: (root / "tests/new.cpp").write_text("")),
            ([runner], lambda: (root / "tests/gate.py").unlink()),
        ):
            if change:
                change()
            try:
                check(root, tests, [], build)
            except ValueError:
                continue
            raise ValueError("inventory self-test accepted an unregistered, partial or stale source")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meson-info", type=Path, help="intro-tests.json of a configured build")
    args = parser.parse_args()
    self_test()
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
