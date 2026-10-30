512-byte AGF/AGI sectors from the same pinned Linux 6.12.107 dirty history as xfs-core-redo. Four AGs, original before recovery; decoded hashes are in hashes.json. The reviewed Linux summary counts are inode count 64, free inode count 59, free blocks 114656. Mutated test inputs are synthetic and CRC-repaired, not interoperability evidence.

INOBT blocks are the original complete 4096-byte root leaves at AG-local block3.
AG0 contains one full (non-sparse) record starting at inode96 with freecount59
and mask0xffffffffffffffe0, so96 through100 are allocated. The other roots are
empty. AG header fields and CRC offsets follow Linux v6.12.107
fs/xfs/libxfs/xfs_format.h; validation and counter meanings follow
xfs_alloc.c:xfs_agf_verify, xfs_ialloc.c:xfs_agi_verify/xfs_inobt_check_irec,
and xfs_ag.c:xfs_initialize_perag_data. Synthetic later-record cases verify
that finding an allocated target does not bypass the rest of the tree.
