import A.Preservation
namespace Aurora.A

variable {Agent : Type} {allocation : Extent} {s : State Agent}

def registeredState (s : State Agent) (r : R.RequestId) (destination : Option Agent)
    (e : R.Entry Agent) (a : Agent) (p : Payload Agent) : State Agent :=
  let t := putGrant (atProtocol s
    (R.enqueue (R.registerId (R.issue s.protocol e.generation
      (R.requestedKind a destination)) r s.protocol.next) (.grant r s.protocol.next)))
    s.protocol.next p.grant
  if p.grant.writable then move t p.grant.generation
    (registerLocation destination s.protocol.next) else t

/-- First-registration payload binding is derived from immutable packet origin
and its original source grant, not a handler read of remote mutable state. -/
theorem registration_binding (h : Invariant allocation s)
    (packet : R.Packet.register r destination ∈ s.protocol.packets)
    (found : s.protocol.entries r.1 = some e) (gate : e.kind = .gate a)
    (payload : s.payloads r = some p) :
    p.grant.generation = e.generation ∧
    p.grant.subject = destination.getD a ∧ p.grant.extent.Within allocation := by
  obtain ⟨q, hq, qdest⟩ := h.protocol.2.packetsValid _ packet
  obtain ⟨q', parent, hq', hp, _, derived⟩ := h.payloadBound r p payload
  have same : q' = q := Option.some.inj (hq'.symm.trans hq)
  subst q'
  have bind := grant_entry h hp found
  have owner : parent.subject = a := by simpa [gate, subject] using bind.2.1.symm
  refine ⟨derived.2.2.1.trans bind.1.symm, ?_, ?_⟩
  · simpa [qdest, owner] using derived.2.1
  · have inner := derived.2.2.2.1
    have outer := bind.2.2
    exact ⟨Nat.le_trans outer.1 inner.1, inner.2.1, Nat.le_trans inner.2.2 outer.2.2⟩

