"""Pure host reference model. No hardware adapter and no DMA authority.

Acknowledgements are injected observations from a hypothetical trusted adapter;
callers of this Python model can fabricate them. They are not security tokens.
"""
from dataclasses import dataclass
from enum import Enum, auto
from itertools import count

class Phase(Enum):
    EMPTY = auto()
    RESERVED = auto()
    INSTALLING = auto()
    MAPPED = auto()
    RUNNING = auto()
    QUIESCING = auto()
    INVALIDATING = auto()
    SCRUBBING = auto()
    RETIRED = auto()
    QUARANTINED = auto()

@dataclass(frozen=True)
class Binding:
    broker: int
    requester: int
    incarnation: int
    pages: tuple[int, ...]
    lease_generations: tuple[int, ...]
    map_generation: int

@dataclass(frozen=True)
class Completion:
    binding: Binding
    operation: int
    kind: str

class Lifecycle:
    """One requester, two exclusive pages, one mapping, one outstanding operation.

    No destructor or timeout releases pages. Quarantine has no recovery transition.
    max_generation is reduced in tests to exercise exhaustion without wrapping.
    """
    _brokers = count(1)

    def __init__(self, max_generation=255):
        if type(max_generation) is not int or max_generation < 1:
            raise ValueError("positive bounded generation required")
        self.broker = next(self._brokers)
        self.limit = max_generation
        self.phase = Phase.EMPTY
        self.incarnation = 0
        self.operation = 0
        self.page_generations = [0, 0]
        self.binding = None
        self.pending = None
        self.pinned = False
        self.zeroed = True
        self.may_dma = False
        self.translation_visible = False
        self.quiescent = True
        self.invalidated = True

    def reserve(self, requester=0x10):
        if (self.phase not in (Phase.EMPTY, Phase.RETIRED)
                or type(requester) is not int or requester != 0x10
                or self.incarnation == self.limit
                or any(x == self.limit for x in self.page_generations)):
            return False
        self.incarnation += 1
        self.page_generations = [x + 1 for x in self.page_generations]
        self.binding = Binding(self.broker, requester, self.incarnation, (0, 1),
                               tuple(self.page_generations), self.incarnation)
        self.pinned = True
        self.phase = Phase.RESERVED
        return True

    def _begin(self, kind, phase):
        if self.operation == self.limit:
            # No operation can be given a fresh identity. Retain all ownership.
            self.phase = Phase.QUARANTINED
            return True
        self.operation += 1
        self.pending = Completion(self.binding, self.operation, kind)
        self.phase = phase
        return True

    def install(self, binding):
        if self.phase != Phase.RESERVED or binding != self.binding:
            return False
        if not self._begin("install", Phase.INSTALLING):
            return False
        # Publication might partially reach hardware before completion is seen.
        if self.phase == Phase.INSTALLING:
            self.translation_visible = True
            self.invalidated = False
        return True

    def start(self, binding):
        if self.phase != Phase.MAPPED or binding != self.binding:
            return False
        self.phase = Phase.RUNNING
        self.may_dma = True
        self.quiescent = False
        self.zeroed = False
        return True

    def retire(self, binding):
        if binding != self.binding or self.phase not in (
                Phase.RESERVED, Phase.MAPPED, Phase.RUNNING):
            return False
        if self.phase == Phase.RESERVED:
            return self._begin("scrub", Phase.SCRUBBING)
        # Even a never-started published mapping requires a trusted stop/drain
        # observation before invalidation. Software intent alone is insufficient.
        return self._begin("quiesce", Phase.QUIESCING)

    def complete(self, completion, success=True):
        if (type(success) is not bool or self.pending is None
                or completion != self.pending
                or self.phase not in (Phase.INSTALLING, Phase.QUIESCING,
                                      Phase.INVALIDATING, Phase.SCRUBBING)):
            return False
        kind = self.pending.kind
        self.pending = None
        if not success:
            self.phase = Phase.QUARANTINED
            return True
        if kind == "install":
            self.phase = Phase.MAPPED
        elif kind == "quiesce":
            self.may_dma = False
            self.quiescent = True
            self._begin("invalidate", Phase.INVALIDATING)
        elif kind == "invalidate":
            self.translation_visible = False
            self.invalidated = True
            self._begin("scrub", Phase.SCRUBBING)
        elif kind == "scrub":
            self.zeroed = True
            self.pinned = False
            self.phase = Phase.RETIRED
        return True

    def timeout(self):
        if self.pending is None or self.phase == Phase.QUARANTINED:
            return False
        self.pending = None
        self.phase = Phase.QUARANTINED
        return True

    def invariant(self):
        # No free frame while DMA or cached/published translation can reach it.
        if not self.pinned and (self.may_dma or self.translation_visible
                                or not self.zeroed or not self.invalidated):
            return False
        if self.phase == Phase.RUNNING and not (self.pinned and self.translation_visible):
            return False
        if self.phase in (Phase.INVALIDATING, Phase.SCRUBBING, Phase.RETIRED):
            if not self.quiescent or self.may_dma:
                return False
        if self.phase in (Phase.SCRUBBING, Phase.RETIRED):
            if self.translation_visible or not self.invalidated:
                return False
        if self.phase == Phase.QUARANTINED and not self.pinned:
            return False
        if self.pending is not None and self.pending.binding != self.binding:
            return False
        return True

    def key(self):
        return (self.phase, self.incarnation, self.operation,
                tuple(self.page_generations), self.binding, self.pending,
                self.pinned, self.zeroed, self.may_dma,
                self.translation_visible, self.quiescent, self.invalidated)
