import SourceBinding.RuntimeEvaluationInversion
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

theorem word : RuntimeExpressionResult functions context state (.word value) (.scalar .word)
    (readScalar .word (some (.word value))) := by
  intro kind outcome events evaluated
  cases evaluated
  exact ⟨rfl,rfl⟩

theorem boolean : RuntimeExpressionResult functions context state (.boolean value) (.scalar .boolean)
    (.value (.boolean value)) := by
  intro kind outcome events evaluated
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
  intro kind actual events evaluated
  cases evaluated with
  | not evaluated => exact ⟨rfl,congrArg (fun result => result.then notValue) (inner _ _ _ evaluated).2⟩

theorem and_false
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean false))) :
    RuntimeExpressionResult functions context state (.binary .and lhs rhs) (.scalar .boolean) (.value (.boolean false)) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | andFault evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | andStop evaluated => exact ⟨rfl,rfl⟩
  | andContinue evaluated _ => have impossible := (left _ _ _ evaluated).2; cases impossible

theorem and_true
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean true)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) outcome) :
    RuntimeExpressionResult functions context state (.binary .and lhs rhs) (.scalar .boolean) outcome := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | andFault evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | andStop evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | andContinue _ evaluated => exact ⟨rfl,(right _ _ _ evaluated).2⟩

theorem or_true
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean true))) :
    RuntimeExpressionResult functions context state (.binary .or lhs rhs) (.scalar .boolean) (.value (.boolean true)) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | orFault evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | orStop evaluated => exact ⟨rfl,rfl⟩
  | orContinue evaluated _ => have impossible := (left _ _ _ evaluated).2; cases impossible

theorem or_false
    (left : RuntimeExpressionResult functions context state lhs (.scalar .boolean) (.value (.boolean false)))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .boolean) outcome) :
    RuntimeExpressionResult functions context state (.binary .or lhs rhs) (.scalar .boolean) outcome := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault operator _ => cases operator
  | wordBinary operator _ _ => cases operator
  | orFault evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | orStop evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | orContinue _ evaluated => exact ⟨rfl,(right _ _ _ evaluated).2⟩


theorem wordBinary
    (known : RuntimeWordOperator operator primitive resultKind)
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.value value))
    (right : RuntimeExpressionResult functions context state rhs (.scalar .word) outcome) :
    RuntimeExpressionResult functions context state (.binary operator lhs rhs) (.scalar resultKind)
      (outcome.then (binaryValue primitive value)) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault op evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | wordBinary op first second =>
    obtain ⟨samePrimitive,sameKind⟩ := op.unique known
    cases samePrimitive; cases sameKind
    have sameValue := (left _ _ _ first).2
    cases sameValue
    exact ⟨rfl,congrArg (fun result => result.then (binaryValue primitive value)) (right _ _ _ second).2⟩
  | enumCompareFault evaluated => have impossible := (left _ _ _ evaluated).1; cases impossible
  | enumCompare first second => have impossible := (left _ _ _ first).1; cases impossible
  | shiftLeft _ _ => cases known
  | shiftRight _ _ => cases known
  | andFault _ => cases known
  | andStop _ => cases known
  | andContinue _ _ => cases known
  | orFault _ => cases known
  | orStop _ => cases known
  | orContinue _ _ => cases known

theorem wordBinaryFault
    (known : RuntimeWordOperator operator primitive resultKind)
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) (.trap fault)) :
    RuntimeExpressionResult functions context state (.binary operator lhs rhs) (.scalar resultKind) (.trap fault) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault op evaluated =>
    obtain ⟨samePrimitive,sameKind⟩ := op.unique known
    cases sameKind
    exact ⟨rfl,(left _ _ _ evaluated).2⟩
  | wordBinary op first second => have impossible := (left _ _ _ first).2; cases impossible
  | enumCompareFault evaluated => have impossible := (left _ _ _ evaluated).1; cases impossible
  | enumCompare first second => have impossible := (left _ _ _ first).1; cases impossible
  | shiftLeft _ _ => cases known
  | shiftRight _ _ => cases known
  | andFault _ => cases known
  | andStop _ => cases known
  | andContinue _ _ => cases known
  | orFault _ => cases known
  | orStop _ => cases known
  | orContinue _ _ => cases known

private theorem compare_flag_injective {a b : Bool}
    (same : SourceBinOp.compare (if a then .eq else .ne) = .compare (if b then .eq else .ne)) : a = b := by
  cases a <;> cases b <;> cases same <;> rfl

theorem enumCompare
    (left : RuntimeExpressionResult functions context state lhs (.nominal identity) (.value value))
    (right : RuntimeExpressionResult functions context state rhs (.nominal identity) outcome) :
    RuntimeExpressionResult functions context state
      (.binary (.compare (if equal then .eq else .ne)) lhs rhs) (.scalar .boolean)
      (outcome.then (compareNominal identity equal value)) := by
  intro kind actual events evaluated
  generalize operatorEq : SourceBinOp.compare (if equal then .eq else .ne) = operator at evaluated
  cases evaluated with
  | wordBinaryFault op evaluated => have impossible := (left _ _ _ evaluated).1; cases impossible
  | wordBinary op first second => have impossible := (left _ _ _ first).1; cases impossible
  | enumCompareFault evaluated => have impossible := (left _ _ _ evaluated).2; cases impossible
  | enumCompare first second =>
    have sameFlag := compare_flag_injective operatorEq
    cases sameFlag
    have sameIdentity := (left _ _ _ first).1
    cases sameIdentity
    have sameValue := (left _ _ _ first).2
    cases sameValue
    constructor
    · rfl
    · rw [(right _ _ _ second).2]
  | shiftLeft _ _ => cases equal <;> cases operatorEq
  | shiftRight _ _ => cases equal <;> cases operatorEq
  | andFault _ => cases equal <;> cases operatorEq
  | andStop _ => cases equal <;> cases operatorEq
  | andContinue _ _ => cases equal <;> cases operatorEq
  | orFault _ => cases equal <;> cases operatorEq
  | orStop _ => cases equal <;> cases operatorEq
  | orContinue _ _ => cases equal <;> cases operatorEq

theorem shiftLeft
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) outcome)
    (known : SourceShiftCount rhs count) :
    RuntimeExpressionResult functions context state (.binary .shift lhs rhs) (.scalar .word)
      (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault op _ => cases op
  | wordBinary op _ _ => cases op
  | shiftLeft evaluated actualCount =>
    have same := shift_count_unique known actualCount
    subst count
    constructor
    · rfl
    · rw [(left _ _ _ evaluated).2]

theorem shiftRight
    (left : RuntimeExpressionResult functions context state lhs (.scalar .word) outcome)
    (known : SourceShiftCount rhs count) :
    RuntimeExpressionResult functions context state (.binary .rightShift lhs rhs) (.scalar .word)
      (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) := by
  intro kind actual events evaluated
  cases evaluated with
  | wordBinaryFault op _ => cases op
  | wordBinary op _ _ => cases op
  | shiftRight evaluated actualCount =>
    have same := shift_count_unique known actualCount
    subst count
    constructor
    · rfl
    · rw [(left _ _ _ evaluated).2]

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
  cases evaluated with
  | next first rest => cases first
  | returned first rest =>
    cases first with
    | returnValue actual =>
      have same := (expression _ _ _ actual).2
      subst result; rfl
  | trapped first rest =>
    cases first with
    | returnFault actual =>
      have same := (expression _ _ _ actual).2
      subst result; rfl

end RuntimeExpressionResult
end Aurora.SourceBinding
