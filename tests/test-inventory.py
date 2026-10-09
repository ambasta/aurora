#!/usr/bin/env python3
"""Account for every compiler runner without equating registration with acceptance."""

import argparse
import json
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def make_inventory(source):
    """Literal dependency/recipe graph for the two authoritative Makefiles."""
    dependencies, recipes, current = {}, {}, []
    for line in re.sub(r"\\\r?\n", " ", source).splitlines():
        if line.startswith("\t"):
            line = line.split("#", 1)[0]
            if not line.strip().lstrip("@+-").strip():
                continue
            for target in current:
                recipes.setdefault(target, []).append(line)
            continue
        rule = line.split("#", 1)[0]
        if ":" not in rule or "=" in rule:
            current = []
            continue
        targets, prerequisites = rule.split(":", 1)
        current = targets.split()
        for target in current:
            dependencies.setdefault(target, set()).update(prerequisites.split())

    def runners(targets):
        return set(
            re.findall(
                r"tests/compiler/([\w_]+\.py)",
                "\n".join(line for target in targets for line in recipes.get(target, [])),
            )
        )

    reached, pending = set(), ["test"]
    while pending:
        target = pending.pop()
        if target not in reached:
            reached.add(target)
            pending.extend(dependencies.get(target, set()))
    return runners(recipes), runners(reached), reached, recipes


def compiler_dispatch(recipes):
    return any(
        re.fullmatch(r"\s*[@+]*\s*\$\(MAKE\)\s+-C\s+compiler\s+test\s*", recipe)
        for recipe in recipes.get("test-compiler", [])
    )


def check(manifest, files, make_runners, registered=None, root_runners=None):
    if set(manifest) != files:
        raise ValueError(
            f"compiler inventory drift: added={sorted(files - set(manifest))}, removed={sorted(set(manifest) - files)}"
        )
    for name, entry in manifest.items():
        if entry["make"] != (name in make_runners):
            raise ValueError(f"Make routing drift: {name}")
        if root_runners is not None and entry["root_make"] != (name in root_runners):
            raise ValueError(f"root Make coverage drift: {name}")
        if not entry["reason"] or entry["kind"] not in ("runner", "supplemental-runner"):
            raise ValueError(f"unclassified runner: {name}")
        if registered is not None and entry["meson"] != (name in registered):
            raise ValueError(f"Meson registration drift: {name}")


def canonical_command(arguments, root, build, workdir=None):
    """Normalize real path arguments, preserving flags and argument order."""
    roots = sorted(((Path(root).resolve(), '@SOURCE@'), (Path(build).resolve(), '@BUILD@')),
                   key=lambda item: len(item[0].parts), reverse=True)
    result = []
    for argument in arguments:
        value = str(argument)
        if value.startswith('/') or (workdir is not None and value.startswith(('./', '../'))):
            path = Path(value)
            if not path.is_absolute():
                path = Path(workdir) / path
            path = path.resolve()
            for prefix, replacement in roots:
                if path.is_relative_to(prefix):
                    relative = path.relative_to(prefix).as_posix()
                    value = replacement + (('/' + relative) if relative != '.' else '')
                    break
        result.append(value)
    return result


def check_commands(manifest, records, root, build):
    by_name = {record['name']: record for record in records}
    for runner, entry in manifest.items():
        expected = entry.get('meson_commands', {})
        if entry['meson'] and not expected:
            raise ValueError('unaccounted compiler command variants: ' + runner)
        actual = {record['name'] for record in records
                  if any(Path(arg).resolve() == root / 'tests/compiler' / runner
                         for arg in record['cmd'])}
        if actual != set(expected):
            raise ValueError('compiler command membership drift: ' + runner)
        for name, declaration in expected.items():
            record = by_name[name]
            # The Python executable can differ per toolchain environment; all
            # runner arguments, wrappers, fixtures, profiles and modes are exact.
            command = canonical_command(record['cmd'][1:], root, build, record.get('workdir'))
            command = ['@PYTHON@' if value == record['cmd'][0] else value for value in command]
            if command != declaration['arguments']:
                raise ValueError('compiler command/profile/mode drift: ' + name)
            if sorted(suite.rsplit(':', 1)[-1] for suite in record['suite']) != declaration['suites']:
                raise ValueError('compiler suite coverage drift: ' + name)


