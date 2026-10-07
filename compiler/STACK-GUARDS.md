# Disposable-child generated-stack guard fixtures

Focused hosted qualification and independent source/result review passed on
2026-10-07. The x86 emitter reserves function frames and canonical argument
records in steps of at most 4096 bytes, immediately executing `orq $0,(%rsp)`
after each positive step, including sub-page tails. Zero reservations do not
touch memory. All GPR values except the intended RSP movement are preserved;
condition flags are dead at the two reservation sites. Frame extents, hidden
slots, call alignment, result storage and existing checked-operation UD2 traps
are unchanged. Scalar pushes and the eight-byte alignment-plus-call pair retain
their existing small-step behavior.

Protection depends on an existing inaccessible guard of at least 4096 bytes
and a valid starting stack. This is no stack allocator, recursion bound or
kernel admission rule. The fixtures below are host test adapters, not an Aurora
C ABI. Trusted C++/assembly and kernel exception-stack behavior remain separate.
The mechanism follows the page-step/immediate-touch approach documented by
[GCC](https://gcc.gnu.org/onlinedocs/gcc/Instrumentation-Options.html#index-fstack-clash-protection).

## Boundary and oracle

`tests/compiler/stack_probes.cpp --emit-guard-fixtures` emits validated direct IR.
`sector_values_abi.py --stack-guards` selects only the compact guard corpus. It
checks literal frame/record reservations, immediate real endpoint probes and
bottom-slot stores before adding global labels at probe instructions. Stripping
those labels must recover the exact emitted text. No instructions are rewritten,
no missing probes are synthesized, and no unprotected variant is run.

Each case runs one small native harness subprocess through the existing runner's
60-second timeout and core 0 soft/hard limits. Inside that disposable subprocess,
the observer reserves an anonymous shared mapping: a writable 4096-byte landing
page, one 4096-byte `PROT_NONE` guard, and up to 17 pages for the test stack. A
separate anonymous private 64 KiB alternate-stack mapping starts inaccessible.
Only the fork child makes its test-stack and alternate-stack pages writable.
The observer never switches stacks. No `MAP_FIXED`, real-process-stack depletion,
host-wide setting, kernel fault, QEMU run, new supervisor or receipt format is
involved. All 4096 landing bytes have independently reproducible canaries.

The tiny assembly shim saves the caller's six callee-saved GPRs and original RSP,
switches to an aligned mapped-stack top, seeds every callee-saved GPR, and calls
an emitted function. Positive returns record all six GPRs, the exact test RSP
and result; restoration uses separate child-local scratch, not a register the
callee was supposed to preserve. The shim restores the original six GPRs/RSP.
No generated call runs on the observer's or harness child's real process stack.

Negative children use `SA_SIGINFO | SA_ONSTACK`. The handler verifies its local
record is on the separate 64 KiB alternate stack, captures `si_addr`, RIP and RSP,
writes one 48-byte pipe record and calls `_exit`. Its only external calls are
async-signal-safe `write` and `_exit`; it does not allocate, format, unwind,
return, or attempt recovery onto the exhausted stack. The observer reaps the
child, requires SIGSEGV/SEGV_ACCERR in that record, the exact labeled probe PC,
exact guarded address/RSP, handler address within the known alternate mapping,
and every landing canary unchanged. Missing/extra records, ordinary body faults,
wrong PCs and wrong signals fail. A child-local five-second default SIGALRM
terminates a stuck fixture before the outer subprocess timeout; the observer
waits/reaps the child. Existing outer process-group/artifact controls remain in
charge of the admitted lane.

## Finite cases

Offsets below are from the first writable stack byte above the guard. Every
frame includes an additional 16 bytes for the initial call and saved RBP.

- Exact-fit frame returns: 4080, 4096, 4112, 8192 and 65536 bytes; the frame's bottom
  slot and final probe are at offset 0. Results and all preserved GPRs/RSP match.
- Page fault: 4096-byte frame, top 4096, probe 1 at offset −16.
- Tail fault: 4112-byte frame, top 4112. Probe 1 reaches offset 0; probe 2 faults at −16.
- Required 8 KiB skip guard: 8192-byte frame, top 4096, probe 1 faults at −16 before
  any bottom-slot store. A hypothetical skipped whole reservation would target
  offset −4112, in the writable landing page; that variant is never executed.
- Maximum frame fault: 65536-byte frame, top 65536, probe 16 at −16.
- Cumulative sub-page allocation: 32-byte caller frame plus 16-byte outgoing
  record. Even top 48 faults on the record probe at −16. Odd top 64 keeps one live
  eight-byte operand, faults on the record probe at −8 and preserves its operand
  in the separate success case. Successful exact-fit tops are 112/128, including
  the nested target's 32-byte frame and the odd call's eight-byte alignment.
- Bounded recursion: 512-byte frames plus 16 bytes per call/saved RBP. Argument 64
  on top 4096 faults on the eighth frame probe at −128; the preceding frame leaves
  400 writable bytes, so call/push instructions do not fault first. Argument 3
  succeeds at top 2128, including temporary-expression space, and returns 42.

## Focused gate

From the repository root, with a fresh output directory managed by the existing
native controller:

```sh
g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror -Icompiler \
  tests/compiler/stack_probes.cpp -o "$OUT/stack-probe-tests"
"$OUT/stack-probe-tests"
python3 -B tests/compiler/sector_values_abi.py "$OUT/stack-probe-tests" \
  --stack-guards --work-dir "$OUT/guards-normal"
python3 -B -O tests/compiler/sector_values_abi.py "$OUT/stack-probe-tests" \
  --stack-guards --work-dir "$OUT/guards-optimized"
```

The Python runner compiles the small C/assembly adapter with GCC, emits one
labeled assembly file and links one executable per mode. It uses no copied large
ABI corpus or new controller. Plan a 16 MiB fresh-output ceiling including the
one direct-IR build, both modes, logs and existing controller records; measure
actual output before accepting that estimate. No full compiler rebuild is needed.
The mode fails closed outside x86-64 Linux with 4096-byte pages. It is registered
beside the existing stack-probe executable in the full compiler Make test recipe.
Registration in the full recipe does not claim that the full native aggregate was run.

Kernel/BIOS/UEFI stacks, mixed C++/assembly chains, other page sizes/hosts,
performance and arbitrary-program finite stack bounds require separate gates.

## Fresh focused results — 2026-10-07

Four warning-clean C++23 producer builds and all 23 selected components passed:

- 47 direct-IR/assembly probe cases, 67 sector IR checks and 51 method IR checks
- 21 sector and 21 method handwritten-ABI cases in each Python mode
- 17 sector native cases, 21 rejections and six exact bounds traps in each mode
- Eight existing value/container/constructor/method/packed/span/integer suites
- All 15 disposable-child guard cases in each mode: eight successful returns
  and seven expected faults. Exact fault PC/address/RSP, alternate-stack use,
  every landing canary and positive register/stack restoration were checked.

Independent retained-machine-code review confirmed all 28 exported probe labels
point to actual ORQ instructions. Normal and optimized emitted guard assembly is
identical. The finite sector fixture peaks remain 9968/9984/2128 bytes; these are
controlled emitted-layout calculations, not runtime high-water measurements or
arbitrary-program bounds.

An earlier attempt exceeded its 256 MiB output cap while retaining a second
large ABI corpus. Its raw artifacts were subsequently lost during workspace
replacement and are not acceptance evidence. Source was recovered to its exact
673-file digest, independently re-reviewed, and all focused gates were rerun.
The fresh build/normal phase retained 148692992 bytes, optimized/regression phase
262144 bytes, and guard phase 94208 bytes. Their caps were 256/256/16 MiB.
One full large ABI corpus is retained; the existing runner removes successful
optimized-mode scratch. Current receipts and guard artifacts are retained.

The accepted tested source manifest is
`8cc9a9b4788bf1f18722548580d411344a7c01f7e6e22c4ca10e93eaf514009b`.
The compiler digest is
`762ba74b8b58d4c6ae7c335507a7b06560a90f44c98d268defa36e086fa41630`.
No full native aggregate, performance neutrality, kernel/QEMU qualification,
C++/assembly-wide protection or general stack-safety proof is claimed.

## Current storage-consumer composition

Publication was joined onto PR52 main
`c3f2587b25bf2aa6be49d8036f6c2b31475218a8`, preserving the owned-sector and
block-I/O modules, examples and Make/Meson registrations. No compiler
implementation input changed in that join. A separate nine-invocation focused
compatibility run passed on the qualified probe compiler: owned-sector's 43
native cases/nine rejections and block-I/O's 38 native cases/13 rejections in
both Python modes, including their examples, plus complete optimized block-value,
binary-writer, byte-codec, RAM-block and storage-binary runners. This adds hosted
consumer compatibility, not a full aggregate, kernel or device qualification.
