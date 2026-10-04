"""Independent release predicate catches deliberately broken implementations."""
from lifecycle import Lifecycle, Phase

def retained(model):
    if not model.pinned and (model.may_dma or model.translation_visible
                             or not model.invalidated or not model.zeroed):
        raise RuntimeError("reachable DMA or unsanitized memory was recycled")

class ReleaseOnTimeout(Lifecycle):
    def timeout(self):
        result = super().timeout()
        if result:
            self.pinned = False
        return result

class ReleaseOnQuiescence(Lifecycle):
    def complete(self, ticket, success=True):
        result = super().complete(ticket, success)
        if result and ticket.kind == "quiesce":
            self.pinned = False
        return result

class ReleaseOnInvalidation(Lifecycle):
    def complete(self, ticket, success=True):
        result = super().complete(ticket, success)
        if result and ticket.kind == "invalidate":
            self.pinned = False
        return result

caught = 0
for implementation in (ReleaseOnTimeout, ReleaseOnQuiescence, ReleaseOnInvalidation):
    model = implementation(); model.reserve(); model.install(model.binding)
    try:
        if implementation == ReleaseOnTimeout:
            model.timeout(); retained(model)
        else:
            model.complete(model.pending); model.start(model.binding)
            model.retire(model.binding)
            model.complete(model.pending); retained(model)
            model.complete(model.pending); retained(model)
    except RuntimeError:
        caught += 1
if caught != 3:
    raise RuntimeError("mutation oracle failed")
print("3 premature-release mutation controls rejected")
