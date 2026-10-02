# Implementation review record

The milestone-zero section below is a historical snapshot; the later milestone-one section records extensions and supersedes the earlier feature inventory.

## Milestone zero

This review covers the scalar compiler and disposable x86-64 BIOS/QEMU bootstrap in this source tree. It is a bounded implementation review, not a security certification or proof of language soundness. No physical disk or host bootloader was modified.

## Verified findings and corrections

1. **Decimal literal miscompilation.** The original emitter copied source text directly into GNU assembly: `010` executed as octal 8, while `08` was accepted by the compiler and rejected by the assembler. The emitter now normalizes parsed decimal values. The suite includes leading-zero values and compile-time/runtime agreement regressions; all pass.
2. **Smoke-test false positive.** A simulated emulator that printed both `AURORA_BOOT_OK` and `AURORA_BOOT_FAIL`, then exited 33, originally passed. Bash exempts a command under `!` from `set -e`. The script now uses an explicit shared transcript validator that rejects a failure marker. Independently exercised negative controls reject a wrong exit status, a missing success marker, and contradictory success/failure markers. Its permanent self-test passes one success case and eight failure cases, including under Python optimization.
3. **Validation robustness.** Image and compiler rejection checks now use explicit failures rather than Python assertions, preserving checks under `PYTHONOPTIMIZE=1`. Image validation checks ELF class, endianness, machine, executable type, and exact entry address. Both test paths were rerun with Python optimization enabled.

## Executed checks

- Compiler build with `-Wall -Wextra -Wpedantic -Werror` succeeded.
- `make -C compiler test`: 75 tests passed, including positive execution, ownership/type rejection, reflection, branch joins, decimal regression, and arithmetic differential cases. The same suite passed with `PYTHONOPTIMIZE=1`.
- Independent temporary programs exercised branch-return move exclusion, mutable-borrow scope release, owner shadowing, use after a conditional move, movement while borrowed, owner reads during an exclusive borrow, and lexical reference escape. Expected executable results and rejection diagnostics were observed.
- An independent host bridge checked an exact 64-bit result of 1,100,173 through nested six-argument calls, arithmetic temporaries, and signed subtraction, plus a Boolean return. This supplements the repository's assembly-only bridge tests; it does not establish a supported foreign ABI.
- Image validation passed with six malformed-image negative controls and a 970-byte kernel payload within the loader's 32 KiB budget.
- Real QEMU software-emulated boot passed after the fixes: BIOS transport, long-mode entry, emitted Aurora code returning 42, serial success marker, and debug-exit status 33. QEMU was supplied from a temporary local installation using `QEMU`, `QEMU_DATA`, and `LD_LIBRARY_PATH`; it was not on the default PATH.
- Reviewed the stack alignment/call sequence, preserved frame pointer, BSS clearing, fixed loader bounds, paging-table setup, and branch ownership-state restoration against this small target.

## Limits and remaining work

Supported scalar arithmetic intentionally wraps modulo 2^64; checked-default arithmetic is a future design objective. The compiler does not implement division, indexing, pointers, heap allocation, general classes, destructors, borrow-carrying function signatures, concurrency, or reflective invocation. These tests do not imply Rust-equivalent safety. Malformed-input fuzzing, compiler resource limits, richer lifetime proofs, cross-backend validation, and adversarial runtime testing remain future work.

The kernel has no interrupts, scheduler, user mode, process isolation, IOMMU policy, W^X enforcement, production drivers, or general hardware support. Its writable/executable identity map and trusted C++/assembly bootstrap are explicitly temporary. Boot success demonstrates a small end-to-end executable milestone, not a complete operating system or production readiness.


## Milestone one: local classes and kernel foundations

### Class compiler checks

The final compiler suite passed **116 tests**, also with `PYTHONOPTIMIZE=1`. Eleven additional independent programs covered copy isolation under separate mutations, shadow construction from an outer binding, conditional local storage, initializer side-effect order and value snapshots, nine-field layout with nested function calls, Boolean mutation typing, invalid scalar-to-class copying, unsupported aggregate assignment, expired local field access, and runtime/static metadata boundaries. All returned the expected values or rejection diagnostics.

