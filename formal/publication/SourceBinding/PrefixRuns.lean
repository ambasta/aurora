import SourceBinding.GuardSemantics
namespace Aurora.SourceBinding

/-- A finite execution stopped at its FIRST visit to the continuation PC, return,
    or trap. The continuation instruction is not executed. No fuel or matcher is
    part of this relation; the non-hit premise covers every preceding step. -/
inductive FirstExit (program : Program) (cut : Nat) : Machine → Execution → Prop
  | hit : state.pc = cut → FirstExit program cut state (.next state)
  | next : initial.pc ≠ cut → step program initial = .next middle →
      FirstExit program cut middle result → FirstExit program cut initial result
  | returned : initial.pc ≠ cut → step program initial = .returned value →
      FirstExit program cut initial (.returned value)
  | trap : initial.pc ≠ cut → step program initial = .trap fault →
      FirstExit program cut initial (.trap fault)

def AtExit (cut : Nat) : Execution → Prop
  | .next state => state.pc = cut
  | .returned _ | .trap _ => True

theorem FirstExit.at_exit (run : FirstExit program cut initial result) : AtExit cut result := by
  induction run with
  | hit hitCut => exact hitCut
  | next _ _ _ ih => exact ih
  | returned _ _ => trivial
  | trap _ _ => trivial

theorem FirstExit.to_runs (run : FirstExit program cut initial result) : Runs program initial result := by
  induction run with
  | hit _ => exact .reflexive
  | next _ step _ ih => exact .next step ih
  | returned _ step => exact .returned step
  | trap _ step => exact .trap step

/-- Determinism includes the first-hit rule: no alternative prefix execution can
    run the tail instruction or choose another outcome after a proven exit. -/
theorem FirstExit.unique (left : FirstExit program cut initial a)
    (right : FirstExit program cut initial b) : a = b := by
  induction left generalizing b with
  | hit hitCut =>
    cases right with
    | hit _ => rfl
    | next away _ _ => exact False.elim (away hitCut)
    | returned away _ => exact False.elim (away hitCut)
    | trap away _ => exact False.elim (away hitCut)
  | next away step tail ih =>
    cases right with
    | hit hitCut => exact False.elim (away hitCut)
    | next _ step' tail' =>
      have eq := step.symm.trans step'
      cases eq
      exact ih tail'
    | returned _ step' => cases step.symm.trans step'
    | trap _ step' => cases step.symm.trans step'
  | returned away step =>
    cases right with
    | hit hitCut => exact False.elim (away hitCut)
    | next _ step' _ => cases step.symm.trans step'
    | returned _ step' => exact step.symm.trans step'
    | trap _ step' => cases step.symm.trans step'
  | trap away step =>
    cases right with
    | hit hitCut => exact False.elim (away hitCut)
    | next _ step' _ => cases step.symm.trans step'
    | returned _ step' => cases step.symm.trans step'
    | trap _ step' => exact step.symm.trans step'

/-- A finite run ending at an exit guarantees SOME first exit, possibly an earlier
    visit to the cutpoint. It does NOT identify that earlier machine with the last
    machine: use FirstExit directly to establish precise continuation-frame facts. -/
theorem Runs.first_exit_exists (run : Runs program initial result) (ready : AtExit cut result) :
    ∃ first, FirstExit program cut initial first := by
  induction run with
  | @reflexive state => exact ⟨.next state, .hit ready⟩
  | @next initial middle result step tail ih =>
    by_cases hitCut : initial.pc = cut
    · exact ⟨.next initial, .hit hitCut⟩
    · obtain ⟨first, proof⟩ := ih ready
      exact ⟨first, .next hitCut step proof⟩
  | @returned initial value step =>
    by_cases hitCut : initial.pc = cut
    · exact ⟨.next initial, .hit hitCut⟩
    · exact ⟨.returned value, .returned hitCut step⟩
  | @trap initial fault step =>
    by_cases hitCut : initial.pc = cut
    · exact ⟨.next initial, .hit hitCut⟩
    · exact ⟨.trap fault, .trap hitCut step⟩

/-- Infinite execution that never reaches the cutpoint. Ordinary divergence after
    the continuation begins is deliberately not excluded by prefix theorems. -/
def DivergesBefore (program : Program) (cut : Nat) (initial : Machine) : Prop :=
  ∃ states : Nat → Machine, states 0 = initial ∧
    (∀ n, (states n).pc ≠ cut) ∧
    ∀ n, step program (states n) = .next (states (n + 1))

theorem FirstExit.not_diverges_before (run : FirstExit program cut initial result) :
    ¬ DivergesBefore program cut initial := by
  induction run with
  | hit hitCut =>
    rintro ⟨states, start, away, steps⟩
    exact away 0 (start ▸ hitCut)
  | @next initial middle result away step tail ih =>
    rintro ⟨states, start, avoids, steps⟩
    have nextEq : states 1 = middle := by
      have first := steps 0
      rw [start, step] at first
      exact (Execution.next.inj first).symm
    apply ih
    exact ⟨fun n => states (n + 1), nextEq, fun n => avoids (n + 1), fun n => steps (n + 1)⟩
  | returned away step =>
    rintro ⟨states, start, avoids, steps⟩
    have first := steps 0
    rw [start, step] at first
    cases first
  | trap away step =>
    rintro ⟨states, start, avoids, steps⟩
    have first := steps 0
    rw [start, step] at first
    cases first

