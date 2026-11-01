import Q.Model

namespace Aurora.Q

variable {Cpu : Type} {s t : State Cpu} {e replacement : Entry Cpu}

/-- Independent physical capability must remain covered by protocol liability. -/
structure EntryOK (generation : Nat) (e : Entry Cpu) : Prop where
  covered : e.possible = true → e.live = true
  receiptSound : e.receipt = true → e.possible = false
  notFuture : e.generation ≤ generation
  liveCurrent : e.live = true → e.generation = generation

structure Invariant (s : State Cpu) : Prop where
  fresh : ∀ i, s.next ≤ i → s.entries i = none
  entriesOK : ∀ i e, s.entries i = some e → EntryOK s.generation e
  quietEmpty : s.phase = .quiescent → LedgerEmpty s

theorem initial_invariant : Invariant (initial : State Cpu) := by
  constructor
  · intro i h; rfl
  · intro i e h; cases h
  · intro h; cases h

theorem registered_lt (h : Invariant s) (found : s.entries i = some e) :
    i < s.next := by
  by_cases good : i < s.next
  · exact good
  · have absent := h.fresh i (Nat.le_of_not_gt good)
    rw [found] at absent
    contradiction

theorem possible_current (h : Invariant s) (found : s.entries i = some e)
    (possible : e.possible = true) : e.generation = s.generation :=
  (h.entriesOK i e found).liveCurrent ((h.entriesOK i e found).covered possible)

theorem possible_not_quiet (h : Invariant s) (found : s.entries i = some e)
    (possible : e.possible = true) : s.phase ≠ .quiescent := by
  intro quiet
  have empty := h.quietEmpty quiet i e found
  have live := (h.entriesOK i e found).covered possible
  simp [empty] at live

/-- Replacing one identity cannot alter any other registered liability. -/
theorem put_other (s : State Cpu) (i j : Nat) (e : Entry Cpu) (different : j ≠ i) :
    (put s i e).entries j = s.entries j := by simp [put, different]

theorem replace_invariant (h : Invariant s) (found : s.entries i = some e)
    (good : EntryOK s.generation replacement)
    (noNewLiability : replacement.live = true → e.live = true) :
    Invariant (put s i replacement) := by
  have oldBound := registered_lt h found
  constructor
  · intro j bound
    change s.next ≤ j at bound
    have different : j ≠ i := by omega
    simp [put, different, h.fresh j bound]
  · intro j x hx
    by_cases same : j = i
    · subst j
      simp [put] at hx
      subst x
      exact good
    · simp [put, same] at hx
      exact h.entriesOK j x hx
  · intro quiet j x hx
    by_cases same : j = i
    · subst j
      simp [put] at hx
      subst x
      have oldEmpty := h.quietEmpty quiet i e found
      cases live : replacement.live
      · rfl
      · have := noNewLiability live
        simp [oldEmpty] at this
    · simp [put, same] at hx
      exact h.quietEmpty quiet j x hx

theorem issue_invariant (h : Invariant s) (current : generation = s.generation)
    (notQuiet : s.phase ≠ .quiescent) (kind : Kind Cpu) :
    Invariant (issue s generation kind) := by
  subst generation
  constructor
  · intro j bound
    change s.next + 1 ≤ j at bound
    have different : j ≠ s.next := by omega
    simp [issue, put, different, h.fresh j (by omega)]
  · intro j e found
    by_cases same : j = s.next
    · subst j
      simp [issue, put] at found
      subst e
      exact ⟨by simp, by simp, Nat.le_refl _, by simp [issue, put]⟩
    · simp [issue, put, same] at found
      exact h.entriesOK j e found
  · intro quiet
    exact False.elim (notQuiet quiet)

theorem stopped_ok (h : EntryOK g e) : EntryOK g (stopped e) := by
  constructor
  · simp [stopped]
  · simp [stopped]
  · exact h.notFuture
  · exact h.liveCurrent

theorem acknowledged_ok (h : EntryOK g e) (complete : e.possible = false) :
    EntryOK g (acknowledged e) := by
  exact ⟨h.covered, by simpa [acknowledged] using complete, h.notFuture, h.liveCurrent⟩

theorem retired_ok (h : EntryOK g e) (receipt : e.receipt = true) :
    EntryOK g (retired e) := by
  constructor
  · simp [retired, h.receiptSound receipt]
  · exact h.receiptSound
  · exact h.notFuture
  · simp [retired]

theorem resolved_ok (h : EntryOK g e) : EntryOK g (resolved e) := by
  exact ⟨by simp [resolved], by simp [resolved], h.notFuture, by simp [resolved]⟩

theorem step_preserves_invariant (h : Invariant s) (step : Step s event t) :
    Invariant t := by
  cases step with
  | root c active =>
      exact issue_invariant h rfl (by simp [active]) _
  | admit i e c found gate possible =>
      exact issue_invariant h (possible_current h found possible)
        (possible_not_quiet h found possible) _
  | send i e c d found gate possible =>
      exact issue_invariant h (possible_current h found possible)
        (possible_not_quiet h found possible) _
  | activate i e d found transfer possible =>
      have replaced := replace_invariant h found
        (resolved_ok (h.entriesOK i e found)) (by simp [resolved])
      exact issue_invariant replaced (by simpa only [put] using (possible_current h found possible))
        (by simpa only [put] using (possible_not_quiet h found possible)) _
  | beginClose active =>
      exact ⟨h.fresh, h.entriesOK, by simp⟩
  | hardwareStop i e found =>
      exact replace_invariant h found (stopped_ok (h.entriesOK i e found)) (by simp [stopped])
  | ack i generation e found bound complete =>
      exact replace_invariant h found (acknowledged_ok (h.entriesOK i e found) complete)
        (by simp [acknowledged])
  | retire i e found receipt =>
      exact replace_invariant h found (retired_ok (h.entriesOK i e found) receipt)
        (by simp [retired])
  | quiesce closing empty gates =>
      exact ⟨h.fresh, h.entriesOK, fun _ => empty⟩
  | reuse quiet =>
      constructor
      · exact h.fresh
      · intro i e found
        have good := h.entriesOK i e found
        have empty := h.quietEmpty quiet i e found
        exact ⟨good.covered, good.receiptSound, Nat.le_step good.notFuture,
          by simp [empty]⟩
      · simp
  | access => exact h
  | stutter => exact h

theorem trace_preserves_invariant (h : Invariant s) (trace : Trace s events t) :
    Invariant t := by
  induction trace with
  | nil => exact h
  | cons step tail ih => exact ih (step_preserves_invariant h step)

theorem reachable_invariant (reachable : Reachable s) : Invariant s := by
  obtain ⟨events, trace⟩ := reachable
  exact trace_preserves_invariant initial_invariant trace

end Aurora.Q
