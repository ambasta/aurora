# Verified Aurora interrupt-budget checkpoint

Verified locally on 2026-10-05 on the exact 533-file tested freeze below. A fresh
compiler build, complete native aggregate, all 170 actual emulator modes and two
additional normal BIOS/UEFI boots passed, with independent terminal reviews.

The Aurora policy computes interrupt-count next state and resume/exhaust. Its
private scalar bridge returns a copied value to trusted C++/assembly. Hardware,
ISR/frame/domain/epoch authority, live grants and cancellation remain bootstrap
mechanisms. No general scheduler, native kernel, physical AMD support, source-
safety proof or equivalent-C performance result is established.

## Exact source and compiler

- Publication baseline: PR21 main `758458e8258b76b24f7c29e06a2ce01a83766b68`;
  tree `df584b38be517aa444257c90f5c7897487d484f8`.
- Tested source manifest SHA256:
  `627fb53116ec13b72cd3d755dd190abb2f6ab59cc3cecb6e4560cd3cefbb0c25`.
- Rebuilt and separately frozen compiler SHA256:
  `8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631`.
- Ordered 170-mode tuple digest:
  `9a597765dbba45b9c8a19cd3652ca54740657e3080fd0c025fd25564721d6a47`.

This source checkpoint changes only result documentation and this index after
the test freeze. Its separate source manifest and narrow PR21 delta identify all
post-test documentation changes. Unlisted remote historical files are preserved;
the source subset must never replace the full remote tree.

## Successful fresh chain

[receipts.json](receipts.json) gives full hashes and artifact-relative paths.
The complete evidence backup uses `fresh/` for the accepted candidate evidence,
`historical/` for separately classified earlier records, and `recovery/` for the
interruption investigation. Its packaging manifest supplies the completed archive
hash; that backup does not alter the tested source or this checkpoint.

- Fresh compiler terminal `064aafd7f940082565e1f350fdf363367c1a2f773924182428df4c80cc3a96fb`.
- Full native terminal `fe9650562ef30942301752433d5e6f78b4cb4334645ebfd2e17a121960ed119e`.
- Full native independent review `a86e5a72e27b1a0aea66fcb7a8c22198b2f5315ff238cfea0a16a92eb567b137`.
- Fresh 170+2 terminal `e151f2d6c2c3b56afcd5bb2c3ad4ef9f10cdf59f0d154a27b4646139535ce88b`.
- Emulator evidence seal `48a9148d1998fea06993b9ad5b5555751929c4f216cc76020b59f4382c139508`.
- Emulator independent review `1910abec87efb431f744a144c3bef89e6535190751bf7ae9c586ea6c11e406fe`.

The native result includes 104,120 policy cases, 815,301 decoder cases and ten
rejection runs. Historical independent corpora overlap these cases and are not
added to those counts. The fresh actual emulator run covers 37 BIOS, 115 UEFI,
seven BAR and eleven IVRS modes, followed by two more normal boots. All four new
policy modes pass; the output mode matches five reviewed linked-image members
before boot. Independent review replays validators, all 18 BAR/IVRS traces and
provenance records, stack checks, native archive members and final image checks.

## Earlier failures and interruption

The initial full-170 run remains FAIL, terminal
`2de39384f8eefc19c923a61ab596174c822e6e235c5b083679646623d53e6e82`.
The live size census raced a disappearing owned build descendant after 46
completed modes. Its closed failure receipts and verified preservation archives
remain historical.

The subsequent continuation stopped after 88 additional completed modes, through
global ordinal134. The next mode began rebuilding but has no completed receipt.
No successful continuation terminal or final normal pair exists; its unresolved
lease remains preserved. Namespace-local process listings did not establish
global quiescence. The fresh acceptance run used a new source/build/receipt root
and contributes all 170 modes itself, with no historical prefix credit.

## Preserved scope and limits

Qualified clean-firmware CODE remains
`24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268`;
original VARS remains
`5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e`.
Fresh applicable VARS copies belong to each test output. No new firmware
qualification, physical device, device activation or bootloader action occurred.
The historical constant-folded output-fault probe is not relabeled as dynamic
decoder coverage. Source documentation, publication and local verification are
separately identified, with no implicit merge or release claim.
