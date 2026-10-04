# Independent final acceptance: read-only UTF-8 line scanner

**Accepted as a verified local library checkpoint on 2026-10-04.** The independent
review found no product defect. The frozen implementation passed 875 independent
native cases / 3,500 complete i64 observations, 15 rejection controls, and one
checked-bounds SIGILL control. The actual fresh top-level aggregate passed with
exit 0, including the line Make target, previous UTF-8 gates, compiler/image/hosted
kernel/UEFI/semantics checks, and inherited package-identity gate. Repeated test
populations overlap; these numbers are not a safety or performance proof.

## Exact tested and reviewed identities

- Base commit: `d8222ad235fa218629266aa28e7b42ba87f4ee5e`.
- Base tree: `b8369852f9b316680bb24ee54ed228f1b4b5a095`.
- Tested freeze: 477 files; SHA-256
  `a50baa8175acae6b308d1ab3212ff796c6298139b76f91d2fec8062b93549c8f`.
- Unchanged M022 compiler SHA-256:
  `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
- Fresh aggregate receipt SHA-256:
  `63e4063ce002d6d6653b8ff722af21e672156ca0dbb7fbed818f8d721d5e4ea6`.
- Full independent review SHA-256:
  `003749f5bb64ffc86846b6500bd4ddd4eb7ae4a1a3ed82067042cb401f1aadf2`.
- Independent aggregate audit SHA-256:
  `c95c70bf28c6b981135f960b68f7ed6355019b48cb92e9091da6bdcbcaa36864`.

The subsequent result-only package was independently verified as 505 files.
Exactly four result/status documents changed from the tested freeze, with 28
evidence files added. No tested implementation, test, Makefile, compiler, kernel,
or old API changed after the aggregate. All copied evidence matches its original
bytes. All available tool executable identities still match.

- Result-source manifest SHA-256:
  `32bd6e936aa392ca26f2dcb651f3e78d979d616d620cb490d3224de9cd167c91`.
- Result-source archive: 1,546,064 bytes; SHA-256
  `b77cc998788f0f49c3bf9df618292a49618a0fb47419428509ce75598cabcbef`.
- Incremental publication manifest SHA-256:
  `e75d385d29c440a3b2dd9862a0c29028ce88cd9543e9cb8869168c84a1ac2c18`.
- Independent result-source verification SHA-256:
  `81e1aff9c97443e5b601554e93246d0f8b7f8e83562849a1ad9330ca09fde1c3`.

Every result archive member was checked for exact path, regular-file type, bytes,
length, and mode. The incremental publication set is exactly four updates and 32
additions relative to the verified base, with no deletions; Git blob identities
and update-base preconditions match. Unlisted historical remote paths must be
preserved. This is not authorization to replace a remote tree or publish.

## Permitted final evidence append

Acceptance carries forward when this exact file is copied, without alteration,
to `docs/evidence/utf8-lines-pr17-20261004/final-seal.md`, and the final source
manifest/archive adds only that file. All prior 505 entries must remain identical
in bytes, length, and mode. The resulting inventory must contain 506 source files
and an incremental manifest of four updates / 33 additions / zero deletions.
Regenerating companion inventory/archive metadata is permitted; no other source
change is covered by this append allowance. Final archive identities must be
reported and verified independently of this pre-append identity record.

The acceptance scope remains the copied read-only consumed-line API. It adds no
stream buffering, broad Unicode line-breaking, terminal action, heap/view API,
compiler/kernel feature, optional feature, extent reader, framebuffer capability,
sanitizer/emulator qualification, physical hardware support, or performance claim.
Remote publication, merge, main adoption, and release remain separate actions.
