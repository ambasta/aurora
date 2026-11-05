import SourceBinding.RuntimeEvaluationInversion
import SourceBinding.RuntimeSingleton
namespace Aurora.SourceBinding

/-- A proof-only contract about every derivation of an existing raw expression.
    It computes nothing and does not constrain traces or assume successful reads. -/
def RuntimeExpressionResult (functions : List RuntimeSourceFunction)
    (context : RuntimeExprContext) (state : RuntimeLocals) (raw : SourceExpr)
    (kind : RuntimeType) (outcome : Outcome Value) : Prop :=
  ∀ actualKind actual events, RuntimeEvaluation functions context state raw actualKind actual events →
    actualKind = kind ∧ actual = outcome

private theorem shift_count_unique (first : SourceShiftCount raw a) (second : SourceShiftCount raw b) : a = b := by
  cases first <;> cases second <;> rfl

namespace RuntimeExpressionResult

/-- A universal pure result contract applies to any actual effect observation of
    that pure context, recovering its old derivation through constructor closure. -/
theorem effect (result : RuntimeExpressionResult functions context state raw kind outcome)
    (evaluated : EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
      ⟨state,shared⟩ raw actualKind actual after events) :
    actualKind = kind ∧ actual = sourceLift outcome := by
  rcases evaluated.pure_induction (pureRuntimeAlgebra functions) context rfl with
    ⟨oldOutcome,oldEvents,old,same,_,_⟩
  have known := result _ _ _ old
  exact ⟨known.1,same.trans (congrArg sourceLift known.2)⟩

private theorem of_effect
    (contract : ∀ actualKind actual after events,
      EffectEvaluation (functions.map RuntimeSourceFunction.toEffect)
        (fun (_ : SourceResourceRequest PUnit) (_ : SourceExternalOutcome PUnit) _ => False)
        (.pure context) ⟨state,⟨fun _ => none,PUnit.unit⟩⟩ raw actualKind actual after events →
      actualKind = kind ∧ actual = sourceLift outcome) :
    RuntimeExpressionResult functions context state raw kind outcome := by
  intro actualKind actual events evaluated
  have known := contract _ _ _ _ (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩)
  exact ⟨known.1,sourceLift_injective known.2⟩

private theorem boolean_malformed
    (evaluated : EffectEvaluation functions response context state raw (.scalar .boolean) (.value value) after events)
    (malformed : readScalar .boolean value = .trap fault) : False := by
  have typed := evaluated.outcome_typed
  cases value with
  | none => exact typed
  | some value =>
    change readScalar .boolean (some value) = .value value at typed
    rw [typed] at malformed
    cases malformed

theorem word : RuntimeExpressionResult functions context state (.word value) (.scalar .word)
    (readScalar .word (some (.word value))) := by
  apply of_effect
  intro kind outcome after events evaluated
  cases evaluated
  exact ⟨rfl,rfl⟩

theorem boolean : RuntimeExpressionResult functions context state (.boolean value) (.scalar .boolean)
    (.value (.boolean value)) := by
  apply of_effect
  intro kind outcome after events evaluated
  cases evaluated
  exact ⟨rfl,rfl⟩

theorem readVariable (valid : RuntimeContextValid context)
    (known : RuntimeVariableBinding context name binding) :
    RuntimeExpressionResult functions context state (.name [name]) binding.kind (state.readBound binding) := by
  intro kind outcome events evaluated
  obtain ⟨kindEq,outcomeEq,_⟩ := evaluated.variable_result valid known
  exact ⟨kindEq,outcomeEq⟩

theorem enumValue (valid : RuntimeContextValid context)
    (known : RuntimeEnumValue context name identity ordinal) :
    RuntimeExpressionResult functions context state (.name name) (.nominal identity)
      (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) := by
  intro kind outcome events evaluated
  obtain ⟨kindEq,outcomeEq,_⟩ := evaluated.enum_result valid known
  exact ⟨kindEq,outcomeEq⟩

