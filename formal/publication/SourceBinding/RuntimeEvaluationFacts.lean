import SourceBinding.RuntimeEvaluation
import SourceBinding.ArgumentValues
import SourceBinding.RuntimeFacts
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

theorem RuntimeEvaluates.outcome_typed (evaluated : RuntimeEvaluates context state raw kind outcome) :
    RuntimeOutcomeTyped kind outcome := by
  induction evaluated with
  | word => rw [runtime_scalar_outcome]; exact read_typed _ _
  | boolean => rfl
  | readVariable binding => exact RuntimeLocals.readBound_typed _ _
  | enumValue binding => exact runtime_read_outcome _ _
  | not child ih =>
    apply runtime_then_typed
    intro value
    rw [runtime_scalar_outcome]
    exact not_typed value
  | wordBinaryFault => trivial
  | wordBinary operator left right ihLeft ihRight =>
    apply runtime_then_typed
    intro value
    exact runtime_word_operator_typed operator _ _
  | enumCompareFault => trivial
  | enumCompare left right ihLeft ihRight =>
    apply runtime_then_typed
    intro value
    exact runtime_nominal_compare_typed _ _ _ _
  | shiftLeft left count ih | shiftRight left count ih =>
    apply runtime_then_typed
    intro value
    rw [runtime_scalar_outcome]
    exact binary_typed _ _ _
  | andFault | orFault => trivial
  | andStop | orStop => rfl
  | andContinue _ _ _ right | orContinue _ _ _ right => exact right

/-- Every admitted call-free expression has an operational result, possibly a
    fault. This is not a successful-evaluation assumption or a no-overflow claim. -/
theorem RuntimeExprTyped.evaluates (typed : RuntimeExprTyped context raw kind) (state : RuntimeLocals) :
    ∃ outcome, RuntimeEvaluates context state raw kind outcome := by
  induction typed with
  | word bound => exact ⟨_,.word⟩
  | boolean => exact ⟨_,.boolean⟩
  | readVariable binding => exact ⟨_,.readVariable binding⟩
  | enumValue binding => exact ⟨_,.enumValue binding⟩
  | not child ih =>
    obtain ⟨out,evaluated⟩ := ih
    exact ⟨_,.not evaluated⟩
  | wordBinary operator left right ihLeft ihRight =>
    obtain ⟨out,evaluated⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.wordBinaryFault operator evaluated⟩
    | value value =>
      obtain ⟨outRight,evaluatedRight⟩ := ihRight
      exact ⟨_,.wordBinary operator evaluated evaluatedRight⟩
  | enumCompare left right ihLeft ihRight =>
    obtain ⟨out,evaluated⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.enumCompareFault evaluated⟩
    | value value =>
      obtain ⟨outRight,evaluatedRight⟩ := ihRight
      exact ⟨_,.enumCompare evaluated evaluatedRight⟩
  | shiftLeft left count ih =>
    obtain ⟨out,evaluated⟩ := ih
    exact ⟨_,.shiftLeft evaluated count⟩
  | shiftRight left count ih =>
    obtain ⟨out,evaluated⟩ := ih
    exact ⟨_,.shiftRight evaluated count⟩
  | and left right ihLeft ihRight =>
    obtain ⟨out,evaluated⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.andFault evaluated⟩
    | value value =>
      have valid := evaluated.outcome_typed
      cases value with
      | boolean value => cases value with
        | false => exact ⟨_,.andStop evaluated⟩
        | true =>
          obtain ⟨outRight,evaluatedRight⟩ := ihRight
          exact ⟨_,.andContinue evaluated evaluatedRight⟩
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ =>
        simp only [RuntimeOutcomeTyped,readRuntime,readScalar,reduceCtorEq,if_false] at valid
  | or left right ihLeft ihRight =>
    obtain ⟨out,evaluated⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.orFault evaluated⟩
    | value value =>
      have valid := evaluated.outcome_typed
      cases value with
      | boolean value => cases value with
        | true => exact ⟨_,.orStop evaluated⟩
        | false =>
          obtain ⟨outRight,evaluatedRight⟩ := ihRight
          exact ⟨_,.orContinue evaluated evaluatedRight⟩
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ =>
        simp only [RuntimeOutcomeTyped,readRuntime,readScalar,reduceCtorEq,if_false] at valid

end Aurora.SourceBinding
