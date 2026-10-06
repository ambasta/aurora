# Developer test-build and explicit acceptance contract

## Current-main IPC integration addendum — 2026-10-06

This combined source on accepted main `25d76b1799c2a29d21b175b6b720c7a256e97b9e`
remains unqualified. The prior 586-file `2b4da219…` checkpoint separately passed
full D/P native, five-entrypoint fatal sanitizer, bounded linked review of all
28 images and 177+3+2 actual runtime boots. The original reviewer completed the
missing two-input-image review in a fresh reconsideration; its accepted result
does not give credit to the interrupted attempt or to this later source.
Current `memory.S` and linked layout require fresh source/static review, followed
by newly admitted complete native, sanitizer and runtime integration. Main's
scanner, portable controls and host workflows keep their own recorded scope;
PR33 established full GCC 14 native and focused GCC 16 image/boot results,
not Clang kernel or full Gentoo native acceptance. See [exact results and
remaining gates](kernel-ipc-transition-integration-results.md).

## Historical PR28 native status — before input-review reconsideration

Fresh full public developer D and pinned-prebuilt P release workflows on the
586-file manifest `2b4da2190713a207e53e54c597e722ce1ad3cf8a51d438af6072bfae729ebabf`
have independent terminal/provenance and retained-corpus approval. D built current
source once; P recorded `externally-pinned-prebuilt` with zero bootstrap builds.
All six actual 1024 MiB sampled-storage-cap consumers passed. These results do
not establish sanitizer, guest-boot, broad-host or full IPC/kernel acceptance;
the hosted service-budget gate does not exercise IPC/RR restart. Separately, the
five-entrypoint fatal sanitizer supplement and all 177+3+2 actual runtime boots
now have scoped independent acceptance on that same 586-file source. Their
evidence does not close the blocked input-guard linked gate or qualify a new
documentation-only source. See [exact results and limits](kernel-ipc-transition-integration-results.md).
The following reconstruction and PR27 five-consumer records are historical;
neither supplies substitute credit for the new runs. This status overlay changes
documentation only and does not claim execution of its new source manifest.

## Historical accepted-base IPC source reconciliation

This candidate reconciles the 578-file IPC source, historically identified by
manifest `531af7f09e4b7a3456e8e99df1e6f21a5edd7e7fe18455513d850faca825310c`,
with the reviewed 574-file tooling documentation/results overlay, historically
identified by manifest `cad13bfbf84ff657b97ac9c4d44f4423d9238fe524119cb4727ad43eb4cf581c`.
PR27 merged at 2026-10-05 22:52:33 UTC. The accepted base is main
`772b9c8a6291aa3cc656b409ce0263f73d45b034`, tree
`62a2728942d9c36df16bd00189260f6a94cb847e`.
The older IPC/PR28 source ancestry and failed/interrupted receipts retain their
original identities and scope. This local integration requires independent review,
a final current-source freeze and freshly admitted qualification; it is not an
accepted integration head.

After an execution-environment reset, this candidate was freshly reconstructed
from independently verified published PR26, PR27 and IPC PR28 source trees.
The PR27 recovery manifest is
`aa0e772957f2248bde3b369f4fc9dd3092a6faf0a4d392792dde176a553e81dd`;
the IPC recovery manifest is
`6c66ea2ec9585305ec54cb32010c0871454ab0c9fad81f2accedcf48b9d5182a`.
Recovery checked file SHA256, Git blob SHA1, sizes and executable modes. Exact
historical PR27 manifest bytes were not restored; their digest remains a historical
reference, not a claim of recovered manifest-byte identity. The lost provisional
integration checkpoint is not presumed restored or hash-identical. A fresh merge
ledger, manifest and independent review are required.

IPC is now the sixth explicitly named portable native cap consumer. Source-only
review and Python AST/Bash syntax checks do not rerun any native, sanitizer,
compiler, Make-control or emulator workload. The historical developer audit
failure/composite and prebuilt acceptance result below retain their exact
five-consumer source scope. No result is transferred to this integration.

## Reviewed five-consumer tooling checkpoint

