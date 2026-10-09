#!/usr/bin/env python3
"""Compiler-free controls for explicitly observed Meson artifact identity."""
import argparse
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compiler_contract as contract
import meson_toolchain
import meson_test


class MesonIdentityTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(compiler_sha256=None, developer_build_receipt=None, meson_selected_compiler=True)
        values.update(changes)
        return argparse.Namespace(**values)

    def test_no_external_pin_or_fresh_build_claim(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            path = Path(tmp) / 'fixture'
            path.write_text('synthetic executable bytes; never invoked')
            path.chmod(0o755)
            identity = contract.resolve_identity(self.args(), path, tmp)
            self.assertIsNone(identity.expected)
            self.assertEqual(identity.record()['origin'], 'meson-selected-artifact')
            self.assertIsNone(identity.record()['external_expected_sha256'])
            identity.verify()
            path.write_text('changed bytes')
            with self.assertRaises(contract.ContractError):
                identity.verify()

    def test_conflicting_identity_modes_rejected(self):
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(compiler_sha256='0' * 64))
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(developer_build_receipt=Path('/not-read')))

    def test_no_legacy_context_bypass(self):
        with patch.dict(os.environ, {'AURORA_TEST_CONTEXT': '/not-read'}):
            with self.assertRaises(contract.ContractError):
                contract.validate_identity_selection(self.args())

    def test_missing_identity_still_rejected(self):
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(meson_selected_compiler=False))

    def test_toolchain_replacement_rejected(self):
        first = dict(files={'/compiler': 'old'}, version='14')
        meson_toolchain.verify(first, first.copy())
        with self.assertRaises(ValueError):
            meson_toolchain.verify(first, dict(files={'/compiler': 'new'}, version='14'))

    def test_implicit_search_variables_rejected_before_tool_queries(self):
        for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
            for value in ('', '/one:/two'):
                with self.subTest(name=name, value=value), \
                        patch.dict(os.environ, {name: value}, clear=True), \
                        patch.object(meson_toolchain.subprocess, 'check_output') as query:
                    with self.assertRaisesRegex(ValueError, 'Unset ' + name):
                        meson_toolchain.snapshot(['never-executed'])
                    query.assert_not_called()

    def test_absent_search_variables_bind_policy_and_reject_legacy_record(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            tool = Path(tmp) / 'synthetic-tool'
            tool.write_text('compiler-free fingerprint fixture')
            def query(command, **kwargs):
                return {'-dumpfullversion': '14.2.0', '-dumpmachine': 'x86_64-linux-gnu'}.get(
                    command[-1], str(tool))
            with patch.object(meson_toolchain.shutil, 'which', return_value=str(tool)), \
                    patch.object(meson_toolchain.subprocess, 'check_output', side_effect=query):
                observed = meson_toolchain.snapshot([str(tool)])
            self.assertEqual(observed['search_policy'], 'explicit-meson-flags-v1')
            meson_toolchain.verify(observed, observed.copy())
            legacy = {key: value for key, value in observed.items() if key != 'search_policy'}
            with self.assertRaises(ValueError):
                meson_toolchain.verify(legacy, observed)

    def test_direct_meson_guard_rejects_before_creating_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / 'aurora-toolchain.json'
            argv = ['meson_toolchain.py', '--configure', '--cxx', 'never-executed',
                    '--record', str(record)]
            for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
                with self.subTest(name=name), patch.dict(os.environ, {name: ''}, clear=True), \
                        patch.object(sys, 'argv', argv), \
                        patch.object(meson_toolchain.subprocess, 'check_output') as query:
                    with self.assertRaisesRegex(ValueError, 'Unset ' + name):
                        meson_toolchain.main()
                    query.assert_not_called()
                    self.assertFalse(record.exists())

    def test_make_convenience_rejects_before_meson_or_build_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
                with self.subTest(name=name), \
                        patch.dict(os.environ, {name: '/one:/two'}, clear=True), \
                        patch.object(contract, 'tool_record', return_value={
                            'resolved': '/synthetic/compiler', 'sha256': '0' * 64}), \
                        patch.object(contract, 'query', return_value='14.2.0'), \
                        patch.object(meson_test.subprocess, 'run') as launch:
                    with self.assertRaisesRegex(ValueError, 'Unset ' + name):
                        meson_test.execute(root, 'full')
                    launch.assert_not_called()
                    self.assertFalse((root / 'build').exists())

    def test_cli_modes_are_exclusive(self):
        parser = argparse.ArgumentParser()
        contract.add_identity_arguments(parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(['--meson-selected-compiler', '--compiler-sha256', '0' * 64])


if __name__ == '__main__':
    unittest.main()
