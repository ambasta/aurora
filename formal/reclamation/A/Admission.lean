import A.Metadata

namespace Aurora.A
variable {Agent : Type} {allocation : Extent} {s : State Agent}

private theorem token_frame (known : s.tokens generation = old)
    (different : old ≠ s.tokens changed) :
    (if generation = changed then replacement else s.tokens generation) = old := by
  have ne : generation ≠ changed := by intro same; subst generation; exact different known.symm
  simp [ne, known]

private theorem frozen_frame (frozen : Frozen s generation)
    (notFrozen : ∀ i, s.tokens changed ≠ .frozen i) :
    ∃ i, (if generation = changed then replacement else s.tokens generation) = .frozen i := by
  obtain ⟨i, hi⟩ := frozen
  exact ⟨i, token_frame hi (fun eq => notFrozen i eq.symm)⟩

def rootState (s : State Agent) (issuer subject : Agent) (allocation : Extent) : State Agent :=
  move (putGrant (atProtocol s
    (R.enqueue (R.issue s.protocol s.protocol.generation (.gate subject)) (.publish s.protocol.next)))
    s.protocol.next ⟨issuer,subject,s.protocol.generation,allocation,true,true⟩)
    s.protocol.generation (.gate s.protocol.next)

theorem root_preserves (h : Invariant allocation s) (issuer subject : Agent)
    (active : s.protocol.phase = .active) (valid : allocation.first ≤ allocation.limit)
    (available : s.tokens s.protocol.generation = .unissued) :
    Invariant allocation (rootState s issuer subject allocation) := by
  have fresh := grants_fresh h (Nat.le_refl s.protocol.next)
  have entryFresh : s.protocol.entries s.protocol.next = none := by
    have hf := h.protocol.1.fresh s.protocol.next (Nat.le_refl _)
    cases he : s.protocol.entries s.protocol.next with
    | none => rfl
    | some e => simp [R.project, he] at hf
  have oldGrant : ∀ i g, s.grants i = some g → i ≠ s.protocol.next := by
    intro i g hg same
    subst i
    simp [fresh] at hg
  have notFrozen : ∀ i, s.tokens s.protocol.generation ≠ .frozen i := by simp [available]
  constructor
  · exact R.step_preserves_invariant h.protocol (.root s.protocol subject active)
  · intro i g hg
    change (if i = s.protocol.next then some _ else s.grants i) = some g at hg
    by_cases same : i = s.protocol.next
    · subst i
      simp at hg
      subst g
      refine ⟨{ generation := s.protocol.generation, kind := .gate subject }, ?_, rfl, rfl, ?_⟩
      · simp [rootState, move, putGrant, atProtocol, R.enqueue, R.issue, R.put]
      · exact ⟨Nat.le_refl _, valid, Nat.le_refl _⟩
    · simp only [if_neg same] at hg
      obtain ⟨e, he, rest⟩ := h.grantsBound i g hg
      exact ⟨e, by simpa [rootState, move, putGrant, atProtocol, R.enqueue, R.issue, R.put, same] using he, rest⟩
  · intro i e he
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at he
    by_cases same : i = s.protocol.next
    · subst i
      exact ⟨⟨issuer,subject,s.protocol.generation,allocation,true,true⟩, by simp [rootState, move, putGrant]⟩
    · simp only [if_neg same] at he
      obtain ⟨g, hg⟩ := h.grantsTotal i e he
      exact ⟨g, by simpa [rootState, move, putGrant, atProtocol, same] using hg⟩
  · intro r payload hpayload
    obtain ⟨q, parent, hq, hg, rest⟩ := h.payloadBound r payload hpayload
    exact ⟨q, parent, hq, by simpa [rootState, move, putGrant, atProtocol, oldGrant _ _ hg] using hg, rest⟩
  · exact h.payloadTotal
  · intro r i hi
    obtain ⟨payload, hpayload, hg⟩ := h.registeredBound r i hi
    exact ⟨payload, hpayload, by simpa [rootState, move, putGrant, atProtocol, oldGrant _ _ hg] using hg⟩
  · intro r payload hpayload writer absent
    have known := h.pendingWriter r payload hpayload writer absent
    exact token_frame (s := s) known (by simp [available])
  · intro i g e hg he writer unsealed executing
    change (if i = s.protocol.next then some _ else s.grants i) = some g at hg
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at he
    by_cases same : i = s.protocol.next
    · subst i
      simp at he
      subst e
      contradiction
    · simp only [if_neg same] at hg he
      have known := h.executingWriter i g e hg he writer unsealed executing
      apply token_frame (s := s) known
      cases e.kind <;> simp [executingLocation, available]
  · intro r payload hpayload reader
    exact frozen_frame (h.readerPayload r payload hpayload reader) notFrozen
  · intro i g hg reader
    change (if i = s.protocol.next then some _ else s.grants i) = some g at hg
    by_cases same : i = s.protocol.next
    · subst i
      simp at hg
      subst g
      contradiction
    · simp only [if_neg same] at hg
      exact frozen_frame (h.readerGrant i g hg reader) notFrozen
  · intro i readable
    obtain ⟨g, hg, frozen⟩ := h.readableSound i readable
    exact ⟨g, by simpa [rootState, move, putGrant, atProtocol, oldGrant _ _ hg] using hg,
      frozen_frame frozen notFrozen⟩
  · intro i g e hg he writer
    change (if i = s.protocol.next then some _ else s.grants i) = some g at hg
    change (if i = s.protocol.next then some _ else s.protocol.entries i) = some e at he
    by_cases same : i = s.protocol.next
    · subst i
      simp at he
      subst e
      exact Nat.zero_le _
    · simp only [if_neg same] at hg he
      exact h.sequential i g e hg he writer