/-- Executable bounded observer. `none` means insufficient fuel, not divergence.
    Unlike `step`, this stops BEFORE executing the continuation instruction. -/
def firstExitFuel (program : Program) (cut : Nat) : Nat → Machine → Option Execution
  | fuel, initial =>
    if initial.pc = cut then some (.next initial) else
    match fuel with
    | 0 => none
    | n + 1 => match step program initial with
      | .next middle => firstExitFuel program cut n middle
      | .returned value => some (.returned value)
      | .trap fault => some (.trap fault)

theorem first_exit_fuel_sound (accepted : firstExitFuel program cut fuel initial = some result) :
    FirstExit program cut initial result := by
  induction fuel generalizing initial with
  | zero =>
    simp only [firstExitFuel] at accepted
    split at accepted
    next hitCut => cases accepted; exact .hit hitCut
    next => cases accepted
  | succ fuel ih =>
    simp only [firstExitFuel] at accepted
    split at accepted
    next hitCut => cases accepted; exact .hit hitCut
    next away =>
      cases eq : step program initial with
      | next middle =>
        simp only [eq] at accepted
        exact .next away eq (ih accepted)
      | returned value =>
        simp only [eq, Option.some.injEq] at accepted
        exact accepted ▸ FirstExit.returned away eq
      | trap fault =>
        simp only [eq, Option.some.injEq] at accepted
        exact accepted ▸ FirstExit.trap away eq

theorem FirstExit.bounded (run : FirstExit program cut initial result) :
    ∃ fuel, firstExitFuel program cut fuel initial = some result := by
  induction run with
  | hit hitCut => exact ⟨0, by simp [firstExitFuel,hitCut]⟩
  | next away step tail ih =>
    obtain ⟨fuel, success⟩ := ih
    exact ⟨fuel + 1, by simp [firstExitFuel,away,step,success]⟩
  | returned away step => exact ⟨1, by simp [firstExitFuel,away,step]⟩
  | trap away step => exact ⟨1, by simp [firstExitFuel,away,step]⟩

-- Tiny kernel witnesses: the cutpoint's trap/loop instruction is never executed.
example (state : Machine) :
    firstExitFuel (fun _ => none) state.pc 0 state = some (.next state) := by
  simp [firstExitFuel]
example (state : Machine) :
    FirstExit (fun _ => some (.jump state.pc)) state.pc state (.next state) := .hit rfl

/-- Replace the continuation instruction with a state-preserving self-loop.
    Expression checking on this program cannot execute the actual tail. -/
def stallAt (program : Program) (cut : Nat) : Program := fun pc =>
  if pc = cut then some (.jump cut) else program pc

theorem step_stall_at (hitCut : state.pc = cut) :
    step (stallAt program cut) state = .next state := by
  cases state
  simp_all [step,stallAt]

theorem step_stall_away (away : state.pc ≠ cut) :
    step (stallAt program cut) state = step program state := by
  simp [step,stallAt,away]

/-- Once stalled, every finite run retains EXACTLY the same machine, not merely PC. -/
theorem Runs.stalled (run : Runs (stallAt program cut) initial result)
    (hitCut : initial.pc = cut) : result = .next initial := by
  induction run with
  | reflexive => rfl
  | @next initial middle result first tail ih =>
    rw [step_stall_at hitCut] at first
    cases first
    exact ih hitCut
  | returned first =>
    rw [step_stall_at hitCut] at first
    cases first
  | trap first =>
    rw [step_stall_at hitCut] at first
    cases first

/-- Precise first-hit bridge. A checked run on the stalled program ending at an
    exit preserves the SAME exit state under the original program's first-exit
    semantics. Earlier visits cannot change that state while stalling. This does
    not certify a checker run on the unstalled program. -/
theorem Runs.stalled_first_exit (run : Runs (stallAt program cut) initial result)
    (ready : AtExit cut result) : FirstExit program cut initial result := by
  induction run with
  | reflexive => exact .hit ready
  | @next initial middle result first tail ih =>
    by_cases hitCut : initial.pc = cut
    · have ending := (Runs.next first tail).stalled hitCut
      rw [ending]
      exact .hit hitCut
    · rw [step_stall_away hitCut] at first
      exact .next hitCut first (ih ready)
  | @returned initial value first =>
    by_cases hitCut : initial.pc = cut
    · rw [step_stall_at hitCut] at first
      cases first
    · rw [step_stall_away hitCut] at first
      exact .returned hitCut first
  | @trap initial fault first =>
    by_cases hitCut : initial.pc = cut
    · rw [step_stall_at hitCut] at first
      cases first
    · rw [step_stall_away hitCut] at first
      exact .trap hitCut first

end Aurora.SourceBinding