The prior **PR26-based developer-test workflow with reviewed full native results** composes the
reviewed PR25 developer-test tooling with the accepted 569-file PR26 source
baseline. Its underlying 566-file tested implementation manifest is `f8aec37b518c2dc9ccfe0ba95b35055b06bbc3e01fa10d2295348abcd2de9366`.
That implementation includes round-robin policy and exact-bool short-circuit
operators. Their implementation bytes, all behavioral gates, the five-consumer
cap driver, and the 173 production + 3 capacity + 2 restoration boot requirements
are preserved. This adapter/routing change adds no language, library, kernel or
hardware capability.

The six result-document updates and three added result documents have been
reconciled from final PR26 source manifest
`184bc9512620c4e7d217166f1453fa98c18f0c8dd6109a16b7e703b898b727db`.
The accepted baseline is main commit
`3ac216b64caf8b769147f1864aa8389011f0112b`, tree
`e47002622df3e8d13d9496cd09fe90b33794335b`, confirmed at PR26 merge on
2026-10-05. The tested revision-5 source has 572 files, manifest
`e097d1151156066b1147641ccc70092b729af9abc81c0fa0750c9314457dded9`.
Fresh, separately admitted full public developer and externally pinned prebuilt
native workflows completed on the reviewed GNU/Linux GCC 14 host. Independent
review accepted the developer result through its explicit composite audit and
the prebuilt result through its passed original terminal. No earlier PR25 or
PR26 native receipt substitutes for these new runs.

The developer command and product receipt passed; its original outer audit failed
on three stale completion-label expectations and remains unchanged. A separately
reviewed read-only audit and independent composite establish the retained result.
Prebuilt acceptance passed with zero bootstrap builds. See [workflow results](developer-test-workflow-results.md)
for exact identities, the preserved failure and evidence limits. The subsequent
publication overlay changes documentation/evidence only; it does not claim a new
execution of a different implementation. Gentoo make-test, new ASan/UBSan and
emulator runs, physical hardware and broad-host qualification remain separate.
Do not describe these scoped results as verified portable.

The first supported build recipe is the default GNU release recipe on x86-64
Linux. A local build receipt identifies observed inputs and output under a trusted
local workflow. It does not establish independent approval, compiler correctness,
resistance to a malicious compiler, global memory safety or a complete supply-chain
proof. Physical-hardware and broad-host qualification remain separate.

## Ordinary developer tests

From the repository root:

```sh
make test
```

The outer Make entry invokes `scripts/compiler_contract.py`. For this run it:

1. Validates supported controls before creating run artifacts.
2. Inventories actual current source contents and test inputs, rather than relying
   on timestamps or a pre-existing `build/aurorac`.
3. Records the exact build recipe, working directory, flags, relevant environment,
   resolved GNU tool executables and versions, and the fresh bootstrap compiler's
   discovered header dependency closure. Normal distribution symlinks are resolved and their names retained.
4. Builds the current compiler once into a unique run-owned directory beneath
   `build/test-contract-*`, verifies the observed dependency closure and inputs,
   and makes the compiler read-only and executable.
5. Passes that same compiler path and byte identity through all compiler-consuming
   gates in the requested graph. The inner graph validates its receipt and must
   not rebuild or replace those bytes. Existing positive, rejection, oracle,
   mutation, image and hosted-kernel checks remain required.
6. Rechecks source, tools, the recorded bootstrap headers when present, receipt
   and target-compiler identity and records the
   actual native-stage result. Failure or interruption is retained as failure,
   never successful prefix coverage.

Ordinary developer builds have no fixed reference-binary SHA-256 requirement.
Their observed compiler hash is a result of the build, not an externally approved
expected pin. A successful local build is not itself a successful test aggregate.
The run-owned read-only copy limits accidental replacement; it is not a security
boundary against its owner, hostile tools or a hostile host.

`make -C compiler test` follows the same build-once route but has **complete
compiler-only scope**. It does not run the root's complete native aggregate.
Focused targets, such as `make test-package-identity` or
`make -C compiler test-utf8-range`, likewise own a fresh compiler but establish
only the requested subset. Ordinary `make` / `make -C compiler` still build normal
development outputs; they do not produce native acceptance by themselves.

## Explicit externally pinned acceptance

An independently reviewed expected digest must be supplied by the caller as
exactly 64 lowercase hexadecimal characters:

```sh
make test-acceptance ACCEPTANCE_COMPILER_SHA256="$REVIEWED_SHA256"
```

