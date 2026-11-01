import R.Model
namespace Aurora.R

/-- Only packets whose soundness is needed to authorize a state change carry
semantic evidence here. Other packets are harmless unless their handler's local
checks succeed; the channel still has no arbitrary-injection transition. -/
def PacketValid (s : State Agent) : Packet Agent → Prop
  | .register r destination => ∃ q, s.requests r = some q ∧ q.destination = destination
  | .grant r i => (∃ q, s.requests r = some q) ∧ s.registrations r = some i
  | .receipt generation i => ∃ e, s.entries i = some e ∧ e.generation = generation ∧ e.sealed = true
  | _ => True

structure LocalInvariant (s : State Agent) : Prop where
  requestSource : ∀ r q, s.requests r = some q →
    ∃ e a, s.entries r.1 = some e ∧ e.kind = .gate a
  settledRegistered : ∀ r q, s.requests r = some q → q.settled = true →
    ∃ i, s.registrations r = some i
  sealedSafe : ∀ i e, s.entries i = some e → e.sealed = true →
    e.closed = true ∧ (∀ a, e.kind = .use a → e.work = 0)
  gateBarrier : ∀ i e a, s.entries i = some e → e.kind = .gate a →
    e.sealed = true → Settled s i
  transferSeal : ∀ i e a, s.entries i = some e → e.kind = .transfer a →
    e.sealed = e.receiver.isSome
  packetsValid : ∀ p, p ∈ s.packets → PacketValid s p

/-- Q's old-state invariant is an inductive strengthening, not an operational
constructor premise or a replacement for the concrete simulation proof. -/
def Invariant (s : State Agent) : Prop := Q.Invariant (project s) ∧ LocalInvariant s

variable {s : State Agent} {e : Entry Agent}

theorem initial_local : LocalInvariant (initial : State Agent) := by
  constructor <;> simp [initial, PacketValid]

theorem not_closed_unsealed (h : LocalInvariant s) (found : s.entries i = some e)
    (notClosed : e.closed = false) : e.sealed = false := by
  cases hs : e.sealed
  · rfl
  · have hc := (h.sealedSafe i e found hs).1
    simp [notClosed] at hc

theorem work_unsealed (h : LocalInvariant s) (found : s.entries i = some e)
    (use : e.kind = .use a) (work : 0 < e.work) : e.sealed = false := by
  cases hs : e.sealed
  · rfl
  · have hw := (h.sealedSafe i e found hs).2 a use
    omega

theorem registration_unsealed (h : LocalInvariant s)
    (packet : Packet.register r destination ∈ s.packets)
    (absent : s.registrations r = none) (found : s.entries r.1 = some e)
    (gate : e.kind = .gate a) : e.sealed = false := by
  obtain ⟨q, hq, _⟩ := h.packetsValid _ packet
  cases hs : e.sealed
  · rfl
  · have settled := h.gateBarrier r.1 e a found gate hs r q hq rfl
    obtain ⟨j, hj⟩ := h.settledRegistered r q hq settled
    simp [absent] at hj

theorem receipt_sealed (h : LocalInvariant s)
    (packet : Packet.receipt generation i ∈ s.packets)
    (found : s.entries i = some e) : e.sealed = true := by
  obtain ⟨old, ho, _, hs⟩ := h.packetsValid _ packet
  have same : old = e := Option.some.inj (ho.symm.trans found)
  simpa [same] using hs

end Aurora.R
