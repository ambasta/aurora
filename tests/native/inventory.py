"""Read-only native coverage checks used by the existing test inventory gate."""

import hashlib
import json
import shlex
from pathlib import Path


COMPILER_GOALS = {"test-compiler", "test-package-identity", "test-package-manifest", "test-package-graph"}


def discovered_files(root):
    return {
        path.relative_to(root).as_posix()
        for pattern in ("tests/*.py", "tests/*.cpp", "tests/compiler/*.cpp", "tests/modules/*.cpp", "scripts/*test*.sh")
        for path in root.glob(pattern)
        if path.name != "compiler-test.sh"
    }


def normalize(arguments, root, build, workdir, python, cxx, outputs=()):
    """Canonical paths follow the actual cwd, including nested in-tree builds."""
    roots = sorted(
        ((Path(root).resolve(), "@SOURCE@"), (Path(build).resolve(), "@BUILD@")),
        key=lambda pair: len(pair[0].parts),
        reverse=True,
    )
    cwd = Path(workdir or build)
    result = []
    for argument in arguments:
        value = str(argument)
        if value == python:
            result.append("@PYTHON@")
            continue
        if value == cxx:
            result.append("@CXX@")
            continue
        path = Path(value)
        if path.is_absolute() and path.name in ("as", "ld", "nm", "objdump", "objcopy", "readelf"):
            result.append("@" + path.name.upper() + "@")
            continue
        candidate = path if path.is_absolute() else cwd / path
        if path.is_absolute() or value.startswith(("./", "../")) or candidate.resolve() in outputs:
            path = candidate.resolve()
            for prefix, replacement in roots:
                if path.is_relative_to(prefix):
                    relative = path.relative_to(prefix).as_posix()
                    value = replacement + ("/" + relative if relative != "." else "")
                    break
        result.append(value)
    return result


def contracts(records, targets, root, build):
    """Normalize observed declarations, never executing a target or compiler."""
    named = {target["id"]: target["name"] for target in targets}
    compiler = next(target for target in targets if target["name"] == "aurorac")
    cpp = next(group["compiler"] for group in compiler["target_sources"] if group.get("language") == "cpp")
    cxx = shlex.join(cpp)
    anchor = next(record for record in records if record["name"] == "compiler-test-inventory")
    python = anchor["cmd"][0]
    outputs = {Path(path).resolve() for target in targets for path in target["filename"]}

    def norm(values, cwd=None):
        return normalize(values, root, build, cwd, python, cxx, outputs)

    test_contracts = {}
    for record in records:
        cwd = record.get("workdir")
        test_contracts[record["name"]] = dict(
            command=norm(record["cmd"], cwd),
            suites=sorted(value.rsplit(":", 1)[-1] for value in record["suite"]),
            environment={key: norm([value], cwd)[0] for key, value in record.get("env", {}).items()},
            workdir=norm([cwd])[0] if cwd else None,
            depends=sorted(named.get(value, value) for value in record.get("depends", [])),
            is_parallel=record.get("is_parallel"),
            protocol=record.get("protocol"),
        )
    target_contracts = {}
    for target in targets:
        target_contracts[target["name"]] = dict(
            type=target["type"],
            outputs=norm(target["filename"]),
            sources=sorted(norm([path for group in target["target_sources"] for path in group.get("sources", [])])),
            generated_sources=sorted(
                norm([path for group in target["target_sources"] for path in group.get("generated_sources", [])])
            ),
            depends=sorted(named.get(value, value) for value in target.get("depends", [])),
            fixture_flags=[
                dict(
                    kind=group.get("language", "link"),
                    flags=[
                        flag
                        for flag in group.get("parameters", [])
                        if flag.startswith(("-D", "-U", "-O", "-std=", "-fsanitize="))
                        or flag
                        in (
                            "-g",
                            "-pthread",
                            "-no-pie",
                            "-fno-pie",
                            "-fno-exceptions",
                            "-fno-rtti",
                            "-fno-builtin",
                            "-Werror",
                        )
                    ],
                )
                for group in target["target_sources"]
                if "language" in group or "linker" in group
            ],
        )
        # Custom fixture commands are observable in introspection; retain their
        # actual compiler/assembler selection and complete argument sequence.
        if target["type"] == "custom":
            target_contracts[target["name"]]["commands"] = [
                norm(group.get("compiler", [])) for group in target["target_sources"]
            ]
    return test_contracts, target_contracts


