import SourceBinding.BodySyntax
import SourceBinding.EffectExpressions
namespace Aurora.SourceBinding

inductive SourceExecution where
  | next (state : SourceState)
  | returned (value : Value) (state : SourceState)
  | trap (fault : EffectFault) (state : SourceState)

def SourceExecution.state : SourceExecution → SourceState
  | .next state | .returned _ state | .trap _ state => state

structure BodyEvaluation where
  execution : SourceExecution
  stores : List StoreEvent := []

/-- Pure evaluation is always against the current source store. -/
def sourceExpression (state : SourceState) (outcome : Outcome Value)
    (next : Value → BodyEvaluation) : BodyEvaluation :=
  match outcome with
  | .value value => next value
  | .trap fault => ⟨.trap (.scalar fault) state,[]⟩

/-- Finite structural evaluation includes assertion and scalar failures. Neither
    sequence nor require rewinds earlier state changes or completed-store events. -/
def evalBody : EffectBody → SourceState → BodyEvaluation
  | .skip, state => ⟨.next state,[]⟩
  | .seq first rest, state =>
    let initial := evalBody first state
    match initial.execution with
    | .next next =>
      let later := evalBody rest next
      ⟨later.execution,initial.stores ++ later.stores⟩
    | _ => initial
  | .assign kind ordinal value, state =>
    sourceExpression state (evalGuard state value) fun scalar =>
      sourceExpression state (readScalar kind (some scalar)) fun checked =>
        ⟨.next {state with fields := fun index => if index = ordinal then some checked else state.fields index},
          [⟨ordinal,checked⟩]⟩
  | .require condition, state =>
    sourceExpression state (evalGuard state condition) fun value =>
      match value with
      | .boolean true => ⟨.next state,[]⟩
      | .boolean false => ⟨.trap .assertion state,[]⟩
      | _ => ⟨.trap (.scalar .type) state,[]⟩
  | .returnValue _ value, state =>
    sourceExpression state (evalGuard state value) fun scalar => ⟨.returned scalar state,[]⟩
  | .branch condition body, state =>
    sourceExpression state (evalGuard state condition) fun value =>
      match value with
      | .boolean true => evalBody body state
      | .boolean false => ⟨.next state,[]⟩
      | _ => ⟨.trap (.scalar .type) state,[]⟩

/-- Continuations re-establish the expression context after each store. Faults
    compare actual final stores, not temporary IR expression-stack contents. -/
def BodyResultRelated (slots : Nat → Nat) (stack : List Value) (stop : Nat) :
    SourceExecution → EffectExecution → Prop
  | .next source, .next machine => machine.pc = stop ∧ machine.stack = stack ∧ ContextRelated source machine slots
  | .returned a source, .returned b machine => a = b ∧ machine.receiver = source.fields ∧ machine.stack = stack
  | .trap a source, .trap b machine => a = b ∧ machine.receiver = source.fields
  | _, _ => False

/-- Definite return means no normal fallthrough; a preceding assertion may fail. -/
theorem DefinitelyReturns.no_fallthrough {body : EffectBody} (returns : DefinitelyReturns body)
    (state : SourceState) : ∀ final, (evalBody body state).execution ≠ .next final := by
  induction returns generalizing state with
  | returnValue =>
    intro final
    simp only [evalBody,sourceExpression]
    cases evalGuard state _ <;> simp
  | first first ih =>
    intro final
    simp only [evalBody]
    cases eq : (evalBody _ state).execution with
    | next middle => exact False.elim (ih state middle eq)
    | returned value middle => simp [eq]
    | trap fault middle => simp [eq]
  | rest rest ih =>
    intro final
    simp only [evalBody]
    cases eq : (evalBody _ state).execution with
    | next middle => exact ih middle final
    | returned value middle => simp [eq]
    | trap fault middle => simp [eq]

end Aurora.SourceBinding
