#!/usr/bin/env python3
"""Compiler-free semantic selection, authority separation and full-corpus controls."""

import argparse
from dataclasses import asdict
import hashlib
import json
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
    finalize_selected_identity,
    add_identity_arguments,
    profile_record,
    select_cases,
    validate_identity_selection,
)

MODULES = (identity, manifest, graph)
FULL = (
    (5503, 20, "96c5f134b951ca1a8e120f655e4cd778bbd4f2c16284f888a196e5f52b8adaea"),
    (20022, 29, "5f46d52299bc0a842f63b3dba956841fc846997d7acb176923cc6785fe80855a"),
    (5548, 30, "8c78779d2b53490c470c181282e50ea92d2af3838dbda00aa7b2e000706ffb6e"),
)
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
    def test_full_corpus_unchanged(self):
        # Captured from reviewed PR44; only owned-byte diagnostic wording was
        # refreshed after verifying the old digest with those strings restored.
        # Includes full-width expectations, source bodies/helpers/arguments,
        # every rejection diagnostic/source, and the complete shared observer.
        for module, (count, rejects, expected_hash) in zip(MODULES, FULL):
            selected = cases(module, False)
            self.assertEqual(len(selected), count)
            self.assertEqual(len(module.negative_cases()), rejects)
            digest = hashlib.sha256()
            for case in selected:
                digest.update(json.dumps(asdict(case), sort_keys=True, separators=(",", ":")).encode())
                digest.update(b"\n")
            digest.update(json.dumps(module.negative_cases(), separators=(",", ":")).encode())
            digest.update(module.shared().encode())
            self.assertEqual(digest.hexdigest(), expected_hash, module.__name__)

    def test_selected_counts_and_complete_safety_cases(self):
        for module, (count, observations), (_, rejects, _) in zip(MODULES, DEV, FULL):
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

    def test_explicit_authority_separation(self):
        self.assertEqual(arguments().profile, "full")
        for values in (
            ("--developer-selected-compiler",),
            ("--profile", "dev", "--developer-selected-compiler", "--compiler-sha256", "a" * 64),
            ("--profile", "dev", "--developer-selected-compiler", "--developer-build-receipt", "build.json"),
            ("--profile", "dev", "--developer-selected-compiler", "--smoke"),
            ("--profile", "dev", "--developer-selected-compiler", "--freeze-reference", "frozen"),
        ):
            with self.assertRaises(ContractError):
                validate_identity_selection(arguments(*values))
        selected = arguments("--profile", "dev", "--developer-selected-compiler")
        with patch.dict(os.environ, {"AURORA_TEST_CONTEXT": "aggregate.json"}):
            with self.assertRaises(ContractError):
                validate_identity_selection(selected)
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