def self_test():
    for build in ('/repo/build/gcc14', '/build/gcc14'):
        command = [build + '/../../repo/tests/compiler/a.py' if build == '/build/gcc14'
                   else build + '/../../tests/compiler/a.py', '../aurorac', '--profile', 'full']
        expected = ['@SOURCE@/tests/compiler/a.py', '@BUILD@/aurorac', '--profile', 'full']
        if canonical_command(command, '/repo', build, build + '/tests') != expected:
            raise ValueError('layout-independent path normalization failed')
    commands = {'a.py': dict(meson=True, meson_commands={'a': dict(
        arguments=['-B', '@SOURCE@/tests/compiler/a.py', '--profile', 'full'], suites=['full', 'slow'])})}
    record = dict(name='a', cmd=['python3', '-B', '/repo/tests/compiler/a.py', '--profile', 'full'],
                  suite=['aurora:full', 'aurora:slow'], workdir='/build/tests')
    check_commands(commands, [record], Path('/repo'), Path('/build'))
    for altered in ([], [dict(record, cmd=record['cmd'][:-1] + ['dev'])],
                    [dict(record, cmd=['python3', '-O'] + record['cmd'][1:])],
                    [dict(record, suite=['aurora:dev'])]):
        try:
            check_commands(commands, altered, Path('/repo'), Path('/build'))
        except ValueError:
            pass
        else:
            raise ValueError('compiler command/profile/mode negative control accepted drift')

    sample = {"a.py": dict(make=True, root_make=True, meson=True, kind="runner", reason="native oracle")}
    all_runners, aggregate, _, _ = make_inventory(
        "test: first\nfirst:\n\tpython3 tests/compiler/a.py\nother:\n\tpython3 tests/compiler/b.py\n"
    )
    if all_runners != {"a.py", "b.py"} or aggregate != {"a.py"}:
        raise ValueError("Make reachability self-test failed")
    for bad in ("test-formatter", "test-json", "test --ignore-errors"):
        if compiler_dispatch({"test-compiler": ["\t$(MAKE) -C compiler " + bad]}):
            raise ValueError("nonaggregate compiler dispatch accepted")
    if compiler_dispatch({"test-compiler": ["\t-$(MAKE) -C compiler test"]}):
        raise ValueError("failure-suppressing compiler aggregate dispatch accepted")
    if not compiler_dispatch({"test-compiler": ["\t$(MAKE) -C compiler test"]}):
        raise ValueError("literal compiler aggregate dispatch not recognized")
    commented, _, _, recipes = make_inventory(
        "test: test-compiler\ntest-compiler:\n\t# $(MAKE) -C compiler test\n\t@# python3 tests/compiler/a.py\n"
    )
    if commented or compiler_dispatch(recipes):
        raise ValueError("commented recipe counted as runnable")
    check(sample, {"a.py"}, {"a.py"}, {"a.py"})
    try:
        check(sample, {"a.py"}, {"a.py"}, {"a.py"}, set())
    except ValueError:
        pass
    else:
        raise ValueError("removed aggregate prerequisite was not rejected")
    for files, make, meson in [
        ({"a.py", "new.py"}, {"a.py"}, {"a.py"}),
        ({"a.py"}, set(), {"a.py"}),
        ({"a.py"}, {"a.py"}, set()),
    ]:
        try:
            check(sample, files, make, meson)
        except ValueError:
            continue
        raise ValueError("inventory mutation was not rejected")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meson-info", type=Path)
    args = parser.parse_args()
    self_test()
    manifest = json.loads((ROOT / "tests/compiler-test-inventory.json").read_text())
    files = {p.name for p in (ROOT / "tests/compiler").glob("*.py")}
    root_all, root_runners, reached, recipes = make_inventory((ROOT / "Makefile").read_text())
    compiler_all, compiler_runners, _, _ = make_inventory((ROOT / "compiler/Makefile").read_text())
    if "test-compiler" not in reached or not compiler_dispatch(recipes):
        raise ValueError("root Make no longer dispatches the complete compiler aggregate")
    make_runners = root_all | compiler_all
    root_runners |= compiler_runners
    registered = None
    records = None
    if args.meson_info:
        records = json.loads(args.meson_info.read_text())
        registered = set()
        for entry in records:
            for argument in entry["cmd"]:
                path = Path(argument).resolve()
                if path.parent == ROOT / "tests/compiler":
                    registered.add(path.name)
        if not registered:
            raise ValueError("no compiler runners in Meson introspection")
    check(manifest, files, make_runners, registered, root_runners)
    if records is not None:
        check_commands(manifest, records, ROOT, args.meson_info.resolve().parents[1])
    native_spec = importlib.util.spec_from_file_location('aurora_native_inventory', ROOT / 'tests/native/inventory.py')
    native = importlib.util.module_from_spec(native_spec)
    native_spec.loader.exec_module(native)
    native_summary = native.check(ROOT, records, reached)
    gaps = sorted(name for name, entry in manifest.items() if not entry["meson"])
    print(
        f"PASS compiler inventory: {len(files)} runnable scripts; "
        f"{len(make_runners)} Make-routed ({len(root_runners)} root aggregate); "
        f"{len(files) - len(gaps)} Meson memberships "
        f"({'verified' if registered is not None else 'declared, not checked in this invocation'}); "
        f"{len(gaps)} explicitly documented Meson gaps"
    )
    print("Native inventory: " + json.dumps(native_summary, sort_keys=True))
    print("Registration is not execution; final-source full Meson and affected emulator gates remain required.")


if __name__ == "__main__":
    main()
