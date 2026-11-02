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

/-- Replaying exactly the completed stores describes the receiver mutation;
    this is derived from steps, not an assumed callee frame contract. -/
def applyStores (receiver : Nat → Option Value) : List StoreEvent → Nat → Option Value
  | [] => receiver
  | event :: rest => applyStores (fun index => if index = event.ordinal then some event.value else receiver index) rest

theorem applyStores_append (receiver : Nat → Option Value) (first rest : List StoreEvent) :
    applyStores receiver (first ++ rest) = applyStores (applyStores receiver first) rest := by
  induction first generalizing receiver with
  | nil => rfl
  | cons event tail ih => exact ih _

theorem effect_step_frame (program : EffectProgram) (state : Machine) :
    applyStores state.receiver (effectStep program state).stores = (effectStep program state).execution.state.receiver ∧
    (effectStep program state).execution.state.arguments = state.arguments := by
  cases code : program state.pc with
  | none =>
    simp only [effectStep,code,applyStores]
    exact ⟨(pure_step_frame (pureView program) state).1.symm,(pure_step_frame (pureView program) state).2⟩
  | some operation =>
    cases operation with
    | pure op =>
      simp only [effectStep,code,applyStores]
      exact ⟨(pure_step_frame (pureView program) state).1.symm,(pure_step_frame (pureView program) state).2⟩
    | store kind ordinal =>
      simp only [effectStep,code]
      cases readScalar kind state.accumulator <;> exact ⟨rfl,rfl⟩
    | require =>
      simp only [effectStep,code]
      cases state.accumulator with
      | none => exact ⟨rfl,rfl⟩
      | some value =>
        cases value with
        | word _ | signedCount12 => exact ⟨rfl,rfl⟩
        | boolean b => cases b <;> exact ⟨rfl,rfl⟩

theorem EffectRuns.store_frame {program : EffectProgram} {initial : Machine}
    {events : List StoreEvent} {result : EffectExecution} (run : EffectRuns program initial events result) :
    result.state.receiver = applyStores initial.receiver events ∧ result.state.arguments = initial.arguments := by
  induction run with
  | reflexive => exact ⟨rfl,rfl⟩
  | @next initial middle events later result step rest ih =>
    have frame := effect_step_frame program initial
    rw [step] at frame
    exact ⟨by rw [applyStores_append,frame.1]; exact ih.1,ih.2.trans frame.2⟩
  | @returned initial value state events step =>
    have frame := effect_step_frame program initial
    rw [step] at frame
    exact ⟨frame.1.symm,frame.2⟩
  | @trap initial fault state events step =>
    have frame := effect_step_frame program initial
    rw [step] at frame
    exact ⟨frame.1.symm,frame.2⟩

end Aurora.SourceBinding
