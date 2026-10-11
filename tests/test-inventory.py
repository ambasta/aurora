#!/usr/bin/env python3
"""Account for every compiler runner without equating registration with acceptance."""

import argparse
import json
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def make_inventory(source):
    """Literal Make recipes and prerequisites for shortcut checks."""
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


COMPILER_MESON_ROUTES = {
    "all": "--build-only aurorac --publish-compiler",
    "formatter": "--build-only aurora-fmt --publish-formatter",
    "test": "--suite compiler",
    "test-modules": "--tests modules source-depth host-sources-tests host-output-tests",
    "test-storage": "--tests storage-binary xfs-offline-native",
    "test-initialization-facts": "--tests initialization-facts",
    "test-utf8": "--tests utf8",
    "test-utf8-encoding": "--tests utf8-encoding",
    "test-xfs-geometry": "--tests xfs-geometry",
    "test-xfs-root": "--tests xfs-root xfs-root-api xfs-root-entry",
    "test-utf8-range": "--tests utf8-range",
    "test-utf8-lines": "--tests utf8-lines",
    "test-function-overloads": "--tests function-overloads",
    "test-readonly-windows": "--tests readonly-windows readonly-windows-ir readonly-windows-ir-native",
    "test-short-circuit": "--tests short-circuit short-circuit-ir short-circuit-ir-native",
    "test-token-scan": "--tests token-scan",
    "test-json": "--tests json-profile json-owned",
    "test-json-codecs": "--tests json-codecs",
    "test-json-integers": "--tests json-integers",
    "test-json-lookup": "--tests json-lookup",
    "test-borrowed-objects": "--tests borrowed-objects borrowed-objects-ir borrowed-objects-abi",
    "test-json-string-write": "--tests json-string-write",
    "test-console-service": "--tests console-service-source-native console-service-ir console-session",
    "test-display-service": "--tests display-service-source-native display-service-ir",
    "test-iommu-event-service": "--tests iommu-event-source-native iommu-event-session",
    "test-formatter": "--tests hosted-lexer-format hosted-lexer-format-cli",
    "test-lint": "--tests semantic-lint",
}


def compiler_meson_inventory(source, manifest, records=None):
    """Check exact forwarding recipes and derive coverage from declared Meson commands.

    The manifest's exact argv/suite bindings are independently compared with real
    Meson introspection by check_commands; a forwarded alias cannot remove any
    component of the previous focused selection unnoticed.
    """
    _, _, _, recipes = make_inventory(source)
    if set(recipes) != set(COMPILER_MESON_ROUTES):
        raise ValueError("compiler Make entrypoint set drift")
    prefix = 'python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" '
    named = set()
    for target, selection in COMPILER_MESON_ROUTES.items():
        if [line.strip() for line in recipes[target]] != [prefix + selection]:
            raise ValueError("compiler Meson route drift: " + target)
        if selection.startswith("--tests "):
            named.update(selection.split()[1:])
    if records is not None:
        names = [record["name"] for record in records]
        for name in named:
            if names.count(name) != 1:
                raise ValueError("missing or duplicate compiler alias Meson test: " + name)
    aggregate = {
        runner
        for runner, entry in manifest.items()
        if any("compiler" in command["suites"] for command in entry.get("meson_commands", {}).values())
    }
    focused = {runner for runner, entry in manifest.items() if named.intersection(entry.get("meson_commands", {}))}
    return aggregate | focused, aggregate