With no compiler path supplied, this fresh-builds current source under the same
controlled recipe, then requires the output to equal the expected digest before
starting tests. A build/pin mismatch cannot pass native acceptance. Do not derive
`REVIEWED_SHA256` from the compiler under test and present that observation as
independent review.

The existing independently supervised prebuilt workflow is also supported:

```sh
make test-acceptance \
  ACCEPTANCE_COMPILER_SHA256="$REVIEWED_SHA256" \
  ACCEPTANCE_COMPILER=/absolute/path/to/reviewed/aurorac
```

The supplied executable must match the expected pin before run artifacts are
created. The supervisor makes a byte-identical private read-only copy, checks
both identities, and uses that copy for the native graph. Its provenance is
`externally-pinned-prebuilt`; there is **no fresh-source-build claim** for these
compiler bytes. Recording the current test source tree does not establish that
the supplied compiler was built from it. Independent source/tool/evidence
supervision and the actual required emulator gates remain necessary separately.

The shared controls are the supported way to select a prebuilt compiler through
Make. `OUT`, `AURORAC` and per-family compiler-path variables cannot silently
replace the run-owned fresh compiler. Conflicting paths or expected pins reject.
An explicit compatible per-family pin remains supported for a focused Make
invocation, but it never turns that subset into a complete root acceptance run.

## Direct runners and diagnostics

Existing low-level `--compiler-sha256 DIGEST` invocation remains supported. A
native pin-aware runner requires exactly one explicit expected pin or
`--developer-build-receipt /absolute/path/to/compiler-context.json`; it has no
implicit historical expected pin. The latter validates an actual controlled
developer fresh-build receipt, matching source root, compiler, recipe, tools,
recorded bootstrap headers and environment. It does not accept a boolean “developer mode” assertion
or relabel a prebuilt compiler as freshly built.

Help and explicitly compiler-free self-tests/cap-only checks, and reference-freeze
diagnostics where provided, remain diagnostics. Their availability and argument
requirements are runner-specific. A diagnostic success, preflight, or focused
native success cannot count as native aggregate acceptance.

Full root and compiler aggregates, and all acceptance-mode Make invocations,
reject `*_TEST_FLAGS` and controls that reduce coverage or replace the supervised
recipe. Use an explicitly focused developer target for a representative, quick,
case-filtered or diagnostic selection. Such a run is labeled partial/focused even
if its selected cases all pass. Do not use these overrides to bypass full coverage.

## Supported host build controls

The default recipe uses GNU C++ with
`-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`. `CXX` must select a single
supported GNU executable; ordinary distribution symlinks are allowed. The
supervisor records the resolved driver and selected GNU subtools.

For supervised compiler-consuming test routes, both `CXXFLAGS` and
`IR_TEST_CXXFLAGS` accept only the explicit allowlist of ordinary standard,
optimization, warning, debug, sanitizer, simple define/undefine and other exact
recipe options in `parse_flags`. User header/search/forced-header options are
rejected in both vectors: attached or separate `-I`, `-isystem`, `-iquote`,
`-idirafter`, `-include`, and `-imacros`. Response files, specs, plugins, explicit
PCH-control flags, LTO, profile/module controls, alternate subtool controls and untracked wrappers
remain unsupported. Hardcoded recipe includes such as `-I.` are unchanged.

Fresh bootstrap builds record their discovered header inputs and recheck them.
That closure covers the bootstrap compilation only. It is not a comprehensive
header/PCH inventory for every host test recipe; prebuilt target-compiler mode
performs no bootstrap-header discovery. The two recorded host-test flag vectors
identify admitted argv, not comprehensive host-header/PCH identity. Neither an
external target-compiler hash nor recorded host argv closes that separate gap.

The Python grammar applies to supervised compiler-consuming test entrypoints and
their validated inner graph. Ordinary `make`/`make -C compiler` and a standalone
host-only `make -C compiler test-initialization-facts` do not enter that grammar
or establish its receipt contract. Existing Make raw-expression guards are not
a replacement for the supervised Python policy. This is no generic arbitrary-
flag guarantee, and accepted syntax does not qualify every flag combination,
sanitizer setup or host. Only the exact default-vector full workflows in the
[results record](developer-test-workflow-results.md) are qualified here.

## Receipts and interpretation

Each run retains `run.json`, its compiler context, and build/native logs when those
stages execute. A receipt distinguishes:

