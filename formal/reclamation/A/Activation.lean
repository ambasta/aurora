import A.Preservation

namespace Aurora.A
variable {Agent : Type} {allocation : Extent} {s : State Agent}

private def reserveGate (s : State Agent) (generation : Nat) (destination : Agent)
    (g : Grant Agent) : State Agent :=
  putGrant (atProtocol s (R.enqueue (R.issue s.protocol generation (.gate destination))
    (.publish s.protocol.next))) s.protocol.next g

/-- Registering a reserved gate adds no executing writer or physical use. -/
private theorem reserveGate_preserves (h : Invariant allocation s) (g : Grant Agent)
    (sameGeneration : g.generation = generation) (sameSubject : g.subject = destination)
    (bounded : g.extent.Within allocation)
    (readonly : g.writable = false → Frozen s g.generation)
    (hp : R.Invariant (R.enqueue (R.issue s.protocol generation (.gate destination))
      (.publish s.protocol.next))) :
    Invariant allocation (reserveGate s generation destination g) := by
  have fresh := grants_fresh h (Nat.le_refl s.protocol.next)
  have other : ∀ i grant, s.grants i = some grant → i ≠ s.protocol.next := by
    intro i grant found same
    subst i
    simp [fresh] at found
  constructor
  · exact hp
  · intro i grant found
    change (if i = s.protocol.next then some g else s.grants i) = some grant at found
    by_cases same : i = s.protocol.next
    · subst i
      simp at found
      subst grant
      exact ⟨{ generation, kind := .gate destination }, by simp [reserveGate,putGrant,atProtocol,R.enqueue,R.issue,R.put],
        sameGeneration.symm, sameSubject.symm, bounded⟩
    · simp only [if_neg same] at found
      obtain ⟨e,he,rest⟩ := h.grantsBound i grant found
      exact ⟨e,by simpa [reserveGate,putGrant,atProtocol,R.enqueue,R.issue,R.put,same] using he,rest⟩
  · intro i e found
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at found
    by_cases same : i = s.protocol.next
    · subst i
      exact ⟨g,by simp [reserveGate,putGrant]⟩
    · simp only [if_neg same] at found
      obtain ⟨grant,hg⟩ := h.grantsTotal i e found
      exact ⟨grant,by simpa [reserveGate,putGrant,atProtocol,same] using hg⟩
  · intro r payload found
    obtain ⟨q,parent,hq,hg,rest⟩ := h.payloadBound r payload found
    exact ⟨q,parent,hq,by simpa [reserveGate,putGrant,atProtocol,other _ _ hg] using hg,rest⟩
  · exact h.payloadTotal
  · intro r i registered
    obtain ⟨payload,hp,hg⟩ := h.registeredBound r i registered
    exact ⟨payload,hp,by simpa [reserveGate,putGrant,atProtocol,other _ _ hg] using hg⟩
  · exact h.pendingWriter
  · intro i grant e hg he writer unsealed executing
    change (if i = s.protocol.next then some g else s.grants i) = some grant at hg
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at he
    by_cases same : i = s.protocol.next
    · subst i
      simp at he
      subst e
      contradiction
    · simp only [if_neg same] at hg he
      exact h.executingWriter i grant e hg he writer unsealed executing
  · exact h.readerPayload
  · intro i grant hg reader
    change (if i = s.protocol.next then some g else s.grants i) = some grant at hg
    by_cases same : i = s.protocol.next
    · subst i
      simp at hg
      subst grant
      exact readonly reader
    · simp only [if_neg same] at hg
      exact h.readerGrant i grant hg reader
  · intro i readable
    obtain ⟨grant,hg,frozen⟩ := h.readableSound i readable
    exact ⟨grant,by simpa [reserveGate,putGrant,atProtocol,other _ _ hg] using hg,frozen⟩
  · intro i grant e hg he writer
    change (if i = s.protocol.next then some g else s.grants i) = some grant at hg
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at he
    by_cases same : i = s.protocol.next
    · subst i
      simp at he
      subst e
      exact Nat.zero_le _
    · simp only [if_neg same] at hg he
      exact h.sequential i grant e hg he writer

