import A.Model
namespace Aurora.A

/-- Physical cell extents, not alias names, carry attenuation. -/
def Derived (parent : Grant Agent) (destination : Option Agent) (g : Grant Agent) : Prop :=
  g.issuer = parent.subject ∧ g.subject = destination.getD parent.subject ∧
  g.generation = parent.generation ∧ g.extent.Within parent.extent ∧
  (g.writable = true → parent.writable = true) ∧
  (g.delegates = true → parent.delegates = true) ∧
  (destination.isSome = true → parent.delegates = true)

def subject : Q.Kind Agent → Agent
  | .gate a | .use a | .transfer a => a

def executingLocation : Q.Kind Agent → Nat → Location
  | .use _, i => .use i
  | .transfer _, i => .transfer i
  | .gate _, i => .gate i

def Executing : Q.Kind Agent → Prop
  | .use _ | .transfer _ => True
  | .gate _ => False

structure Invariant (allocation : Extent) (s : State Agent) : Prop where
  protocol : R.Invariant s.protocol
  grantsBound : ∀ i g, s.grants i = some g →
    ∃ e, s.protocol.entries i = some e ∧ e.generation = g.generation ∧
      subject e.kind = g.subject ∧ g.extent.Within allocation
  grantsTotal : ∀ i e, s.protocol.entries i = some e → ∃ g, s.grants i = some g
  payloadBound : ∀ r p, s.payloads r = some p →
    ∃ q parent, s.protocol.requests r = some q ∧ s.grants r.1 = some parent ∧
      p.origin = r.1 ∧ Derived parent q.destination p.grant
  payloadTotal : ∀ r q, s.protocol.requests r = some q → ∃ p, s.payloads r = some p
  registeredBound : ∀ r i, s.protocol.registrations r = some i →
    ∃ p, s.payloads r = some p ∧ s.grants i = some p.grant
  pendingWriter : ∀ r p, s.payloads r = some p → p.grant.writable = true →
    s.protocol.registrations r = none → s.tokens p.grant.generation = .request r
  executingWriter : ∀ i g e, s.grants i = some g → s.protocol.entries i = some e →
    g.writable = true → e.sealed = false → Executing e.kind →
    s.tokens g.generation = executingLocation e.kind i
  readerPayload : ∀ r p, s.payloads r = some p → p.grant.writable = false → Frozen s p.grant.generation
  readerGrant : ∀ i g, s.grants i = some g → g.writable = false → Frozen s g.generation
  readableSound : ∀ i, s.readable i = true → ∃ g, s.grants i = some g ∧ Frozen s g.generation
  sequential : ∀ i g e, s.grants i = some g → s.protocol.entries i = some e →
    g.writable = true → e.work ≤ 1

variable {s : State Agent} {allocation : Extent}

theorem initial_invariant : Invariant allocation (initial : State Agent) := by
  constructor
  · exact R.initial_invariant
  all_goals simp [initial, R.initial]

theorem grants_fresh (h : Invariant allocation s) (bound : s.protocol.next ≤ i) :
    s.grants i = none := by
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

theorem grant_entry (h : Invariant allocation s) (hg : s.grants i = some g)
    (he : s.protocol.entries i = some e) :
    e.generation = g.generation ∧ subject e.kind = g.subject ∧ g.extent.Within allocation := by
  obtain ⟨old, hold, rest⟩ := h.grantsBound i g hg
  have same : old = e := Option.some.inj (hold.symm.trans he)
  simpa [same] using rest

theorem frozen_not_location (h : Frozen s generation) :
    s.tokens generation ≠ .gate i ∧ s.tokens generation ≠ .request r ∧
    s.tokens generation ≠ .use j ∧ s.tokens generation ≠ .transfer k ∧
    s.tokens generation ≠ .unissued := by
  obtain ⟨n, hn⟩ := h
  simp [hn]

end Aurora.A
