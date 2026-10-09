#!/usr/bin/env python3
"""Exact fixture/patch identities and synthetic mocks; never launches an emulator."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_context_prerequisites(source):
    """Inspect literal rules directly inside the existing active-context guard.

    Target order is irrelevant to a multi-target ':' rule. This deliberately
    checks the repository's literal rule form, without evaluating Make syntax.
    Definitions support simple identifier names, optional ordinary assignment
    operators and unique export/unexport/override/private modifiers. Nested
    definitions must be bare; modified nested definitions and other definition
    forms reject. This is not a general Make parser or conditional evaluator.
    Comments, recipes, assignments and supported define bodies are excluded.
    """
    targets, conditions, define_depth = set(), [], 0
    for original in re.sub(r"\\\r?\n", " ", source).splitlines():
        if original.startswith("\t"):
            continue
        line = original.split("#", 1)[0].strip()
        definition = re.match(r"^((?:(?:export|unexport|override|private)\s+)*)define(?:\s|$)", line)
        if definition:
            modifiers = definition[1].split()
            require(not define_depth or not modifiers, "Unsupported modified nested Make define")
            require(
                len(modifiers) == len(set(modifiers)) and not {"export", "unexport"} <= set(modifiers),
                "Unsupported repeated or conflicting Make define modifiers",
            )
            require(
                re.fullmatch(
                    r"(?:(?:export|unexport|override|private)\s+)*define\s+"
                    r"[A-Za-z_][A-Za-z0-9_]*(?:\s*(?:=|:=|::=|\?=|\+=))?",
                    line,
                ),
                "Unsupported Make define header",
            )
            define_depth += 1
            continue
        if line == "endef":
            require(define_depth > 0, "Unmatched Make endef")
            define_depth -= 1
            continue
        if define_depth:
            continue
        require(
            not re.match(r"^[A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*\s+define(?:\s|$)", line),
            "Unsupported Make define modifier",
        )
        if re.match(r"^(?:ifeq|ifneq|ifdef|ifndef)(?:\s|$)", line):
            conditions.append(line == "ifneq ($(strip $(AURORA_TEST_CONTEXT)),)")
            continue
        if line == "else" or line.startswith("else "):
            require(bool(conditions), "Unmatched Make conditional")
            conditions[-1] = False
            continue
        if line == "endif":
            require(bool(conditions), "Unmatched Make conditional")
            conditions.pop()
            continue
        names, separator, prerequisites = line.partition(":")
        if (
            conditions
            and conditions[-1]
            and separator
            and prerequisites.split() == ["aurora-test-context"]
            and names.split()
            and all(re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in names.split())
        ):
            targets.update(names.split())
    require(not conditions and not define_depth, "Unclosed Make conditional or define")
    require({"test-inventory", "test-iommu-diagnostics"} <= targets, "Missing context prerequisite")


def context_prerequisite_cases():
    guard = "ifneq ($(strip $(AURORA_TEST_CONTEXT)),)\n"
    end = "endif\n"
    rule = "test-inventory test-iommu-diagnostics: aurora-test-context\n"
    missing = "test-iommu-diagnostics: aurora-test-context\n"
    valid = (
        guard + rule + end,
        guard + "test-iommu-diagnostics test-graphical-controls test-inventory: aurora-test-context\n" + end,
        guard + "test-inventory \\\n    test-graphical-controls test-iommu-diagnostics: aurora-test-context\n" + end,
        guard + missing + "test-inventory: aurora-test-context\n" + end,
    )
    invalid = {
        "missing-inventory": guard + missing + end,
        "missing-diagnostics": guard + "test-inventory: aurora-test-context\n" + end,
        "wrong-prerequisite": guard + rule.replace("aurora-test-context", "unrelated") + end,
        "inventory-misrouted": guard + missing + "test-inventory: unrelated\n" + end,
        "diagnostics-misrouted": (
            guard + "test-inventory: aurora-test-context\ntest-iommu-diagnostics: unrelated\n" + end
        ),
        "comment-decoy": guard + missing + "# " + rule + end,
        "recipe-decoy": guard + missing + "\t" + rule + end,
        "assignment-decoy": guard + missing + "DECOY := " + rule + end,
        "outside-guard-decoy": guard + missing + end + rule,
        "wrong-guard": guard.replace("ifneq", "ifeq") + rule + end,
        "else-branch-decoy": guard + missing + "else\n" + rule + end,
        "define-body-decoy": guard + missing + "define DECOY\n" + rule + "endef\n" + end,
        "continued-recipe-decoy": guard + missing + "\t@echo \\\n" + rule + end,
    }
    nested = "define OUTER\ndefine INNER\nliteral text\nendef\n"
    valid += (guard + nested + "literal outer text\nendef\n" + rule + end,)
    invalid["nested-define-body-decoy"] = guard + nested + rule + "endef\n" + end
    prefixes = (
        "",
        "override ",
        "export ",
        "private ",
        "unexport ",
        "export override ",
        "private export ",
        "override private ",
        "export private override ",
    )
    for prefix in prefixes:
        definition = prefix + "define DECOY\n"
        name = prefix.strip().replace(" ", "-") or "bare"
        valid += (guard + definition + "literal text\nendef\n" + rule + end,)
        invalid["definition-only-" + name] = guard + definition + rule + "endef\n" + end
    for operator in ("=", ":=", "::=", "?=", "+="):
        definition = "define DECOY " + operator + "\n"
        valid += (guard + definition + "literal text\nendef\n" + rule + end,)
        invalid["definition-assignment-" + operator] = guard + definition + rule + "endef\n" + end
    invalid.update(
        {
            "unsupported-modified-nested-define": (
                guard + "define OUTER\nexport define INNER\ntext\nendef\n" + rule + "endef\n" + end
            ),
            "unsupported-define-name": guard + "define $(NAME)\ntext\nendef\n" + rule + end,
            "unsupported-define-modifier": guard + "unknown define DECOY\n" + rule + "endef\n" + end,
            "repeated-define-modifier": guard + "export export define DECOY\ntext\nendef\n" + rule + end,
            "conflicting-define-modifiers": guard + "export unexport define DECOY\ntext\nendef\n" + rule + end,
            "unmatched-endef": guard + rule + "endef\n" + end,
            "unclosed-nested-define": guard + nested + rule + end,
        }
    )
    return valid, invalid


def check_context_prerequisite_controls():
    valid, invalid = context_prerequisite_cases()
    for source in valid:
        check_context_prerequisites(source)
    for name, source in invalid.items():
        try:
            check_context_prerequisites(source)
        except ValueError:
            continue
        raise ValueError("Invalid guarded Make membership accepted: " + name)
    print(f"PASS guarded Make membership: {len(valid)} positive and {len(invalid)} negative controls")


def check_runtime_fixture_routes(source):
    # Only frozen IOMMU runtime fixtures are forbidden here. XFS native corpus
    # registrations are ordinary required tests, despite sharing the word fixtures.
    forbidden = ('iommu/fixtures/', 'frozen-import.py', 'transport-import-v1.py',
                 'command-stop-diagnostic.py')
    require(not any(name in source for name in forbidden), 'An IOMMU runtime fixture entered default test routing')



def check_integrity():
    manifest = json.loads((ROOT / "tools/qemu-amdvi/artifacts.json").read_text())["sha256"]
    expected_paths = {
        "tools/qemu-amdvi/patches/0001-event-record-transport.patch",
        "tools/qemu-amdvi/patches/0002-mode1-requester-permissions-v2.patch",
        "tools/qemu-amdvi/patches/0003-command-stop-v1.patch",
        "tests/iommu/fixtures/frozen-import.py",
        "tests/iommu/fixtures/transport-import-v1.py",
        "tests/iommu/fixtures/command-stop-diagnostic.py",
    }
    require(set(manifest) == expected_paths, "Expected three exact patches and three frozen diagnostic fixtures")
    for name, expected in manifest.items():
        path = ROOT / name
        require(path.is_relative_to(ROOT), "Artifact escaped repository")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "Artifact identity changed: " + name)
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=name)
        if path.suffix == ".patch":
            for line in path.read_text().splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    require(line == line.rstrip(), "Trailing whitespace in added source: " + name)
    frozen = ROOT / "tests/iommu/fixtures/frozen-import.py"
    require(
        hashlib.sha256(frozen.read_bytes()).hexdigest()
        == "a380e4792cd50417b457e638fdfeb6e3f5efd3b8126dcf8915a0c88ef0c27e28",
        "Historical 17-case fixture or expectations changed",
    )
    make = (ROOT / "Makefile").read_text()
    meson = (ROOT / "tests/meson.build").read_text()
    require("test: test-iommu-diagnostics\n" in make, "Root aggregate lost static diagnostics")
    check_context_prerequisites(make)
    require("files('iommu-diagnostics.py')" in meson, "Meson lost static diagnostics")
    check_runtime_fixture_routes(make + meson)
    check_runtime_fixture_routes("fixtures/xfs-root ../fixtures/xfs-offline/verify_native.py")
    for forbidden in ("tests/iommu/fixtures/unknown.py", "frozen-import.py",
                      "transport-import-v1.py", "command-stop-diagnostic.py"):
        try:
            check_runtime_fixture_routes(forbidden)
        except ValueError:
            pass
        else:
            raise ValueError("IOMMU runtime fixture routing rejection failed")
    require(not (frozen.parent / "TARGET-BINARY.json").exists(), "Runtime target must remain outside repository")
    print("PASS 6 exact artifacts and compiler-free routing; frozen 17-case expectations unchanged")


def check_patch_parser():
    spec = importlib.util.spec_from_file_location("iommu_patch_check", ROOT / "tools/qemu-amdvi/verify_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch = "--- a/a\n+++ b/a\n@@ -1,2 +1,2 @@\n one\n-two\n+three\n"
    inputs = {"a": b"one\ntwo\n"}
    require(module.apply_patch(inputs, patch) == {"a": b"one\nthree\n"}, "Valid patch was not reconstructed")
    require(inputs == {"a": b"one\ntwo\n"}, "Parser changed input mapping")
    for bad in (
        patch.replace("-two", "-wrong"),
        patch.replace("+1,2", "+2,2"),
        patch.replace("-1,2", "-1,3"),
        patch.replace("+++ b/a", "+++ b/other"),
    ):
        try:
            module.apply_patch(inputs, bad)
        except ValueError:
            continue
        raise ValueError("Malformed patch was accepted")
    print("PASS strict in-memory patch parser controls")


def main():
    check_integrity()
    check_context_prerequisite_controls()
    check_patch_parser()
    # Command mocks install a live process-denial audit hook. Access mocks add
    # another hook afterward. Neither invokes main() or a frozen Guest/case.
    for name in ("mock_command.py", "mock_access.py"):
        try:
            runpy.run_path(str(ROOT / "tests/iommu" / name), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
    print("PASS static/mock IOMMU diagnostics; no native, QEMU or physical-device qualification")


if __name__ == "__main__":
    main()
