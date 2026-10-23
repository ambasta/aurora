#!/usr/bin/env python3
"""Account for every compiler runner without equating registration with acceptance."""

import argparse
import json
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def make_inventory(source, root_target="test"):
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

    reached, pending = set(), [root_target]
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
}


def compiler_meson_inventory(source, manifest):
    """Check the surviving build/aggregate routes; Meson owns focused selection."""
    _, _, _, recipes = make_inventory(source)
    if set(recipes) != set(COMPILER_MESON_ROUTES):
        raise ValueError("compiler Make entrypoint set drift")
    prefix = 'python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" '
    for target, selection in COMPILER_MESON_ROUTES.items():
        if [line.strip() for line in recipes[target]] != [prefix + selection]:
            raise ValueError("compiler Meson route drift: " + target)
    return {
        runner
        for runner, entry in manifest.items()
        if any("compiler" in command["suites"] for command in entry.get("meson_commands", {}).values())
    }


def root_meson_inventory(source, manifest):
    """Normal full and exhaustive are separate forwarding commands, without prerequisites."""
    prefix = 'python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite '
    for target, suite in (("test", "full"), ("test-exhaustive", "exhaustive")):
        _, _, reached, recipes = make_inventory(source, target)
        if [line.strip() for line in recipes.get(target, [])] != [prefix + suite]:
            raise ValueError("root Meson forwarding drift: " + target)
        if reached != {target}:
            raise ValueError("root Make test selections must only forward to Meson")
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
        if not entry["reason"] or entry["kind"] not in ("runner", "supplemental-runner", "composed-runner", "helper"):
            raise ValueError(f"unclassified runner: {name}")
        if entry["kind"] == "helper":
            if any(entry[key] for key in ("make", "root_make", "meson")) or entry.get("meson_commands"):
                raise ValueError(f"helper classified as standalone runner: {name}")
            importers = entry.get("imported_by", [])
            if not importers or any(parent not in manifest or not manifest[parent]["meson"] for parent in importers):
                raise ValueError(f"helper lacks registered importing runners: {name}")
            if registered is not None and any(parent not in registered for parent in importers):
                raise ValueError(f"missing helper importer registration: {name}")
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
    "graphical-admission-controls-optimized": ("kernel-graphical-admission-controls.py", "dev", True),
    "graphical-image-policy-optimized": ("kernel-graphical-image-policy.py", "dev", True),
    "graphical-profile-metadata-optimized": ("kernel-graphical-profile-metadata.py", "dev", True),
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
    # The selected predecessor is a per-machine path; record it by role.
    options = Path(build) / "meson-info/intro-buildoptions.json"
    predecessor = None
    role_values = {}
    if options.exists():
        values = json.loads(options.read_text())
        predecessor = next((option["value"] for option in values if option["name"] == "bootstrap_compiler"), None)
        if predecessor is None:
            raise ValueError("Meson build options lack bootstrap_compiler")
        comparison_base = next(
            (option["value"] for option in values if option["name"] == "emitter_comparison_base"), None
        )
        if not isinstance(comparison_base, str):
            raise ValueError("Meson build options lack emitter_comparison_base")
        receipt = next((option["value"] for option in values if option["name"] == "bootstrap_receipt"), None)
        if receipt:
            evidence = json.loads(Path(receipt).read_text())
            oracle = next(
                stage["artifact"]
                for stage in evidence["stages"]
                if stage["source"]["name"] == evidence["route"]["historical_cpp_oracle"]
            )
            role_values = {
                receipt: "@BOOTSTRAP_RECEIPT@",
                oracle["path"]: "@HISTORICAL_CPP_ORACLE@",
                oracle["sha256"]: "@HISTORICAL_CPP_ORACLE_SHA256@",
            }
        role_values["--comparison-base=" + comparison_base] = "--comparison-base=@EMITTER_COMPARISON_BASE@"
    arguments = {record["name"]: {Path(arg).resolve() for arg in record["cmd"]} for record in records}
    for runner, entry in manifest.items():
        expected = entry.get("meson_commands", {})
        if entry["meson"] and not expected:
            raise ValueError("unaccounted compiler command variants: " + runner)
        script = root / "tests/compiler" / runner
        actual = {name for name, paths in arguments.items() if script in paths}
        if actual != set(expected):
            raise ValueError("compiler command membership drift: " + runner)
        for name, declaration in expected.items():
            record = by_name[name]
            # The Python executable can differ per toolchain environment; all
            # runner arguments, wrappers, fixtures, profiles and modes are exact.
            raw = [
                role_values.get(value, "@PREDECESSOR@" if value == predecessor else value)
                for value in record["cmd"][1:]
            ]
            command = canonical_command(raw, root, build, record.get("workdir"))
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

    helper = dict(
        make=False,
        root_make=False,
        meson=False,
        meson_commands={},
        kind="helper",
        reason="shared fixture transport",
        imported_by=["a.py"],
    )
    with_helper = dict(sample, **{"helper.py": helper})
    check(with_helper, set(with_helper), {"a.py"}, {"a.py"}, {"a.py"})
    for changed in (
        dict(helper, imported_by=[]),
        dict(helper, imported_by=["missing.py"]),
        dict(helper, meson=True),
        dict(helper, meson_commands={"fake": {}}),
    ):
        altered = dict(sample, **{"helper.py": changed})
        try:
            check(altered, set(altered), {"a.py"}, {"a.py"}, {"a.py"})
        except ValueError:
            pass
        else:
            raise ValueError("helper inventory mutation was not rejected")

    source = "\n".join(
        target + ':\n\tpython3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" ' + selection
        for target, selection in COMPILER_MESON_ROUTES.items()
    )
    compiler_manifest = {
        "a.py": {"meson_commands": {"frontend": {"suites": ["compiler", "full"]}}},
        "b.py": {"meson_commands": {"separate": {"suites": ["full"]}}},
    }
    if compiler_meson_inventory(source, compiler_manifest) != {"a.py"}:
        raise ValueError("compiler Meson aggregate coverage control failed")
    for changed in (
        source.replace("--suite compiler", "--suite dev"),
        source.replace("\tpython3", "\t-python3", 1),
        source + "\nextra:\n\ttrue\n",
    ):
        try:
            compiler_meson_inventory(changed, compiler_manifest)
        except ValueError:
            pass
        else:
            raise ValueError("compiler Meson forwarding mutation was accepted")

    root = 'test:\n\tpython3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite full\n'
    root += 'test-exhaustive:\n\tpython3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite exhaustive\n'
    if root_meson_inventory(root, compiler_manifest) != {"a.py", "b.py"}:
        raise ValueError("root Meson full selection control failed")
    for changed in (
        root.replace("--suite full", "--suite compiler"),
        root.replace("test:", "test: test-clean"),
        root.replace("test-exhaustive:", "test-exhaustive: test"),
        root.replace("--suite exhaustive", "--suite full"),
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
    compiler_all = compiler_meson_inventory(compiler_source, manifest)
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
    native_spec = importlib.util.spec_from_file_location("aurora_native_inventory", ROOT / "tests/native/inventory.py")
    native = importlib.util.module_from_spec(native_spec)
    native_spec.loader.exec_module(native)
    native_summary = native.check(ROOT, records)
    gaps = sorted(
        name
        for name, entry in manifest.items()
        if not entry["meson"] and entry["kind"] not in ("composed-runner", "helper")
    )
    composed = sum(entry["kind"] == "composed-runner" for entry in manifest.values())
    helpers = sum(entry["kind"] == "helper" for entry in manifest.values())
    print(
        f"PASS compiler inventory: {len(files) - helpers} runnable scripts and {helpers} imported helpers; "
        f"{len(make_runners)} Make-routed ({len(root_runners)} root aggregate); "
        f"{len(files) - len(gaps) - composed - helpers} direct Meson memberships and {composed} composed child "
        f"({'verified' if registered is not None else 'declared, not checked in this invocation'}); "
        f"{len(gaps)} separate baseline-dependent gates"
    )
    print("PASS exact compiler/root Meson forwarding")
    print("Native inventory: " + json.dumps(native_summary, sort_keys=True))
    print("Registration is not execution; final-source full Meson and affected emulator gates remain required.")


if __name__ == "__main__":
    main()