- mode and origin: local developer fresh build, pinned fresh build, or
  `externally-pinned-prebuilt`;
- actual source/test content, build recipe and flags, tools, relevant environment
  and, for a fresh bootstrap build, that compilation's discovered header closure;
- recorded host-test flag vectors, without comprehensive host-header/PCH attestation;
- the **observed** compiler SHA-256 and the separately **caller-supplied expected**
  digest, which is absent for ordinary developer mode;
- requested entry/goal and scope, stage return codes, completion status and limits.

To claim the root native stage passed, require a **newly completed matching
`run.json`** with successful status, matching source/compiler/context/pin and
requested root aggregate, and its successful native-stage result. The root record
must have `status: passed`, `scope: native-aggregate` and `native_complete: true`;
a complete compiler-only record uses `scope: compiler-suite` and leaves
`native_complete: false`. Inspect the recorded commands and logs. A compiler-only
complete run, focused run, preflight
or stale receipt cannot satisfy that claim. Acceptance mode labels a pin-checked
native stage, not a final independent approval decision.

Bare Make exit status zero is insufficient: `make -n`, `-o`, `-f`, skipped
prerequisites, replaced recipes or equivalent Make controls can print or suppress
work without completing this contract. Supported controls are checked and unsafe
routes reject where detectable; a printed command or bypassed wrapper cannot
mint a valid newly completed run. Do not treat filesystem timestamps, a PASS line
or an observed digest alone as acceptance evidence.

Actual emulator checks remain a separate required stage where applicable; neither
`make test` nor `make test-acceptance` implies that QEMU ran. Source/tool review,
evidence preservation, bounded-resource admission and independent review remain
necessary. Existing historical proposal contracts, pins and receipts retain their
original meaning and are not rewritten by this tooling contract.

## Reviewed resource-cap composition

This source integration retains the five reviewed tooling consumers and adds
IPC transaction explicitly: package identity, package manifest, package graph,
kernel budget, round-robin and IPC transaction. Their focused defaults are
128/256/256/128/128/128 MiB; the aggregate selects the
bounded 1024 MiB ceiling. A selected cap does not itself admit a supervised aggregate: retained
workspaces, reserve and the existing free-space floor still need separate measured
admission. Process address-space, source-size, file-size and accounting comparisons
are unchanged. The tooling tests and `tests/native-cap-contracts.py` driver name
all six consumers explicitly, without filtering missing consumers. The aggregate
prerequisite is retained. Their
cap-only controls emit configuration-only results with native_executed=false and
cannot replace any behavioral, native or emulator gate.


## Round-robin and PR26 compiler consumers

`make test-round-robin`, `make test-uefi-dispatch`, and
`make test-uefi-user-phases` enter the same fresh-build supervisor as other focused
compiler consumers. `make -C compiler test-short-circuit` does likewise; its
original compiler/native/IR gates remain in the complete compiler aggregate.
The PR26 UEFI dispatch and user-phase scripts retain their implementation and
consume the supervisor's `AURORAC` rather than rebuilding it.

A direct `scripts/kernel-round-robin-tests.sh` call requires an explicit `AURORAC`
and exactly one argument pair: `--compiler-sha256 DIGEST` or
`--developer-build-receipt FILE`. The shell forwards one Bash array without eval;
it never computes its own expected pin or selects a default compiler. The native
runner validates identity before artifacts, records observed identity separately
from an external expected pin, and revalidates identity before a passing summary.
A cap-only check remains compiler-free configuration evidence.

## IPC consumer and preserved real policy linkage

`make test-ipc-transaction`, `make test-uefi-ipc` and `make test-uefi-budget` enter
the shared supervisor. The latter two now compile the real IPC policy root;
dispatch, user-phase and round-robin focused routes were already supervised.
All retained IPC/dispatch/budget/round-robin hosted linkages honor the selected
`AURORAC` and do not rebuild it. The round-robin hostile adapter still renames
only the round-robin producer while linking the genuine IPC producer. The IPC
hostile adapter still renames only the IPC producer and verifies that the
round-robin and other real symbols remain unchanged. There is no C++ fallback.

