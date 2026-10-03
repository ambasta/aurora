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

The permanent host protection test passed **511 mappings** with permission/domain/address/remap checks and firmware-handoff cases for truncated input, invalid counts, overflow, uncovered ranges, disabled entries, and reserved overlap both before and after a covering usable entry. The same pure firmware decoder is used by the kernel; this is stronger than the earlier inspection-only overlap check, but does not simulate malicious hardware/firmware execution. Final hardening also requires firmware coverage for the image and privileged stacks before activation and validates page-separated RX/R/RW ELF loads with eight malformed-image controls. These final additions were inspected after the independent thirteen-mode run; a separate integration run reported a complete rerun on the frozen source. Final exact-source results belong to the aggregate receipt.

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

The frozen candidate also independently passed **203 source tests** with Python optimization, the **34 additional source cases** from the previous review, and **five exact trap-address probes**. The latter compare SIGILL's actual instruction address to the emitted bounds/overflow label and verify UD2 bytes. Separate semantic-oracle/equivalence tests provide broader behavioral-comparison receipts; those are distinct from these targeted review results.

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

The actual normal contained traps were vector 6 at CPL3 with TSS entry frames; the kernel-origin test was vector 6 at CPL0 on the privileged stack. Per-mode metadata files retain the exact linked trap/return sites for variant builds. The current transcript suite independently passed **16 positive and 110 negative controls** under Python optimization. Separate integration verification reported all 16 QEMU gates on the pinned candidate, including the previous 13 protection modes; final exact-source results belong to the aggregate receipt.

Only recognized bounds/overflow failures from these validated user contracts are contained. Unknown user traps remain fail-stop. There is no arbitrary binary loader, process scheduler, complete FPU/TLS context boundary, concurrent execution, general syscall surface, self-hosting compiler, production driver stack, or demonstrated physical AMD CPU/GPU support. No unresolved reproduced defect remained in this reviewed scope at freeze.

### Milestone-three acceptance reopened: verifier resource regression

An extra integration sanitizer gate exposed a real resource defect after the preliminary review freeze: the supported 4096-element initializer exceeded the unchanged five-second test deadline under instrumentation. Integration measurement of the initial verifier recorded roughly 4.3 GiB release peak RSS and 5.8 GiB instrumented peak RSS. The cause was retaining a deep operand-stack and initialized-slot snapshot at every IR instruction. The failed gate was preserved; its timeout was not increased or reclassified as a pass.

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

## Milestone four: module authority, hardened host I/O, and distinct CR3 domains

This section records the next bounded implementation review. Earlier compiler revisions, signatures, counts and acceptance receipts remain historical. Final acceptance requires an exact-source aggregate receipt; this review does not authorize publication.

### Module resolution and library findings

The new loader resolves named imports under explicit module roots, checks interface headers, limits the graph, and resolves each function body in its defining module and lexical namespace. Imported symbols receive length-prefixed native identities; the narrow unqualified root bootstrap symbols remain unchanged. There is no implicit re-export or aggregate cross-module calling convention. The tiny `std.core` module contains actual compiled `std::min`, `std::max` and checked `std::abs` functions; this is not a complete standard library or full ISO C++ module implementation.

Review reproduced a defining-module resolution defect in the first candidate: an imported exported function calling undeclared `root_only()` was accepted because the later merged semantic table found the root's private `root_only` native symbol. Its generated assembly contained `call root_only`. Unresolved non-builtin calls now fail in their defining-unit resolver instead of being deferred to the merged graph. The original reproduction now rejects.

Eighteen independent module cases passed, covering that regression, private helper lookup despite root shadowing, denied private qualified calls, private class static/runtime reflection, public class copy isolation, absence of implicit transitive exports, direct dependency use, ambiguity, enclosing namespaces, header mismatches, cycles, root-escape symlinks, real standard-library calls, `abs(minimum_i64)` trapping, private standard-library helper hijacking, and reserved native-identity spelling. Runtime metadata access is scoped to the defining module; visibility checking remains a trusted source-level responsibility, not a new independent IR privacy proof.

### Hardened source and artifact access

The initial canonical-path/check/reopen approach was superseded before acceptance. The isolated Linux bootstrap adapter now retains directory descriptors and uses `openat2` with beneath-root, no-symlink and no-magic-link resolution. All source symlinks are rejected, including contained aliases. Unsupported protection fails closed; there is no insecure fallback. Regular-file checks, bounded descriptor reads and RAII ownership keep parsing separate from path re-resolution. This host adapter does not add a source-language filesystem/unsafe/C-ABI surface.

