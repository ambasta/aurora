# Independent reviewer event-history oracle; checks remain active under python -O.
from copy import deepcopy
from dataclasses import dataclass, replace
import json
from lifecycle import Lifecycle, Phase

@dataclass(frozen=True)
class History:
    held: bool = False
    exposed: bool = False
    installed: bool = False
    retiring: bool = False
    drained: bool = False
    invalidated: bool = False
    poisoned: bool = False
    tickets: tuple = ()
    bindings: tuple = ()

def check(model_type, limit):
    initial = model_type(limit)
    frontier = [(initial, History(), ())]
    seen = {(initial.key(), History())}
    edges = 0
    while frontier:
        m, h, path = frontier.pop()
        events = [('reserve', None, True), ('install', m.binding, True), ('start', m.binding, True), ('retire', m.binding, True), ('timeout', None, True)]
        events += [('complete', t, success) for t in h.tickets for success in (True, False)]
        if m.pending:
            events += [('complete', replace(m.pending, operation=0), True), ('complete', replace(m.pending, kind='invented'), True), ('complete', m.pending, 1)]
        events += [(name, b, True) for b in h.bindings for name in ('install', 'start', 'retire')]
        for name, arg, success in events:
            n = deepcopy(m)
            nh = h
            edges += 1
            if name in ('reserve', 'timeout'):
                accepted = getattr(n, name)()
            elif name == 'complete':
                accepted = n.complete(arg, success)
            else:
                accepted = getattr(n, name)(arg)
            step = (name, getattr(arg, 'kind', None), success)
            try:
                if not n.invariant():
                    raise AssertionError('implementation invariant')
                if not accepted:
                    if not n.key() == m.key():
                        raise AssertionError('rejection changed state')
                else:
                    if not not h.poisoned:
                        raise AssertionError('accepted event after quarantine')
                    if name == 'reserve':
                        if not not h.held:
                            raise AssertionError('reserve while historical lease held')
                        nh = History(held=True, tickets=h.tickets, bindings=h.bindings + (n.binding,))
                    elif name == 'install':
                        if not (h.held and (not h.exposed) and (not h.retiring)):
                            raise AssertionError('install ordering')
                        if n.pending is not None:
                            nh = replace(h, exposed=True)
                    elif name == 'start':
                        if not (h.installed and (not h.retiring)):
                            raise AssertionError('start before install acknowledgement')
                    elif name == 'retire':
                        nh = replace(h, retiring=True)
                    elif name == 'complete':
                        if not type(success) is bool:
                            raise AssertionError('nonboolean result accepted')
                        if not (arg == m.pending and arg in h.tickets):
                            raise AssertionError('foreign/replayed acknowledgement accepted')
                        if not success:
                            nh = replace(h, poisoned=True)
                        elif arg.kind == 'install':
                            if not (h.exposed and (not h.retiring)):
                                raise AssertionError('installation ack ordering')
                            nh = replace(h, installed=True)
                        elif arg.kind == 'quiesce':
                            if not (h.exposed and h.retiring):
                                raise AssertionError('drain before close')
                            nh = replace(h, drained=True)
                        elif arg.kind == 'invalidate':
                            if not (h.retiring and h.drained):
                                raise AssertionError('invalidation before quiescence')
                            nh = replace(h, invalidated=True)
                        elif arg.kind == 'scrub':
                            if not (h.retiring and (not h.exposed or (h.drained and h.invalidated))):
                                raise AssertionError('release lacks ordered evidence')
                            nh = replace(h, held=False)
                        elif not False:
                            raise AssertionError('unknown completion accepted')
                    elif name == 'timeout':
                        if not m.pending is not None:
                            raise AssertionError('timeout without operation')
                        nh = replace(h, poisoned=True)
                    if n.phase == Phase.QUARANTINED:
                        nh = replace(nh, poisoned=True)
                    if n.pending is not None and n.pending not in nh.tickets:
                        nh = replace(nh, tickets=nh.tickets + (n.pending,))
                if not n.pinned == nh.held:
                    raise AssertionError('pin state disagrees with historical ownership')
                if nh.poisoned:
                    if not (n.phase == Phase.QUARANTINED and n.pinned):
                        raise AssertionError('quarantine lost')
            except AssertionError as e:
                raise AssertionError((str(e), path + (step,))) from e
            key = (n.key(), nh)
            if key not in seen:
                seen.add(key)
                frontier.append((n, nh, path + (step,)))
    return {'limit': limit, 'history_states': len(seen), 'edges': edges}

class FalseReleaseOnTimeout(Lifecycle):

    def timeout(self):
        accepted = super().timeout()
        if accepted:
            self.phase = Phase.RETIRED
            self.pinned = self.may_dma = self.translation_visible = False
            self.zeroed = self.quiescent = self.invalidated = True
        return accepted

class EarlyReleaseOnQuiescence(Lifecycle):

    def complete(self, completion, success=True):
        accepted = super().complete(completion, success)
        if accepted and success and (completion.kind == 'quiesce'):
            self.phase = Phase.RETIRED
            self.pending = None
            self.pinned = self.may_dma = self.translation_visible = False
            self.zeroed = self.quiescent = self.invalidated = True
        return accepted
results = [check(Lifecycle, n) for n in range(1, 9)]
killed = []
for mutant in (FalseReleaseOnTimeout, EarlyReleaseOnQuiescence):
    try:
        check(mutant, 8)
    except AssertionError as e:
        killed.append({'mutation': mutant.__name__, 'counterexample': e.args[0]})
    else:
        raise AssertionError('oracle missed ' + mutant.__name__)
a, b = (Lifecycle(), Lifecycle())
for m in (a, b):
    if not (m.reserve() and m.install(m.binding)):
        raise AssertionError('independent check failed')
if not not b.complete(a.pending):
    raise AssertionError('independent check failed')
if not (not b.start(a.binding) and (not b.retire(a.binding))):
    raise AssertionError('independent check failed')
print(json.dumps({'results': results, 'mutations_caught': killed, 'cross_broker_replay': 'rejected'}, indent=2))
