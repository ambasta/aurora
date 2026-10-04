# Reviewed initialization-fact storage evidence

The integrated change replaces only local must/may initialization sets with
checked dense bits. It introduces no mutable-byte-view language feature.
Baseline checks and exact reviewed input/delta identities are recorded here.

Author evidence includes the complete isolated release and sanitizer target,
main release target, integrated affected sanitizer replay,64 differential cases,
scalar semantic harness/default630/stress1526 on both pins,7,405,472 set-model
checks and956 IR cases. Independent review includes37,126,294 instrumented set
checks, finite source/diagnostic equivalence, native output controls and both
dense and sparse resource measurements. Counts overlap; they are not summed.

Only the instrumented IR-test binary uses explicitly approved -g1 debug metadata.
All runtime sanitizer checks, -O1, fatal errors and frame pointers remain. Other
instrumented binaries retain -g. Full-debug cc1plus SIGKILL (cause unknown), the
2GiB capped matching-flags allocation failure, initial LSan environment failure
and initial exhaustive-fixture missing-header failure remain separate receipts.
The final complete sanitizer target passed after the scoped accommodation.

Dense-fact workloads improve, but declared-universe bitsets cost memory even for
empty facts. A source-reachable sparse-prefix case increases RSS about10.7%; the
larger IR-only sparse case is also documented. No universal memory/runtime gain
or compiler-wide resource budget is claimed. See compiler/RESOURCE-NOTE.md.

`independent/` contains selected byte-exact text receipts and the original review
manifest. `independent-distribution.json` maps omitted generated artifacts to the
complete unchanged local archive and their hashes; no binary was normalized into
text. Main kernel/combined milestone acceptance is separate and parent-owned.