Independent reader tests passed root rename/replacement, parent/absolute escapes, contained/external symlinks, nonregular files, read limits and an owned-fixture replacement race. In one run, 800 reads racing 400 entry swaps produced 565 safe reads and 235 denials, with no outside bytes returned. The adapter suite has thirteen checks. Descriptor identity does not promise immutable file contents: concurrent writes to the same inode can change bytes while read. No atomic file-content or whole-graph snapshot is claimed.

The output adapter pins the caller-selected parent, rejects observed source-inode aliases and nonregular/symlink destinations, stages a private exclusive regular file, and atomically replaces one destination leaf without opening existing output for writing. Review reproduced and verified fixes for two initial defects:

- Choosing a destination equal to the generated temporary basename made the destination visible before commit. Such candidates are now skipped; the same reproduction leaves the destination absent until commit.
- Retrying after a partial OS write failure appended to stale temporary bytes, producing `abcdXY` instead of the requested `XY`. Failed transactions now remain poisoned and cannot retry writing or commit.

All twenty-two artifact tests passed independently, including real process-local partial-write/EFBIG and rename/EACCES failures, source/hardlink/symlink aliases, pinned-parent replacement, temporary-entry replacement, preserved old output, and failure/retry state checks. Tests touched only owned disposable fixtures. Output limits are 64 MiB, 8192 write calls, 128 interrupted-call retries and 32 temporary-name attempts. Atomic replacement is not an fsync/crash-durability guarantee or protection against an equally authorized/privileged directory writer tampering with private entries or output after commit. Conditional cleanup preserves an observed replacement entry; it is not a host-wide adversarial filesystem transaction.

### Parser robustness correction and final compiler checks

A bounded follow-up reproduced two host SIGSEGV failures below the source byte limit: 32768 nested blocks in a 65,575-byte file, and 16384 nested parentheses in a 32,807-byte file. Namespace nesting above 32 already rejected normally, but that did not bound body/expression recursion.

The parser now has explicit guards for expression recursion 128, block nesting 128 and type recursion 64, alongside namespace depth 32. Every expression-child attachment checks AST depth 128 before retaining an over-deep tree. This also bounds left-skew binary/member/index chains and error cleanup, rather than relying only on parser call depth. Eleven deep-input regressions now return ordinary failure with diagnostics, no artifact, and unchanged source; the original crashing inputs are included. No stack-size or timeout increase was used.

Independent final release checks passed **207 source tests, 51 typed-IR tests, 72 module/library tests, 11 deep-input rejections, 13 source-adapter checks and 22 artifact-adapter checks**. The eighteen independent module cases and all eleven deep rejections also passed against ASan+UBSan compiler `ecde7e3f84b250498949a9fc4c1ede13ce14bbaf937b4400d123ad1f6237cd59`, with halt-on-error and unchanged five-second case deadlines. LeakSanitizer remains unavailable under the execution environment's tracing restriction.

Module quotas are sixteen roots, sixty-four files, import depth sixteen, one MiB per file and four MiB per graph. These and the nesting caps do not establish a global compiler time/memory bound; the earlier documented branch/live-fact scaling remains relevant.

### Domain lifecycle and hardware observations

The kernel now builds three separate, statically owned page-table roots and leases four private physical stack frames per domain. Each root retains the shared kernel mappings as supervisor-only, exposes only its own immutable user code page, and maps the common user stack virtual range to that domain's leased frames. Other fixture code is absent. Supervisor direct aliases of stack frames remain non-executable; the map rejects executable/writable physical aliases in either insertion order.

Review checked ownership stamps across slot reuse and registry reconstruction; allocation rollback; active-domain teardown rejection; kernel-root restoration before retiring roots or stack leases; scrub/readback before free; actual same-frame reuse; and final zero allocator use. Current hardware CR3 must match the active domain before a program event can be accepted. PCID is disabled, leaves are nonglobal, and CR3 writes flush prior translations on the single tested CPU. Pool lifetime is a trusted kernel-lifetime precondition. Page-table objects are static slot-owned storage, not frames returned to the stack allocator.

Independently ran normal boot and three new hostile QEMU modes using pinned compiler `8cfc730080b60b30c623ceba56156b8d9639d2fec15cb9859a0652b89faac131`. Observed domain roots were 110592, 131072 and 151552, distinct from kernel root 184320; first leased stack frames were 1048576, 1064960 and 1081344. Normal execution passed contained user faults, clean restarts, private-stack use, complete scrub, partial allocation rollback, stale-handle rejection, same-frame reuse, and final teardown.

