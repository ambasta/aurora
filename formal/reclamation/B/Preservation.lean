import B.Heap
import B.Retention
namespace Aurora.B
variable {Agent : Type} {config : Config} {s : State Agent} {original : Heap}

theorem start_preserves (h : Invariant config original s)
    (valid : d.Valid config) (admitted : Authorized s.authority ticket d) :
    Invariant config original (start s ticket d) := by
  refine ⟨h.authority,h.source,?_⟩
  intro i c found
  by_cases same : i = ticket
  · subst i
    simp only [start,putCursor,ite_true,Option.some.injEq] at found
    subst c
    exact ⟨valid,Nat.zero_le _,admitted,by simp [start],by intro offset bound; exact False.elim (Nat.not_lt_zero offset bound)⟩
  · simp only [start,putCursor,if_neg same] at found
    have hc := h.cursors i c found
    exact ⟨hc.1,hc.2.1,hc.2.2.1,by simpa [start,same] using hc.2.2.2.1,hc.2.2.2.2⟩

theorem copy_preserves (valid : config.Valid) (h : Invariant config original s)
    (found : s.cursors ticket = some c) (remaining : c.copied < c.descriptor.count) :
    Invariant config original (copy s ticket c) := by
  have hc := h.cursors ticket c found
  refine ⟨h.authority,?_,?_⟩
  · exact source_store h.source (allocation_outside_source valid (hc.2.2.1.in_allocation h.authority remaining))
  · intro i other present
    by_cases same : i = ticket
    · subst i
      simp only [copy,putCursor,ite_true,Option.some.injEq] at present
      subst other
      exact ⟨hc.1,by dsimp [advance]; omega,hc.2.2.1,hc.2.2.2.1,copy_prefix h found remaining⟩
    · simp only [copy,putCursor,if_neg same] at present
      have ho := h.cursors i other present
      refine ⟨ho.1,ho.2.1,ho.2.2.1,ho.2.2.2.1,?_⟩
      exact cursor_store h present (fun offset bound =>
        ho.2.2.1.distinct h.authority (hc.2.2.1.enabled remaining) same (Nat.lt_of_lt_of_le bound ho.2.1))

theorem write_preserves (valid : config.Valid) (h : Invariant config original s)
    (enabled : A.Enabled s.authority ticket cell true) (idle : s.cursors ticket = none) :
    Invariant config original {s with heap := store s.heap cell value} := by
  refine ⟨h.authority,source_store h.source (allocation_outside_source valid (enabled_in_allocation h.authority enabled)),?_⟩
  intro i c found
  have hc := h.cursors i c found
  refine ⟨hc.1,hc.2.1,hc.2.2.1,hc.2.2.2.1,?_⟩
  exact cursor_store h found (fun offset bound => hc.2.2.1.distinct h.authority enabled
    (by intro same; subst i; rw [idle] at found; cases found) (Nat.lt_of_lt_of_le bound hc.2.1))

theorem control_preserves (valid : config.Valid) (h : Invariant config original s)
    (allowed : cell ∈ config.control) :
    Invariant config original {s with heap := store s.heap cell value} := by
  have outside := valid.2.2.2 cell allowed
  refine ⟨h.authority,source_store h.source outside.2,?_⟩
  intro i c found
  have hc := h.cursors i c found
  refine ⟨hc.1,hc.2.1,hc.2.2.1,hc.2.2.2.1,?_⟩
  apply cursor_store h found
  intro offset bound equal
  exact outside.1 (equal ▸ hc.2.2.1.in_allocation h.authority (Nat.lt_of_lt_of_le bound hc.2.1))

theorem fault_preserves (h : Invariant config original s) (found : s.cursors ticket = some c) :
    Invariant config original (putCursor s ticket (some {c with phase := .faulted})) := by
  refine ⟨h.authority,h.source,?_⟩
  intro i other present
  by_cases same : i = ticket
  · subst i
    simp only [putCursor,ite_true,Option.some.injEq] at present
    subst other
    exact h.cursors ticket c found
  · exact h.cursors i other (by simpa [putCursor,same] using present)

theorem release_preserves (h : Invariant config original s) :
    Invariant config original (putCursor s ticket none) := by
  refine ⟨h.authority,h.source,?_⟩
  intro i other present
  by_cases same : i = ticket
  · subst i; simp [putCursor] at present
  · exact h.cursors i other (by simpa [putCursor,same] using present)
theorem protocol_preserves (h : Invariant config original s)
    (action : A.Step issuer subject config.allocation s.authority event next)
    (held : NoHeldFinish s action) : Invariant config original {s with authority := next} := by
  refine ⟨A.step_preserves_invariant h.authority action,h.source,?_⟩
  intro i c found
  have hc := h.cursors i c found
  refine ⟨hc.1,hc.2.1,?_,hc.2.2.2.1,hc.2.2.2.2⟩
  exact hc.2.2.1.retained h.authority action (by intro finish; rw [held i finish] at found; cases found)

theorem step_preserves (valid : config.Valid) (h : Invariant config original s)
    (step : Step issuer subject config s event t) : Invariant config original t := by
  cases step with
  | protocol next event action nonwrite held => exact protocol_preserves h action held
  | beginCopy ticket d fresh empty bounds admitted => exact start_preserves h bounds admitted
  | payload ticket c found running remaining => exact copy_preserves valid h found remaining
  | write next generation ticket cell value action idle =>
    have unchanged := access_state action rfl
    subst next
    exact write_preserves valid h (write_enabled action) idle
  | control cell value allowed => exact control_preserves valid h allowed
  | fault ticket c found running => exact fault_preserves h found
  | release => exact release_preserves h

theorem trace_preserves (valid : config.Valid) (h : Invariant config original s)
    (trace : Trace issuer subject config s events t) : Invariant config original t := by
  induction trace with
  | nil => exact h
  | cons step tail ih => exact ih (step_preserves valid h step)

end Aurora.B