theorem not (inner : RuntimeExpressionResult functions context state raw (.scalar .boolean) outcome) :
    RuntimeExpressionResult functions context state (.not raw) (.scalar .boolean) (outcome.then notValue) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | not evaluated =>
    constructor
    · rfl
    · rw [(inner.effect evaluated).2, sourceThen_sourceLift]

theorem and_false
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean false))) :
    RuntimeExpressionResult functions context state (.binary .and lhs rhs) (.scalar .boolean) (.value (.boolean false)) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | andStopped evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | andStop evaluated => exact ⟨rfl,rfl⟩
  | andContinue evaluated _ => have impossible := (left.effect evaluated).2; cases impossible

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | andMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem and_true
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean true)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) outcome) :
    RuntimeExpressionResult functions context state (.binary .and lhs rhs) (.scalar .boolean) outcome := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | andStopped evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | andStop evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | andContinue _ evaluated => exact ⟨rfl,(right.effect evaluated).2⟩

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | andMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem or_true
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean true))) :
    RuntimeExpressionResult functions context state (.binary .or lhs rhs) (.scalar .boolean) (.value (.boolean true)) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | orStopped evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | orStop evaluated => exact ⟨rfl,rfl⟩
  | orContinue evaluated _ => have impossible := (left.effect evaluated).2; cases impossible

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | orMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem or_false
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean false)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) outcome) :
    RuntimeExpressionResult functions context state (.binary .or lhs rhs) (.scalar .boolean) outcome := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | orStopped evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | orStop evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | orContinue _ evaluated => exact ⟨rfl,(right.effect evaluated).2⟩


  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | orMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem wordBinary
    (known : RuntimeWordOperator operator primitive resultKind)
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.value value))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .word) outcome) :
    RuntimeExpressionResult functions context state (.binary operator lhs rhs) (.scalar resultKind)
      (outcome.then (binaryValue primitive value)) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop op evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | wordBinary op first second =>
    obtain ⟨samePrimitive,sameKind⟩ := op.unique known
    cases samePrimitive; cases sameKind
    have sameValue := (left.effect first).2
    cases sameValue
    constructor
    · rfl
    · rw [(right.effect second).2, sourceThen_sourceLift]
  | enumCompareStop evaluated => have impossible := (left.effect evaluated).1; cases impossible
  | enumCompare first second => have impossible := (left.effect first).1; cases impossible
  | shiftLeft _ _ => cases known
  | shiftRight _ _ => cases known
  | andStopped _ => cases known
  | andStop _ => cases known
  | andContinue _ _ => cases known
  | orStopped _ => cases known
  | orStop _ => cases known
  | orContinue _ _ => cases known

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | enumCompareMissing expression => exact False.elim expression.outcome_typed
  | andMalformed expression fault => exact False.elim (boolean_malformed expression fault)
  | orMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem wordBinaryFault
    (known : RuntimeWordOperator operator primitive resultKind)
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.trap fault)) :
    RuntimeExpressionResult functions context state (.binary operator lhs rhs) (.scalar resultKind) (.trap fault) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop op evaluated =>
    obtain ⟨samePrimitive,sameKind⟩ := op.unique known
    cases sameKind
    exact ⟨rfl,(left.effect evaluated).2⟩
  | wordBinary op first second => have impossible := (left.effect first).2; cases impossible
  | enumCompareStop evaluated => have impossible := (left.effect evaluated).1; cases impossible
  | enumCompare first second => have impossible := (left.effect first).1; cases impossible
  | shiftLeft _ _ => cases known
  | shiftRight _ _ => cases known
  | andStopped _ => cases known
  | andStop _ => cases known
  | andContinue _ _ => cases known
  | orStopped _ => cases known
  | orStop _ => cases known
  | orContinue _ _ => cases known

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | enumCompareMissing expression => exact False.elim expression.outcome_typed
  | andMalformed expression fault => exact False.elim (boolean_malformed expression fault)
  | orMalformed expression fault => exact False.elim (boolean_malformed expression fault)