- Foreign code fetch faulted at `0x1b1000`, vector 14/error 20, CPL3.
- Reading another domain's leased frame faulted at `0x104000`, vector 14/error 5, CPL3.
- An otherwise valid scalar-return event under an injected wrong kernel CR3 was rejected, vector 129 at CPL3.

The domain ownership/alias host suite passed independently. The transcript suite passed **nineteen positive and 134 negative controls** with Python optimization. The independent four-mode run used the earlier module-compiler pin; final compiler host-I/O/depth hardening is covered separately above. Separate integration verification subsequently reported all nineteen QEMU modes passing on corrected compiler `04b7cc71bd2ef8721f99f8c6ec6ef2cdf850358d1b55a5fea2d660073c8bae03`; the final aggregate receipt must retain that exact-source/compiler association.

### BIOS loader bounds

The payload budget increased to 96 sectors (49,152 bytes), starting at physical `0x10000`. That fixed range ends at `0x1bfff`, within the 64 KiB segment transfer window and below the validator's 127-sector ceiling. Review observed that the original assembled disk-address packet was not four-byte aligned; explicit alignment and a binary regression were added. Validation now reads the assembler's packet symbol and checks the actual packet count, destination, LBA, alignment and window, rather than assuming source constants agree. Fourteen malformed-image/packet controls passed during the independent boots, including a destination-preserving window-overflow case. The observed normal payload was 32,880 bytes, explaining why the former 32 KiB budget was insufficient.

This remains a controlled single-CPU, sequential domain bring-up. It does not implement a scheduler, unrestricted process creation/loading, complete context isolation, a full standard library, self-hosting, production drivers, or physical Zen/Navi hardware support. No unresolved reproduced defect remained within this reviewed checkpoint scope after the fixes above.

## Framework complete-machine target review (2026-10-03)

