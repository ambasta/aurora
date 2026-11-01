import A.Preservation
namespace Aurora.A

variable {Agent : Type} {allocation : Footprint} {s : State Agent}

def registeredState (s : State Agent) (r : R.RequestId) (destination : Option Agent)
    (e : R.Entry Agent) (a : Agent) (p : Payload Agent) : State Agent :=
  let t := putGrant (atProtocol s
    (R.enqueue (R.registerId (R.issue s.protocol e.generation
      (R.requestedKind a destination)) r s.protocol.next) (.grant r s.protocol.next)))
    s.protocol.next p.grant
  if p.grant.writable then move t p.grant.generation (.request r)
    (registerLocation destination s.protocol.next) p.grant.footprint else t

/-- First-registration payload binding is derived from immutable packet origin
and its original source grant, not a handler read of remote mutable state. -/
theorem registration_binding (h : Invariant allocation s)
    (packet : R.Packet.register r destination ∈ s.protocol.packets)
    (found : s.protocol.entries r.1 = some e) (gate : e.kind = .gate a)
    (payload : s.payloads r = some p) :
    p.grant.generation = e.generation ∧
    p.grant.subject = destination.getD a ∧ p.grant.footprint.Within allocation := by
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
    exact List.Subset.trans inner outer

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
  have it : t.issued = s.issued := by cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have ret : t.returned = s.returned := by cases hw : p.grant.writable <;> simp [t, registeredState, hw, move, putGrant, atProtocol]
  have hold : t.holdings = fun gen =>
      if p.grant.writable = true ∧ gen = p.grant.generation then
        Inventory.move (s.holdings gen) (.request r)
          (registerLocation destination s.protocol.next) p.grant.footprint else s.holdings gen := by
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
  have freshReturned := returned_fresh h (i := s.protocol.next) (Nat.le_refl _)
  have issued : s.issued p.grant.generation = true := by
    obtain ⟨q,parent,_,hg,_,derived⟩ := h.payloadBound r p payload
    simpa [derived.2.2.1] using h.grantsIssued _ _ hg
  have oldGrant (j : Nat) (g : Grant Agent) (hg : s.grants j = some g) : t.grants j = some g := by
    have ne : j ≠ s.protocol.next := by intro eq; subst j; simp [freshGrant] at hg
    simp [gt, ne, hg]
  have oldEntry (j : Nat) (n : R.Entry Agent) (hn : s.protocol.entries j = some n) : j ≠ s.protocol.next := by
    have less := Q.registered_lt h.protocol.1 (R.project_found hn)
    change j < s.protocol.next at less
    omega
  have frozenEqual (gen : Nat) : t.holdings gen .frozen = s.holdings gen .frozen := by
    simp only [hold]; split
    · cases destination <;> simp [registerLocation, Inventory.move]
    · rfl
  have gateEqual (gen j : Nat) : t.holdings gen (.gate j) = s.holdings gen (.gate j) := by
    simp only [hold]; split
    · cases destination <;> simp [registerLocation, Inventory.move]
    · rfl
  have sourceMembers (gen cell : Nat) : cell ∈ s.holdings gen (.request r) ↔
      p.grant.generation = gen ∧ p.grant.writable = true ∧ cell ∈ p.grant.footprint := by
    rw [h.accounted]
    by_cases hg : p.grant.generation = gen <;> cases hw : p.grant.writable <;>
      simp [expected,payload,absent,hg,hw]
  have freshUse (gen cell : Nat) : cell ∉ s.holdings gen (.use s.protocol.next) := by
    simp [h.accounted,expected,freshGrant]
  have freshTransfer (gen cell : Nat) : cell ∉ s.holdings gen (.transfer s.protocol.next) := by
    simp [h.accounted,expected,freshGrant]
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
  · intro j g hg
    simp only [gt] at hg
    split at hg
    · have eq : g = p.grant := Option.some.inj hg.symm
      subst g; simpa [it] using issued
    · simpa [it] using h.grantsIssued j g hg
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
  · intro gen hi
    simp only [it] at hi
    simp only [hold]
    split
    · rename_i hc
      have owned : p.grant.footprint ⊆ s.holdings gen (.request r) := by
        intro cell member
        exact (sourceMembers gen cell).2 ⟨hc.2.symm,hc.1,member⟩
      apply Inventory.move_partition (h.partition gen hi) _ owned
      cases destination <;> simp [registerLocation]
    · exact h.partition gen hi
  · intro gen hi loc
    simp only [it] at hi
    have ne : gen ≠ p.grant.generation := by intro eq; subst gen; simp [issued] at hi
    simpa [hold,ne] using h.unissuedEmpty gen hi loc
  · intro gen loc cell
    cases loc with
    | gate j => rfl
    | frozen => rfl
    | request q =>
      by_cases same : q = r
      · subst q
        by_cases hw : p.grant.writable = true <;> by_cases heq : gen = p.grant.generation <;>
          simp [hold,hw,heq,Inventory.move,expected,rt,payload,reg,sourceMembers,eq_comm]
      · have old := h.accounted gen (.request q) cell
        by_cases hc : p.grant.writable = true ∧ gen = p.grant.generation <;> cases destination <;>
          simpa [hold,hc,Inventory.move,registerLocation,same,expected,rt,reg] using old
    | use j =>
      by_cases same : j = s.protocol.next
      · subst j
        cases destination <;> by_cases hw : p.grant.writable = true <;>
          by_cases heq : gen = p.grant.generation <;>
          simp [hold,hw,heq,Inventory.move,registerLocation,freshUse,expected,gt,ent,ret,
            freshReturned,R.requestedKind,isUse,eq_comm]
      · have old := h.accounted gen (.use j) cell
        by_cases hc : p.grant.writable = true ∧ gen = p.grant.generation <;> cases destination <;>
          simpa [hold,hc,Inventory.move,registerLocation,same,expected,gt,ent,ret] using old
    | transfer j =>
      by_cases same : j = s.protocol.next
      · subst j
        cases destination <;> by_cases hw : p.grant.writable = true <;>
          by_cases heq : gen = p.grant.generation <;>
          simp [hold,hw,heq,Inventory.move,registerLocation,freshTransfer,expected,gt,ent,
            R.requestedKind,isTransfer,eq_comm]
      · have old := h.accounted gen (.transfer j) cell
        by_cases hc : p.grant.writable = true ∧ gen = p.grant.generation <;> cases destination <;>
          simpa [hold,hc,Inventory.move,registerLocation,same,expected,gt,ent] using old
  · intro gen j cell hc
    obtain ⟨g,n,hg,hn,hgen,hkind,hcell⟩ := h.gateInventory gen j cell (by simpa [gateEqual] using hc)
    exact ⟨g,n,oldGrant j g hg,by simpa [ent,oldEntry j n hn] using hn,hgen,hkind,hcell⟩
  · intro j hj
    obtain ⟨n,b,hn,hkind,hseal⟩ := h.returnedSound j (by simpa [ret] using hj)
    exact ⟨n,b,by simpa [ent,oldEntry j n hn] using hn,hkind,hseal⟩
  · intro q data hd hr
    simpa [Frozen, frozenEqual] using h.readerPayload q data (by simpa [rt] using hd) hr
  · intro j g hg hr
    simp only [gt] at hg
    split at hg
    · have eq : g = p.grant := Option.some.inj hg.symm
      subst g; simpa [Frozen,frozenEqual] using h.readerPayload r p payload hr
    · simpa [Frozen,frozenEqual] using h.readerGrant j g hg hr
  · intro j cell hj
    obtain ⟨g,hg,hcell,hf⟩ := h.readableSound j cell (by simpa [lt] using hj)
    exact ⟨g,oldGrant j g hg,hcell,by simpa [frozenEqual] using hf⟩
  · intro j g n hg hn hw
    simp only [ent] at hn
    split at hn
    · have eq : n = ({ generation := e.generation, kind := R.requestedKind a destination } : R.Entry Agent) :=
        Option.some.inj hn.symm
      subst n; simp
    · rename_i neq
      exact h.sequential j g n (by simpa [gt, neq] using hg) hn hw

end Aurora.A
