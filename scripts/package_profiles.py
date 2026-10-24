"""Observed compiler artifact stability; no build orchestration or qualification authority."""

import os
from pathlib import Path

from compiler_contract import ContractError, file_record


def require(condition, message):
    if not condition:
        raise ContractError(message)


class SelectedCompiler:
    """Observed artifact stability only. Meson/Ninja owns its build dependencies."""

    def __init__(self, compiler):
        self.compiler = Path(compiler).resolve(strict=True)
        require(os.access(self.compiler, os.X_OK), "executable compiler required")
        self.before = file_record(self.compiler)
        self.after = None
        self.sha256 = self.before["sha256"]
        self.expected = None

    def verify(self):
        self.after = file_record(self.compiler)
        require(self.before == self.after, "developer-selected compiler changed during gate")

    def record(self):
        return dict(
            mode="developer-selected",
            origin="developer-selected-artifact",
            observed_compiler_sha256=self.sha256,
            external_expected_sha256=None,
            compiler_before=self.before,
            compiler_after=self.after,
            assurance="Observed artifact stability only; no build provenance or qualification claim",
        )
