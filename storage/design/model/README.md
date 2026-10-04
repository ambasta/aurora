# Host-only durability model

Run `python3 model/test_durability.py` from the package root. Python's standard
library is sufficient. No install, device access, network, mount, user-file read,
disk-image write or target code is involved. The executable uses only in-memory
Python objects. `check_traceability.py` separately reads the package documents.
`test_traceability.py` makes disposable temporary copies of those documents and
checks mutation rejection in subprocesses both normally and under Python `-O`.
It removes only its own temporary copies afterward.

## What it checks

The baseline is a known-good checkpoint with two objects. One bounded transaction
replaces both objects via two payload records, one manifest and one commit. At
every modeled event prefix, enumerate all four persistence masks for each
submitted, unfenced record: neither abstract sector, first only, second only,
or both. Prior completed persistence fences constrain their records to intact
media. Ordinary command completion is deliberately not a persistence fence.
The source's single-final-flush sequence is tested as a deliberately broken
alternative. An early durable acknowledgement is another deliberate mutant.

The recovery function validates the terminal commit, manifest and object
identity/generation/checksum relationships before atomically publishing either
the two old or two new values. A valid commit with invalid/missing dependencies
raises corruption; it does not silently return the old checkpoint. A committed
transaction may be recovered even if no reply was received. The separate bounded
outcome-window helper checks retry consistency, digest conflicts, backpressure
and explicit expired-token results. Terminal outcomes in this narrow helper are
positive u64 commit sequence numbers; None, bool and other Python values are
rejected. Query's None therefore means no retained terminal outcome. Request
numbers are positive u64, digest strings contain 1–128 characters, and the
modeled window capacity is an explicit integer from 1 through 64. It is not
itself a durable result journal.

Adversarial tests additionally flip one bit at every byte position, truncate at
every byte boundary, append extra bytes, recompute checksums over wrong identities,
change sequences and use malformed/duplicate references. These are specific
finite tests, not a fuzzing campaign or a memory-safety proof.

## Fault model and assumptions

- New records use separate fresh locations with zero-filled old bytes. Existing
  checkpoint data is immutable and survives; the model does not reuse sectors.
- Every record is represented by exactly two abstract sectors of nearly equal
  byte length. These are not NVMe sectors or power-fail atomic units. Enumeration
  covers every combination in this finite abstraction, not all physical tears.
- A successful persistence fence makes its required records durable and intact;
  device firmware obeys this contract. Pending writes can persist independently.
  Fence failure paths are represented by crash cuts before successful completion,
  not by a full transport error state machine.
- SHA-256 is an integrity oracle under a no-collision assumption. The toy
  envelope plus JSON is model-only and not Aurora's native format. Hash validity
  alone is insufficient; explicit identities and generations are checked.
- Invalid terminal commit bytes are treated as an uncommitted tail. This is only
  valid for the modeled append-only single tail and power-loss scenario. Do not
  generalize it to latent post-ack media corruption, an interior log record,
  corrupted selected roots or sequence gaps.
- There is one filesystem, one epoch, one previous checkpoint, one writer,
  one transaction and exactly two updated objects. No concurrent dependency
  graph, checkpoint publication, GC/reclamation, quota, snapshots, DMA, IOMMU,
  NVMe driver, SMP, cross-shard coordination, XFS or target Aurora execution
  exists in this model.
- Published state is a Python dictionary built after validation. This models an
  atomic decision; it does not implement or prove CPU memory-order publication.
- Repeated event prefixes overlap in represented states. Printed crash-image
  counts count evaluations, not unique global histories or physical failure
  modes. Do not add them to unrelated test counts as independent coverage.

## Expected qualitative outcomes

Safe two-fence protocol: no violation in the finite model; acknowledged writes
recover new state, and some unacknowledged writes also recover new state.

Without the dependency fence: a complete commit can survive while its manifest
or data do not, causing diagnosed corruption. A final flush cannot prevent a
power loss that occurs before that flush successfully completes.

Without the commit fence: the model finds an acknowledged write whose commit
did not persist, recovering the old state and violating the acknowledgement.

This is useful early design evidence and a mutation-tested regression mechanism.
It is not a formal proof, a benchmark, or delivered filesystem functionality.
