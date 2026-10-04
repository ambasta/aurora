from copy import deepcopy
from dataclasses import replace
import json
from lifecycle import Lifecycle, Phase, Completion

checks = 0
def require(condition, label):
    global checks
    checks += 1
    if not condition:
        raise RuntimeError(label)

def sequence():
    m = Lifecycle()
    require(m.reserve(), "reserve")
    b = m.binding
    require(m.install(b), "install intent")
    old_install = m.pending
    require(m.complete(old_install), "installation completion")
    require(m.start(b), "start")
    require(m.retire(b), "retire request")
    stop = m.pending
    require(not m.complete(old_install), "replayed install rejected")
    require(m.pinned and m.may_dma, "stop request alone releases nothing")
    require(m.complete(stop), "quiescence observed")
    invalidation = m.pending
    require(m.pinned and m.translation_visible, "quiescence alone releases nothing")
    require(m.complete(invalidation), "invalidation observed")
    require(m.pinned and not m.zeroed, "invalidation alone releases nothing")
    scrub = m.pending
    require(m.complete(scrub), "scrub observed")
    require(m.phase == Phase.RETIRED and not m.pinned, "release after all evidence")
    require(m.reserve(), "reuse")
    require(m.binding != b, "new incarnation")
    require(not m.start(b) and not m.install(b) and not m.retire(b), "stale owner denied")
    require(not m.complete(scrub), "old scrub cannot release new lease")

    for failure_stage in ("install", "quiesce", "invalidate", "scrub"):
        for failed in (True, False):
            m = Lifecycle()
            m.reserve(); m.install(m.binding)
            while m.pending.kind != failure_stage:
                m.complete(m.pending)
                if m.phase == Phase.MAPPED:
                    m.start(m.binding); m.retire(m.binding)
            ticket = m.pending
            require(m.complete(ticket, False) if failed else m.timeout(), "failure accepted")
            require(m.phase == Phase.QUARANTINED and m.pinned, "failure quarantines")
            before = m.key()
            for action in (lambda: m.reserve(), lambda: m.install(m.binding),
                           lambda: m.start(m.binding), lambda: m.retire(m.binding),
                           lambda: m.complete(ticket), lambda: m.timeout()):
                require(not action(), "quarantine is terminal")
                require(m.key() == before, "quarantine stable")

    # Snapshot all identity fields: none may be caller-substituted.
    m = Lifecycle(); m.reserve(); m.install(m.binding)
    t = m.pending
    for field, value in (("broker", 0), ("requester", 0x18), ("incarnation", 2), ("pages", (1,0)),
                         ("lease_generations", (2,1)), ("map_generation", 2)):
        forged = replace(t, binding=replace(t.binding, **{field: value}))
        require(not m.complete(forged), f"wrong {field}")
    for forged in (replace(t, operation=2), replace(t, kind="invalidate")):
        require(not m.complete(forged), "wrong operation")

    # A fresh broker with the same local counters must not accept an old ticket.
    other = Lifecycle(); other.reserve(); other.install(other.binding)
    require(not other.complete(t), "cross-broker acknowledgement rejected")

    for limit in range(1, 9):
        m = Lifecycle(limit)
        while m.phase != Phase.QUARANTINED:
            if m.phase in (Phase.EMPTY, Phase.RETIRED):
                if not m.reserve():
                    break
            elif m.phase == Phase.RESERVED:
                m.install(m.binding)
            elif m.phase == Phase.MAPPED:
                m.start(m.binding)
            elif m.phase == Phase.RUNNING:
                m.retire(m.binding)
            else:
                m.complete(m.pending)
            require(m.invariant(), "generation exhaustion invariant")
        require(m.incarnation <= limit and m.operation <= limit, "no wrap")

# Exhaustively enumerate every distinct reachable finite state with small epochs.
# Invalid calls must be observationally inert; success transitions must preserve
# the independent release predicate checked above and below.
def explore(limit):
    initial = Lifecycle(limit)
    frontier = [initial]
    seen = {initial.key()}
    edges = 0
    while frontier:
        m = frontier.pop()
        b = m.binding
        stale = replace(b, incarnation=0) if b else None
        t = m.pending
        wrong = replace(t, operation=0) if t else None
        actions = [lambda x:x.reserve(), lambda x:x.reserve(0x18),
                   lambda x:x.install(b), lambda x:x.install(stale),
                   lambda x:x.start(b), lambda x:x.start(stale),
                   lambda x:x.retire(b), lambda x:x.retire(stale),
                   lambda x:x.complete(t), lambda x:x.complete(wrong),
                   lambda x:x.complete(t, False), lambda x:x.timeout()]
        for action in actions:
            n = deepcopy(m)
            accepted = action(n)
            edges += 1
            require(n.invariant(), "reachable safety invariant")
            if not accepted:
                require(n.key() == m.key(), "rejected event mutates state")
            if m.pinned and not n.pinned:
                require(m.phase == Phase.SCRUBBING and m.quiescent
                        and m.invalidated and not m.translation_visible
                        and not m.may_dma, "release edge requires evidence")
            if n.key() not in seen:
                seen.add(n.key()); frontier.append(n)
    return {"generation_limit":limit,"states":len(seen),"edges":edges}

if __name__ == "__main__":
    sequence()
    results = [explore(n) for n in range(1, 9)]
    print(json.dumps({"checks":checks,"exploration":results,"scope":"pure host model; no hardware evidence"}, indent=2))
