"""Finite HOST model; no filesystem, device I/O, target code, or hardware proof.

Each pending record has two modeled sectors. At a crash, either, both or neither
can contain the new bytes; other bytes are zero in a freshly reserved location.
Successful persistence fences fix preceding dependencies as durable. SHA-256 is
used only as an executable integrity oracle (collision resistance is assumed).
The envelope/JSON format is model-only, NOT Aurora's proposed disk format.
"""

from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json

MAGIC = b"AMDL"
VERSION = 1
HEADER_SIZE = 44
MAX_BODY = 8192
MAX_SEQUENCE = (1 << 64) - 1
MAX_OUTCOME_CAPACITY = 64
FS = "volume-7"
EPOCH = 3
SEQUENCE = 11
OLD = {"a": "old-a", "b": "old-b"}
NEW = {"a": "new-a", "b": "new-b"}


class Corruption(Exception):
    """A recognized commit cannot safely be recovered; never silently roll back."""


class Conflict(Exception):
    pass


class OutcomeExpired(Exception):
    pass


class Pressure(Exception):
    pass


def digest(data):
    return sha256(data).hexdigest()


def seal(kind, body):
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    if kind not in (1, 2, 3) or len(payload) > MAX_BODY:
        raise ValueError("model record bounds")
    prefix = MAGIC + bytes((VERSION, kind, 0, 0)) + len(payload).to_bytes(4, "little")
    return prefix + sha256(prefix + payload).digest() + payload


def decode(data, kind):
    """Return None for absent/torn/invalid envelopes, before interpreting a body."""
    if not isinstance(data, bytes) or not HEADER_SIZE <= len(data) <= HEADER_SIZE + MAX_BODY:
        return None
    if data[:4] != MAGIC or data[4] != VERSION or data[5] != kind or data[6:8] != b"\0\0":
        return None
    size = int.from_bytes(data[8:12], "little")
    if size > MAX_BODY or len(data) != HEADER_SIZE + size:
        return None
    if sha256(data[:12] + data[HEADER_SIZE:]).digest() != data[12:44]:
        return None
    try:
        value = json.loads(data[HEADER_SIZE:])
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def require(condition, message):
    if not condition:
        raise Corruption(message)


def transaction():
    """One bounded transaction atomically replaces exactly two model objects."""
    records = {}
    refs = []
    for object_id in ("a", "b"):
        slot = "data-" + object_id
        records[slot] = seal(
            1, {"fs": FS, "epoch": EPOCH, "object": object_id, "generation": 8, "payload": NEW[object_id]}
        )
        refs.append({"slot": slot, "object": object_id, "generation": 8, "digest": digest(records[slot])})
    records["manifest"] = seal(
        2,
        {
            "fs": FS,
            "epoch": EPOCH,
            "sequence": SEQUENCE,
            "previous": SEQUENCE - 1,
            "request": 1,
            "request_digest": digest(b"replace a and b"),
            "refs": refs,
        },
    )
    records["commit"] = seal(
        3,
        {"fs": FS, "epoch": EPOCH, "sequence": SEQUENCE, "manifest": "manifest", "digest": digest(records["manifest"])},
    )
    return records


def recover(image):
    """Model a known previous checkpoint plus one terminal transaction slot.

    An invalid terminal commit is ignored as uncommitted. This rule must NOT be
    generalized to corrupt interior records or a selected checkpoint/root chain.
    A valid commit with a bad dependency is Corruption, even if unacknowledged.
    """
    commit = decode(image.get("commit"), 3)
    if commit is None:
        return dict(OLD), None
    require(set(commit) == {"fs", "epoch", "sequence", "manifest", "digest"}, "commit schema")
    require(commit["fs"] == FS and commit["epoch"] == EPOCH, "commit identity")
    require(commit["sequence"] == SEQUENCE and commit["manifest"] == "manifest", "commit sequence/location")
    raw_manifest = image.get("manifest")
    require(isinstance(raw_manifest, bytes) and digest(raw_manifest) == commit["digest"], "missing/corrupt manifest")
    manifest = decode(raw_manifest, 2)
    require(manifest is not None, "invalid manifest envelope")
    require(
        set(manifest) == {"fs", "epoch", "sequence", "previous", "request", "request_digest", "refs"}, "manifest schema"
    )
    require(
        manifest["fs"] == FS
        and manifest["epoch"] == EPOCH
        and manifest["sequence"] == SEQUENCE
        and manifest["previous"] == SEQUENCE - 1,
        "manifest identity/sequence",
    )
    require(type(manifest["request"]) is int and manifest["request"] == 1, "request identity")
    require(manifest["request_digest"] == digest(b"replace a and b"), "request digest")
    refs = manifest["refs"]
    require(isinstance(refs, list) and len(refs) == 2, "reference bound")
    staged = {}
    for ref in refs:
        require(isinstance(ref, dict) and set(ref) == {"slot", "object", "generation", "digest"}, "reference schema")
        object_id = ref["object"]
        require(isinstance(object_id, str) and object_id in OLD and object_id not in staged, "duplicate/unknown object")
        require(ref["slot"] == "data-" + object_id and ref["generation"] == 8, "extent location/generation")
        raw = image.get(ref["slot"])
        require(isinstance(raw, bytes) and digest(raw) == ref["digest"], "missing/corrupt extent")
        body = decode(raw, 1)
        require(body is not None and set(body) == {"fs", "epoch", "object", "generation", "payload"}, "extent schema")
        require(
            body["fs"] == FS
            and body["epoch"] == EPOCH
            and body["object"] == object_id
            and body["generation"] == ref["generation"],
            "extent identity/generation",
        )
        require(isinstance(body["payload"], str) and len(body["payload"]) <= 32, "payload bound")
        staged[object_id] = body["payload"]
    # Atomic publication: never modify the old state while checking dependencies.
    require(set(staged) == set(OLD), "incomplete transaction")
    return staged, (manifest["request"], manifest["request_digest"], SEQUENCE)


