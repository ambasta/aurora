# Independent pre-implementation XFS geometry source review

Scope: the exact proposal SHA256 40021cf66fba001094c9f0762475075967b64bd4f55b8be845490ddf37fc5b86, with subsequent explicit precedence clarifications recorded separately. No Linux implementation bodies are copied into Aurora. Local `sources/` files are primary-source research references only; Git blob identities are independently recomputed in `evidence/sources.json`.

Primary repository: https://github.com/torvalds/linux/tree/038d61fd642278bab63ee8ef722c50d10ab01e8f (Linux v6.16). Read-only retrieval on 2026-10-03.

## Confirmed requirements

- `xfs_format.h` lines 702–711 distinguish encoded AG/address composition from linear device placement. Physical start is `(g*A+a)*B`, not `F*B`. Non-power-of-two AGs leave encoded-address gaps. Keep decoded AG number as u64 before range checking, unlike an unsafe narrowing-port interpretation of the C macro.
- `xfs_ag.c` lines 137–157 derive the final AG length from D minus the nominal previous groups. `xfs_fs.h` lines 259–282 establish nominal 16 MiB–1 TiB bounds and the 64-block final minimum. The final group itself need not meet the nominal byte minimum.
- `xfs_sb.c` lines 42–73 require the legacy v5 flags. The format known masks and local-profile allowlists have different meanings. Unknown and recognized-but-excluded bits must remain separately observable, regardless of first error.
- `xfs_sb.c` lines 275–307 require no-realtime count fields zero but preserve nonzero rextsize. It does not require the rt inode numbers zero. The canonical fixture's rt inode numbers 129 and 130 must remain accepted and uninterpreted.
- `xfs_sb.c` lines 500–550 establish SPINODES alignment and optional zero spino_align. Very large blocks can yield a zero expected full-chunk alignment by integer division; do not add a nonzero requirement absent from the contract.
- `xfs_sb.c` lines 593–757 support ceil AG geometry, exponent/size relations, imax_pct zero, log maximums, and log-sector absence semantics. The proposal deliberately avoids reproducing C narrowing or potentially overflowing expressions.
- `xfs_log.c` lines 1398–1433 accept logsunit 0 or 1 as unstriped and default the log sector to 512 when absent. A valid header is not evidence of a clean log.
- `xfs_types.c` lines 20–76 excludes the AG header blocks and requires same-AG extent bounds. This is not a proof that the log avoids every metadata allocation.
- `xfs_log.c` lines 615–644 computes a feature-dependent mount-time minimum log size separately. The proposed header facts deliberately make no fixed minimum-log adequacy claim.

## Clarifications and acceptance limits raised before code

1. Required version bits and required features2 bits both precede excluded version/features2 bits. Parent confirmed this order through the implementer.
2. imax_pct/shared_vn use inconsistent_header/misc_geometry after all log geometry checks, immediately before success. This is the parent's explicit total-order refinement, not an inferred upstream read order.
3. Present log-sector non512 declarations need an explicit coherent-profile-versus-contradiction classification; reviewer asked to distinguish these or document the chosen blanket profile check. Final parent choice is a blanket profile rejection: present SECTORBIT any pair other than512/9 is unsupported_layout/log_geometry; absent bit nonzero pair is inconsistent_header/log_geometry. This deliberately does not distinguish scalar contradictions inside excluded declared log-sector pairs.
4. Explicit overflow guards made redundant by prior field-width/range invariants cannot honestly be mutation-killed by a fixed512 input. For example `(N-1)*A <2^64` follows from u32 fields, and lastAGByteStart is bounded by a successfully checked D*B. Source audit and a stated implication are valid evidence; fabricated executable kills are not.

## Review boundary

This slice interprets only the listed header facts. It does not read a device, inspect an image remainder, traverse metadata, prove log cleanliness, validate a mount, establish read-only compatibility, or qualify hardware. Positive synthetic inputs are CRC-repaired headers, never relabeled real filesystems. Native test acceptance is finite evidence, not an exhaustive no-trap proof.
