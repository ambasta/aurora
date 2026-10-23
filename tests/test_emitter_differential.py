#!/usr/bin/env python3
"""Compiler-free controls for shared, real-file corpus observations."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "compiler"))
import emitter_differential as differential


class BorrowAdapterEquivalenceTests(unittest.TestCase):
    NEW = b"""    pushq %rax
    movq -488(%rbp), %r10
    leaq 224(%r10), %rdi
    leaq -192(%rbp), %rsi
    subq $8, %rsp
    call __au_runtime_bytes_borrow_span
    addq $8, %rsp
    popq %rax
"""
    OLD = b"""    pushq %rax
    movq -488(%rbp), %r10
    leaq 224(%r10), %rdi
    subq $8, %rsp
    call __au_runtime_bytes_borrow_length
    addq $8, %rsp
    movq %rax, -144(%rbp)
    movq $1, -192(%rbp)
    movq -488(%rbp), %r10
    movq 224(%r10), %rcx
    movq %rcx, -184(%rbp)
    movq -488(%rbp), %r10
    movq 232(%r10), %rcx
    movq %rcx, -176(%rbp)
    movq -488(%rbp), %r10
    movq 240(%r10), %rcx
    movq %rcx, -168(%rbp)
    movq -488(%rbp), %r10
    movq 248(%r10), %rcx
    movq %rcx, -160(%rbp)
    movq $0, -152(%rbp)
    popq %rax