@dataclass(frozen=True)
class Cut:
    name: str
    submitted: tuple
    durable: frozenset
    acknowledged: bool = False


def protocol(dependency_fence=True, commit_fence=True):
    """Event prefixes. Ordinary completion deliberately implies no persistence."""
    submitted = []
    durable = set()
    yield Cut("initial", (), frozenset())
    for slot in ("data-a", "data-b", "manifest"):
        submitted.append(slot)
        yield Cut("submit-" + slot, tuple(submitted), frozenset(durable))
        yield Cut("ordinary-complete-" + slot, tuple(submitted), frozenset(durable))
    if dependency_fence:
        durable.update(submitted)
        yield Cut("dependency-fence-complete", tuple(submitted), frozenset(durable))
    submitted.append("commit")
    yield Cut("submit-commit", tuple(submitted), frozenset(durable))
    yield Cut("ordinary-complete-commit", tuple(submitted), frozenset(durable))
    if commit_fence:
        durable.update(submitted)
        yield Cut("commit-fence-complete", tuple(submitted), frozenset(durable))
    yield Cut("publish", tuple(submitted), frozenset(durable))
    yield Cut("acknowledge", tuple(submitted), frozenset(durable), True)


def sector_projection(record, mask):
    """Two abstract sectors, not real device sector size or an atomicity claim."""
    if mask == 0:
        return None
    split = (len(record) + 1) // 2
    first = record[:split] if mask & 1 else bytes(split)
    second = record[split:] if mask & 2 else bytes(len(record) - split)
    return first + second


def crash_images(records, cut):
    """Enumerate all masks for all submitted, not-yet-fenced records at this cut."""
    pending = [slot for slot in cut.submitted if slot not in cut.durable]
    for masks in product(range(4), repeat=len(pending)):
        image = {slot: records[slot] for slot in cut.durable}
        choices = dict(zip(pending, masks))
        for slot, mask in choices.items():
            projected = sector_projection(records[slot], mask)
            if projected is not None:
                image[slot] = projected
        yield image, choices


def verify_protocol(dependency_fence=True, commit_fence=True):
    records = transaction()
    count = 0
    violations = []
    unacknowledged_new = 0
    for cut in protocol(dependency_fence, commit_fence):
        for image, choices in crash_images(records, cut):
            count += 1
            try:
                state, receipt = recover(image)
                if state not in (OLD, NEW):
                    reason = "mixed atomic transaction"
                elif cut.acknowledged and state != NEW:
                    reason = "acknowledged commit lost"
                else:
                    if not cut.acknowledged and state == NEW:
                        unacknowledged_new += 1
                    continue
            except Corruption as exc:
                reason = str(exc)
            violations.append({"cut": cut.name, "masks": choices, "reason": reason})
    return {"crash_images": count, "violations": violations, "unacknowledged_new_states": unacknowledged_new}


class OutcomeWindow:
    """Bounded result retention for one client with monotonic request numbers.

    Terminal outcomes are positive u64 durable commit sequence numbers, not
    arbitrary Python values (in particular None/bool are rejected). None from
    query therefore unambiguously means no retained terminal outcome. This helper
    models the retry API only, not a persistent journal implementation. The real
    journal must preserve its floor and live results in checkpoints.
    """

    def __init__(self, capacity):
        if type(capacity) is not int or not 1 <= capacity <= MAX_OUTCOME_CAPACITY:
            raise ValueError("capacity")
        self.capacity = capacity
        self.floor = 1
        self.entries = {}

    def query(self, request, request_digest):
        if type(request) is not int or not 1 <= request <= MAX_SEQUENCE:
            raise ValueError("request")
        if not isinstance(request_digest, str) or not 1 <= len(request_digest) <= 128:
            raise ValueError("request digest")
        if request < self.floor:
            raise OutcomeExpired(request)
        if request not in self.entries:
            return None
        prior_digest, outcome = self.entries[request]
        if prior_digest != request_digest:
            raise Conflict("request identity reused with different content")
        return outcome

    def record(self, request, request_digest, outcome):
        if type(outcome) is not int or not 1 <= outcome <= MAX_SEQUENCE:
            raise ValueError("outcome must be a positive u64 commit sequence")
        prior = self.query(request, request_digest)
        if prior is not None:
            if prior != outcome:
                raise Conflict("terminal outcome changed")
            return prior
        if len(self.entries) >= self.capacity:
            raise Pressure("outcome window full")
        self.entries[request] = (request_digest, outcome)
        return outcome

    def expire_through(self, request):
        """Explicit protocol-authorized expiry, not time-implied non-commit."""
        if type(request) is not int or not self.floor - 1 <= request <= MAX_SEQUENCE:
            raise ValueError("expiry")
        self.floor = request + 1
        self.entries = {key: value for key, value in self.entries.items() if key >= self.floor}