Both Make entrypoints admit `IPC_TRANSACTION_COMPILER`,
`IPC_TRANSACTION_COMPILER_SHA256` and `IPC_TRANSACTION_CAP_MIB` under the same
selector, pin and raw cap rules as the existing families. The supervisor sets the
IPC compiler alias to its immutable run-owned compiler. The generic family's
existing empty-alias-as-omitted behavior is preserved; this is distinct from
`ACCEPTANCE_COMPILER`, whose explicit empty value is rejected. Conflicting
nonempty compiler paths and mismatched pins are rejected by the shared contract.

The focused cap is 128 MiB and the explicit aggregate cap is 1024 MiB. The cap is
forwarded as one quoted operand. Direct `scripts/kernel-ipc-transaction-tests.sh`
requires `AURORAC` and exactly one `--compiler-sha256 DIGEST` or
`--developer-build-receipt FILE` argument pair, forwarded with a Bash array.
The native runner validates the selection after argument parsing, keeps cap-only
checks compiler-free, resolves identity before artifacts or execution, revalidates
identity before a passing summary and records the identity mode in its inputs and
summary. Neither an observed self-hash nor a fixed default is approval.

The existing finite truth table, full-width/hostile corpus, copy observations,
exhaustive model, source-drift guards and fatal sanitizer paths are retained.
New shell/metadata tests mock commands and cannot claim native acceptance.
All six cap variables enter the existing both-entry developer/pinned-prebuilt
mocked rejection controls. The retired executable-Make-expression observation
stays retired and uncredited. Future changes to executable source still require
source review, a separate final freeze and freshly admitted complete native and
emulator qualification. The exact older 586-file `2b4da219…` source now has
separate full D/P native, five-entrypoint fatal ASan/UBSan, runtime-premise,
28-image bounded static and 177+3+2 guest acceptance, recorded in the dated
addendum. The fresh current-main composition changes executable source and
requires new qualification; none of those receipts establishes a rerun here.

## Native-free emulator clock contract gate

Current-main addendum (2026-10-06): the composed clock and firmware suites now
contain 13 and 15 methods respectively, authored but not executed. Both ordinary
and optimized focused runs and complete native routing remain required. The
historical eight-method result below is not coverage of the added firmware join.

`make test-emulator-clock` runs `tests/kernel-emulator-clock.py` in ordinary and
optimized (`python3 -O`) Python, with `PYTHONDONTWRITEBYTECODE=1` for both recipes.
It is also a prerequisite of the root `make test` aggregate and validates the
immutable test context when nested inside a supervised run. This compiler-free
target does not enter compiler-consuming dispatch, select/build a compiler,
build an image or launch QEMU. Source/argv controls cannot qualify an emulator
run. Launcher syntax, both complete eight-method Python suites inside the public
Make target, and retirement/normal plans passed in the separately admitted
compiler-free stage on source manifest
`e6c08e72e9764615043b4ef7c5a726c5a5dda12c6f1de9f8735ec0fe8b6230b7`.
The target also completed within the independently accepted full D/P workflows
on the later 586-file `2b4da219…` source, whose earlier clock-stage delta was
documentation only. These controls establish no guest-boot result. See
[integration results](kernel-ipc-transition-integration-results.md) for exact
source and receipt identities.

## Earlier PR25-only focused evidence

The original tooling source manifest is
`ec2bc42ea63e6da54e8c817f33900dcd75787ffbab8dd516599cf598a4d8fb3f`,
based on accepted PR25 commit `c2deb1d3319fa9f590f5ccacbddab972d4ad8774`.
Its separately reviewed focused D run built one GNU GCC14 compiler with observed
SHA-256 `b3c8d58565844e1b671d1589975985374b17387b405543e05762631b95552580`.
The P run selected those same historical PR25 bytes explicitly, made a private
read-only copy and performed zero bootstrap rebuilds. Each ran only the complete
kernel-budget focused gate: 104120 policy cases, 815301 decoder cases and 10
rejection/output-preservation checks. D review identity:
`88e86908d7c593065663d90fc21c6bf8e354d1c6d947fedfea13f38a1a67f641`;
P review identity:
`8f7a791b672817ae27996bb48a33f3fdb37865991dd74337c5f5f20ece3b6460`.
Those results remain PR25-only, with `native_complete=false`. They do not
qualify this PR26 composition, full native regression, emulator gates, Gentoo,
physical hardware or portable/broad-host behavior. No historical pin is a default
in the current developer workflow.


## Cap override admission

