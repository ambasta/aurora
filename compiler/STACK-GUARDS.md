# Disposable-child generated-stack guard fixtures

The x86 emitter reserves function frames and canonical argument
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

`aurora-ir-check --output tests/compiler/ir/stack-probes/abi.air guard-fixtures`
emits validated direct IR.
`sector_values_abi.py --stack-guards` selects only the compact guard corpus. It
checks that each prologue reserves at least the declared frame in probed page
steps, that the odd call keeps its live operand and alignment pair, and then adds
global labels at the real probe instructions; `stack_guards.c` names probes by
ordinal and its stack tops by the declared frames. Stripping
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
meson test -C build/meson stack-probes stack-guards
python3 -B tests/compiler/sector_values_abi.py build/meson/tests/aurora-ir-check \
  --stack-guards --work-dir "$OUT/guards-normal"
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

## Compiler-emitted stack/call facts

`aurorac INPUT.au -o OUTPUT.s --stack-facts OUTPUT.stack.json` writes compact
version-2 facts from the same emission that produces the assembly. The optional
output uses the normal source-alias and no-symlink artifact protections; it must
be distinct from the assembly destination and is rejected with `--check`.
Each file is atomically replaced. The pair is valid only after a successful
compiler invocation; this is not a multi-file atomic transaction or an attestation.
The build graph declares both outputs on that one invocation.

The JSON object contains `version: 2` and a `functions` object keyed by exact
emitted symbol. Each entry contains `local_bytes` and `calls`, the latter mapping
callee symbols to their maximum live caller bytes immediately before `call`.
Repeated call sites to the same callee are combined by maximum. Like GCC `.su`,
`local_bytes` includes the function's incoming eight-byte return slot. Call-site
bytes include that caller slot, but exclude the callee's incoming return slot.
For an acyclic, closed graph, a bound is therefore the maximum of `local_bytes`
and each `calls[callee] + bound(callee)`. Roots, budgets, external edges, recursion
rejection, trusted assembly contracts and interrupt/fault allowances belong to
the admission checker, not this compiler metadata format.

The counters share the real emission paths: saved RBP, probed frame reservations,
private ABI saves (16 or 32 bytes), compact copy/receiver-zero saves (24 bytes),
operand pushes/pops, rounded outgoing copied,
service and resource records, call alignment and the pixel host call's seventh
argument reservation. They record backend-inserted runtime and reflection calls
as well as source calls. Reflection helpers are emitted leaf symbols with an
eight-byte bound. Local `ud2` trap labels have no extra stack use or call edge;
hardware fault entry remains a separate contract. Full IR validation precedes
unused-import pruning. The verifier certifies operand-depth continuity through
the retained linear emission order, including control-flow joins; the emitter
checks that operand and outgoing reservations balance at each function's end.
Facts contain only the actual emitted function/reflection symbol set.

The `tests/compiler/ir/stack-probes/` cases check the facts against the emitted
code rather than literal sizes: `CHECK-PROBES` measures the page-stepped, probed
reservation, `local_bytes` must equal it plus 16, hidden saves must lie inside it
beyond the declared frame, and call-site bytes must be 16-byte aligned and cover
the packed record. Copied-record and service facts, including host-call arity,
stay exact because bridges and the C++ runtime depend on them. Cases cover
page-boundary frames, private ABI modes, even/odd packed calls, branches/loops,
service records, seventh host arguments, resource runtime calls, reflection leaves, pruning and emitter reuse. A malformed unused imported
body still rejects. The existing diagnostics CLI gate checks JSON shape, ordinary
assembly equality, option rejection and output protection. These finite checks
support compiler intent and implementation regression coverage; emitted metadata
is not independent proof of the compiler or arbitrary-program stack safety.

V2 also carries `copied_record` for the dense copied R11/R10 ABI. Service
functions may additionally carry `service_abi`: an optional packed entry record
with ordered sealed-kind/byte extents and scalar result width, plus scalar host
call argument counts and completion maxima emitted at their lowering sites.
The graphical admission requires its independently expected dual-grant entry
and seven-argument pixel contract. It binds facts to exact generated object
members and linked call edges instead of replaying generated copy instructions.
Handwritten bridges, private bindings, closed imports, call alignment, image and
stack caps, IRQ/wait closure and runtime authority checks remain independent.
These ABI facts trust compiler lowering; they do not prove grant provenance or
runtime authority. Existing native service and guest behavior gates remain required.
Historical v1/v2 stack-only facts remain readable, but cannot satisfy a native
boundary that requires the new service ABI facts.
