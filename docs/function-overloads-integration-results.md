# Exact ordinary-function overloads: integrated verification

Date: 2026-10-04. This records the completed bounded overload checkpoint and its
limits. It supersedes the earlier isolated candidate's pending-integration status;
it does not claim a complete language, production security or physical hardware
qualification.

## Source and feature boundary

The integration starts from accepted package.graph PR20, main commit
`a7a6fcd62466bde283cb99d936383502492a19ef`, tree
`d699abb5250a2b58c98a3d3c331cb02a7650f1a5`. The tested source has 526 files;
its exact source-manifest SHA256 is
`d236d019540bffec6df42c210b3f33c91babb9c93048e665ba767ed2b3a597a3`.
The final source adds this result document and append-only status notes. Executable
sources, Make recipes, validators and fixtures remain identical to those tested.

Same-module ordinary functions dispatch on exact arity and ordered nominal
parameter types, with at most 32 declarations per name. There are no implicit
conversions, return-type selection, cross-module overload merging or template-name
overloading. Visibility is per declaration and selected signature; private nominal
identities stay distinct. Argument staging remains once, left to right. Existing
single-declaration symbols and entrypoint requirements are preserved; an overloaded
root `answer` rejects. The [contract](../compiler/FUNCTION-OVERLOADS.md) gives the
complete scope. No optional, raw pointer, C ABI, struct, heap/reference API or new
IR instruction is added.

Release compiler SHA256:
`8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631`.
Package identity, manifest and graph gates accept an explicit expected compiler
pin. Their historical M022 defaults remain intact; actual-binary hash checks happen
before native output. Wrong/malformed-pin and output-preservation controls passed.

## Isolated compiler and independent controls

Complete release and fatal host ASan/UBSan compiler targets passed. Author tests
cover 63 fixtures / 83 executions; independent review covers 123 fixtures / 168
checks, including malformed IR, nominal/visibility boundaries, rejection output
preservation, private symbols, order and result-type independence. These overlap
and are not added into a disjoint coverage total. All 60 baseline Aurora sources
preserve exact status/diagnostics/assembly, and 64 bounded native differential
programs agree. The [isolated verification record](../evidence/function-overloads/README.md)
records exact counts, pins, failures and sanitizer/resource limits.

## Fresh native aggregate: tests succeeded, bookkeeping failure preserved

The combined candidate's fresh build passed and reproduced the exact release pin.
Its complete fresh `make test` child exited zero after every recipe completed,
including compiler/IR/module checks, image and hosted kernel checks, package
identity (5,503 oracle cases), manifest (20,022) and graph (5,548).

The aggregate supervisor's original terminal remains **failed**, SHA256
`0097dd1cb90257850a93eb96a5ad4a955f79c0cc166a2f9730d2674df90a2d02`.
Its only finalization error was an unexpected empty, mode-0755 root `tmp` directory
created by existing successful compiler test recipes. This was a source-topology
bookkeeping mismatch, not a failed test command. Complete independent re-audit
verified all source, host/tool and control pins, the exact directory identity,
unchanged compiler, sealed outputs, exit zero and quiescent ownership.

An exact, parent-accepted supplemental review establishes native test success
while preserving that raw failed terminal: supplement SHA256
`2141d57c52181c253615dcf98b637054cf6634fa79dacf2ce674772e0294ea87`;
consumer clearance
`769dc5e870360cad0f360eb1db04d41906673cb88d35554752c9a7eed552f854`.
It is limited to this exact terminal and empty directory; wrong hashes, nonempty
or changed-mode `tmp`, other input drift, missing approval and nonzero exits reject.
No generic failed-run acceptance or retrospective allowlist change was introduced.

Successful post-run compaction independently verified 21,371 exact members and
402,750,601 payload bytes before retiring recoverable build duplicates. Archive
SHA256 is `18fae959054b617a9d9f82bcaa627ce7ded511b459316dd2620a5a02fbb10e8e`;
terminal SHA256 is
`90b6c8458ef5ebaebc18ab5eb5fa21bfae4a8d18d19982a236d050c60465838a`.
The separate frozen compiler is the exact tested pin, mode 0555.

## Actual emulator integration and restoration

All 166 distinct, ordered modes passed: 37 BIOS, 111 ordinary UEFI, seven BAR and
eleven IVRS. Two additional normal BIOS/UEFI images were separately rebuilt and
actually booted successfully afterward. All 168 command exits were zero and used
distinct owned sessions. Expected raw QEMU statuses were 53 occurrences of 33 and
115 of 35; both final normal boots returned 33. Injected fail-stop cases retain
their original validators and expected statuses.

The run completed at 22:59:16 UTC with unchanged inputs, a complete evidence seal,
restored normal images, no errors and quiescent ownership. Terminal SHA256:
`e48fcb174045d4ced7f320734ecad86d116c64b62795b3bd056acdecd5bca292`.
Independent final acceptance review SHA256:
`288c21ad63054c788045bb86b4e467d7792bf6e41c8da32c0439b2661c034e8c`.
It verified all 1,182 sealed entries, raw receipts and adapter identities, six final
images, 526 source files, 57,360 host records, 38 tools, twelve controls, admission,
compiler/archive ancestry and closed ownership.

The emulator phase used a separately admitted 512 MiB candidate ceiling, 160 MiB
entry ceiling, 280 MiB growth allowance, 64 MiB reserve and 1 GiB free-space floor.
Sampled candidate peak was 382,128,128 bytes. Native and compaction phases used
separate explicitly approved resource plans; their historical failures remain.

## Qualified fixture and preserved limits

BAR/IVRS use the separately qualified replacement firmware CODE SHA256
`24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268` and
unchanged pristine VARS
`5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e`.
The historical CODE image remains unrecovered; the replacement is not claimed
bit-reproducible. Its earlier accepted-M022 reference qualification and this fresh
compiler integration are distinct receipts. Three BAR refusal modes deliberately
use stock firmware. Archived real controls retain their original identity and are
revalidated rather than represented as newly generated controls.

These results do not establish whole-run zero interrupt activity, a named-event
valid-write witness, DMA isolation, physical AMD support or firmware security.
The bounded startup witness and existing BAR/IVRS validator limitations remain.

Earlier missing-tool and interrupted-supervisor attempts remain failed and
preserved, as does the undersized compaction archive attempt. No failed receipt
was relabeled or selected for retirement. The final evidence bundle retains all
three integration candidate histories. Publication must apply only the reviewed
source delta over the accepted base and preserve every unlisted remote path.
