import Q.Invariants

namespace Aurora.Q

variable {Cpu : Type} {s t u v : State Cpu} {e : Entry Cpu}

/-- All three kinds of physical possibility are ruled out, not just CPU loads. -/
theorem quiescent_no_possibility (h : Invariant s) (quiet : s.phase = .quiescent)
    (found : s.entries i = some e) : e.possible = false := by
  have empty := h.quietEmpty quiet i e found
  have covered := (h.entriesOK i e found).covered
  cases possible : e.possible
  · rfl
  · have := covered possible
    simp [empty] at this

theorem step_generation_monotone (step : Step s event t) :
    s.generation ≤ t.generation := by
  cases step <;> simp [issue, put]

theorem trace_generation_monotone (trace : Trace s events t) :
    s.generation ≤ t.generation := by
  induction trace with
  | nil => exact Nat.le_refl _
  | cons step tail ih => exact Nat.le_trans (step_generation_monotone step) ih

theorem access_generation_current (h : Invariant s)
    (step : Step s (.access generation ticket) t) : generation = s.generation := by
  cases step with
  | access i e c found use possible => exact possible_current h found possible

/-- Every arbitrarily long future extension after reuse excludes all earlier
    generations, not merely an access at the instant of the reuse transition. -/
theorem after_reuse_no_old_access (h : Invariant s)
    (reuse : Step s (.reuse old) t) (future : Trace t events u)
    (access : Step u (.access generation ticket) v) : old < generation := by
  have ht := step_preserves_invariant h reuse
  have hu := trace_preserves_invariant ht future
  have accessCurrent := access_generation_current hu access
  have monotone := trace_generation_monotone future
  cases reuse
  simp only at monotone
  omega

/-- No fixed CPU cardinality appears in the theorem; instantiate Cpu := Fin n. -/
theorem finite_cpu_safe_reuse (n : Nat) (s t u v : State (Fin n))
    (reachable : Reachable s) (reuse : Step s (.reuse old) t)
    (future : Trace t events u) (access : Step u (.access generation ticket) v) :
    old < generation :=
  after_reuse_no_old_access (reachable_invariant reachable) reuse future access

/-- An identified retirement preserves every other obligation exactly. -/
theorem retirement_preserves_other_obligations (s : State Cpu) (i j : Nat)
    (e : Entry Cpu) (different : j ≠ i) :
    (put s i (retired e)).entries j = s.entries j := put_other s i j _ different

/-- An accepted receipt for this incarnation prevents further admission there. -/
theorem acknowledged_gate_cannot_admit (h : Invariant s)
    (found : s.entries i = some e) (receipt : e.receipt = true) :
    e.possible ≠ true := by
  simp [(h.entriesOK i e found).receiptSound receipt]

/-- Abstract completion-oracle dispatcher, NOT an implemented receipt verifier.
    Its physical-completion test must be refined by a real hardware contract. -/
def receiveAck (s : State Cpu) (ticket generation : Nat) : State Cpu :=
  match s.entries ticket with
  | none => s
  | some e => if e.generation = generation ∧ e.possible = false
      then put s ticket (acknowledged e) else s

theorem receiveAck_step (s : State Cpu) (ticket generation : Nat) :
    Step s .internal (receiveAck s ticket generation) := by
  unfold receiveAck
  split
  · exact .stutter s
  · rename_i e found
    split
    · rename_i valid
      exact .ack s ticket generation e found valid.1 valid.2
    · exact .stutter s

theorem stale_ack_inert (found : s.entries ticket = some e)
    (stale : e.generation ≠ generation) : receiveAck s ticket generation = s := by
  simp [receiveAck, found, stale]

theorem unknown_ack_inert (absent : s.entries ticket = none) :
    receiveAck s ticket generation = s := by simp [receiveAck, absent]

theorem put_existing (found : s.entries ticket = some e) : put s ticket e = s := by
  cases s
  simp only [put, State.mk.injEq, true_and, eq_self]
  funext j
  by_cases same : j = ticket
  · subst j; simpa using found.symm
  · simp [same]

theorem duplicate_ack_inert (found : s.entries ticket = some e)
    (already : e.receipt = true) : receiveAck s ticket generation = s := by
  have same : acknowledged e = e := by
    cases e
    simp_all [acknowledged]
  simp only [receiveAck, found]
  split
  · rw [same]; exact put_existing found
  · rfl

end Aurora.Q
