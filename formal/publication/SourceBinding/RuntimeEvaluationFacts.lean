import SourceBinding.RuntimeSingleton
import SourceBinding.RuntimePrimitiveTyping
import SourceBinding.ArgumentValues
import SourceBinding.RuntimeFacts
namespace Aurora.SourceBinding

theorem RuntimeEvaluation.outcome_typed
    (evaluated : RuntimeEvaluation functions context state raw kind outcome events) :
    RuntimeOutcomeTyped kind outcome := by
  have typed := (evaluated PUnit PUnit (fun _ _ _ => False)
    (⟨fun _ => none, PUnit.unit⟩ : SourceShared PUnit)).outcome_typed
  cases outcome <;> exact typed

theorem RuntimeEvaluatesWith.outcome_typed
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events) :
    RuntimeOutcomeTyped kind outcome := RuntimeEvaluation.outcome_typed evaluated

theorem RuntimeEvaluates.outcome_typed (evaluated : RuntimeEvaluates context state raw kind outcome) :
    RuntimeOutcomeTyped kind outcome := RuntimeEvaluatesWith.outcome_typed evaluated

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
