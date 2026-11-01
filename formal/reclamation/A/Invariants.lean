import A.Model
namespace Aurora.A

def Derived (parent : Grant Agent) (destination : Option Agent) (g : Grant Agent) : Prop :=
  g.issuer = parent.subject ∧ g.subject = destination.getD parent.subject ∧
  g.generation = parent.generation ∧ g.footprint.Within parent.footprint ∧
  (g.writable = true → parent.writable = true) ∧
  (g.delegates = true → parent.delegates = true) ∧
  (destination.isSome = true → parent.delegates = true)

def subject : Q.Kind Agent → Agent
  | .gate a | .use a | .transfer a => a

def isUse : Q.Kind Agent → Bool
  | .use _ => true | _ => false

def isTransfer : Q.Kind Agent → Bool
  | .transfer _ => true | _ => false

/-- Expected exclusive claims are computed from immutable payloads and retained
protocol markers, never from an authority predicate in an operational guard.
Retired-but-unreturned uses retain ownership; read aliases are not claims. -/
def expected (s : State Agent) (generation : Nat) : Location → Footprint
  | .gate i => s.holdings generation (.gate i)
  | .frozen => s.holdings generation .frozen
  | .request r => match s.payloads r with
      | none => []
      | some p => if p.grant.generation = generation ∧ p.grant.writable = true ∧
          s.protocol.registrations r = none then p.grant.footprint else []
  | .use i => match s.grants i, s.protocol.entries i with
      | some g, some e => if g.generation = generation ∧ g.writable = true ∧
          isUse e.kind = true ∧ s.returned i = false then g.footprint else []
      | _, _ => []
  | .transfer i => match s.grants i, s.protocol.entries i with
      | some g, some e => if g.generation = generation ∧ g.writable = true ∧
          isTransfer e.kind = true ∧ e.receiver = none then g.footprint else []
      | _, _ => []

structure Invariant (allocation : Footprint) (s : State Agent) : Prop where
  protocol : R.Invariant s.protocol
  grantsBound : ∀ i g, s.grants i = some g →
    ∃ e, s.protocol.entries i = some e ∧ e.generation = g.generation ∧
      subject e.kind = g.subject ∧ g.footprint.Within allocation
  grantsTotal : ∀ i e, s.protocol.entries i = some e → ∃ g, s.grants i = some g
  grantsIssued : ∀ i g, s.grants i = some g → s.issued g.generation = true
  payloadBound : ∀ r p, s.payloads r = some p →
    ∃ q parent, s.protocol.requests r = some q ∧ s.grants r.1 = some parent ∧
      p.origin = r.1 ∧ Derived parent q.destination p.grant
  payloadTotal : ∀ r q, s.protocol.requests r = some q → ∃ p, s.payloads r = some p
  registeredBound : ∀ r i, s.protocol.registrations r = some i →
    ∃ p, s.payloads r = some p ∧ s.grants i = some p.grant
  partition : ∀ generation, s.issued generation = true →
    Inventory.Partition allocation (s.holdings generation)
  unissuedEmpty : ∀ generation, s.issued generation = false → ∀ location, s.holdings generation location = []
  accounted : ∀ generation location cell,
    cell ∈ s.holdings generation location ↔ cell ∈ expected s generation location
  gateInventory : ∀ generation i cell, cell ∈ s.holdings generation (.gate i) →
    ∃ g e, s.grants i = some g ∧ s.protocol.entries i = some e ∧
      g.generation = generation ∧ e.kind = .gate g.subject ∧ cell ∈ g.footprint
  returnedSound : ∀ i, s.returned i = true →
    ∃ e a, s.protocol.entries i = some e ∧ e.kind = .use a ∧ e.sealed = true
  readerPayload : ∀ r p, s.payloads r = some p → p.grant.writable = false →
    Frozen s p.grant.generation p.grant.footprint
  readerGrant : ∀ i g, s.grants i = some g → g.writable = false → Frozen s g.generation g.footprint
  readableSound : ∀ i cell, cell ∈ s.readable i →
    ∃ g, s.grants i = some g ∧ cell ∈ g.footprint ∧ cell ∈ s.holdings g.generation .frozen
  sequential : ∀ i g e, s.grants i = some g → s.protocol.entries i = some e →
    g.writable = true → e.work ≤ 1

