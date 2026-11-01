import A.Admission
import A.Registration
import A.Activation
import A.Safety
namespace Aurora.A

variable {Agent : Type} {s t u : State Agent}

theorem step_preserves_invariant (h : Invariant allocation s)
    (step : Step issuer initialSubject allocation s event t) : Invariant allocation t := by
  cases step with
  | root active available => exact root_preserves h issuer initialSubject active available
  | request i nonce e g destination footprint writable delegates found gate granted published notClosed fresh
      within delegation attenuate permission =>
    exact request_preserves h i nonce e g destination footprint writable delegates found gate granted published
      notClosed fresh within delegation attenuate permission
  | register r destination e a p packet absent found gate payload =>
    exact register_preserves h packet absent found gate payload
  | activate i e destination g packet found transfer pending granted =>
    exact activate_preserves h i e destination g packet found transfer pending granted
  | submit i e g found use granted published notClosed sequential =>
    exact submit_preserves h found use granted published notClosed sequential
  | effect => exact h
  | returnUse r i e p registered payload writer origin found use bound receipt fresh =>
    exact return_preserves h registered payload writer origin found use bound receipt fresh
  | freeze i e g footprint found gate granted within available =>
    exact freeze_preserves h found gate granted within available
  | passive p op => exact passive_preserves h op
  | reuse quiet => exact reuse_preserves h quiet
  | refuse => exact h

theorem trace_preserves_invariant (h : Invariant allocation s)
    (trace : Trace issuer initialSubject allocation s events t) : Invariant allocation t := by
  induction trace with
  | nil => exact h
  | cons step tail ih => exact ih (step_preserves_invariant h step)

theorem reachable_invariant (reachable : Reachable issuer initialSubject allocation s) :
    Invariant allocation s := by
  obtain ⟨events, trace⟩ := reachable
  exact trace_preserves_invariant initial_invariant trace