All six current `*_CAP_MIB` controls are decimal data only (the reviewed
five-consumer revision history below keeps its original scope). Omission retains the focused
or aggregate default; an explicit empty value, whitespace, option text, shell or
Make expression, out-of-range integer or extra operand rejects before run artifacts
or build/native dispatch. Identity, budget, round-robin and IPC accept 128..1024 MiB;
manifest and graph accept 256..1024 MiB. Make checks raw values without evaluating
or echoing them before export, and the supervisor authoritatively checks the same
reviewed numeric bounds. Recipes quote each cap operand individually. In
particular, `128 --check-cap-only` is invalid cap data and cannot turn a complete
native graph into configuration-only success. Existing compiler-free cap controls
still report `native_executed=false`; they cannot satisfy root acceptance.


## Revision 2: bounded flag data and exact forwarded argv

Revision 1, source manifest
`72110f9ef4066ff74ca883e4f084a187e56c8b403ed4b51d7eed32fb800cc520`,
was not independently approved. Its interrupted independent review confirmed
that a define operand could be interpreted again by Make, changing the flags
recorded by the Python supervisor. The original review and its authorized retry
stopped with a platform interruption; no completion or qualification is inferred.
This revision is a separately authorized ordinary flag-policy correction, not a
retry of that blocked review. The original source and review history remain intact.

Both CXXFLAGS and IR_TEST_CXXFLAGS are parsed before tools or run artifacts, and
both exact argv vectors are recorded in run/context receipts, canonicalized with
shell quoting for forwarding, and compared again during receipt validation.
IR_TEST_CXXFLAGS defaults to the parsed CXXFLAGS vector only when omitted; an
explicit empty or unsupported value rejects. Explicit prebuilt compiler mode
still does not claim that its compiler was freshly built; its host-test flags
are nevertheless recorded and checked.

The raw flag policy accepts at most 16384 characters, 256 parsed arguments and
1024 characters per argument. It supports the listed GNU C++23, ordinary
optimization/debug, known warning, sanitizer and other exact recipe flags in
parse_flags. Simple -D operands name an identifier with an optional identifier
or integer value; -U names one identifier. Revision 2 initially admitted controlled
include/search/forced-header paths. Revision 3 withdraws that admission in both
supervised vectors, as described below. Canonical forwarding still preserves each
admitted parsed argument rather than changing it. String/function-like macro
bodies, arbitrary warnings/options, response files, PCH-control flags, raw dollar/Make
expressions, backticks, line breaks, backslash escapes and shell metacharacters
are unsupported and reject clearly. Unsupported spelling is never sanitized
into a different accepted option.

Make checks raw dollar, backtick and newline syntax without evaluating or
printing user values before export. The Python grammar also rejects other
control/unsupported characters before tool queries or artifacts. CXX must name
one simple executable path using letters, digits, underscore, dot, slash, plus
or hyphen. Spaces, expression syntax and command wrappers are unsupported;
normal distribution compiler symlinks still resolve through the recorded tool
identity. This bounded correction does not redesign other path selectors or
provide a generic arbitrary-flag/host-toolchain guarantee. Synthetic checks do
not establish compiler/native/emulator, current-source full-workflow or portable
host qualification.


## Revision 3: narrow user-header rejection and attestation limits

The completed read-only static review of revision 2 found F1: user header and
search flags were admitted for host tests even though dependency discovery and
PCH checks cover only a fresh bootstrap compilation. Recording argv alone cannot
attest comprehensive host-header identity, and prebuilt mode does not discover
bootstrap headers at all. Revision 2 remains a preserved, explicitly unaccepted
WIP; neither its static review nor its earlier selected author checks establish
full acceptance.

This revision rejects caller-supplied header/search/forced-header options in both
supervised vectors until complete host closure is available. It adds no dependency
framework and changes no Make recipe, fixed `-I.` input, compiler, library, kernel,
or behavioral gate. External target-compiler identity, optional fresh-bootstrap
header closure, and recorded host-test vectors remain distinct forms of evidence.
Normal GNU release flags remain admitted. The supervised-only scope and ordinary
Make/standalone-host-test limits above are explicit.

Validation of this narrow correction uses pure parsing, mocked rejection before
tools/artifacts and ordinary syntax checks only. No Make probe, compiler, native
or emulator workload is run. Revision 2's 66 selected ordinary and optimized
results remain historical; its unchanged omitted executable-expression cap
method is not newly credited. A permitted review and complete separately admitted
qualification remain necessary, with no approval or execution authority implied.


