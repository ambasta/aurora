import A.Admission
import A.Registration
import A.Activation
import A.Safety
namespace Aurora.A

variable {Agent : Type} {s t u : State Agent}

theorem step_preserves_invariant (h : Invariant allocation s)
    (step : Step issuer initialSubject allocation s event t) : Invariant allocation t := by
  cases step with
  | root active valid available => exact root_preserves h issuer initialSubject active valid available
  | request i nonce e g destination extent writable delegates found gate granted published notClosed fresh
      within delegation attenuate permission =>
    exact request_preserves h i nonce e g destination extent writable delegates found gate granted published
      notClosed fresh within delegation attenuate permission
  | register r destination e a p packet absent found gate payload =>
    exact register_preserves h packet absent found gate payload
  | activate i e destination g packet found transfer pending granted =>
    exact activate_preserves h i e destination g packet found transfer pending granted
  | submit i e g found use granted published notClosed sequential =>
    exact submit_preserves h found use granted published notClosed sequential
  | effect => exact h
  | returnUse r i e p registered payload writer found use receipt held =>
    exact return_preserves h found use receipt held
  | freeze i g granted held => exact freeze_preserves h granted held
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
    (left : Enabled s i x wi) (right : Enabled s j y wj) (distinct : i ≠ j) :
    wi = false ∧ wj = false :=
  distinct_enabled_streams_are_readers (reachable_invariant reachable) left right distinct

theorem reachable_effect_bounds (reachable : Reachable issuer initialSubject allocation s)
    (enabled : Enabled s i cell write) : allocation.Contains cell :=
  enabled_within_allocation (reachable_invariant reachable) enabled

theorem reachable_frozen_no_write (reachable : Reachable issuer initialSubject allocation s)
    (frozen : Frozen s s.protocol.generation) : ¬Enabled s i cell true :=
  frozen_excludes_enabled_write (reachable_invariant reachable) frozen

/-- Every retained request has an original issuer/subject binding and locally
attenuated extent/write/delegation rights. Authentication is not inferred. -/
theorem reachable_payload_authorization (reachable : Reachable issuer initialSubject allocation s)
    (payload : s.payloads r = some p) :
    ∃ q parent, s.protocol.requests r = some q ∧ s.grants r.1 = some parent ∧
      p.origin = r.1 ∧ Derived parent q.destination p.grant :=
  (reachable_invariant reachable).payloadBound r p payload

theorem reachable_ticket_identity (reachable : Reachable issuer initialSubject allocation s)
    (granted : s.grants i = some g) (found : s.protocol.entries i = some e) :
    e.generation = g.generation ∧ subject e.kind = g.subject ∧ g.extent.Within allocation :=
  grant_entry (reachable_invariant reachable) granted found

/-- Frozen history is never thawed, even when a later generation is issued. -/
theorem step_preserves_frozen (h : Invariant allocation s) (frozen : Frozen s generation)
    (step : Step issuer initialSubject allocation s event t) : Frozen t generation := by
  obtain ⟨f, hf⟩ := frozen
  have other {changed : Nat} {loc : Location} (held : s.tokens changed = loc)
      (different : loc ≠ .frozen f) : generation ≠ changed := by
    intro eq; subst generation
    exact different (held.symm.trans hf)
  cases step with
  | root active valid available =>
    have ne := other available (by simp)
    exact ⟨f, by simpa [move, putGrant, atProtocol, ne] using hf⟩
  | request i nonce e g destination extent writable delegates found gate granted published notClosed fresh
      within delegation attenuate permission =>
    cases hw : writable
    · simpa [hw, Frozen, putPayload, atProtocol] using (show Frozen s generation from ⟨f,hf⟩)
    · have held : s.tokens g.generation = .gate i := (by simpa [hw] using permission :
        g.writable = true ∧ s.tokens g.generation = .gate i).2
      have ne := other held (by simp)
      exact ⟨f, by simpa [hw, move, putPayload, atProtocol, ne] using hf⟩
  | register r destination e a p packet absent found gate payload =>
    cases hw : p.grant.writable
    · simpa [hw, Frozen, putGrant, atProtocol] using (show Frozen s generation from ⟨f,hf⟩)
    · have held := h.pendingWriter r p payload hw absent
      have ne := other held (by simp)
      exact ⟨f, by simpa [hw, move, putGrant, atProtocol, ne] using hf⟩
  | activate i e destination g packet found transfer pending granted =>
    cases hw : g.writable
    · simpa [hw, Frozen, readEnable, putGrant, atProtocol] using (show Frozen s generation from ⟨f,hf⟩)
    · have hs := h.protocol.2.transferSeal i e destination found transfer
      have unsealed : e.sealed = false := by simpa [pending] using hs
      have held := h.executingWriter i g e granted found hw unsealed (by simp [transfer, Executing])
      have loc : s.tokens g.generation = .transfer i := by simpa [transfer, executingLocation] using held
      have ne := other loc (by simp)
      exact ⟨f, by simpa [hw, move, putGrant, atProtocol, ne] using hf⟩
  | submit => exact ⟨f,hf⟩
  | effect => exact ⟨f,hf⟩
  | returnUse r i e p registered payload writer found use receipt held =>
    have ne := other held (by simp)
    exact ⟨f, by simpa [move, ne] using hf⟩
  | freeze i g granted held =>
    have ne := other held (by simp)
    exact ⟨f, by simpa [readEnable, move, ne] using hf⟩
  | passive => exact ⟨f,hf⟩
  | reuse => exact ⟨f,hf⟩
  | refuse => exact ⟨f,hf⟩

theorem trace_preserves_frozen (h : Invariant allocation s) (frozen : Frozen s generation)
    (trace : Trace issuer initialSubject allocation s events t) : Frozen t generation := by
  induction trace with
  | nil => exact frozen
  | cons step tail ih =>
    exact ih (step_preserves_invariant h step) (step_preserves_frozen h frozen step)

/-- Event immutability, not heap-byte verification: while this version remains
current, every finite future extension after freezing excludes ordinary writes. -/
theorem frozen_future_no_write (reachable : Reachable issuer initialSubject allocation s)
    (frozen : Frozen s generation) (future : Trace issuer initialSubject allocation s events t)
    (current : generation = t.protocol.generation) : ¬Enabled t i cell true := by
  have h := reachable_invariant reachable
  have ht := trace_preserves_invariant h future
  have ft := trace_preserves_frozen h frozen future
  exact frozen_excludes_enabled_write ht (by simpa [current] using ft)

end Aurora.A