def root_meson_inventory(source, manifest):
    """The root aggregate is one full-suite forwarding command, without prerequisites."""
    _, _, reached, recipes = make_inventory(source)
    prefix = 'python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite '
    for target, suite in (("test", "full"), ("test-compiler", "compiler")):
        if [line.strip() for line in recipes.get(target, [])] != [prefix + suite]:
            raise ValueError("root Meson forwarding drift: " + target)
    if reached != {"test"}:
        raise ValueError("root Make test must only forward to Meson")
    return {
        runner
        for runner, entry in manifest.items()
        if any("full" in command["suites"] for command in entry.get("meson_commands", {}).values())
    }


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
        if not entry["reason"] or entry["kind"] not in ("runner", "supplemental-runner", "composed-runner"):
            raise ValueError(f"unclassified runner: {name}")
        if entry["kind"] == "composed-runner":
            parent = entry.get("meson_parent")
            if parent not in manifest or not manifest[parent]["meson"]:
                raise ValueError(f"unregistered composed runner parent: {name}")
            if registered is not None and parent not in registered:
                raise ValueError(f"missing composed runner registration: {name}")
        if registered is not None and entry["meson"] != (name in registered):
            raise ValueError(f"Meson registration drift: {name}")


GRAPHICAL_PYTHON_TESTS = {
    "graphical-console-native": ("kernel-graphical-console.py", "slow", True),
    "graphical-admission-controls": ("kernel-graphical-admission-controls.py", "dev", False),
    "graphical-admission-controls-optimized": ("kernel-graphical-admission-controls.py", "dev", True),
    "graphical-image-policy": ("kernel-graphical-image-policy.py", "dev", False),
    "graphical-image-policy-optimized": ("kernel-graphical-image-policy.py", "dev", True),
    "graphical-profile-metadata": ("kernel-graphical-profile-metadata.py", "dev", False),
    "graphical-profile-metadata-optimized": ("kernel-graphical-profile-metadata.py", "dev", True),
    "graphical-smoke-controls": ("kernel-graphical-smoke.py", "dev", False),
    "graphical-smoke-controls-optimized": ("kernel-graphical-smoke.py", "dev", True),
}


def check_graphical_meson(entries):
    names = [entry["name"] for entry in entries]
    for name, (script, feedback, optimized) in GRAPHICAL_PYTHON_TESTS.items():
        if names.count(name) != 1:
            raise ValueError("missing or duplicate graphical Meson test: " + name)
        entry = next(row for row in entries if row["name"] == name)
        expected = ["-B"] + (["-O"] if optimized else [])
        arguments = entry["cmd"][1:]
        if name == "graphical-console-native":
            if (
                len(arguments) < 3
                or arguments[0] != "-B"
                or Path(arguments[1]).resolve() != ROOT / "tests/meson_artifacts.py"
                or arguments[2] != entry["cmd"][0]
            ):
                raise ValueError("graphical Meson artifact adapter drift")
            arguments = arguments[3:]
        size = len(expected)
        if (
            arguments[:size] != expected
            or len(arguments) <= size
            or Path(arguments[size]).resolve() != ROOT / "tests" / script
        ):
            raise ValueError("graphical Meson runner/flags drift: " + name)
        tail = arguments[size + 1 :]
        if name == "graphical-console-native":
            if (
                len(tail) != 5
                or tail[0] != "--run"
                or Path(tail[1]).name != "aurorac"
                or tail[2] != "--developer-selected-compiler"
                or tail[3:] != ["--artifacts", "@ARTIFACTS@"]
                or "aurorac@exe" not in entry.get("depends", [])
            ):
                raise ValueError("graphical Meson selected compiler/dependency drift")
        elif tail:
            raise ValueError("unexpected graphical control arguments: " + name)
        if {suite.rsplit(":", 1)[-1] for suite in entry["suite"]} != {"full", feedback}:
            raise ValueError("graphical Meson suite drift: " + name)
    if names.count("graphical-paging") != 1:
        raise ValueError("missing or duplicate graphical paging Meson test")
    paging = next(row for row in entries if row["name"] == "graphical-paging")
    if (
        len(paging["cmd"]) != 1
        or Path(paging["cmd"][0]).name != "graphical-paging"
        or not any(item.endswith("@@graphical-paging@exe") for item in paging.get("depends", []))
        or {suite.rsplit(":", 1)[-1] for suite in paging["suite"]} != {"full", "dev"}
    ):
        raise ValueError("graphical paging executable/dependency/suite drift")
    expected_scripts = {script for script, _, _ in GRAPHICAL_PYTHON_TESTS.values()}
    for entry in entries:
        for argument in entry["cmd"][1:]:
            if Path(argument).name in expected_scripts and entry["name"] not in GRAPHICAL_PYTHON_TESTS:
                raise ValueError("unexpected duplicate graphical runner registration")