Reviewed `framework-13-7840u.md` and its AMD-support/roadmap references as requirements only. The [vendor model announcement](https://frame.work/blog/announcing-the-framework-laptop-13-powered-by-amd-ryzen) supports the stated 7840U/780M identity and asymmetric expansion-slot capabilities; exact installed replaceable parts remain deliberately unspecified. The [vendor hardware repository](https://github.com/FrameworkComputer/Framework-Laptop-13) provides module documentation, not evidence of complete open firmware or Aurora compatibility. No physical qualification was performed.

The inventory already requires storage, multi-user isolation, native graphics, network/radio, input, audio, camera, power and recovery qualification. Review added explicit target gates for authenticated boot/update trust, documented antirollback and authorized recovery tradeoffs, firmware lifecycle/recovery, DMA protection across boot/hotplug/resume, entropy and credential handling, and encrypted-storage/key recovery boundaries. These additions are acceptance requirements, with no corresponding implementation or test-pass claim. Existing emulator evidence remains insufficient for the selected laptop or any physical AMD-support claim.

## Constructor and scalar-method review (milestone five candidate)

Independently ran all 74 constructor/method source cases on release compiler `d1aef9e30e8e5a874b02e6f2de589ac4908950f7264d64aab08ff89ff2141c1a`. Twelve additional cases exercised private value-copy independence, same-name inner copies, index-before-receiver-mutation evaluation, constructor argument snapshots, bool fields, branch/loop const lifetimes, method bounds traps, wrong initializer types, rejected receiver-to-mutable-reference conversion, and an imported private class behind an exported scalar function. All passed on release and ASan/UBSan compiler `060095244309c4db5bc04a19de53b39d36c264363ce0f3ede7488e05985b2032`; all 74 permanent class cases also passed independently with that instrumented compiler. Unsupported logical-operator syntax still rejects. Trap testing here checked exact SIGILL, not an independently inspected trap address.

The first inspected candidate accepted a constructor-name method with an explicit return type. This contradicted the restricted grammar; the corrected parser rejects it and the permanent regression passed. No emitted receiver-authority bypass was reproduced by that spelling.

Inspected the hidden receiver ABI and verifier: receiver authority is separate from scalar values/slots, calls require the matching nominal class and const permission, scalar borrow handles cannot name object fields, and indexed field stores also respect const. `BeginObject`/`EndObject` clear per-lifetime initialization facts; joins require compatible active lifetimes and combine definite/maybe initialization appropriately. Constructor completion and repeated initialization are checked. Private visibility/name resolution remain trusted frontend obligations, not independently proved by IR validation.

Independently executed all 132 direct valid/malformed IR tests under ASan/UBSan. LeakSanitizer cannot run under this traced execution environment; the initial attempt reported that limitation, and successful runs explicitly used `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. No leak-check result is claimed. Reviewed iterative call-graph SCC traversal, including scalar bridges to receiver cycles. An additional 12,000-helper source graph (457,906 bytes) compiled in 0.099 seconds; making its terminal helper call the receiver-owning root rejected normally in 0.079 seconds. These are bounded observations, not global resource or runtime-stack guarantees. Pure scalar recursion remains allowed.

This scope is inline scalar-field construction and synchronous statically dispatched scalar methods. It excludes escaping receivers, aggregate argument/result ABI, inheritance, destruction, heap lifetime safety and general concurrency. Exact-source aggregate integration is a separate acceptance step.

### Bounded integer preemption review

Inspected the xAPIC adapter, context policy, scheduler, assembly capture/resume and domain mapping integration. The optional harness requires a single logical CPU and verified xAPIC/PAT configuration. APIC MMIO is supervisor-only, uncached and non-executable. Scheduling authority checks the actual active CR3, privileged TSS frame, linked image range, selectors, stack and flags; the timer additionally requires its real ISR bit. All fifteen integer registers and the IRET frame are copied into privileged storage and revalidated before resume. The user cannot choose the saved kernel continuation.

Reviewed pending-timer retirement explicitly: masking/stopping alone does not clear IRR. The implementation drains an actual pending timer only in its labeled kernel-root/main-stack STI/NOP/CLI window, without charging a task, and requires empty ISR/IRR before rearm or retirement. TPR remains zero. This is a controlled emulator contract, not a general interrupt-controller or physical-platform proof.

Reproduced a transcript false positive: duplicating one saved timer-frame line and removing a different tick's frame still passed because the validator compared only total frames with total ticks. The corrected validator ties a unique frame or terminal record to each active slice, rejects duplicate/mixed evidence, and requires the appropriate event before completion/cancellation. The original counterexample now rejects. Independently ran its nine positive and 185 negative controls with Python optimization enabled.

Six independent actual QEMU modes passed using compiler `d1aef9e30e8e5a874b02e6f2de589ac4908950f7264d64aab08ff89ff2141c1a`: `--schedule`, `--schedule-context`, `--schedule-forged`, `--schedule-fpu`, `--schedule-mmio`, and the historical normal boot. The scheduling run observed fourteen sentinel/DF probe interruptions, finite task result 42, cancellation after 24 charged slices, exact linked bounds containment, kernel-root restoration, teardown/scrub and a fresh result-42 run after frame reuse. Adversarial modes produced respectively rejected vector 64 at CPL3, rejected forged vector 64 at CPL0, unsupported-state vector 7 at CPL3, and page fault 14/error 5 at CPL3 for APIC address `0xfee00000`. The last normal run restored the ordinary image. Separate integration verification reported all nine new and nineteen historical modes passing; that broader count is not an independent rerun here.

The hosted context/budget test also passed an independent ASan/UBSan build with leak detection disabled for the previously documented execution limitation. These results cover an integer-only, single-CPU, bounded harness. Unexpected user faults remain fail-stop; only specified compiler faults are contained. General extended-state/TLS lifecycle, calibrated time, arbitrary executables, dynamic threads, SMP, general process services and physical Framework/AMD support remain outside this evidence. No unresolved reproduced defect remained within this reviewed candidate scope; final exact-source aggregate receipts remain separate.

## Immutable class-value call review (milestone six candidate)

Reviewed ordinary-function class parameters/results, defining-module signature visibility, typed call operations and the private x86 call-record/result ABI. Scalar-field class arguments are copied left-to-right into distinct readonly snapshots before later arguments execute. Callees copy those values into readonly frame objects; returned values must be complete named locals of the exact nominal result type. The caller's fresh result storage cannot overlap argument snapshots. Hidden record/result addresses are saved outside source-addressable scalar slots, including when a receiver method invokes an aggregate-signature function. Six arguments and 64 fields bound each boundary layout; ordinary recursion and total stack use remain unbounded by those local limits.

Independently ran all 59 permanent value-boundary source cases and 64 additional native ABI cases on release compiler `f16fffe8a976b71c82bbebf90e32150142aad044649b2f02dd585c8933719a71` and ASan/UBSan compiler `ab8ad95501780fdc268d0e1511b323cfeb9f0d9884814ab245a1803c8c77f63b`. The additional matrix exercised all 63 nonempty class/scalar combinations across six parameter positions with class results, plus six maximum-width values mixing bool/i64 fields. Permanent tests cover snapshot timing around mutation, copy independence, recursion, odd operand depth, result/parameter loop lifetimes, private and direct-import signature rules, malformed source and exact SIGILL failures. All passed; leak detection was disabled for the documented execution-environment limitation.

Independently executed all 206 direct IR cases under ASan/UBSan and all four exhaustive-dispatch controls. The latter first compile unchanged verifier/backend headers, then inject an unknown variant into temporary copies and require each consumer's specific compile-time assertion. This closes the silent-omission failure mode reported from an incomplete development build; that partial state is not treated as a released or verified candidate. Source privacy remains a trusted frontend obligation. No reproduced aggregate aliasing, nominal-layout, initialization or hidden-pointer bypass remained in this reviewed candidate; final exact-source integration remains a separate gate.

### Independent UEFI handoff review

Reviewed the separate OVMF loader/payload, bounded firmware descriptor parser, fixed arena handoff, complete page-table validation, ABI transition and post-exit code path. Only the exact firmware-allocated arena supplies payload, tables, stack and page-pool storage; arbitrary loader-code descriptors do not authorize unrelated allocation. After successful ExitBootServices, no firmware callback is used or passed to the payload. The bounded retry path uses another map/exit pair and stops after three rejected keys, consistent with the [UEFI Boot Services contract](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html#efi-boot-services-exitbootservices).

Review identified these issues before final validation:

- The RX trampoline's GDT descriptors initially had Accessed bits clear. Loading a data selector attempted a write to that read-only page under CR0.WP. The integration QEMU trace confirmed page fault 14/error 3 at the descriptor byte; pre-setting Accessed bits corrected it. This behavior follows the [architectural descriptor rules](https://cdrdv2-public.intel.com/671190/253668-sdm-vol-3a.pdf). Integration also corrected a separately found linker-relaxed absolute payload-entry address; final object-relocation validation permits only the specified PC-relative forms.
- A CR3 switch alone could retain inherited global translations. The corrected transition clears PGE and rejects unsupported PCIDE/LA57 states; the payload verifies the resulting mode. Complete tree validation rejects unauthorized leaves, aliases, cycles and out-of-pool links. Successful map lengths are checked before constructing the descriptor view.
- The initial malformed-map probe tagged the first descriptor, which need not cover the owned arena. A two-descriptor hosted reproduction retained valid arena ownership after that change. The corrected probe targets the covering allocation descriptor; ordinary runtime regions elsewhere remain reserved and valid.
- The initial transcript validator accepted language execution followed by a malformed-map failure. The corrected validator forbids downstream execution on every failure path and enforces protection/result/completion ordering. The original counterexample now rejects.

All eight actual OVMF modes passed independently with compiler `f16fffe8a976b71c82bbebf90e32150142aad044649b2f02dd585c8933719a71`: normal, stale key, exhausted retries, malformed handoff, malformed ownership map, unauthorized table mapping, supervisor text write and data execution. The observed normal arena was 99,753,984 with 111 descriptors, private CR3 99,823,616 and private stack 100,048,752. Normal exit succeeded on attempt one; stale-key recovery succeeded on attempt two; exhausted retry stopped after rejected attempts one, two and three without entering the payload. Text writes faulted with vector 14/error 3 at arena+`0x22000`; data execution faulted with vector 14/error 17 and matching RIP/CR2 at arena+`0x50000`. Successful payloads executed compiled Aurora code returning 42. Each independent build passed fourteen negative PE/PIC image controls, and the final mode restored the normal UEFI image.

Independently compiled and ran all 124 hosted descriptor/header/tree policy cases under ASan/UBSan, and eight positive/148 negative transcript controls under Python optimization. Separate integration verification reported all twenty-eight BIOS gates passing with the new class-result fixture; those BIOS gates were not independently rerun in this UEFI review. Firmware trust, DMA/device quiescence, runtime services, Secure Boot, transition NMI/SMI behavior, scheduler integration and physical Framework support remain outside this bounded OVMF evidence. No unresolved reproduced defect remained within this reviewed candidate scope; exact-source aggregate acceptance remains separate.
