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

## Milestone three: typed IR boundary and compiled user programs

This review covers the phase split and controlled user-program execution added after milestone two. Earlier acceptance records are preserved; this section does not replace their historical counts or claim a complete safe language/OS.

### Compiler boundary and reproduced findings

The frontend now produces typed IR after source name/type/const/visibility/lifetime analysis. The backend accepts a validated-module wrapper, has no AST or ownership checker, and emits only from a closed instruction set. Checked arithmetic and array bounds guards are explicit operations. The verifier checks CFG targets, slot layout and initialization, scalar types, canonical Boolean constants, balanced temporary stacks, call signatures, and matching checked-index tokens.

Independent malformed-IR review found four accepted cases in the first candidate:

1. A function symbol containing a newline/assembler directive passed validation and flowed into textual assembly emission.
2. An unreachable invalid parameter-binding instruction was not checked even though the emitter would visit it.
3. An unreachable push changed the emitter's linear stack-depth accounting, causing an incorrectly adjusted call stack on the actual reachable path.
4. Parameter binding after a metadata call copied a clobbered argument register. A generated executable was observed returning 42 from a Boolean function called with canonical Boolean 1.

These were internal-IR boundary defects, not demonstrations that the source checker emitted such modules. The corrected verifier restricts symbol grammar/helper names, requires parameter bindings in the exact entry prefix, rejects unreachable semantic operations, and removes only unreachable structural label/jump artifacts. All four original reproductions now reject. The permanent direct suite passed **42 IR tests**, including the regressions and guard/layout/type/initialization/control-flow failures.

Bounds protection attaches to the actual abstract current/stack value rather than merely to an array shape. Four additional focused checks passed: loading an index from an ordinary slot loses the token; arithmetic loses the token; replacing a saved stack index with an unchecked value rejects; a saved checked index survives an unrelated slot overwrite and a metadata call on the RHS. This matches the backend's actual register/stack behavior. A frame store that leaves the current register unchanged need not invalidate its token; an ordinary reload cannot recreate one.

The frozen candidate also independently passed **203 source tests** with Python optimization, the **34 additional source cases** from the previous review, and **five exact trap-address probes**. The latter compare SIGILL's actual instruction address to the emitted bounds/overflow label and verify UD2 bytes. The separate semantic-oracle/equivalence workstream supplies broader behavioral-comparison receipts; those are distinct from these targeted review results.

The source semantic/lifetime analyzer remains trusted for ownership, const, privacy, scope, and aggregate rules. The IR verifier does not independently reconstruct those source policies from scalar slots. The x86 emitter and host C++ implementation remain trusted. This is a meaningful internal validation boundary, not a proof of Rust-equivalent soundness or arbitrary optimizer correctness.

### Compiled user-program contract

Three programs are separately compiled and linked at fixed one-page addresses. Build validation checks RX-only linked bytes, entry/return symbols, and exact compiler bounds/overflow UD2 labels before generating read-only kernel metadata. Installed pages have no writable identity alias after protection activation. They share a single user domain; this is explicitly not inter-process isolation.

Each launch clears integer registers and scrubs/verifies the user stack. The trusted user entry checks initial integer state, calls the compiled function, and uses a narrow scalar-return gate. Kernel acceptance requires the active contract, exact linked return PC or known compiler trap PC, the expected vector/error, user CS/SS, permitted saved flags, user stack bounds/alignment, and a TSS entry-stack frame. Return additionally requires the top-of-stack restored by the trusted entry sequence. The continuation comes from a protected kernel-owned saved stack, never a user-supplied continuation address.

Review identified a metadata lifetime/mutation footgun in the first `ProgramRun` API, which retained a pointer to the caller's contract. It now snapshots the contract by value and is noncopyable. An independent check begins a run, changes the caller's original return-PC contract, and confirms the changed authorization is rejected. The permanent host policy suite passed snapshot lifetime, replay, nested run, full scalar-bit-pattern result, exact trap/opcode, flags/stack/origin, stale-result reset, and clean-run-after-fault checks.

### Executed kernel evidence

Against pinned compiler SHA-256 `765ed87efa9c28909217f0ab01bacc97ef2fbdea6fd76547db778726b18a8918`, independently ran normal boot and the three new hostile modes:

- Normal sequence: clean compiled array/loop program returns 42; known bounds UD2 is contained; clean program returns 42 again; known overflow UD2 is contained; clean program returns 42 again; the kernel reaches normal boot success.
- A user return through vector 129 at the wrong linked PC fails closed.
- A user UD2 not named by the active compiler-trap metadata fails closed.
- Execution of the exact known compiler bounds-UD2 address at CPL0 remains fatal, rather than being mistaken for a contained user-language failure.

The actual normal contained traps were vector 6 at CPL3 with TSS entry frames; the kernel-origin test was vector 6 at CPL0 on the privileged stack. Per-mode metadata files retain the exact linked trap/return sites for variant builds. The current transcript suite independently passed **16 positive and 110 negative controls** under Python optimization. The kernel author separately reports all 16 QEMU gates on the pinned candidate, including the previous 13 protection modes; the parent owns the final aggregate receipt.

Only recognized bounds/overflow failures from these validated user contracts are contained. Unknown user traps remain fail-stop. There is no arbitrary binary loader, process scheduler, complete FPU/TLS context boundary, concurrent execution, general syscall surface, self-hosting compiler, production driver stack, or demonstrated physical AMD CPU/GPU support. No unresolved reproduced defect remained in this reviewed scope at freeze.

### Milestone-three acceptance reopened: verifier resource regression

An extra parent sanitizer gate exposed a real resource defect after the preliminary review freeze: the supported 4096-element initializer exceeded the unchanged five-second test deadline under instrumentation. Parent/author measurement of the initial verifier recorded roughly 4.3 GiB release peak RSS and 5.8 GiB instrumented peak RSS. The cause was retaining a deep operand-stack and initialized-slot snapshot at every IR instruction. The failed gate was preserved; its timeout was not increased or reclassified as a pass.

The verifier now snapshots abstract states only at basic-block entries and walks each straight-line block using one mutable state. Separate reachability tracking preserves rejection of unreachable semantic instructions and normalization of only dead structural jumps/labels. Entry-prefix, symbol, target, frame, bounds-token, type and initialization checks remain in force. Code inspection covered leader discovery, conditional fallthrough, loop reprocessing, shrinking initialization/guard state at late joins, and final reachability normalization.

The corrected direct suite passed **46 IR tests**. New cases cover loop guard loss, a late predecessor removing initialization, identical guarded values joining successfully, and the maximum initializer's retained-state metrics. The latter records one entry snapshot, operand depth 4096, and zero retained entry value/initialization facts for its straight-line block. Four independent token-provenance checks and all four original malformed-IR reproductions were rerun successfully.

Independent release measurements for a 4096-element initialized array followed by bounded branch-dense suffixes were:

- Zero branches: 0.011 seconds, 10,768 KiB peak RSS.
- 64 if/else branches: 0.087 seconds, 48,512 KiB peak RSS.
- 128 if/else branches: 0.153 seconds, 85,988 KiB peak RSS.

Using the matching-flags ASan+UBSan binary with SHA-256 `f336d8269b9f4de441e3b39a163b6d4e1721ea8b2792a0ae0e1902bc1330bd91`, independent results were:

- Zero branches: 0.096 seconds, 46,448 KiB peak RSS.
- 64 branches: 0.680 seconds, 217,956 KiB peak RSS.
- 128 branches: 1.163 seconds, 385,648 KiB peak RSS.

Each resource probe retained a five-second deadline and exited successfully. The full **203 source-test suite** also passed with that instrumented binary, Python optimization enabled, and ASan/UBSan configured to halt on error. Leak detection alone remained disabled because the execution environment's tracing restriction prevents LeakSanitizer operation; no LeakSanitizer pass is claimed.

These are measurements in this environment, not portable performance guarantees. The straight-line quadratic-retention bug is corrected, but retained join states still scale with basic-block entries times live slot facts. No global compilation memory/time bound or general linear-complexity claim follows. Large branch-dense/untrusted inputs require additional resource budgeting or more compact state representation before production claims. The corrected compiler supersedes the earlier pinned executable for final milestone-three acceptance; all aggregate/oracle/kernel receipts must be rerun on the corrected source rather than reusing the preliminary freeze results.