def canonical_command(arguments, root, build, workdir=None):
    """Normalize real path arguments, preserving flags and argument order."""
    roots = sorted(
        ((Path(root).resolve(), "@SOURCE@"), (Path(build).resolve(), "@BUILD@")),
        key=lambda item: len(item[0].parts),
        reverse=True,
    )
    result = []
    for argument in arguments:
        value = str(argument)
        if value.startswith("/") or (workdir is not None and value.startswith(("./", "../"))):
            path = Path(value)
            if not path.is_absolute():
                path = Path(workdir) / path
            path = path.resolve()
            for prefix, replacement in roots:
                if path.is_relative_to(prefix):
                    relative = path.relative_to(prefix).as_posix()
                    value = replacement + (("/" + relative) if relative != "." else "")
                    break
        result.append(value)
    return result


def check_commands(manifest, records, root, build):
    by_name = {record["name"]: record for record in records}
    for runner, entry in manifest.items():
        expected = entry.get("meson_commands", {})
        if entry["meson"] and not expected:
            raise ValueError("unaccounted compiler command variants: " + runner)
        actual = {
            record["name"]
            for record in records
            if any(Path(arg).resolve() == root / "tests/compiler" / runner for arg in record["cmd"])
        }
        if actual != set(expected):
            raise ValueError("compiler command membership drift: " + runner)
        for name, declaration in expected.items():
            record = by_name[name]
            # The Python executable can differ per toolchain environment; all
            # runner arguments, wrappers, fixtures, profiles and modes are exact.
            command = canonical_command(record["cmd"][1:], root, build, record.get("workdir"))
            command = ["@PYTHON@" if value == record["cmd"][0] else value for value in command]
            if command != declaration["arguments"]:
                raise ValueError("compiler command/profile/mode drift: " + name)
            if sorted(suite.rsplit(":", 1)[-1] for suite in record["suite"]) != declaration["suites"]:
                raise ValueError("compiler suite coverage drift: " + name)