Classes currently contain scalar fields only and exist as local stack values. Each field occupies an eight-byte slot; even an empty class reserves eight bytes. Copies have independent storage. The reviewed initializer evaluates named expressions in written order before storing their results in declaration-order slots. Reflection identifies classes and reports their size/field count; this is not general reflective field inspection or method invocation. Class IDs are declaration-order IDs within this compilation, not a persistent schema identity.

Two minor grammar issues found during review were corrected with regression tests: adjacent `own<i64>=...` initialization and parenthesized field access `(p).x`. No class-layout or copy-aliasing defect was found in the tested subset. This does not prove general aggregate ownership soundness: classes still cannot contain owners or references, appear in function signatures, or escape their lexical frame.

### Kernel checks

Independently executed real QEMU normal boot now passes the firmware memory-map gate, physical-page tests, language result, and success exit. A separate fault build intentionally divides by zero and passes only on vector-0/error-0 diagnostics and failure exit 35. The fault script restores a normal build afterward. A second fault build injected a page fault and passed on vector-14/error-0 diagnostics and failure exit 35, exercising a CPU-pushed error-code frame. The final smoke validators passed three positive and seventeen negative transcripts under Python optimization.

The breakpoint recovery probe loads distinct values into all fifteen general-purpose registers other than RSP, sets the direction flag, executes `int3`, and verifies register and direction-flag restoration. Its QEMU execution passed. Code review checked the common stub's vector/error/RIP offsets, sixteen-byte call alignment, saved registers, and `iretq` return. The page-fault run exercised one hardware-error-code exception path. Other exception vectors, stack exhaustion/double faults, nested interrupts, privilege transitions, SIMD preservation, external interrupts, and SMP were not exercised.

The allocator passed an independent host test under AddressSanitizer and UndefinedBehaviorSanitizer, checking 128 unique aligned frames, exhaustion, invalid ranges, moves, foreign-owner rejection, release/reuse, retired-lease rejection, double frees, and cleanup. LeakSanitizer could not operate under the execution environment's ptrace restriction, so leak detection was disabled; this is not a LeakSanitizer pass. The repository's permanent host allocator test additionally passed 10,000 deterministic state transitions with accounting and pairwise non-alias checks. In-guest testing wrote all bytes of each allocated frame and checked boundary contents before release.

### Review findings and explicit boundaries

- Malformed E820 continuation results previously retained a partial map after a bad signature or short entry. The boot path now invalidates the map in those cases, matching its existing over-capacity rejection. This correction was verified by code-path inspection and subsequent ordinary QEMU boot; malformed firmware itself was not injected. Firmware carry-flag termination remains a distinct transport convention.
- An independently reproduced allocator-instance bug allowed trusted C++ code to destroy an allocator while a lease survived, reconstruct an allocator at the same address, and match the old lease against a newly allocated frame. The implementation now embeds a monotonically unique allocator epoch in each lease and refuses initialization on epoch exhaustion. The original reproduction now rejects the stale lease and preserves the current allocation; the permanent suite includes a same-address reconstruction regression. This is a single-CPU identity mechanism, not a concurrency-safe or persistent-handle design. A lease's `valid()` method only describes whether it has been moved/released; authoritative ownership still requires the allocator's checked address/release operations.

This milestone adds local class values, an IDT/exception bring-up path, firmware range checking, and a small single-CPU page allocator. It remains far short of a self-hosting operating-system stack. No physical AMD Zen CPU family or Navi-or-later GPU was tested; QEMU execution does not demonstrate support for any physical device family. There is still no user-mode isolation, general scheduling, production driver stack, GPU support, complete reflection, or established Rust-equivalent safety guarantee.

## Milestone two: restricted C++ surface, checked execution, protected bootstrap

This section describes the current reviewed revision. Earlier sections are historical evidence for earlier revisions: in particular, their `fn`/`let` grammar, wrapping arithmetic, and writable/executable bootstrap mapping no longer describe current source or post-activation behavior. The new surface deliberately breaks those earlier spellings; it is still a small restricted dialect, not complete ISO C++ or a self-hosting compiler.

### Compiler verification

The current repository suite passed **203 tests**, including with `PYTHONOPTIMIZE=1`. Thirty-four independent cases additionally exercised nested zero-iteration loops, rejecting a moved owner on a continuing nested backedge, mixed return/backedge ownership paths, lexical borrow/shadow cleanup, three independent array copies, single index evaluation, index preservation across a six-argument RHS call, signed bounds, arithmetic overflow before index address computation, arithmetic boundary values, const-array rejection, obsolete aggregate syntax rejection, and twenty loop/array differential programs.

