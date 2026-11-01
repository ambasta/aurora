import SourceBinding.Stateful
namespace Aurora.SourceBinding

def EffectTerminal : EffectExecution → Prop
  | .next _ => False
  | .returned _ _ | .trap _ _ => True

/-- Deterministic terminal executions agree on both final state and store order. -/
theorem EffectRuns.terminal_unique {program : EffectProgram} {initial : Machine}
    {events otherEvents : List StoreEvent} {result otherResult : EffectExecution}
    (run : EffectRuns program initial events result) (terminal : EffectTerminal result)
    (other : EffectRuns program initial otherEvents otherResult) (otherTerminal : EffectTerminal otherResult) :
    events = otherEvents ∧ result = otherResult := by
  induction run generalizing otherEvents otherResult with
  | reflexive => exact False.elim terminal
  | next step rest ih =>
    cases other with
    | reflexive => exact False.elim otherTerminal
    | next otherStep later =>
      have same := step.symm.trans otherStep
      cases same
      obtain ⟨trace,result⟩ := ih terminal later otherTerminal
      cases trace; cases result
      exact ⟨rfl,rfl⟩
    | returned otherStep => have impossible := step.symm.trans otherStep; cases impossible
    | trap otherStep => have impossible := step.symm.trans otherStep; cases impossible
  | returned step =>
    cases other with
    | reflexive => exact False.elim otherTerminal
    | next otherStep later => have impossible := step.symm.trans otherStep; cases impossible
    | returned otherStep => have same := step.symm.trans otherStep; cases same; exact ⟨rfl,rfl⟩
    | trap otherStep => have impossible := step.symm.trans otherStep; cases impossible
  | trap step =>
    cases other with
    | reflexive => exact False.elim otherTerminal
    | next otherStep later => have impossible := step.symm.trans otherStep; cases impossible
    | returned otherStep => have impossible := step.symm.trans otherStep; cases impossible
    | trap otherStep => have same := step.symm.trans otherStep; cases same; exact ⟨rfl,rfl⟩

def EffectDiverges (program : EffectProgram) (initial : Machine) : Prop :=
  ∃ states : Nat → Machine, states 0 = initial ∧
    ∀ n, ∃ events, effectStep program (states n) = ⟨.next (states (n + 1)),events⟩

/-- Finite terminal evidence excludes an alternative infinite local execution. -/
theorem EffectRuns.not_diverges {program : EffectProgram} {initial : Machine}
    {events : List StoreEvent} {result : EffectExecution}
    (run : EffectRuns program initial events result) (terminal : EffectTerminal result) :
    ¬ EffectDiverges program initial := by
  intro ⟨states,first,infinite⟩
  induction run generalizing states with
  | reflexive => exact False.elim terminal
  | @next initial middle events later result step rest ih =>
    obtain ⟨emitted,next⟩ := infinite 0
    rw [first,step] at next
    cases next
    apply ih terminal (fun n => states (n + 1)) rfl
    intro n
    exact infinite (n + 1)
  | returned step =>
    obtain ⟨emitted,next⟩ := infinite 0
    rw [first,step] at next
    cases next
  | trap step =>
    obtain ⟨emitted,next⟩ := infinite 0
    rw [first,step] at next
    cases next

end Aurora.SourceBinding