theorem register_preserves (h : Invariant allocation s)
    (packet : R.Packet.register r destination ∈ s.protocol.packets)
    (absent : s.protocol.registrations r = none)
    (found : s.protocol.entries r.1 = some e) (gate : e.kind = .gate a)
    (payload : s.payloads r = some p) :
    Invariant allocation (registeredState s r destination e a p) := by
  let t := registeredState s r destination e a p
  let rp := R.enqueue (R.registerId (R.issue s.protocol e.generation
      (R.requestedKind a destination)) r s.protocol.next) (.grant r s.protocol.next)
  have pt : t.protocol = rp := by cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol, rp]
  have gt : t.grants = fun j => if j = s.protocol.next then some p.grant else s.grants j := by
    cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have rt : t.payloads = s.payloads := by cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have lt : t.readable = s.readable := by cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have tok : t.tokens = fun gen =>
      if p.grant.writable = true ∧ gen = p.grant.generation then
        registerLocation destination s.protocol.next else s.tokens gen := by
    funext gen; cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have reg : t.protocol.registrations = fun q => if q = r then some s.protocol.next else s.protocol.registrations q := by
    rw [pt]; rfl
  have ent : t.protocol.entries = fun j => if j = s.protocol.next then
      some ({ generation := e.generation, kind := R.requestedKind a destination } : R.Entry Agent)
      else s.protocol.entries j := by rw [pt]; rfl
  have req : t.protocol.requests = s.protocol.requests := by rw [pt]; rfl
  have hp : R.Invariant t.protocol := by
    rw [pt]; exact R.step_preserves_invariant h.protocol
      (.register s.protocol r destination e a packet absent found gate)
  have binding := registration_binding h packet found gate payload
  have freshGrant := grants_fresh h (i := s.protocol.next) (Nat.le_refl _)
  have oldGrant (j : Nat) (g : Grant Agent) (hg : s.grants j = some g) : t.grants j = some g := by
    have ne : j ≠ s.protocol.next := by intro eq; subst j; simp [freshGrant] at hg
    simp [gt, ne, hg]
  have oldEntry (j : Nat) (n : R.Entry Agent) (hn : s.protocol.entries j = some n) : j ≠ s.protocol.next := by
    have less := Q.registered_lt h.protocol.1 (R.project_found hn)
    change j < s.protocol.next at less
    omega
  have frozen (gen : Nat) (hf : Frozen s gen) : Frozen t gen := by
    obtain ⟨j, hj⟩ := hf
    refine ⟨j, ?_⟩
    simp only [tok]
    split
    · rename_i hc
      have held := h.pendingWriter r p payload hc.1 absent
      rw [hc.2, held] at hj
      contradiction
    · exact hj
  change Invariant allocation t
  constructor
  · exact hp
  · intro j g hg
    simp only [gt] at hg
    split at hg
    · rename_i same
      subst j
      have eq : g = p.grant := Option.some.inj hg.symm
      subst g
      refine ⟨({ generation := e.generation, kind := R.requestedKind a destination } : R.Entry Agent),
        by simp [ent], binding.1.symm, ?_, binding.2.2⟩
      cases destination <;> simpa [R.requestedKind, subject] using binding.2.1.symm
    · obtain ⟨n, hn, ng, ns, nb⟩ := h.grantsBound j g hg
      exact ⟨n, by simpa [ent, oldEntry j n hn] using hn, ng, ns, nb⟩
  · intro j n hn
    simp only [ent] at hn
    split at hn
    · subst j; exact ⟨p.grant, by simp [gt]⟩
    · obtain ⟨g, hg⟩ := h.grantsTotal j n hn
      exact ⟨g, oldGrant j g hg⟩
  · intro q data hdata
    simp only [rt] at hdata
    obtain ⟨request, parent, hr, hg, origin, derived⟩ := h.payloadBound q data hdata
    exact ⟨request, parent, by simpa [req] using hr, oldGrant _ _ hg, origin, derived⟩
  · intro q request hr
    simpa [rt] using h.payloadTotal q request (by simpa [req] using hr)
  · intro q j hj
    simp only [reg] at hj
    split at hj
    · rename_i same
      subst q
      have eq : j = s.protocol.next := Option.some.inj hj.symm
      subst j
      exact ⟨p, by simpa [rt] using payload, by simp [gt]⟩
    · obtain ⟨data, hd, hg⟩ := h.registeredBound q j hj
      exact ⟨data, by simpa [rt] using hd, oldGrant _ _ hg⟩
  · intro q data hd hw ha
    simp only [rt] at hd
    have neq : q ≠ r := by intro eq; subst q; simp [reg] at ha
    have old := h.pendingWriter q data hd hw (by simpa [reg, neq] using ha)
    simp only [tok]
    split
    · rename_i hc
      have held := h.pendingWriter r p payload hc.1 absent
      have same : q = r := Location.request.inj (by simpa [hc.2, held] using old.symm)
      exact False.elim (neq same)
    · exact old
  · intro j g n hg hn hw hu hx
    simp only [gt] at hg
    split at hg
    · rename_i same
      subst j
      have geq : g = p.grant := Option.some.inj hg.symm
      subst g
      have ne : n = ({ generation := e.generation, kind := R.requestedKind a destination } : R.Entry Agent) := by
        simpa [ent] using hn.symm
      subst n
      simp [tok, hw]
      cases destination <;> rfl
    · rename_i neq
      have oldfound : s.protocol.entries j = some n := by simpa [ent, neq] using hn
      have old := h.executingWriter j g n hg oldfound hw hu hx
      simp only [tok]
      split
      · rename_i hc
        have held := h.pendingWriter r p payload hc.1 absent
        rw [hc.2, held] at old
        cases nk : n.kind <;> simp_all [Executing, executingLocation]
      · exact old
  · intro q data hd hr
    exact frozen _ (h.readerPayload q data (by simpa [rt] using hd) hr)
  · intro j g hg hr
    simp only [gt] at hg
    split at hg
    · have eq : g = p.grant := Option.some.inj hg.symm
      subst g; exact frozen _ (h.readerPayload r p payload hr)
    · exact frozen _ (h.readerGrant j g hg hr)
  · intro j hj
    obtain ⟨g, hg, hf⟩ := h.readableSound j (by simpa [lt] using hj)
    exact ⟨g, oldGrant _ _ hg, frozen _ hf⟩
  · intro j g n hg hn hw
    simp only [ent] at hn
    split at hn
    · have eq : n = ({ generation := e.generation, kind := R.requestedKind a destination } : R.Entry Agent) :=
        Option.some.inj hn.symm
      subst n; simp
    · rename_i neq
      exact h.sequential j g n (by simpa [gt, neq] using hg) hn hw

end Aurora.A
