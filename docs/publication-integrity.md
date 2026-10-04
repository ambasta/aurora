# Repository receipt byte preservation

A publication audit on 2026-10-03 found that the earlier JSON snapshot preparation
used text-mode universal newline conversion. This changed CRLF serial transcripts
to LF while the original source archives and test hash receipts retained raw bytes.
The issue concerns publication evidence byte identity, not a reproduced compiler
or kernel execution defect.

For milestone012, 578 files differ between original tar and prepared JSON; for
milestone013, 857 differ. Every difference is under docs/evidence and is explained
exactly by CRLF-to-LF conversion. Membership and Git modes match; the archives
contain only regular files. Compiler, kernel and other files outside evidence
remain byte-identical. Current raw-source manifests pass 209/209 and 227/227 entries.
Original archived kernel receipt manifests also pass; normalization instead breaks
563 referenced hashes in milestone012 and 841 in milestone013.

The normalized milestone012 JSON reconstructs Git tree
1fbb144070992a80e2d90ed5304dc74db09e4288, matching the published checkpoint receipt.
The byte-preserving source-archive trees are:

- milestone012: c43ac8033b7a290308a9fec2c46e251ff8f372ec
- milestone013: 9a9ea9e8a4a815cfa0e977ac9d67887404038502

Available milestone006–011 archive/JSON pairs have the same CRLF-only class of
change. That comparison is local evidence; it is not an assertion that every
older remote commit has been independently fetched and verified.

Original tars, JSON snapshots and commits are retained unchanged. New snapshots
use tools/publication/snapshot_bytes.py, which decodes raw UTF-8 bytes without
newline conversion, asserts exact byte round trips, checks modes/member paths and
computes Git object identities. Seventeen normal and optimized regression tests
cover newline forms, Unicode, empty data, no final newline, modes, member safety,
delta reconstruction and Git object ordering. The corrected milestone013 delta
from the actually published normalized milestone012 tree includes 578 historical
byte repairs as well as milestone013 changes. It must not resume the obsolete
partially uploaded normalized delta.

This main-tree snapshot preserves the original evidence bytes. Remote repair is
a separate publication action; preparing a corrected tree does not establish that
it has been uploaded. The original source archives remain the byte-exact authority
for the tested historical checkpoints. See evidence/milestone-014/publication-audit
for the audit report and independent test reruns.