def requestState (s : State Agent) (i nonce : Nat) (g : Grant Agent)
    (destination : Option Agent) (extent : Extent) (writable delegates : Bool) : State Agent :=
  let t := putPayload (atProtocol s
    (R.enqueue (R.putRequest s.protocol (i,nonce) ⟨destination,false⟩)
      (.register (i,nonce) destination))) (i,nonce)
    ⟨child g destination extent writable delegates,i⟩
  if writable then move t g.generation (.request (i,nonce)) else t

theorem request_preserves (h : Invariant allocation s) (i nonce : Nat)
    (e : R.Entry Agent) (g : Grant Agent) (destination : Option Agent)
    (extent : Extent) (writable delegates : Bool)
    (found : s.protocol.entries i = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants i = some g) (published : e.published = true)
    (notClosed : e.closed = false) (fresh : s.protocol.requests (i,nonce) = none)
    (within : extent.Within g.extent)
    (delegation : destination.isSome = true → g.delegates = true)
    (attenuate : delegates = true → g.delegates = true)
    (permission : if writable then g.writable = true ∧ s.tokens g.generation = .gate i
                  else s.readable i = true) :
    Invariant allocation (requestState s i nonce g destination extent writable delegates) := by
  let t := requestState s i nonce g destination extent writable delegates
  let protocol := R.enqueue (R.putRequest s.protocol (i,nonce) ⟨destination,false⟩)
    (.register (i,nonce) destination)
  let newPayload : Payload Agent := ⟨child g destination extent writable delegates,i⟩
  have hp : t.protocol = protocol := by cases writable <;> rfl
  have hg : t.grants = s.grants := by cases writable <;> rfl
  have hr : t.readable = s.readable := by cases writable <;> rfl
  have hpay : t.payloads = fun r => if r = (i,nonce) then some newPayload else s.payloads r := by
    cases writable <;> rfl
  have ht : ∀ gen, t.tokens gen =
      if writable then (if gen = g.generation then .request (i,nonce) else s.tokens gen)
      else s.tokens gen := by intro gen; cases writable <;> rfl
  have freshPayload := payload_fresh h fresh
  have oldPayload : ∀ r p, s.payloads r = some p → r ≠ (i,nonce) := by
    intro r p hfound same
    subst r
    simp [freshPayload] at hfound
  have keepFrozen : ∀ gen, Frozen s gen → Frozen t gen := by
    intro gen frozen
    cases writable
    · exact frozen
    · have held := permission.2
      obtain ⟨j,hj⟩ := frozen_frame (replacement := .request (i,nonce)) frozen
        (changed := g.generation) (by simp [held])
      exact ⟨j, by simpa [ht] using hj⟩
  have keepToken : ∀ gen loc, s.tokens gen = loc → loc ≠ .gate i → t.tokens gen = loc := by
    intro gen loc known different
    cases writable
    · exact known
    · have held := permission.2
      have preserve := token_frame (replacement := .request (i,nonce)) known
        (changed := g.generation) (by simpa [held] using different)
      simpa [ht] using preserve
  have derived : Derived g destination newPayload.grant := by
    refine ⟨rfl,rfl,rfl,within,?_,attenuate,delegation⟩
    intro hw
    change writable = true at hw
    subst writable
    exact permission.1
  change Invariant allocation t
  constructor
  · rw [hp]
    exact R.step_preserves_invariant h.protocol
      (.request s.protocol i nonce e g.subject destination found gate published notClosed fresh)
  · intro j grant hgrant
    rw [hg] at hgrant
    obtain ⟨old,ho,rest⟩ := h.grantsBound j grant hgrant
    exact ⟨old, by simpa [hp,protocol,R.enqueue,R.putRequest] using ho, rest⟩
  · intro j entry hentry
    have old : s.protocol.entries j = some entry := by simpa only [hp] using hentry
    obtain ⟨grant,hgrant⟩ := h.grantsTotal j entry old
    exact ⟨grant,by simpa [hg] using hgrant⟩
  · intro r payload hfound
    rw [hpay] at hfound
    by_cases same : r = (i,nonce)
    · subst r
      simp at hfound
      subst payload
      exact ⟨⟨destination,false⟩,g,by simp [hp,protocol,R.enqueue,R.putRequest],
        by simpa [hg] using granted,rfl,derived⟩
    · simp only [if_neg same] at hfound
      obtain ⟨q,parent,hq,hparent,rest⟩ := h.payloadBound r payload hfound
      exact ⟨q,parent,by simpa [hp,protocol,R.enqueue,R.putRequest,same] using hq,
        by simpa [hg] using hparent,rest⟩
  · intro r q hq
    rw [hp] at hq
    change (if r = (i,nonce) then some ⟨destination,false⟩ else s.protocol.requests r) = some q at hq
    by_cases same : r = (i,nonce)
    · subst r
      exact ⟨newPayload,by simp [hpay]⟩
    · simp only [if_neg same] at hq
      obtain ⟨payload,hpayload⟩ := h.payloadTotal r q hq
      exact ⟨payload,by simpa [hpay,same] using hpayload⟩
  · intro r j registered
    obtain ⟨payload,hpayload,hgrant⟩ := h.registeredBound r j (by simpa only [hp] using registered)
    exact ⟨payload,by simpa [hpay,oldPayload _ _ hpayload] using hpayload,
      by simpa [hg] using hgrant⟩
  · intro r payload hfound writer absent
    rw [hpay] at hfound
    by_cases same : r = (i,nonce)
    · subst r
      simp at hfound
      subst payload
      change writable = true at writer
      simp [ht,writer,newPayload,child]
    · simp only [if_neg same] at hfound
      exact keepToken _ _ (h.pendingWriter r payload hfound writer (by simpa only [hp] using absent)) (by simp)
  · intro j grant entry hgrant hentry writer unsealed executing
    rw [hg] at hgrant
    have oldEntry : s.protocol.entries j = some entry := by simpa only [hp] using hentry
    have known := h.executingWriter j grant entry hgrant oldEntry writer unsealed executing
    apply keepToken _ _ known
    cases kind : entry.kind <;> simp_all [Executing,executingLocation]
  · intro r payload hfound reader
    rw [hpay] at hfound
    by_cases same : r = (i,nonce)
    · subst r
      simp at hfound
      subst payload
      change writable = false at reader
      subst writable
      obtain ⟨grant,hgrant,frozen⟩ := h.readableSound i permission
      have eq : grant = g := Option.some.inj (hgrant.symm.trans granted)
      subst grant
      exact frozen
    · simp only [if_neg same] at hfound
      exact keepFrozen _ (h.readerPayload r payload hfound reader)
  · intro j grant hgrant reader
    rw [hg] at hgrant
    exact keepFrozen _ (h.readerGrant j grant hgrant reader)
  · intro j readable
    rw [hr] at readable
    obtain ⟨grant,hgrant,frozen⟩ := h.readableSound j readable
    exact ⟨grant,by simpa [hg] using hgrant,keepFrozen _ frozen⟩
  · intro j grant entry hgrant hentry writer
    rw [hg] at hgrant
    exact h.sequential j grant entry hgrant (by simpa only [hp] using hentry) writer

end Aurora.A
