import A.Invariants
import A.Simulation

namespace Aurora.A

variable {Agent : Type} {s t : State Agent} {p q : R.State Agent}
variable {allocation : Footprint} {issuer initialSubject : Agent}

/-- An endpoint-only update cannot create a new entry or extend physical work. -/
private theorem put_entry_backward (oldFound : p.entries j = some old)
    (generation : new.generation = old.generation) (kind : new.kind = old.kind)
    (sealMonotone : new.sealed = false → old.sealed = false) (work : new.work ≤ old.work)
    (found : (R.put p j new).entries i = some e) :
    ∃ before, p.entries i = some before ∧ e.generation = before.generation ∧
      e.kind = before.kind ∧ (e.sealed = false → before.sealed = false) ∧ e.work ≤ before.work := by
  by_cases same : i = j
  · subst i
    simp [R.put] at found
    subst e
    exact ⟨old, oldFound, generation, kind, sealMonotone, work⟩
  · simp only [R.put, if_neg same] at found
    exact ⟨e, found, rfl, rfl, fun h => h, Nat.le_refl _⟩

/-- Passive operations preserve identity/kind, cannot unseal, and cannot add work. -/
theorem passive_entry_backward (operation : Passive p q) (found : q.entries i = some e) :
    ∃ before, p.entries i = some before ∧ e.generation = before.generation ∧
      e.kind = before.kind ∧ (e.sealed = false → before.sealed = false) ∧ e.work ≤ before.work := by
  cases operation <;> try exact ⟨e, found, rfl, rfl, fun h => h, Nat.le_refl _⟩
  case publish j old packet oldFound kind unsealed =>
    exact put_entry_backward (new := { old with published := true }) oldFound rfl rfl (fun h => h) (Nat.le_refl _) found
  case close j old packet oldFound kind =>
    exact put_entry_backward (new := { old with closed := true }) oldFound rfl rfl (fun h => h) (Nat.le_refl _) found
  case finishOne j n old a oldFound use work =>
    exact put_entry_backward (new := { old with work := n }) oldFound rfl rfl (fun h => h) (by simp [work]) found
  case sealGate j old a oldFound gate closed settled =>
    exact put_entry_backward (new := { old with sealed := true }) oldFound rfl rfl (by simp) (Nat.le_refl _) found
  case sealUse j old a oldFound use closed drained =>
    exact put_entry_backward (new := { old with sealed := true }) oldFound rfl rfl (by simp) (Nat.le_refl _) found
  case receiveReceipt j generation old packet oldFound bound =>
    exact put_entry_backward (new := { old with receipt := true }) oldFound rfl rfl (fun h => h) (Nat.le_refl _) found
  case retire j old oldFound receipt =>
    exact put_entry_backward (new := { old with live := false }) oldFound rfl rfl (fun h => h) (Nat.le_refl _) found

private theorem put_entry_identity (oldFound : p.entries j = some old)
    (generation : new.generation = old.generation) (kind : new.kind = old.kind) :
    ((R.put p j new).entries i).map (fun e => (e.generation, e.kind)) =
      (p.entries i).map (fun e => (e.generation, e.kind)) := by
  by_cases same : i = j
  · subst i
    simp [R.put, oldFound, generation, kind]
  · simp [R.put, same]

/-- No passive transition creates, deletes or changes an entry's identity/kind. -/
theorem passive_entry_identity (operation : Passive p q) (i : Nat) :
    (q.entries i).map (fun e => (e.generation, e.kind)) =
      (p.entries i).map (fun e => (e.generation, e.kind)) := by
  cases operation <;> try rfl
  all_goals apply put_entry_identity <;> first | assumption | rfl

private theorem put_receiver_identity (oldFound : p.entries j = some old)
    (receiver : new.receiver = old.receiver) :
    ((R.put p j new).entries i).map R.Entry.receiver =
      (p.entries i).map R.Entry.receiver := by
  by_cases same : i = j
  · subst i; simp [R.put, oldFound, receiver]
  · simp [R.put, same]

/-- Passive handlers cannot resolve a transfer or change its reserved receiver. -/
theorem passive_receiver_identity (operation : Passive p q) (i : Nat) :
    (q.entries i).map R.Entry.receiver = (p.entries i).map R.Entry.receiver := by
  cases operation <;> try rfl
  all_goals apply put_receiver_identity <;> first | assumption | rfl

theorem passive_receiver_same (operation : Passive p q)
    (before : p.entries i = some e) (after : q.entries i = some n) :
    n.receiver = e.receiver := by
  have identity := passive_receiver_identity operation i
  simpa [before, after] using identity

