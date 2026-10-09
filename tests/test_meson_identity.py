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

    def test_cli_modes_are_exclusive(self):
        parser = argparse.ArgumentParser()
        contract.add_identity_arguments(parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(['--meson-selected-compiler', '--compiler-sha256', '0' * 64])


if __name__ == '__main__':
    unittest.main()