def check_exact(expected, actual, label):
    for name, contract in expected.items():
        if name not in actual:
            raise ValueError("missing " + label + ": " + name)
        if contract != actual[name]:
            changed = sorted(
                key for key in set(contract) | set(actual[name]) if contract.get(key) != actual[name].get(key)
            )
            raise ValueError(label + " drift: " + name + ": " + ", ".join(changed))


def check_manifest(manifest, actual_files, tests=None, root_targets=None, kernel_images=True):
    listed = set(manifest["files"])
    if actual_files != listed:
        raise ValueError(
            "native source inventory drift: added="
            + repr(sorted(actual_files - listed))
            + ", removed="
            + repr(sorted(listed - actual_files))
        )
    for path, entry in manifest["files"].items():
        if not entry.get("reason") or entry.get("kind") not in {
            "direct-registration",
            "existing-registration",
            "retained-wrapper",
            "native-fixture",
            "imported-helper",
            "separate-gate",
            "compiler-owned",
        }:
            raise ValueError("unclassified native source: " + path)
    if root_targets is not None:
        required = {name for name in root_targets if name.startswith("test-")} - COMPILER_GOALS
        if required != set(manifest["goals"]):
            raise ValueError(
                "native root prerequisite inventory drift: added="
                + repr(sorted(required - set(manifest["goals"])))
                + ", removed="
                + repr(sorted(set(manifest["goals"]) - required))
            )
    if tests is None:
        return
    by_name = {entry["name"]: entry for entry in tests}
    required = {name for names in manifest["goals"].values() for name in names}
    required.update(manifest["registrations"])
    required.update(manifest.get("exact_tests", {}))
    missing = required - set(by_name)
    if missing:
        raise ValueError("missing native Meson registrations: " + repr(sorted(missing)))
    for name in required:
        if not any(suite.split(":")[-1] == "full" for suite in by_name[name]["suite"]):
            raise ValueError("native gate omitted from full suite: " + name)
    for name, expected in manifest["registrations"].items():
        if not kernel_images and name in (
            "native-bios-image",
            "native-uefi-normal-image",
            "native-uefi-span-integration",
        ):
            continue  # Exact failure commands are checked against the actual configured option.
        argv = by_name[name]["cmd"]
        source = expected.get("source", "")
        if source.endswith((".py", ".sh")) and not any(
            Path(str(arg)).resolve().as_posix().endswith("/" + source) for arg in argv
        ):
            raise ValueError("native runner command drift: " + name)
        if "optimized" in expected and ("-O" in argv) != expected["optimized"]:
            raise ValueError("native Python optimization-mode drift: " + name)
        for argument in expected.get("arguments", []):
            if argument not in argv:
                raise ValueError("missing native runner argument: " + name + ": " + argument)
        if "--meson-selected-compiler" in expected.get("arguments", []):
            if "--compiler-sha256" in argv or "--developer-build-receipt" in argv:
                raise ValueError("native developer gate mislabels compiler provenance: " + name)


