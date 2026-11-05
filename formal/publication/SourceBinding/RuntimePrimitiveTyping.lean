import SourceBinding.ArgumentValues
import SourceBinding.RuntimeFacts
import SourceBinding.RuntimeEvaluationData
namespace Aurora.SourceBinding

def RuntimeOutcomeTyped (kind : RuntimeType) : Outcome Value → Prop
  | .trap _ => True
  | .value value => readRuntime kind (some value) = .value value

theorem runtime_read_outcome (kind : RuntimeType) (input : Option Value) :
    RuntimeOutcomeTyped kind (readRuntime kind input) := by
  cases result : readRuntime kind input with
  | trap fault => trivial
  | value value => exact readRuntime_typed kind input value result

theorem RuntimeLocals.readBound_typed (state : RuntimeLocals) (binding : SourceLocal) :
    RuntimeOutcomeTyped binding.kind (state.readBound binding) := by
  unfold RuntimeLocals.readBound
  split
  next declared =>
    simp only [RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration]
    split
    · exact runtime_read_outcome _ _
    · trivial
  next => trivial

theorem runtime_nominal_compare_typed (identity : NominalIdentity) (equal : Bool) (left right : Value) :
    RuntimeOutcomeTyped (.scalar .boolean) (compareNominal identity equal left right) := by
  unfold compareNominal
  cases readRuntime (.nominal identity) (some left) <;>
    cases readRuntime (.nominal identity) (some right) <;> simp only [Outcome.then]
  all_goals first | trivial | (rename_i a b; cases a <;> cases b <;> simp [RuntimeOutcomeTyped,readRuntime,readScalar])

theorem runtime_scalar_outcome (kind : GuardType) (outcome : Outcome Value) :
    RuntimeOutcomeTyped (.scalar kind) outcome = TypedOutcome kind outcome := by
  cases outcome <;> rfl

theorem runtime_then_typed (outcome : Outcome Value) (next : Value → Outcome Value)
    (typed : ∀ value, RuntimeOutcomeTyped kind (next value)) :
    RuntimeOutcomeTyped kind (outcome.then next) := by
  cases outcome with
  | trap fault => trivial
  | value value => exact typed value

theorem runtime_word_operator_typed (operator : RuntimeWordOperator op primitive result) (left right : Value) :
    RuntimeOutcomeTyped (.scalar result) (binaryValue primitive left right) := by
  rw [runtime_scalar_outcome]
  cases operator <;> exact binary_typed _ _ _

def RuntimeBodyOutcomeTyped (kind : RuntimeType) : RuntimeBodyOutcome → Prop
  | .returned value _ => readRuntime kind (some value) = .value value
  | .continued _ | .trapped _ _ => True


end Aurora.SourceBinding
