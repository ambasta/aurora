import SourceBinding.RuntimeExecution
namespace Aurora.SourceBinding

/-- Constructive source/IR correspondence for the admitted call-free expressions.
    The source outcome is fixed independently of caller accumulator/operand stack.
    It can be a fault: no success, no-overflow or initialized-value premise occurs.
    Declaration provenance and scope activity remain an explicit local context
    relation, to be discharged by the enclosing function/statement certificate. -/
theorem RuntimeExpressionCode.evaluates_and_runs
    (code : RuntimeExpressionCode program context raw kind start stop)
    (source : RuntimeLocals) (base : Machine)
    (bindings : RuntimeBindingsPresent context source)
    (locals : ∀ slot, base.locals slot = source.values slot) :
    ∃ outcome, RuntimeEvaluates context source raw kind outcome ∧
      ∀ accumulator stack, RuntimeRun program base start stop accumulator stack outcome := by
  induction code with
  | word bound operation =>
    refine ⟨_,.word,?_⟩
    intro accumulator stack
    apply runtime_single
    simp only [effectStep,frameState,operation,pureView,step]
    cases readScalar .word (some (.word _)) <;> rfl
  | boolean operation =>
    refine ⟨_,.boolean,?_⟩
    intro accumulator stack
    apply runtime_single
    simp only [effectStep,frameState,operation,pureView,step,readScalar,if_true]
    rfl
  | readVariable binding operation =>
    refine ⟨_,.readVariable binding,?_⟩
    intro accumulator stack
    exact RuntimeExpressionCode.variable_run operation (bindings _ _ binding).1
      (bindings _ _ binding).2 locals
  | enumValue binding operation =>
    refine ⟨_,.enumValue binding,?_⟩
    intro accumulator stack
    apply runtime_single
    simp only [effectStep,frameState,operation]
    cases readRuntime (.nominal _) (some (.nominal _ _)) <;> rfl
  | not child operation ih =>
    obtain ⟨out,evaluated,run⟩ := ih
    exact ⟨_,.not evaluated,fun accumulator stack => (run accumulator stack).negate operation⟩
  | @wordBinary op primitive result rawLeft initial middle rawRight last operator left push right operation ihLeft ihRight =>
    obtain ⟨leftOut,leftEval,leftRun⟩ := ihLeft
    obtain ⟨rightOut,rightEval,rightRun⟩ := ihRight
    refine ⟨leftOut.then (fun a => rightOut.then (binaryValue primitive a)),?_,?_⟩
    · cases leftOut with
      | trap fault => exact .wordBinaryFault operator leftEval
      | value value => exact .wordBinary operator leftEval rightEval
    · intro accumulator stack
      exact runtime_binary_run (leftRun accumulator stack) push
        (fun value => rightRun (some value) (value::stack)) operation
  | @enumCompare rawLeft identity initial middle rawRight last equal left push right operation ihLeft ihRight =>
    obtain ⟨leftOut,leftEval,leftRun⟩ := ihLeft
    obtain ⟨rightOut,rightEval,rightRun⟩ := ihRight
    refine ⟨leftOut.then (fun a => rightOut.then (compareNominal identity equal a)),?_,?_⟩
    · cases leftOut with
      | trap fault => exact .enumCompareFault leftEval
      | value value => exact .enumCompare leftEval rightEval
    · intro accumulator stack
      exact runtime_enum_compare_run (leftRun accumulator stack) push
        (fun value => rightRun (some value) (value::stack)) operation
  | shiftLeft left count push countCode operation ih =>
    obtain ⟨out,evaluated,run⟩ := ih
    exact ⟨_,.shiftLeft evaluated count,fun accumulator stack =>
      runtime_shift_run (run accumulator stack) push countCode operation⟩
  | shiftRight left count push countCode operation ih =>
    obtain ⟨out,evaluated,run⟩ := ih
    exact ⟨_,.shiftRight evaluated count,fun accumulator stack =>
      runtime_shift_run (run accumulator stack) push countCode operation⟩
  | and left branch right label ihLeft ihRight =>
    obtain ⟨out,evaluated,run⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.andFault evaluated,fun accumulator stack => run accumulator stack⟩
    | value value =>
      have valid := evaluated.outcome_typed
      cases value with
      | boolean value => cases value with
        | false => exact ⟨_,.andStop evaluated,fun accumulator stack =>
            runtime_and_stop (run accumulator stack) branch label⟩
        | true =>
          obtain ⟨rightOut,rightEval,rightRun⟩ := ihRight
          exact ⟨_,.andContinue evaluated rightEval,fun accumulator stack =>
            runtime_and_continue (run accumulator stack) branch (rightRun _ stack) label⟩
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ =>
        simp only [RuntimeOutcomeTyped,readRuntime,readScalar,reduceCtorEq,if_false] at valid
  | or left branch jump begin right label ihLeft ihRight =>
    obtain ⟨out,evaluated,run⟩ := ihLeft
    cases out with
    | trap fault => exact ⟨_,.orFault evaluated,fun accumulator stack => run accumulator stack⟩
    | value value =>
      have valid := evaluated.outcome_typed
      cases value with
      | boolean value => cases value with
        | true => exact ⟨_,.orStop evaluated,fun accumulator stack =>
            runtime_or_stop (run accumulator stack) branch jump label⟩
        | false =>
          obtain ⟨rightOut,rightEval,rightRun⟩ := ihRight
          exact ⟨_,.orContinue evaluated rightEval,fun accumulator stack =>
            runtime_or_continue (run accumulator stack) branch begin (rightRun _ stack) label⟩
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ =>
        simp only [RuntimeOutcomeTyped,readRuntime,readScalar,reduceCtorEq,if_false] at valid

end Aurora.SourceBinding
