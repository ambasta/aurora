# XFS root offline slices

These four canonical hex files decode to exactly 512 bytes each. They were
reconstructed after a workspace reset and matched previously recorded full
SHA-256 identities. The original full filesystem images and their old local
xfs_db receipts were lost; no fresh full-image or xfs_db execution is claimed.
The two roots are v3 512-byte local directories at root inode128/byte offset65536.
Empty: count0, payload6, parent128. Named: count2, payload31; alpha maps to inode131,
raw type1, saved offset96; docs maps to inode132, raw type2, saved offset120.
These numbers establish fixture bytes and checked geometry, not allocation or
file-data existence. Names are raw bytes, not a Unicode guarantee.

Exact decoded hashes:

- empty-superblock.hex: 55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586
- empty-root.hex: 963d4d1ae9f5821528cdeaac5dbc65abc0a4146a737dab84ade621a12d2c326e
- named-superblock.hex: 9fd8b9f7bfa7d12c99ae6e7b3a7633cc3ab48c45ff5facde79c36ad69503edb7
- named-root.hex: 283d31448057d3a9b1406cf655274b799e0636abb32e466b40c15bf3df9d265b

The retained recovery receipts record how those bytes were reconstructed; exact
identity was established only after the complete 512-byte hashes matched.
Neither fixture creation nor any device access is needed to run the test suite.