"""

    def test_exact_receiver_and_standalone_expansions(self):
        expanded, sites = differential.historical_borrow_expansion(self.NEW)
        self.assertEqual(expanded, self.OLD)
        self.assertEqual(sites, [dict(owner_offset=224, result_offset=-192, base="r10")])
        # Standalone case: no reload, no alignment shim, distinct local slots.
        new = self.NEW.replace(b"    movq -488(%rbp), %r10\n", b"").replace(b"224(%r10)", b"-64(%rbp)")
        old = self.OLD.replace(b"    movq -488(%rbp), %r10\n", b"")
        for old_offset, new_offset in ((224, -64), (232, -56), (240, -48), (248, -40)):
            old = old.replace(f"{old_offset}(%r10)".encode(), f"{new_offset}(%rbp)".encode())
        for shim in (b"    subq $8, %rsp\n", b"    addq $8, %rsp\n"):
            new, old = new.replace(shim, b""), old.replace(shim, b"")
        self.assertEqual(differential.historical_borrow_expansion(new)[0], old)

    def test_malformed_sequences_never_expand(self):
        changes = (
            (b"pushq %rax", b"pushq %rdx"),
            (b"popq %rax", b"popq %rdx"),
            (b"    addq $8, %rsp\n", b""),
            (b"    subq $8, %rsp\n", b""),
            (b"-192(%rbp), %rsi", b"-193(%rbp), %rsi"),
            (b"-192(%rbp), %rsi", b"-48(%rbp), %rsi"),
            (b"224(%r10)", b"225(%r10)"),
            (b"    movq -488(%rbp), %r10\n", b""),
            (b"%rsi\n", b"%rdx\n"),
        )
        for before, after in changes:
            with self.subTest(change=(before, after)):
                self.assertEqual(differential.historical_borrow_expansion(self.NEW.replace(before, after)), (None, []))

    def test_only_historical_edge_and_exact_other_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            for label, assembly, callee in (("old", self.OLD, "borrow_length"), ("new", self.NEW, "borrow_span")):
                output = case / label / "outputs"
                output.mkdir(parents=True)
                (output / "assembly.s").write_bytes(assembly)
                (output / "stack.json").write_text('{"__au_runtime_bytes_' + callee + '":160}')
                (output / "abi.json").write_text("unchanged ABI\n")
            self.assertTrue(differential.historical_borrow_equivalence(case, ("old", "new")))
            self.assertFalse(differential.historical_borrow_equivalence(case, ("c1", "new")))
            output = case / "new/outputs"
            for name in ("assembly.s", "stack.json", "abi.json"):
                before = (output / name).read_bytes()
                (output / name).write_bytes(before + b" ")
                self.assertFalse(differential.historical_borrow_equivalence(case, ("old", "new")))
                (output / name).write_bytes(before)

    def test_unrelated_bytes_remain_literal(self):
        expanded, _ = differential.historical_borrow_expansion(b"unrelated\n" + self.NEW + b"suffix\n")
        self.assertEqual(expanded, b"unrelated\n" + self.OLD + b"suffix\n")


class ClosedProfileSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="emitter-profile-control-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in (*differential.SOURCE_ROOTS, "runtime", "scripts"):
            (self.root / name).mkdir()
        for name in ("meson.build", "meson_options.txt", "compiler/x86_module.au", "scripts/frontend_bridge.py"):
            (self.root / name).write_text("fixture\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "comparison baseline")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *arguments):
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                *arguments,
            ],
            text=True,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        )

    def required(self, base=None):
        return differential.closed_profile_required(self.root, self.base if base is None else base)[0]

    def test_missing_base_never_infers_head(self):
        with patch.object(differential.subprocess, "run", side_effect=AssertionError("unexpected Git query")):
            self.assertTrue(self.required(""))

    def test_unchanged_and_documentation_only_skip(self):
        self.assertFalse(self.required())
        (self.root / "README.md").write_text("documentation change")
        self.assertFalse(self.required())

    def test_native_kernel_only_skips(self):
        (self.root / "kernel/runtime.cpp").write_text("native-only fixture")
        self.assertFalse(self.required())

    def test_relevant_and_unknown_untracked_inputs_run(self):
        for name in (
            "compiler/abi.hpp",
            "scripts/generator.py",
            "library/helper.au",
            "kernel/input.au",
            "tests/selector.py",
            "runtime/adapter.hpp",
            "tool-options.json",
        ):
            with self.subTest(path=name):
                path = self.root / name
                path.write_text("relevant fixture")
                self.assertTrue(self.required())
                path.unlink()

    def test_dirty_tracked_emitter_runs(self):
        (self.root / "compiler/x86_module.au").write_text("changed emitter")
        self.assertTrue(self.required())

    def test_ignored_au_imports_run_but_ignored_build_outputs_do_not(self):
        (self.root / ".git/info/exclude").write_text("*.au\n")
        (self.root / "build").mkdir()
        (self.root / "build/generated.au").write_text("retained output")
        self.assertFalse(self.required())
        for root in (*differential.SOURCE_ROOTS, "runtime", "scripts"):
            with self.subTest(root=root):
                path = self.root / root / "shadow.au"
                path.write_text("ignored import")
                self.assertTrue(self.required())
                path.unlink()

    def test_staged_generator_runs(self):
        (self.root / "scripts/frontend_bridge.py").write_text("changed generator")
        self.git("add", "scripts/frontend_bridge.py")
        self.assertTrue(self.required())

    def test_options_change_runs(self):
        (self.root / "meson_options.txt").write_text("changed options")
        self.assertTrue(self.required())

    def test_committed_change_uses_explicit_base_not_head_parent(self):
        (self.root / "compiler/x86_module.au").write_text("changed emitter")
        self.git("commit", "-qam", "emitter change")
        (self.root / "README.md").write_text("later documentation")
        self.git("add", "README.md")
        self.git("commit", "-qm", "later documentation")
        self.assertTrue(self.required())

    def test_invalid_and_ambiguous_bases_run(self):
        self.assertTrue(self.required("missing-comparison-base"))
        self.git("branch", "ambiguous")
        self.git("tag", "ambiguous")
        self.assertTrue(self.required("ambiguous"))

    def test_unsupported_layout_runs(self):
        (self.root / "compiler/x86_module.au").unlink()
        self.assertTrue(self.required())

    def test_hidden_index_changes_run(self):
        self.git("update-index", "--assume-unchanged", "compiler/x86_module.au")
        (self.root / "compiler/x86_module.au").write_text("hidden emitter edit")
        self.assertTrue(self.required())

    def test_source_symlink_runs(self):
        (self.root / "compiler/indirect.au").symlink_to("x86_module.au")
        self.git("add", "compiler/indirect.au")
        self.git("commit", "-qm", "unsupported source symlink")
        self.assertTrue(self.required(self.git("rev-parse", "HEAD").strip()))

    def test_git_failure_runs(self):
        with patch.object(differential.subprocess, "run", side_effect=OSError("git unavailable")):
            self.assertTrue(self.required())

    def test_skip_does_not_launch_profile(self):
        with patch.object(differential.os, "execvp", side_effect=AssertionError("unexpected compiler work")):
            self.assertEqual(
                differential.selected_closed_profile(
                    ["--source-root", str(self.root), "--comparison-base=" + self.base, "--", "selected-command"]
                ),
                77,
            )

    def test_required_profile_replaces_selector_with_guarded_command(self):
        class ReplacedProcess(Exception):
            pass

        with patch.object(differential.os, "execvp", side_effect=ReplacedProcess) as called:
            with self.assertRaises(ReplacedProcess):
                differential.selected_closed_profile(
                    ["--source-root", str(self.root), "--comparison-base=-invalid", "--", "selected-command", "arg"]
                )
        called.assert_called_once_with("selected-command", ["selected-command", "arg"])


class SharedObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="corpus-observation-control-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case = self.root / "case.au"
        self.case.mkdir()
        self.compilers = {name: Path(name) for name in ("old", "c1", "new")}
        self.arguments = []
        for option, name in zip(("-o", "--stack-facts", "--abi-facts"), differential.OUTPUTS, strict=True):
            self.arguments.extend((option, str(self.case / "invocation" / name)))
        self.commands = []
        self.statuses = {}
        self.changed = {}
        self.in_place = set()

    def compiler_observation(self, command, stdout, *, stderr, **kwargs):
        """Produce controlled output files without launching any compiler."""
        self.commands.append(command)
        label = command[0]
        status = self.statuses.get(label, 0)
        for name, stream in (("stdout.bin", stdout), ("stderr.bin", stderr)):
            default = (
                b"fixture.au:1:1: error AU1001: unsupported syntax\n" if status == 1 and name == "stderr.bin" else b""
            )
            stream.write(self.changed.get((label, name), default))
        if status == 0:
            for name in differential.OUTPUTS:
                output = self.case / "invocation" / name
                content = self.changed.get((label, name), ("emitted " + name + "\n").encode())
                if (label, name) in self.in_place:
                    output.write_bytes(content)
                else:
                    temporary = output.with_suffix(".replacement")
                    temporary.write_bytes(content)
                    os.replace(temporary, output)
        return status

    def observe(self, *, historical=True, must_accept=True, current_convergence=True):
        with patch.object(differential, "run_logged", side_effect=self.compiler_observation):
            return differential.observe_case(
                self.case,
                self.compilers,
                self.arguments,
                self.root,
                30,
                historical=historical,
                must_accept=must_accept,
                current_convergence=current_convergence,
            )

    def test_default_observes_each_role_once_and_shares_c2_files(self):
        runs, comparisons, problems = self.observe()
        self.assertFalse(problems)
        self.assertEqual(list(runs), ["old", "c1", "new"])
        self.assertEqual([row["compilers"] for row in comparisons], [["old", "new"], ["c1", "new"]])
        self.assertEqual([command[0] for command in self.commands], ["old", "c1", "new"])
        self.assertTrue(all(command[1:] == self.arguments for command in self.commands))
        for label in runs:
            for name in differential.OUTPUTS:
                self.assertTrue((self.case / label / "outputs" / name).is_file())
            self.assertTrue((self.case / label / "run.json").is_file())

    def test_closed_historical_profile_keeps_independent_observations(self):
        self.arguments[:0] = ["--local-symbols", "--referenced-reflection-only"]
        runs, comparisons, problems = self.observe(current_convergence=False)
        self.assertFalse(problems)
        self.assertEqual(list(runs), ["old", "new"])
        self.assertEqual([row["compilers"] for row in comparisons], [["old", "new"]])
        self.assertEqual([command[0] for command in self.commands], ["old", "new"])
        self.assertTrue(all(command[1:3] == self.arguments[:2] for command in self.commands))

    def test_second_consumer_reads_shared_files_and_detects_intervening_corruption(self):
        original_compare = differential.compare
        consumers = []

        def compare_then_corrupt(case, runs, must_accept, labels):
            problems = original_compare(case, runs, must_accept, labels)
            consumers.append((labels, list(problems), len(self.commands)))
            if labels == ("old", "new"):
                (case / "new/outputs/assembly.s").write_bytes(b"corrupted shared assembly\n")
            return problems

        with patch.object(differential, "compare", side_effect=compare_then_corrupt):
            _, _, problems = self.observe()
        self.assertEqual(consumers[0], (("old", "new"), [], 3))
        self.assertEqual(consumers[1], (("c1", "new"), ["assembly.s differs byte-for-byte"], 3))
        self.assertEqual(problems, ["c1/new: assembly.s differs byte-for-byte"])

    def test_existing_observations_cannot_be_reused_for_another_request(self):
        self.observe()
        original_arguments, original_compilers = list(self.arguments), dict(self.compilers)
        for change in ("unchanged", "input", "profile", "compiler"):
            with self.subTest(change=change):
                self.arguments, self.compilers = list(original_arguments), dict(original_compilers)
                if change == "input":
                    self.arguments.insert(0, "different-input.au")
                elif change == "profile":
                    self.arguments.insert(0, "--local-symbols")
                elif change == "compiler":
                    self.compilers["c1"] = Path("different-compiler")
                with self.assertRaises(FileExistsError):
                    self.observe()
                self.assertEqual(len(self.commands), 3)

        # A fresh request is observed again, never filled from prior observations.
        original_case = self.case
        self.case = self.root / "fresh-case.au"
        self.case.mkdir()
        self.arguments = [argument.replace(str(original_case), str(self.case)) for argument in original_arguments]
        _, _, problems = self.observe()
        self.assertFalse(problems)
        self.assertEqual([command[0] for command in self.commands[3:]], ["old", "different-compiler", "new"])

    def test_later_consumer_requires_old_rejection_and_current_convergence(self):
        self.statuses["old"] = 1
        runs, comparisons, problems = self.observe(historical=False, current_convergence=False)
        self.assertFalse(problems)
        self.assertEqual(list(runs), ["old", "c1", "new"])
        self.assertEqual([row["compilers"] for row in comparisons], [["c1", "new"]])
        self.assertTrue((self.case / "oracle-membership.json").is_file())
        for name in differential.OUTPUTS:
            self.assertEqual((self.case / "old/outputs" / name).read_bytes(), differential.SENTINELS[name])

    def test_unlisted_acceptance_fails_before_current_compilers(self):
        with self.assertRaisesRegex(ValueError, "oracle accepted unlisted"):
            self.observe(historical=False)
        self.assertEqual([command[0] for command in self.commands], ["old"])

    def test_unlisted_internal_diagnostic_is_not_unsupported_evidence(self):
        self.statuses["old"] = 1
        self.changed["old", "stderr.bin"] = b"fixture.au:1:1: error AU9001: internal failure\n"
        with self.assertRaisesRegex(ValueError, "internal compiler diagnostic"):
            self.observe(historical=False)
        self.assertEqual(len(self.commands), 1)

    def test_each_current_output_and_diagnostic_mismatch_is_detected(self):
        for name in (*differential.OUTPUTS, "stdout.bin", "stderr.bin"):
            with self.subTest(name=name), tempfile.TemporaryDirectory(dir=self.root) as directory:
                self.case = Path(directory) / "case.au"
                self.case.mkdir()
                self.arguments = [
                    argument
                    for option, output in zip(("-o", "--stack-facts", "--abi-facts"), differential.OUTPUTS, strict=True)
                    for argument in (option, str(self.case / "invocation" / output))
                ]
                self.changed = {("c1", name): b"different current C1 bytes\n"}
                _, comparisons, problems = self.observe()
                self.assertFalse(comparisons[0]["problems"])
                self.assertTrue(any("c1/new: " + name + " differs byte-for-byte" == item for item in problems))

    def test_current_rejection_cannot_pass_on_historical_success(self):
        self.statuses["c1"] = 1
        _, comparisons, problems = self.observe()
        self.assertFalse(comparisons[0]["problems"])
        self.assertTrue(any("required compiler/library module rejected" in item for item in problems))

    def test_vocabulary_rejection_still_compares_all_current_outputs(self):
        self.statuses = {label: 1 for label in self.compilers}
        _, comparisons, problems = self.observe(must_accept=False)
        self.assertFalse(problems)
        self.assertEqual(len(comparisons), 2)

    def test_current_success_must_replace_output_inode(self):
        self.in_place.add(("c1", "stack.json"))
        _, comparisons, problems = self.observe()
        self.assertFalse(comparisons[0]["problems"])
        self.assertTrue(any("c1: successful compilation did not replace stack.json" in item for item in problems))

    def test_rejected_output_metadata_mutation_is_detected(self):
        self.statuses = {label: 1 for label in self.compilers}
        original = self.compiler_observation

        def changed_metadata(command, *args, **kwargs):
            status = original(command, *args, **kwargs)
            if command[0] == "c1":
                os.utime(self.case / "invocation/abi.json", ns=(1_000_000_000, 1_000_000_000))
            return status

        with patch.object(self, "compiler_observation", side_effect=changed_metadata):
            _, comparisons, problems = self.observe(must_accept=False)
        self.assertFalse(comparisons[0]["problems"])
        self.assertTrue(any("c1: rejected compilation changed abi.json" in item for item in problems))


if __name__ == "__main__":
    if shutil.which("git") is not None:
        unittest.main()
    # The selector itself fails closed without Git and always runs the closed
    # profile; its controls need a real repository. Run the rest, then report SKIP.
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromTestCase(case)
        for case in (BorrowAdapterEquivalenceTests, SharedObservationTests)
    )
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        sys.exit(1)
    print("SKIP: git is unavailable; closed-profile selector controls were not run")
    sys.exit(77)