def self_test():
    for build in ("/repo/build/gcc14", "/build/gcc14"):
        command = [
            build + "/../../repo/tests/compiler/a.py"
            if build == "/build/gcc14"
            else build + "/../../tests/compiler/a.py",
            "../aurorac",
            "--profile",
            "full",
        ]
        expected = ["@SOURCE@/tests/compiler/a.py", "@BUILD@/aurorac", "--profile", "full"]
        if canonical_command(command, "/repo", build, build + "/tests") != expected:
            raise ValueError("layout-independent path normalization failed")
    commands = {
        "a.py": dict(
            meson=True,
            meson_commands={
                "a": dict(
                    arguments=["-B", "@SOURCE@/tests/compiler/a.py", "--profile", "full"], suites=["full", "slow"]
                )
            },
        )
    }
    record = dict(
        name="a",
        cmd=["python3", "-B", "/repo/tests/compiler/a.py", "--profile", "full"],
        suite=["aurora:full", "aurora:slow"],
        workdir="/build/tests",
    )
    check_commands(commands, [record], Path("/repo"), Path("/build"))
    for altered in (
        [],
        [dict(record, cmd=record["cmd"][:-1] + ["dev"])],
        [dict(record, cmd=["python3", "-O"] + record["cmd"][1:])],
        [dict(record, suite=["aurora:dev"])],
    ):
        try:
            check_commands(commands, altered, Path("/repo"), Path("/build"))
        except ValueError:
            pass
        else:
            raise ValueError("compiler command/profile/mode negative control accepted drift")

    sample = {"a.py": dict(make=True, root_make=True, meson=True, kind="runner", reason="native oracle")}
    all_runners, aggregate, _, _ = make_inventory(
        "test: first\nfirst:\n\tpython3 tests/compiler/a.py\nother:\n\tpython3 tests/compiler/b.py\n"
    )
    if all_runners != {"a.py", "b.py"} or aggregate != {"a.py"}:
        raise ValueError("Make reachability self-test failed")
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

    source = "\n".join(
        target + ':\n\tpython3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" ' + selection
        for target, selection in COMPILER_MESON_ROUTES.items()
    )
    compiler_manifest = {
        "a.py": {"meson_commands": {"frontend": {"suites": ["compiler", "full"]}}},
        "b.py": {"meson_commands": {"separate": {"suites": ["full"]}}},
    }
    if compiler_meson_inventory(source, compiler_manifest) != ({"a.py"}, {"a.py"}):
        raise ValueError("compiler Meson aggregate coverage control failed")
    for changed in (
        source.replace("--suite compiler", "--suite dev"),
        source.replace("short-circuit short-circuit-ir short-circuit-ir-native", "short-circuit"),
        source.replace("--tests semantic-lint", "--tests another-test"),
        source.replace("\tpython3", "\t-python3", 1),
        source + "\nextra:\n\ttrue\n",
    ):
        try:
            compiler_meson_inventory(changed, compiler_manifest)
        except ValueError:
            pass
        else:
            raise ValueError("compiler Meson forwarding mutation was accepted")

    root = (
        'test:\n\tpython3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite full\n'
        'test-compiler:\n\tpython3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite compiler\n'
    )
    if root_meson_inventory(root, compiler_manifest) != {"a.py", "b.py"}:
        raise ValueError("root Meson full selection control failed")
    for changed in (
        root.replace("--suite full", "--suite compiler"),
        root.replace("test:", "test: test-clean"),
        root.replace("\tpython3", "\t-python3", 1),
    ):
        try:
            root_meson_inventory(changed, compiler_manifest)
        except ValueError:
            pass
        else:
            raise ValueError("root Meson forwarding mutation was accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meson-info", type=Path)
    args = parser.parse_args()
    self_test()
    manifest = json.loads((ROOT / "tests/compiler-test-inventory.json").read_text())
    files = {p.name for p in (ROOT / "tests/compiler").glob("*.py")}
    root_runners = root_meson_inventory((ROOT / "Makefile").read_text(), manifest)
    compiler_source = (ROOT / "compiler/Makefile").read_text()
    compiler_all, _ = compiler_meson_inventory(compiler_source, manifest)
    make_runners = root_runners | compiler_all
    registered = None
    records = None
    if args.meson_info:
        records = json.loads(args.meson_info.read_text())
        registered = set()
        check_graphical_meson(records)
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
        compiler_meson_inventory(compiler_source, manifest, records)
    native_spec = importlib.util.spec_from_file_location("aurora_native_inventory", ROOT / "tests/native/inventory.py")
    native = importlib.util.module_from_spec(native_spec)
    native_spec.loader.exec_module(native)
    native_summary = native.check(ROOT, records)
    gaps = sorted(name for name, entry in manifest.items() if not entry["meson"] and entry["kind"] != "composed-runner")
    composed = sum(entry["kind"] == "composed-runner" for entry in manifest.values())
    print(
        f"PASS compiler inventory: {len(files)} runnable scripts; "
        f"{len(make_runners)} Make-routed ({len(root_runners)} root aggregate); "
        f"{len(files) - len(gaps) - composed} direct Meson memberships and {composed} composed child "
        f"({'verified' if registered is not None else 'declared, not checked in this invocation'}); "
        f"{len(gaps)} separate baseline-dependent gates"
    )
    print("PASS exact compiler/root Meson forwarding")
    print("Native inventory: " + json.dumps(native_summary, sort_keys=True))
    print("Registration is not execution; final-source full Meson and affected emulator gates remain required.")


if __name__ == "__main__":
    main()