## Revision 4: active safe-suite scope and retired observation

The active `test_make_caps_reject_raw_values_without_expansion` method is retired
from the current suite and preserved in the immutable revision-3 history (source
manifest `9fb6708056d472e312c4d8ecbf03f8bcd5c499ce3e58fbd6bb60a5f8c99695c5`).
It is not rerun, assigned a new PASS, or replaced by static inspection credit.
It attempted an end-to-end dynamic observation about executable Make expressions;
that observation is not reproduced by this revision.

The existing pure cap tests now use inert dollar references or ordinary malformed
data. Expanded `test_cap_controls_reject_before_artifacts_or_execution` covers all
five cap variables through both supervisor entries, developer mode and explicitly
pinned-prebuilt mode. Root pinned coverage models `test-acceptance`; compiler
pinned coverage models the existing focused `test-short-circuit` route. It
requires rejection before tool/query/capture/execution or artifact-write calls,
and checks unchanged temporary-artifact membership, contents and modes. This is
Python pre-dispatch coverage. A separate static composition review inspects the
Makefiles' non-evaluating raw-value guards and their order before export; that
static review is not equivalent to the retired dynamic execution observation.

Revision 4 had 69 active methods. That phase executed the complete permitted
non-Make set of 63 methods in ordinary and optimized Python. Six ordinary Make-invoking
methods remain active in source but are explicitly unrun in this phase:

- `test_nested_future_source_does_not_rebuild_compiler`
- `test_make_cap_ranges_reject_before_build_dispatch`
- `test_safe_public_make_dry_runs_reject_inert_raw_flag_syntax`
- `test_safe_public_make_dry_runs_preserve_canonical_flag_arguments`
- `test_pr26_consuming_targets_use_shared_fresh_route`
- `test_make_pin_rejections_do_not_launch_builds`

They are retained for separately admitted legitimate public Make workflow checks;
this phase does not impose a permanent ban or silently remove those controls.
Owned lifecycle, diagnostic-only subprocesses and the unchanged RR wrapper with
its failing owned stub remain bounded non-Make controls. A validation-only guard
rejects unapproved processes, and any such violation fails the whole validation;
it never turns blocked work into success. Exact included/excluded lists, call
chains and remaining Make commands/artifacts/resource needs accompany the source
packet. Passing the permitted subset does not mean all 69 methods or a native
aggregate passed. Historical partial reviews/results are not stitched into
complete-current-composition approval. Static composition review and separately
admitted complete qualification remain required.


## Revision 5: explicit-empty prebuilt selector admission

Omitting `ACCEPTANCE_COMPILER` retains the documented fresh-build selection,
including a fresh build checked against an explicit expected pin when requested.
An explicitly present empty `ACCEPTANCE_COMPILER` is unsupported and rejects in
`prepare_controls` before tool queries, command execution or run artifacts.
Valid nonempty prebuilt paths keep their existing acceptance-only path, executable
and expected-hash checks. Empty input is not silently reinterpreted as omission.

The completed revision-4 static composition review found one fail-closed ordering
defect: an empty selector could survive truthiness checks and cause tool queries
and failed-run artifacts before a later regular-file check rejected it. It could
not execute a selected compiler, create a passing context or produce a false native
pass. This correction moves that rejection to the promised input boundary; it is
not described as repairing a false-pass defect. The reviewed revision-4 freeze
and its evidence remain unchanged, and no static review grants workload admission.

At the initial revision-5 source-validation stage, the active suite had 70 methods.
The complete permitted non-Make set had 64,
including an inert pure/mocked empty-vs-omitted/nonempty selector regression across
both entries and developer/pinned-prebuilt routes. It checks zero query/capture/
execution/write calls and unchanged artifact membership, contents and modes.
At that stage, the same six ordinary Make methods and 98 calls per mode remained
unrun and subject to separate admission. They later passed their separately
admitted bounded controls, followed by both complete 70-method suites in each
full public workflow; see the current results record. The retired dynamic experiment stays retired
and uncredited. Current-source composition continuity, the genuine three-file
delta and new validation records accompany this revision; earlier reports are
not summed into acceptance of corrected source or a complete native workflow.