variable {s : State Agent} {allocation : Footprint}

theorem initial_invariant : Invariant allocation (initial : State Agent) := by
  constructor
  · exact R.initial_invariant
  all_goals simp [initial, R.initial, expected, Frozen, Footprint.Within]
  intro location cell
  cases location <;> simp

theorem grants_fresh (h : Invariant allocation s) (bound : s.protocol.next ≤ i) : s.grants i = none := by
  cases found : s.grants i with
  | none => rfl
  | some g =>
      obtain ⟨e, he, _⟩ := h.grantsBound i g found
      have hn := h.protocol.1.fresh i bound
      simp [R.project, he] at hn

theorem payload_fresh (h : Invariant allocation s) (absent : s.protocol.requests r = none) :
    s.payloads r = none := by
  cases found : s.payloads r with
  | none => rfl
  | some p =>
      obtain ⟨q, _, hq, _⟩ := h.payloadBound r p found
      simp [absent] at hq

theorem returned_fresh (h : Invariant allocation s) (bound : s.protocol.next ≤ i) : s.returned i = false := by
  cases mark : s.returned i with
  | false => rfl
  | true =>
      obtain ⟨e, a, he, _⟩ := h.returnedSound i mark
      have hn := h.protocol.1.fresh i bound
      simp [R.project, he] at hn

theorem grant_entry (h : Invariant allocation s) (hg : s.grants i = some g)
    (he : s.protocol.entries i = some e) :
    e.generation = g.generation ∧ subject e.kind = g.subject ∧ g.footprint.Within allocation := by
  obtain ⟨old, hold, rest⟩ := h.grantsBound i g hg
  have same : old = e := Option.some.inj (hold.symm.trans he)
  simpa [same] using rest

theorem pending_holding (h : Invariant allocation s) (hp : s.payloads r = some p)
    (writer : p.grant.writable = true) (pending : s.protocol.registrations r = none) :
    ∀ cell, cell ∈ s.holdings p.grant.generation (.request r) ↔ cell ∈ p.grant.footprint := by
  intro cell
  simpa [expected, hp, writer, pending] using h.accounted p.grant.generation (.request r) cell

theorem use_holding (h : Invariant allocation s) (hg : s.grants i = some g)
    (he : s.protocol.entries i = some e) (use : e.kind = .use g.subject)
    (writer : g.writable = true) (unreturned : s.returned i = false) :
    ∀ cell, cell ∈ s.holdings g.generation (.use i) ↔ cell ∈ g.footprint := by
  intro cell
  simpa [expected, hg, he, use, isUse, writer, unreturned] using h.accounted g.generation (.use i) cell

theorem transfer_holding (h : Invariant allocation s) (hg : s.grants i = some g)
    (he : s.protocol.entries i = some e) (transfer : e.kind = .transfer g.subject)
    (writer : g.writable = true) (pending : e.receiver = none) :
    ∀ cell, cell ∈ s.holdings g.generation (.transfer i) ↔ cell ∈ g.footprint := by
  intro cell
  simpa [expected, hg, he, transfer, isTransfer, writer, pending] using h.accounted g.generation (.transfer i) cell

theorem unsealed_unreturned (h : Invariant allocation s) (he : s.protocol.entries i = some e)
    (unsealed : e.sealed = false) : s.returned i = false := by
  cases mark : s.returned i with
  | false => rfl
  | true =>
      obtain ⟨old, a, hold, _, hs⟩ := h.returnedSound i mark
      have same : old = e := Option.some.inj (hold.symm.trans he)
      simp [same, unsealed] at hs

end Aurora.A
