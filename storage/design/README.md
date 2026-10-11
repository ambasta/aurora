# Aurora native storage and XFS design package

This package adapts the user's 56-section NVMe-native filesystem
proposal to Aurora and adds the separately requested XFS on-disk compatibility
target. It is an engineering requirements package, not a working filesystem.

- `original-requirements.md`: byte-for-byte preserved user input (26,360 bytes).
  SHA-256: `72ff3628f4d8043560c5a2055b507e4881178b29fc95a9212f6955804aa64bf6`.
- `requirements.md`: adapted requirements, mandatory safety contracts, XFS stages.
- `traceability.md`: every original numbered section and the new XFS requirement.
- `roadmap.md`: dependency order, observable acceptance gates, and blocking gaps.
- `sources.md`: primary specifications, research, limitations, and access date.
- `model/`: executable, in-memory **host verification model** of a small durability
  protocol. It does not implement an Aurora driver, disk format, or filesystem.

The native engine and XFS adapter will share the safe storage transport contract,
not an on-disk format or Linux implementation. Native durable transactions,
bounded recovery, isolation and integrity precede throughput claims. The complete
target includes read-write XFS; clean read-only XFS is an intermediate gate.

Run the host checks from this directory:

```sh
python3 model/test_durability.py
python3 model/check_traceability.py
python3 model/test_traceability.py
```

The document-checker mutation tests create disposable copies under the temporary
directory; all other work uses memory and files in this package. They do not open
devices, mount filesystems, load drivers, or format media. Do not apply this
experimental design to a user's disk. Physical qualification needs a separately
authorized dedicated test setup and cannot follow from host/model results.
