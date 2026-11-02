import SourceBinding.RuntimeEvaluation
import SourceBinding.ArgumentValues
namespace Aurora.SourceBinding

/-- Formal metadata is installed independently of the argument values. Missing,
    malformed and out-of-range arguments remain visible to both read semantics. -/
def ScalarFormalFrame (context : RuntimeExprContext) (state : RuntimeLocals) (source : SourceState) : Prop :=
  context.visible = [] ∧ 0 ∈ state.scopes ∧
  ∀ index declaration kind, context.formals[index]? = some declaration →
    declaration.type = guardSourceType kind →
    state.declarations (8 * (index + 1)) = some ⟨.scalar kind,false,0⟩ ∧
    state.values (8 * (index + 1)) = source.parameters index

theorem scalar_source_type (kind : GuardType) :
    RuntimeSourceType members module path (guardSourceType kind) (.scalar kind) := by
  cases kind with
  | word => exact .word
  | boolean => exact .boolean

theorem scalar_formal_evaluates {declaration : Formal} (frame : ScalarFormalFrame context state source)
    (present : context.formals[index]? = some declaration) (named : declaration.name = name)
    (scalar : declaration.type = guardSourceType kind) :
    RuntimeEvaluates context state (.name [name]) (.scalar kind)
      (readScalar kind (source.parameters index)) := by
  have binding : RuntimeVariableBinding context name ⟨name,.scalar kind,false,0,8*(index+1)⟩ :=
    .formal present named (scalar ▸ scalar_source_type kind) (by rw [frame.1]; simp)
  have evaluated := RuntimeEvaluates.readVariable (state := state) binding
  have facts := frame.2.2 index declaration kind present scalar
  rw [RuntimeLocals.readBound_eq _ _ facts.1 frame.2.1, facts.2] at evaluated
  exact evaluated

theorem RuntimeEvaluates.word_binary (operator : RuntimeWordOperator op primitive kind)
    (leftEval : RuntimeEvaluates context state left (.scalar .word) leftOutcome)
    (rightEval : RuntimeEvaluates context state right (.scalar .word) rightOutcome) :
    RuntimeEvaluates context state (.binary op left right) (.scalar kind)
      (leftOutcome.then fun a => rightOutcome.then (binaryValue primitive a)) := by
  cases leftOutcome with
  | trap fault => exact .wordBinaryFault operator leftEval
  | value value => exact .wordBinary operator leftEval rightEval

/-- Conservative embedding of the entire old field-free scalar expression
    fragment, INCLUDING faults. No successful-evaluation or bounded-argument
    premise is imposed, and no receiver-field semantics is reimplemented. -/
theorem TypedGuard.runtime_compatible {fields : List Formal} {kind : GuardType} {expression : GuardExpr kind}
    (typed : TypedGuard fields context.formals raw expression)
    (emptyFields : fields = []) (frame : ScalarFormalFrame context state source) :
    RuntimeEvaluates context state raw (.scalar kind) (evalGuard source (kind := kind) expression) := by
  induction typed with
  | word bound => exact .word
  | boolean => exact .boolean
  | parameter present named scalar => exact scalar_formal_evaluates frame present named scalar
  | field present named scalar => simp only [emptyFields,List.getElem?_nil] at present; contradiction
  | not child ih => exact .not (ih)
  | subtract left right ihLeft ihRight => exact RuntimeEvaluates.word_binary .subtract (ihLeft) (ihRight)
  | bitAnd left right ihLeft ihRight => exact RuntimeEvaluates.word_binary .bitAnd (ihLeft) (ihRight)
  | bitOr left right ihLeft ihRight => exact RuntimeEvaluates.word_binary .bitOr (ihLeft) (ihRight)
  | compare left right ihLeft ihRight => exact RuntimeEvaluates.word_binary .compare (ihLeft) (ihRight)
  | shift12 child ih => exact .shiftLeft (ih) .twelve
  | @and rawLeft typedLeft rawRight typedRight left right ihLeft ihRight =>
    cases outcome : evalGuard source typedLeft with
    | trap fault =>
      simp only [evalGuard,outcome,Outcome.then]
      exact .andFault (outcome ▸ ihLeft)
    | value value =>
      have correct := eval_value_typed source typedLeft value outcome
      cases value with
      | boolean value =>
        simp only [evalGuard,outcome,Outcome.then]
        cases value with
        | false => exact .andStop (outcome ▸ ihLeft)
        | true => exact .andContinue (outcome ▸ ihLeft) (ihRight)
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => simp [readScalar] at correct
  | @or rawLeft typedLeft rawRight typedRight left right ihLeft ihRight =>
    cases outcome : evalGuard source typedLeft with
    | trap fault =>
      simp only [evalGuard,outcome,Outcome.then]
      exact .orFault (outcome ▸ ihLeft)
    | value value =>
      have correct := eval_value_typed source typedLeft value outcome
      cases value with
      | boolean value =>
        simp only [evalGuard,outcome,Outcome.then]
        cases value with
        | false => exact .orContinue (outcome ▸ ihLeft) (ihRight)
        | true => exact .orStop (outcome ▸ ihLeft)
      | word _ | signedCount4 | signedCount12 | signedCount32 | nominal _ _ => simp [readScalar] at correct

end Aurora.SourceBinding