private theorem resolved_transfer_move (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) (sealed : e.sealed = true)
    (held : s.tokens generation = .transfer i) :
    Invariant allocation (move s generation location) := by
  apply move_invariant h
  · intro r p hp writer absent
    apply token_move_other (h.pendingWriter r p hp writer absent)
    simp [held]
  · intro j g n hg hn writer unsealed executing
    have old := h.executingWriter j g n hg hn writer unsealed executing
    by_cases same : g.generation = generation
    · have loc : executingLocation n.kind j = .transfer i := by rw [same,held] at old; exact old.symm
      cases kind : n.kind with
      | gate a => simp [kind,Executing] at executing
      | use a => simp [kind,executingLocation] at loc
      | transfer a =>
          have ji : j = i := by simpa [kind,executingLocation] using loc
          subst j
          have eq : n = e := Option.some.inj (hn.symm.trans found)
          simp [eq,sealed] at unsealed
    · simpa [move,same] using old
  · intro g frozen
    exact move_frozen frozen (by intro j; simp [held])

def activatedState (s : State Agent) (i : Nat) (e : R.Entry Agent)
    (destination : Agent) (g : Grant Agent) : State Agent :=
  let t := putGrant (atProtocol s
    (R.enqueue (R.issue (R.put s.protocol i (R.resolved e s.protocol.next))
      e.generation (.gate destination)) (.publish s.protocol.next))) s.protocol.next g
  if g.writable then move t g.generation (.gate s.protocol.next)
  else readEnable t s.protocol.next

theorem activate_preserves (h : Invariant allocation s) (i : Nat) (e : R.Entry Agent)
    (destination : Agent) (g : Grant Agent)
    (packet : R.Packet.activate i ∈ s.protocol.packets)
    (found : s.protocol.entries i = some e) (transfer : e.kind = .transfer destination)
    (pending : e.receiver = none) (granted : s.grants i = some g) :
    Invariant allocation (activatedState s i e destination g) := by
  have unsealed : e.sealed = false := by
    simpa [pending] using h.protocol.2.transferSeal i e destination found transfer
  have genSub := grant_entry h granted found
  have subjectEq : g.subject = destination := by simpa [transfer,subject] using genSub.2.1.symm
  have freshIndex : i ≠ s.protocol.next := by
    have bound := Q.registered_lt h.protocol.1 (R.project_found found)
    change i < s.protocol.next at bound
    omega
  have resolvedProtocol : R.Invariant (R.put s.protocol i (R.resolved e s.protocol.next)) := by
    constructor
    · rw [R.project_put]
      exact Q.replace_invariant h.protocol.1 (R.project_found found)
        (Q.resolved_ok (h.protocol.1.entriesOK i _ (R.project_found found))) (by simp [R.abstractEntry, R.resolved])
    · apply R.local_put (new := R.resolved e s.protocol.next) h.protocol.2 found rfl rfl
      · intro; rfl
      · intro; refine ⟨rfl,?_⟩
        intro a use
        simp [R.resolved,transfer] at use
      · intro a gate
        simp [R.resolved,transfer] at gate
      · intro; intro; rfl
  have resolvedInv : Invariant allocation (atProtocol s (R.put s.protocol i (R.resolved e s.protocol.next))) := by
    apply replace_preserves (fresh := R.resolved e s.protocol.next) h found rfl rfl (by simp [R.resolved])
    · intro grant hg writer
      exact h.sequential i grant e hg found writer
    · exact resolvedProtocol
  have finalProtocol := R.step_preserves_invariant h.protocol
    (R.Step.activate s.protocol i e destination packet found transfer pending)
  let base := atProtocol s (R.put s.protocol i (R.resolved e s.protocol.next))
  let reserved := reserveGate base e.generation destination g
  have reservedInv : Invariant allocation reserved :=
    reserveGate_preserves resolvedInv g genSub.1.symm subjectEq genSub.2.2
      (h.readerGrant i g granted) finalProtocol
  have reservedGrant : reserved.grants s.protocol.next = some g := by simp [reserved,reserveGate,base,putGrant,atProtocol,R.put]
  change Invariant allocation (if g.writable then move reserved g.generation (.gate s.protocol.next)
    else readEnable reserved s.protocol.next)
  cases writer : g.writable
  · apply enable_preserves reservedInv reservedGrant
    exact h.readerGrant i g granted writer
  · have held : reserved.tokens g.generation = .transfer i := by
      have original := h.executingWriter i g e granted found writer unsealed (by simp [transfer,Executing])
      simpa [reserved,reserveGate,base,putGrant,atProtocol,transfer,executingLocation] using original
    have resolvedFound : reserved.protocol.entries i = some (R.resolved e s.protocol.next) := by
      simp [reserved,reserveGate,base,putGrant,atProtocol,R.enqueue,R.issue,R.put,freshIndex]
    exact resolved_transfer_move reservedInv resolvedFound rfl held

end Aurora.A
