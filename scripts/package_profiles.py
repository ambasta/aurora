"""Explicit partial package profiles; no build orchestration or qualification authority."""

import os
from pathlib import Path
import tempfile

from compiler_contract import (
    ContractError,
    add_identity_arguments as add_contract_arguments,
    file_record,
    resolve_identity as resolve_contract_identity,
    validate_identity_selection as validate_contract_selection,
)


def require(condition, message):
    if not condition:
        raise ContractError(message)


def add_identity_arguments(parser):
    add_contract_arguments(parser)
    parser.add_argument(
        "--profile",
        choices=("full", "dev"),
        default="full",
        help="dev selects named semantic cases; partial coverage, never qualification",
    )
    parser.add_argument(
        "--developer-selected-compiler",
        action="store_true",
        help="observe an already built compiler for --profile dev; no build or external pin claim",
    )


def validate_identity_selection(args, preflight=False):
    if args.profile == "dev":
        require(not args.smoke, "--profile dev and --quick/--smoke are mutually exclusive")
        require(not getattr(args, "freeze_reference", None), "reference freezing requires the full profile")
        require(not os.environ.get("AURORA_TEST_CONTEXT"), "partial dev profile cannot enter an aggregate context")
    if args.developer_selected_compiler:
        require(args.profile == "dev", "developer-selected compiler requires --profile dev")
        require(
            args.compiler_sha256 is None and args.developer_build_receipt is None,
            "developer-selected compiler cannot claim a pin or fresh-build receipt",
        )
    else:
        validate_contract_selection(args, preflight=preflight)


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


def resolve_identity(args, compiler, repo_root):
    validate_identity_selection(args)
    if args.developer_selected_compiler:
        return SelectedCompiler(compiler)
    return resolve_contract_identity(args, compiler, repo_root)


def finalize_selected_identity(identity, report):
    # Refresh failed-run observations without hiding the primary native error.
    # Existing pin/build-receipt verification is unchanged.
    if not isinstance(identity, SelectedCompiler):
        return []
    errors = []
    try:
        identity.verify()
    except Exception as exc:
        errors.append("developer-selected compiler final identity: " + str(exc))
        report.update(status="failed", compiler_identity_error=str(exc))
    report["compiler_identity"] = identity.record()
    return errors


def developer_artifacts(args, family):
    # A unique invocation directory beneath Meson's build-local TMPDIR. Never
    # clean a shared parent or write generated products into the source tree.
    value = args.artifact_root or Path(tempfile.gettempdir()) / f"package-{family}-dev-{os.getpid()}"
    raw = Path(value).absolute()
    require(".." not in raw.parts, "artifact path traversal denied")
    require(not any(path.is_symlink() for path in (raw, *raw.parents)), "symlink output root denied")
    return raw.resolve(strict=False)


def select_cases(cases, *, labels=(), prefixes=()):
    """Fail closed when a required semantic label disappears or is ambiguous."""
    chosen = [case for case in cases if case.label in labels or case.label.startswith(tuple(prefixes))]
    names = [case.label for case in chosen]
    require(len(names) == len(set(names)), "duplicate selected case label")
    require(set(labels).issubset(names), "missing selected labels: " + repr(sorted(set(labels) - set(names))))
    for prefix in prefixes:
        require(any(name.startswith(prefix) for name in names), "missing selected case family: " + prefix)
    return chosen


def profile_record(args, cases, rejections):
    partial = args.profile == "dev" or args.smoke
    return dict(
        profile="legacy-smoke" if args.smoke else args.profile,
        coverage="partial developer feedback" if partial else "complete package corpus",
        qualification_eligible=not partial,
        selected_case_labels=[case.label for case in cases],
        selected_rejection_labels=[case[0] for case in rejections],
    )