private theorem compare_flag_injective {a b : Bool}
    (same : SourceBinOp.compare (if a then .eq else .ne) = .compare (if b then .eq else .ne)) : a = b := by
  cases a <;> cases b <;> cases same <;> rfl

theorem enumCompare
    (left : RuntimeExpressionResult functions context state lhs (.nominal identity) (.value value))
    (right : RuntimeExpressionResult functions context state rhs (.nominal identity) outcome) :
    RuntimeExpressionResult functions context state
      (.binary (.compare (if equal then .eq else .ne)) lhs rhs) (.scalar .boolean)
      (outcome.then (compareNominal identity equal value)) := by
  apply of_effect
  intro kind actual after events evaluated
  generalize operatorEq : SourceBinOp.compare (if equal then .eq else .ne) = operator at evaluated
  cases evaluated with
  | wordBinaryStop op evaluated => have impossible := (left.effect evaluated).1; cases impossible
  | wordBinary op first second => have impossible := (left.effect first).1; cases impossible
  | enumCompareStop evaluated => have impossible := (left.effect evaluated).2; cases impossible
  | enumCompare first second =>
    have sameFlag := compare_flag_injective operatorEq
    cases sameFlag
    have sameIdentity := (left.effect first).1
    cases sameIdentity
    have sameValue := (left.effect first).2
    cases sameValue
    constructor
    · rfl
    · rw [(right.effect second).2, sourceThen_sourceLift]
  | shiftLeft _ _ => cases equal <;> cases operatorEq
  | shiftRight _ _ => cases equal <;> cases operatorEq
  | andStopped _ => cases equal <;> cases operatorEq
  | andStop _ => cases equal <;> cases operatorEq
  | andContinue _ _ => cases equal <;> cases operatorEq
  | orStopped _ => cases equal <;> cases operatorEq
  | orStop _ => cases equal <;> cases operatorEq
  | orContinue _ _ => cases equal <;> cases operatorEq

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
  | enumCompareMissing expression => exact False.elim expression.outcome_typed
  | andMalformed expression fault => exact False.elim (boolean_malformed expression fault)
  | orMalformed expression fault => exact False.elim (boolean_malformed expression fault)
theorem shiftLeft
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) outcome)
    (known : SourceShiftCount rhs count) :
    RuntimeExpressionResult functions context state (.binary .shift lhs rhs) (.scalar .word)
      (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop op _ => cases op
  | wordBinary op _ _ => cases op
  | shiftLeft evaluated actualCount =>
    have same := shift_count_unique known actualCount
    subst count
    constructor
    · rfl
    · rw [(left.effect evaluated).2, sourceThen_sourceLift]

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
theorem shiftRight
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) outcome)
    (known : SourceShiftCount rhs count) :
    RuntimeExpressionResult functions context state (.binary .rightShift lhs rhs) (.scalar .word)
      (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) := by
  apply of_effect
  intro kind actual after events evaluated
  cases evaluated with
  | wordBinaryStop op _ => cases op
  | wordBinary op _ _ => cases op
  | shiftRight evaluated actualCount =>
    have same := shift_count_unique known actualCount
    subst count
    constructor
    · rfl
    · rw [(left.effect evaluated).2, sourceThen_sourceLift]

  | wordBinaryMissing _ expression => exact False.elim expression.outcome_typed
/-- A singleton source return keeps its exact current local state, whether the
    expression returns or traps. No checked-IR endpoint is substituted. -/
theorem singleton
    (expression : RuntimeExpressionResult functions
      (runtimeStatementContext members module path formals before) state raw kind result)
    (evaluated : RuntimeStatementsEvaluation functions members module path formals kind
      before state [.returnValue raw] after outcome events) :
    outcome = match result with
      | .value value => .returned value state
      | .trap fault => .trapped fault state := by
  rcases runtime_singleton_cases evaluated with ⟨actual,derivation,_,same⟩
  have resultEq := (expression _ _ _ derivation).2
  cases resultEq
  cases result <;> exact same

end RuntimeExpressionResult
end Aurora.SourceBinding