theorem reachable_stream_exclusion (reachable : Reachable issuer initialSubject allocation s)
    (left : Enabled s i cell wi) (right : Enabled s j cell wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false :=
  overlapping_enabled_streams_are_readers (reachable_invariant reachable) left right distinct

theorem reachable_effect_bounds (reachable : Reachable issuer initialSubject allocation s)
    (enabled : Enabled s i cell write) : allocation.Contains cell :=
  enabled_within_allocation (reachable_invariant reachable) enabled

theorem reachable_frozen_no_write (reachable : Reachable issuer initialSubject allocation s)
    (frozen : Frozen s s.protocol.generation footprint) (member : cell ∈ footprint) : ¬Enabled s i cell true :=
  frozen_cell_excludes_enabled_write (reachable_invariant reachable) (frozen member)

/-- Every retained request has an original issuer/subject binding and locally
attenuated footprint/write/delegation rights. Authentication is not inferred. -/
theorem reachable_payload_authorization (reachable : Reachable issuer initialSubject allocation s)
    (payload : s.payloads r = some p) :
    ∃ q parent, s.protocol.requests r = some q ∧ s.grants r.1 = some parent ∧
      p.origin = r.1 ∧ Derived parent q.destination p.grant :=
  (reachable_invariant reachable).payloadBound r p payload

theorem reachable_ticket_identity (reachable : Reachable issuer initialSubject allocation s)
    (granted : s.grants i = some g) (found : s.protocol.entries i = some e) :
    e.generation = g.generation ∧ subject e.kind = g.subject ∧ g.footprint.Within allocation :=
  grant_entry (reachable_invariant reachable) granted found

/-- Exact union AND uniqueness for the actual retained claim classification.
Read aliases are not additional exclusive claims; old unreturned uses still are. -/
theorem reachable_authority_conservation
    (reachable : Reachable issuer initialSubject allocation s)
    (issued : s.issued generation = true) :
    ∀ cell, cell ∈ allocation ↔ ∃ location, cell ∈ expected s generation location ∧
      ∀ other, cell ∈ expected s generation other → other = location := by
  have h := reachable_invariant reachable
  have partition := h.partition generation issued
  intro cell
  constructor
  · intro member
    obtain ⟨location,held⟩ := partition.cover cell member
    refine ⟨location,(h.accounted _ _ _).mp held,?_⟩
    intro other claim
    exact partition.unique other location cell ((h.accounted _ _ _).mpr claim) held
  · rintro ⟨location,claim,_⟩
    exact partition.bound location ((h.accounted _ _ _).mpr claim)

/-- The old whole-allocation exclusion is a restricted profile corollary, not
an assertion that the generalized model trace-refines the stronger A0 model. -/
theorem reachable_whole_writer_profile_exclusion
    (reachable : Reachable issuer initialSubject allocation s)
    (profile : WholeWriterProfile allocation s)
    (left : Enabled s i x wi) (right : Enabled s j y wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false :=
  whole_writer_profile_exclusion (reachable_invariant reachable) profile left right distinct

/-- Frozen backing history only grows, even when later generations are issued. -/
theorem step_preserves_frozen (h : Invariant allocation s) (frozen : Frozen s generation footprint)
    (step : Step issuer initialSubject allocation s event t) : Frozen t generation footprint := by
  cases step with
  | root active available =>
    by_cases same : generation = s.protocol.generation
    · intro cell member
      have old := frozen member
      have empty := h.unissuedEmpty s.protocol.generation available .frozen
      simp [same,empty] at old
    · simpa [Frozen, mint, putGrant, atProtocol, same] using frozen
  | request i nonce e g destination f writable delegates found gate granted published notClosed fresh
      within delegation attenuate permission =>
    cases writable
    · exact frozen
    · exact move_frozen frozen (by simp)
  | register r destination e a p packet absent found gate payload =>
    cases p.grant.writable
    · exact frozen
    · exact move_frozen frozen (by simp)
  | activate i e destination g packet found transfer pending granted =>
    cases g.writable
    · exact frozen
    · exact move_frozen frozen (by simp)
  | submit => exact frozen
  | effect => exact frozen
  | returnUse => exact move_frozen frozen (by simp)
  | freeze => exact move_frozen frozen (by simp)
  | passive => exact frozen
  | reuse => exact frozen
  | refuse => exact frozen

theorem trace_preserves_frozen (h : Invariant allocation s) (frozen : Frozen s generation footprint)
    (trace : Trace issuer initialSubject allocation s events t) : Frozen t generation footprint := by
  induction trace with
  | nil => exact frozen
  | cons step tail ih =>
    exact ih (step_preserves_invariant h step) (step_preserves_frozen h frozen step)

/-- Event immutability, not heap-byte verification. The member premise scopes
partial freeze correctly: disjoint ordinary writes remain legal. -/
theorem frozen_future_no_write (reachable : Reachable issuer initialSubject allocation s)
    (frozen : Frozen s generation footprint) (future : Trace issuer initialSubject allocation s events t)
    (current : generation = t.protocol.generation) (member : cell ∈ footprint) : ¬Enabled t i cell true := by
  have h := reachable_invariant reachable
  have ht := trace_preserves_invariant h future
  have ft := trace_preserves_frozen h frozen future
  exact frozen_cell_excludes_enabled_write ht (by simpa [current] using ft member)

/-- A returned-ticket tombstone is permanent, including after new borrowing
and generation reuse. No invariant premise or fresh-generation reset is hidden. -/
theorem step_preserves_returned (returned : s.returned i = true)
    (step : Step issuer initialSubject allocation s event t) : t.returned i = true := by
  cases step <;> simp_all [mint,move,putGrant,putPayload,atProtocol,readEnable,markReturned]
  all_goals split <;> simp_all

theorem trace_preserves_returned (returned : s.returned i = true)
    (trace : Trace issuer initialSubject allocation s events t) : t.returned i = true := by
  induction trace with
  | nil => exact returned
  | cons step tail ih => exact ih (step_preserves_returned returned step)
end Aurora.A