def self_test():
    manifest = dict(
        files={"tests/a.py": dict(kind="direct-registration", reason="fixture")},
        goals={"test-a": ["a"]},
        registrations={"a": dict(source="tests/a.py", optimized=True, arguments=["--self-test"])},
    )
    valid = [dict(name="a", suite=["aurora:full"], cmd=["python3", "-O", "/repo/tests/a.py", "--self-test"])]
    check_manifest(manifest, {"tests/a.py"}, valid, {"test", "test-a"})
    aliased = [dict(valid[0], cmd=["python3", "-O", "/repo/tests/native/../a.py", "--self-test"])]
    check_manifest(manifest, {"tests/a.py"}, aliased, {"test", "test-a"})
    bad = [
        ({"tests/a.py", "tests/new.py"}, valid, {"test", "test-a"}),
        ({"tests/a.py", "tests/compiler/new.cpp"}, valid, {"test", "test-a"}),
        ({"tests/a.py", "tests/modules/new.cpp"}, valid, {"test", "test-a"}),
        ({"tests/a.py"}, [], {"test", "test-a"}),
        ({"tests/a.py"}, valid, {"test", "test-a", "test-uncovered"}),
    ]
    for files, tests, targets in bad:
        try:
            check_manifest(manifest, files, tests, targets)
        except ValueError:
            pass
        else:
            raise ValueError("native inventory negative control did not reject drift")
    for field, value in [
        ("suite", ["aurora:dev"]),
        ("cmd", ["python3", "/repo/tests/a.py", "--self-test"]),
        ("cmd", ["python3", "-O", "/repo/tests/a.py"]),
        ("cmd", ["python3", "-O", "/repo/tests/other.py", "--self-test"]),
    ]:
        altered = [dict(valid[0], **{field: value})]
        try:
            check_manifest(manifest, {"tests/a.py"}, altered, {"test", "test-a"})
        except ValueError:
            pass
        else:
            raise ValueError("native inventory negative control accepted command/suite drift")

    # Both source/build nesting orders must preserve actual fixture resolution.
    for build in ("/repo/build/gcc14", "/build/gcc14"):
        source = (
            build + "/../../repo/tests/compiler/a.cpp"
            if build == "/build/gcc14"
            else build + "/../../tests/compiler/a.cpp"
        )
        actual = normalize(
            [source, "../aurorac", "fixture"],
            "/repo",
            build,
            build + "/tests",
            "/python",
            "/cxx",
            {Path(build + "/tests/fixture")},
        )
        if actual != ["@SOURCE@/tests/compiler/a.cpp", "@BUILD@/aurorac", "@BUILD@/tests/fixture"]:
            raise ValueError("native source/build path normalization failed")
    expected = {
        "initialization-facts": dict(
            command=["@BUILD@/tests/initialization-facts"],
            suites=["core", "dev", "full"],
            environment={},
            depends=["initialization-facts"],
        )
    }
    for actual in (
        {},
        {"initialization-facts": dict(expected["initialization-facts"], command=["other"])},
        {"initialization-facts": dict(expected["initialization-facts"], environment={"CXX": "other"})},
        {"initialization-facts": dict(expected["initialization-facts"], suites=["dev"])},
        {"initialization-facts": dict(expected["initialization-facts"], depends=[])},
    ):
        try:
            check_exact(expected, actual, "fixture registration")
        except ValueError:
            pass
        else:
            raise ValueError("fixture contract negative control accepted drift")
    target = {
        "host-output-tests": dict(
            sources=["@SOURCE@/tests/modules/host_output_tests.cpp"], outputs=["@BUILD@/tests/host-output-tests"]
        )
    }
    try:
        check_exact(target, {"host-output-tests": dict(target["host-output-tests"], sources=[])}, "fixture target")
    except ValueError:
        pass
    else:
        raise ValueError("fixture source mapping negative control accepted drift")


def check(root, registered_tests=None, root_targets=None):
    root = Path(root)
    self_test()
    manifest = json.loads((root / "tests/native/inventory.json").read_text())
    if registered_tests is not None:
        anchor = next(record for record in registered_tests if record["name"] == "compiler-test-inventory")
        arguments = anchor["cmd"]
        info = Path(arguments[arguments.index("--meson-info") + 1])
        if not info.is_absolute():
            info = Path(anchor.get("workdir") or root) / info
        build = info.resolve().parents[1]
        options = json.loads((build / "meson-info/intro-buildoptions.json").read_text())
        kernel_images = next(option["value"] for option in options if option["name"] == "kernel_images")
        targets = json.loads((build / "meson-info/intro-targets.json").read_text())
        observed_tests, observed_targets = contracts(registered_tests, targets, root, build)
        expected_tests = dict(manifest["exact_tests"])
        if not kernel_images:
            for name in ("native-bios-image", "native-uefi-normal-image", "native-uefi-span-integration"):
                expected_tests[name] = dict(
                    expected_tests[name],
                    depends=[],
                    command=[
                        "@PYTHON@",
                        "-c",
                        'raise SystemExit("Kernel images disabled: configure '
                        '-Dkernel_images=true for full/boot qualification")',
                    ],
                )
        check_exact(expected_tests, observed_tests, "Meson test contract")
        check_exact(manifest["fixture_targets"], observed_targets, "Meson fixture target")
    check_manifest(
        manifest,
        discovered_files(root),
        registered_tests,
        root_targets,
        kernel_images if registered_tests is not None else True,
    )
    for name, expected in manifest["wrapper_sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("native shell command inventory needs review after wrapper change: " + name)
    return {
        "root_native_goals": len(manifest["goals"]),
        "native_registrations": len(manifest["registrations"]),
        "classified_native_files": len(manifest["files"]),
        "exact_test_contracts": len(manifest.get("exact_tests", {})),
        "fixture_target_contracts": len(manifest.get("fixture_targets", {})),
    }
