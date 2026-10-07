# Direct owned-field mutation: focused results

Date: 2026-10-07. The bounded [source/IR contract](../compiler/OWNED-FIELD-MUTATION.md)
passed the focused checks below. Independent source, retained machine-code and
final documentation claim review accepted this bounded scope.
This is not a full native aggregate, sanitizer or emulator qualification.

## Identity and mechanism

The verified base is main `92e28a823afe56af774a128df8f9093083f26e29`, tree
`3801b9524589ce363f7ce00aae505c88c7d86679` (682 files, after PR53).
All base content/blob hashes and the complete reconstructed Git tree matched.
The final exercised source manifest is
`3375ce325d5086d07ab05db3153affc9f43dafc703edab03aff40c3e6251b0a5`;
subsequent results/status edits are documentation-only. The production compiler
source did not change after its initial independently reviewed build.

A direct owned class field can receive a complete independent replacement or
act as a synchronous method receiver. Mutable authority comes from its named
local or bound nonconstructor receiver root. Private access, readonly parameters,
complete initialization, exact nominal identity, distinct copied arguments and
fresh results remain checked. No scalar capability, escaping reference,
constructor bypass, deeper field path or new allocation convention is added.

The fresh GCC 14.2.0 build used C++23, `-O2 -Wall -Wextra -Wpedantic -Werror`.
The host used Python 3.12.14 and GNU binutils 2.44. Exact binaries:

- Compiler: `f44ecd5ae4cad266ca8cff62d42cd3970c61a4bcc04e025cd68e2b5f0656cdbd`
- Owned-field IR fixture: `6a426473aec0e1711de52e59ba158e99a46ae12611445ac1fad86d8f7de15c9e`
- Stack-probe fixture: `560930733e44c558461c63fb2957d065b41478ef549544f754620404867efbcb`

## Passed focused components

- 55 direct-IR checks: nine accepted shapes and 46 malformed-IR rejections
- 50 source cases per Python mode: 16 ordinary native cases, two exact bounds
  traps and 32 rejection runs, including prior-output preservation
- 12 handwritten private-ABI cases per Python mode, covering local/implicit
  roots and scalar, result-only and combined argument-record/result modes
- 47 stack-probe IR/assembly checks; 15 isolated guard cases in each Python mode
- Seven complete core runners: classes, value calls, fixed containers,
  composed values, nested values, method values and function templates
- Nine complete storage runners: packed values, sector values, owned sector,
  byte codecs, binary writer, block values, RAM blocks, block I/O and storage binary
- All 31 unchanged public examples, including kernel policy examples, emitted
  byte-identical assembly against reviewed compiler
  `762ba74b8b58d4c6ae7c335507a7b06560a90f44c98d268defa36e086fa41630`
- Ten exhaustive typed-IR dispatch controls passed after restoring the existing
  diagnostic-header dependency to that test's temporary-header copy list

The two new source/ABI modes use normal Python and `python -O`; assertions use
explicit checks in both. All 24 executed ABI ELFs, corresponding assembly and
full-width observations were retained. Independent disassembly checked canonical
child offsets, typed replacement stores, hidden registers, local ABI symbols,
argument/result separation and immediate stack probes. Each normal/optimized
ELF pair was byte-identical; the reviewer did not rerun native code.

Core acceptance is a preserved-success composite. Initial successful classes,
value calls and fixed containers were retained; composed values passed its
corrected complete replay; nested, method and function templates passed the
last counted-output continuation. Failed outer receipts remain failed. This
composite does not relabel an interrupted or failed phase as a complete pass.

## Preserved preparation and fixture corrections

The initially supplied source folder was the 677-file pre-PR52 join despite
being labelled PR53. Missing block-I/O inputs exposed the mismatch before any
build. The feature delta was rebased onto the independently verified 682-file
PR53 tree, with no production compiler-source change between those bases.

Two early new-source runs stopped at test declarations named `read` or `write`,
which are reserved builtins. The compiler correctly rejected them. Only fixture
names changed; their original failed runs and corrected source hashes remain.
Compile-only admission then checked all 50 new fixtures before complete native
replay. A further 245 legacy fixtures, including 226 rejections, passed separate
compile-only admission before remaining native regressions.

Two legacy rejection fixtures separately expected mutable whole-field copying
to fail. They now use const roots, preserving absent/existing-output rejection
checks while explicit mutable replacements have positive native coverage. These
failures are retained alongside the intentional positive transitions described
in the contract. No production compiler fix or rejection-oracle weakening was
needed during these executions.

The existing method, nested and function-template runners had hardcoded
source-tree temporary parents. They now honor the existing tempfile/TMPDIR
parent so outputs fall inside the invocation's counted root. The first nested
pass remains a functional result with that output-accounting limitation; its
complete corrected replay passed. The 60 KiB method failure reproduction was
preserved. These routing changes and the exhaustive-test header dependency are
available as a separate test-only patch from the language feature.

## Resource and qualification limits

The existing reviewed serialized controller retained its resource/process-control
logic, with task-specific command, source-verification and receipt adapters.
Each fresh phase had a 256 MiB output cap (32 MiB for guards), 32 MiB per-file
limit, 2 GiB child address-space limit, 120/130 CPU-second limits, 180-second
step deadline, 7.5 GiB available-memory admission floor and 1 GiB free-disk floor.
Build peak child RSS was 724,356 KiB. Child limits and sampled admission do not
establish a hard aggregate process-tree or whole-program runtime memory bound.
All accepted phases reached terminal receipts; original process sessions closed
before the lane was released. The exact-image integration below is separate.

The test-only fixes and documentation updates do not establish new storage API
consolidation, durability, hardware-sector access or filesystem support. No
whole-program stack proof, Rust-equivalent safety, C ABI, performance comparison,
copy-elision optimization, fresh host sanitizer gate, complete native aggregate
or physical AMD qualification is claimed.

## PR55 exact-image compatibility

The feature was composed with PR55 main
`1aba1f98386406f91f0695e73aeaaab159caa218`, tree
`284ee7aa2b6593a9b6f27c1c62e777e89e3d5285`. All 701 base files and the complete
Git tree were verified; compiler source/fixture identities remained unchanged.
The compared composition manifest was
`506f7e93bc90a4ef7f6192c50236f880ea015f12c11a4473e9e8d02f644eadca`;
this integration-results addition is documentation-only.

Fresh isolated old/new compiler builds used the ordinary strict image builders
for BIOS normal, BIOS console, UEFI normal, UEFI console and UEFI user-phases.
All 177 outputs per compiler were byte-identical: generated assembly, objects,
headers/metadata, ELF, flat payloads and BIOS disk/UEFI PE transport. The fresh
ELF/PE/disk anchors also matched retained PR55 admitted hashes. The five profile
output counts were respectively 34, 35, 28, 32 and 48.

The original comparison session reached exit zero on 2026-10-07 at 12:31:55 UTC.
The phase retained 127,442,944 bytes under its 256 MiB cap. No guest was rerun:
existing PR55 boot evidence remains applicable to these exact compared images.
This does not transfer qualification to unexamined fault/pending modes, add a
new emulator-matrix result or qualify physical hardware. Source and artifact
comparison received independent review before publication.