theorem passive_entry_forward (operation : Passive p q) (found : p.entries i = some e) :
    ∃ after, q.entries i = some after ∧ after.generation = e.generation ∧ after.kind = e.kind := by
  have identity := passive_entry_identity operation i
  cases afterFound : q.entries i with
  | none => simp [afterFound, found] at identity
  | some after =>
      simp only [afterFound, found, Option.map_some, Option.some.injEq, Prod.mk.injEq] at identity
      exact ⟨after, rfl, identity.1, identity.2⟩

/-- Settling a request changes no immutable destination and creates no request. -/
theorem passive_request_backward (operation : Passive p q)
    (found : q.requests r = some request) :
    ∃ before, p.requests r = some before ∧ request.destination = before.destination := by
  cases operation <;> try exact ⟨request, found, rfl⟩
  case grant id i old packet oldFound =>
    by_cases same : r = id
    · subst r
      simp [R.enqueue, R.putRequest] at found
      subst request
      exact ⟨old, oldFound, rfl⟩
    · simp only [R.enqueue, R.putRequest, if_neg same] at found
      exact ⟨request, found, rfl⟩

theorem passive_request_forward (operation : Passive p q)
    (found : p.requests r = some request) :
    ∃ after, q.requests r = some after ∧ after.destination = request.destination := by
  cases operation <;> try exact ⟨request, found, rfl⟩
  case grant id i old packet oldFound =>
    by_cases same : r = id
    · subst r
      have eq : old = request := Option.some.inj (oldFound.symm.trans found)
      subst old
      exact ⟨{ request with settled := true }, by simp [R.enqueue, R.putRequest], rfl⟩
    · exact ⟨request, by simpa [R.enqueue, R.putRequest, same] using found, rfl⟩

theorem passive_registrations (operation : Passive p q) : q.registrations = p.registrations := by
  cases operation <;> rfl

theorem passive_generation (operation : Passive p q) : q.generation = p.generation := by
  cases operation <;> rfl

/-- Fresh protocol tickets never overwrite an existing grant. -/
theorem step_preserves_grant (h : Invariant allocation s)
    (step : Step issuer initialSubject allocation s event t)
    (found : s.grants i = some g) : t.grants i = some g := by
  have absent := grants_fresh h (Nat.le_refl s.protocol.next)
  have different : i ≠ s.protocol.next := by
    intro same
    subst i
    simp [absent] at found
  cases step with
  | root active available => simpa [mint, putGrant, atProtocol, different] using found
  | request i nonce e grant destination extent writable delegates foundEntry gate granted
      published notClosed fresh within delegation attenuate permission =>
      cases writable <;> exact found
  | register r destination e a payload packet absentReg foundEntry gate hasPayload =>
      cases writable : payload.grant.writable <;>
        simpa [writable, move, putGrant, atProtocol, different] using found
  | activate ticket e destination grant packet foundEntry transfer pending granted =>
      cases writable : grant.writable <;>
        simpa [writable, move, readEnable, putGrant, atProtocol, different] using found
  | submit => exact found
  | effect => exact found
  | returnUse => exact found
  | freeze => exact found
  | passive => exact found
  | reuse => exact found
  | refuse => exact found

/-- The stable request ID continues decoding to its original immutable payload. -/
theorem step_preserves_payload (h : Invariant allocation s)
    (step : Step issuer initialSubject allocation s event t)
    (found : s.payloads r = some payload) : t.payloads r = some payload := by
  cases step with
  | root => exact found
  | request i nonce e grant destination extent writable delegates foundEntry gate granted
      published notClosed fresh within delegation attenuate permission =>
      have absent := payload_fresh h fresh
      have different : r ≠ (i, nonce) := by
        intro same
        subst r
        simp [absent] at found
      cases writable <;> simpa [move, putPayload, atProtocol, different] using found
  | register id destination e a payload packet absentReg foundEntry gate hasPayload =>
      cases writable : payload.grant.writable <;>
        simpa [writable, move, putGrant, atProtocol] using found
  | activate ticket e destination grant packet foundEntry transfer pending granted =>
      cases writable : grant.writable <;>
        simpa [writable, move, readEnable, putGrant, atProtocol] using found
  | submit => exact found
  | effect => exact found
  | returnUse => exact found
  | freeze => exact found
  | passive => exact found
  | reuse => exact found
  | refuse => exact found

end Aurora.A
