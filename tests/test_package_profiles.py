#!/usr/bin/env python3
"""Compiler-free semantic selection, authority separation and full-corpus controls."""

import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/compiler"))
sys.path.insert(0, str(ROOT / "scripts"))
import package_identity as identity
import package_manifest as manifest
import package_graph as graph
from compiler_contract import ContractError
from package_profiles import (
    SelectedCompiler,
    developer_artifacts,
    finalize_selected_identity,
    add_identity_arguments,
    profile_record,
    select_cases,
    validate_identity_selection,
)

MODULES = (identity, manifest, graph)
FULL_REJECTIONS = (20, 29, 30)
DEV = ((183, 6048), (157, 13098), (187, 15029))


def cases(module, developer):
    if module is identity:
        groups = (
            module.developer_groups()
            if developer
            else (
                module.parsing_cases(),
                module.construction_cases(),
                module.comparison_cases(),
                module.ownership_cases(),
            )
        )
        return [case for group in groups for case in group]
    return (module.developer_cases() if developer else module.all_cases())[0]


def arguments(*values):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--freeze-reference")
    add_identity_arguments(parser)
    return parser.parse_args(values)


class Profiles(unittest.TestCase):
    def test_selected_counts_and_complete_safety_cases(self):
        for module, (count, observations), rejects in zip(MODULES, DEV, FULL_REJECTIONS):
            selected = cases(module, True)
            self.assertEqual(len(selected), count)
            self.assertEqual(sum(len(case.expected) for case in selected), observations)
            self.assertEqual(len(module.negative_cases()), rejects)
            names = [case.label for case in selected]
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all(case in selected for case in module.ownership_cases()))
            if module is not identity:
                self.assertTrue(all(case in selected for case in module.binding_cases()))
            record = profile_record(arguments("--profile", "dev"), selected, module.negative_cases())
            self.assertFalse(record["qualification_eligible"])
            self.assertEqual(record["selected_case_labels"], names)
            self.assertEqual(record["selected_rejection_labels"], [case[0] for case in module.negative_cases()])

    def test_semantic_status_and_shape_coverage(self):
        parsing = identity.developer_groups()[0]
        self.assertEqual({case.expected[0] for case in parsing}, {1, 2, 3})
        self.assertEqual(
            {case.expected[1] for case in identity.developer_groups()[2] if len(case.expected) == 2}, {0, 1, 2, 3}
        )
        selected = cases(graph, True)
        self.assertTrue(set(range(1, 9)).issubset({case.expected[0] for case in selected}))
        names = {case.label for case in selected}
        for shape in ("empty", "chain", "dense", "cycle", "disconnected-cycle", "diamond"):
            self.assertEqual(
                sum(name.startswith(f"adversarial/eight/{shape}/") for name in names),
                {"chain": 3, "dense": 3, "diamond": 4}.get(shape, 2),
            )
        self.assertEqual(sum(name.startswith("adversarial/precedence/") for name in names), 20)
        self.assertEqual(sum(name.startswith("adversarial/out-of-range-before-") for name in names), 5)
        for module in MODULES:
            with patch.object(
                module,
                "all_cases" if module is not identity else "comparison_cases",
                side_effect=AssertionError("unexpected full corpus"),
            ):
                if module is not identity:
                    module.developer_cases()
        with patch.object(graph, "exhaustive_cases", side_effect=AssertionError("exhaustive graphs generated")):
            graph.developer_cases()
        for module in (identity, manifest):
            original = module.parsing_cases
            with patch.object(module, "parsing_cases", wraps=original) as factory:
                cases(module, True)
                factory.assert_called_once_with(exhaustive=False)

    def test_selection_rejects_missing_and_duplicate_names(self):
        case = identity.parse_case("known", b"a@0.0.0")
        for inputs, keywords in (
            ([case], dict(labels=("missing",))),
            ([case], dict(prefixes=("missing/",))),
            ([case, case], dict(labels=("known",))),
        ):
            with self.assertRaises(ContractError):
                select_cases(inputs, **keywords)

    def test_out_of_tree_manifest_self_test(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest.self_test(temporary_parent=Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_meson_full_uses_safe_build_local_artifacts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            selected = arguments("--profile", "full", "--meson-selected-compiler")
            validate_identity_selection(selected)
            selected.artifact_root = Path(directory) / "output"
            self.assertEqual(developer_artifacts(selected, "identity"), selected.artifact_root)
            self.assertFalse(profile_record(selected, [], [])["qualification_eligible"])
            selected.artifact_root = Path(directory) / ".." / "escaped"
            with self.assertRaises(ContractError):
                developer_artifacts(selected, "identity")
            link = Path(directory) / "link"
            link.symlink_to(directory, target_is_directory=True)
            selected.artifact_root = link / "output"
            with self.assertRaises(ContractError):
                developer_artifacts(selected, "identity")

    def test_explicit_authority_separation(self):
        self.assertEqual(arguments().profile, "full")
        for values in (
            ("--developer-selected-compiler",),
            ("--profile", "dev", "--developer-selected-compiler", "--compiler-sha256", "a" * 64),
            ("--profile", "dev", "--developer-selected-compiler", "--smoke"),
            ("--profile", "dev", "--developer-selected-compiler", "--freeze-reference", "frozen"),
        ):
            with self.assertRaises(ContractError):
                validate_identity_selection(arguments(*values))
        selected = arguments("--profile", "dev", "--developer-selected-compiler")
        with patch.dict(os.environ, {}, clear=True):
            validate_identity_selection(selected)
            with self.assertRaises(ContractError):
                validate_identity_selection(arguments())
            validate_identity_selection(arguments("--compiler-sha256", "a" * 64))

    def test_selected_artifact_stability(self):
        with tempfile.TemporaryDirectory() as directory:
            compiler = Path(directory) / "compiler"
            compiler.write_bytes(b"observed artifact, never executed")
            compiler.chmod(0o700)
            selected = SelectedCompiler(compiler)
            self.assertIsNone(selected.record()["external_expected_sha256"])
            selected.verify()
            self.assertEqual(selected.record()["compiler_before"], selected.record()["compiler_after"])
            compiler.write_bytes(b"changed")
            with self.assertRaises(ContractError):
                selected.verify()
            report = {"status": "running"}
            self.assertTrue(finalize_selected_identity(selected, report))
            self.assertEqual(report["status"], "failed")
            self.assertNotEqual(
                report["compiler_identity"]["compiler_before"], report["compiler_identity"]["compiler_after"]
            )


if __name__ == "__main__":
    unittest.main()
