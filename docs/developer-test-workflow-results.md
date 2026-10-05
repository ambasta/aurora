# PR26-based developer-test workflow results

The exact revision-5 implementation completed both full public native workflows
on the reviewed x86-64 GNU/Linux host with GNU C++ 14. Independent review accepted
the developer result through an explicit composite and the externally pinned
prebuilt result through its passed original terminal. The [compact evidence record](../evidence/developer-test-workflow/pr26-rev5-native-results.json)
contains the source, command, result and review identities.

The tested source has 572 files, manifest
`e097d1151156066b1147641ccc70092b729af9abc81c0fa0750c9314457dded9`, based on
accepted PR26 main `3ac216b64caf8b769147f1864aa8389011f0112b` and tree
`e47002622df3e8d13d9496cd09fe90b33794335b`. The later results overlay changes four
status documents and adds this document plus the compact evidence record.
All compiler, library, kernel, Make, test, script and frozen-oracle bytes are
unchanged. These results qualify that tested implementation; the documentation
addition is reviewed statically and is not described as a new native execution.

## Completed public commands

The developer run executed `/usr/bin/make --jobs=1 test`. It fresh-built the current
compiler once, recorded source/recipe/tool/flag/header inputs, and routed every
compiler consumer through its immutable run-owned compiler. The public command
and product receipt passed after 2,342.939 seconds.

The prebuilt run executed `/usr/bin/make --jobs=1 test-acceptance`, supplying the
read-only developer compiler path and the separately selected historical PR26
expected digest:

`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`

The expected digest was selected after independent complete-byte comparison with
accepted PR26 history. It was not promoted from the developer's observed hash
alone. P copied those bytes to its own distinct inode, mode 0555, and recorded
`externally-pinned-prebuilt` provenance. The actual complete public command passed
after 2,190.970 seconds, with zero bootstrap builds and no bootstrap build log or
dependency output. Both host-test flag vectors remained the default
`-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`.

## Preserved developer audit failure

The original developer outer terminal remains **FAILED**, with
`native_complete=false`, at digest
`40aa066a40f3f385491e175d4f8a92d0670af47deb07006ba0d70ba077a9e77c`.
The actual Make command and product receipt passed. The outer verifier had three
stale package completion-label expectations: it expected “pinned compiler
unchanged”, while the reviewed runners print “selected compiler identity
unchanged”. The first failed anchor was package graph. No command failure or
additional finalization error was waived.

A new read-only audit changed exactly those three strings, with all counts,
recipes, source/tool/compiler closure and generated artifacts unchanged. Its
result is `31d6793a70e97908c8b673368bb9ac667a896cf0adcb47189cc677d0456805be`.
Independent disposition
`9846d696716bec2faee70b2fdc88b85328bca841a8e1030ac7a3ac602665a5f1`
explicitly composes the original failed terminal, passed product and corrected
audit. The original failure is not relabeled, overwritten or represented as a
clean original run. No native workload was rerun for this metadata correction.
P's reviewed consumer requires this exact composition and the separate historical
pin selection; it does not generically accept failed prior terminals.

## Independent prebuilt terminal review

P's original outer terminal is passed, `native_complete=true`, digest
`63398d7d2b2ce5b0b57b77b78455b0e99ff5c045c757d8a1b0a7c5e3322b875e`.
The product receipt is
`691c72e945f119d530ca90e6aae754df4be1396069c372d617954aae63783e74`.
Independent terminal approval
`75c93f6795bc5e771ed4ef8a4adaafc2205ce0e4b9f7ed665511e517c8f1137d`
accepts the exact completed full public native aggregate with no blocker.

The review checked all three 572-file source roots, 57,362 host records,
23,802 P generated records, 23,804 unchanged D generated records, all current
product inputs, 345 retained gate artifacts, before/after references and exact
closed ownership. Historical, D and P compiler bytes match completely; P's copy
is a distinct object. It reconciled the 43 visible root recipes, 31 compiler
recipes, all 118 completion anchors and the full dependency graph to frozen source.

Each full public workflow ran both complete 70-method contract suites. The earlier
six-method Make stage independently covered 98 calls per mode: 55 dry runs and
43 rejecting preflights. Planned call categories remain distinct from their
observed success/rejection counts. Cap-only and other configuration checks retain
non-native scope and do not substitute for behavioral coverage. The retired
executable-expression probe remains unexecuted and uncredited; inert pre-dispatch
checks and static Make-guard inspection do not reproduce its omitted observation.

Selected complete native family results:

| Family | Cases or observations | Rejection runs |
|---|---|---|
| Package identity | 5,503 cases; 199,213 u64 observations | 40 |
| Package manifest | 20,022 cases; 1,827,671 u64 observations | 58 |
| Package graph | 5,548 cases; 333,671 u64 observations | 60 |
| Kernel budget | 104,120 policy; 815,301 decoder | 10 |
| Round-robin | 17,672 policy; 1,051,016 decoder; 4,096 copies | 10 |

The independent retained-data audit checked all 314 package archives and 8,792
members, compared raw observations with retained oracles, independently
recalculated every kernel policy/decoder row, and checked retained BIOS/user-image
bytes. UTF8, XFS, readonly, short-circuit, ABI, trap, rejection, storage and resource
gates remain in the complete aggregate. Family totals overlap and must not be
summed into a disjoint global case count.

## Resources and limits

The owned public command had a 7,200-second bound. The common retention cap was
2 GiB with a 64 MiB terminal reserve; permitted stage growth was 1 GiB, files were
bounded to 128 MiB, and free space retained a 1 GiB floor plus 3 GiB for prior work.
No blanket inherited CPU or address-space ceiling replaced existing per-harness
limits. P's recorded sampled peak was 1,116,491,776 bytes; independent final
allocation including the terminal was 1,117,167,616 bytes. Canonical cleanup was
quiescent, no owned processes remained, and the matching lease was closed.
These are sampled software resource guards, not kernel quotas. Read-only terminal
verification and sealing followed the timed public command.

Acceptance is scoped to the retained evidence. Some legacy compiler, readonly and
short-circuit runners discard or overwrite per-case output; their exact recipes,
completion anchors, summaries and surviving artifacts were checked without
inventing raw replay. Package/XFS/range/line oracles were not regenerated. UTF8
in-program loops were not reexecuted by the reviewer. The original tool-session
exit is author-observed; the reviewer independently checked the result, seal,
positive cleanup and closed lease, not a reconstructed historical process census.
Zero bootstrap builds is supported by the reviewed route, receipts, absent build
artifacts and private copy, not a system-wide execution census.

Prebuilt mode performs no fresh bootstrap-header discovery or comprehensive
per-recipe host-header/PCH attestation. These runs establish no new sanitizer,
QEMU, Gentoo/GCC 16 make-test, broad-host or physical-platform qualification, and
do not qualify later IPC changes. Build receipts neither supply external approval
nor prove compiler correctness, universal language safety, complete supply-chain
closure or resistance to a malicious compiler/builder. Existing PR26 emulator and
older PR25 focused evidence retain their own original source scope.