Five independent signal-handler probes checked that the actual SIGILL instruction address matched the intended generated bounds or overflow label and that its bytes encoded UD2. These covered a negative-index read, upper-bound store, addition overflow, minimum-integer negation, and overflow within an index expression. This strengthens the suite's signal/assembly checks; it is still targeted execution evidence rather than a proof over all generated programs.

The current surface uses `auto name(type parameter) -> result`, typed initialized locals, `const`, class visibility, and designated named initialization. Obsolete `fn`/`let`, raw pointers, C-style declarations, and an `unsafe` block escape are rejected in the tested grammar. Private fields cannot currently be constructed through this limited aggregate API. Reflection filters field counts by public visibility. Supported signed arithmetic now traps on overflow rather than wrapping.

Fixed scalar arrays copy their values, do not expose element references, and check unsigned index bounds before computing an address; this also rejects negative signed indices. Stores evaluate/check the index before evaluating the RHS. Array lengths are restricted to 1–4096 and local frame storage is capped at 65536 bytes. That frame cap is not a bound on total runtime stack use: temporary expression/initializer pushes and recursive calls also consume stack. Loops conservatively preserve outer ownership/borrow state at every continuing backedge, while allowing ownership-consuming paths that return. They may execute zero times; a loop alone does not establish a function's return completeness.

### Kernel verification

Independently ran **all thirteen protected-bootstrap QEMU modes**: normal operation; divide and unmapped-page faults; supervisor text-write and data-execute denials; kernel stack-guard exhaustion leading to double-fault IST; missing-NX rejection; and six ring-3 denial probes. The observed CPU fault results were:

- Supervisor text write: page fault, error 3.
- Supervisor data execution: page fault, error 17.
- Stack guard: double fault, error 0, on the configured emergency IST stack.
- User kernel read/write: page faults, errors 5 and 7.
- User code write: page fault, error 7.
- User stack execution: page fault, error 21.
- User CLI and port I/O: general-protection fault, error 0.

The validators also check expected origin privilege, denied address/CR2, fault instruction where relevant, TSS entry-stack range, and fail-stop exit. Normal operation verifies a controlled ring-3 payload using its own stack, followed by the narrow authorized return to the saved kernel continuation. NX-disabled emulation fails before reporting protected mapping activation. The transcript validator's **thirteen positive and eighty-nine negative controls** passed with Python optimization enabled.

Code review checked the default-absent four-KiB identity map, RX text, R/NX constants, RW/NX data and stacks, leaf user-access restrictions, NXE and supervisor write protection, guarded main/entry/emergency/user stack ranges, TSS RSP0 and IST1 encoding, explicit I/O denial, saved general-register frame offsets, and protected saved-kernel-stack continuation. The old writable/executable bootstrap map exists transiently before protection activation and is not a production boot-security design.

The permanent host protection test passed **511 mappings** with permission/domain/address/remap checks and firmware-handoff cases for truncated input, invalid counts, overflow, uncovered ranges, disabled entries, and reserved overlap both before and after a covering usable entry. The same pure firmware decoder is used by the kernel; this is stronger than the earlier inspection-only overlap check, but does not simulate malicious hardware/firmware execution. Final hardening also requires firmware coverage for the image and privileged stacks before activation and validates page-separated RX/R/RW ELF loads with eight malformed-image controls. These final additions were inspected after the independent thirteen-mode run; the kernel author reports a complete rerun on the frozen source, and the parent owns the final exact-source aggregate receipt.

### Remaining boundaries

The ring-3 exercise is a controlled integer-only bring-up probe. It is not arbitrary program loading, a process model, a scheduler, a syscall design, complete register/TLS/FPU context isolation, or a concurrency boundary. Page-table memory remains trusted kernel data. Compiler stack/resource exhaustion, general aggregate lifetimes, safe reflective invocation, and full-language verification remain open. No physical AMD Zen processor or Navi-or-later GPU has been tested or is claimed supported by these QEMU results. A self-hosting OS stack and the full requested safety/performance goals remain unfinished.
