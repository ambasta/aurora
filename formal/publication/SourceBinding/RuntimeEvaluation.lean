import SourceBinding.RuntimeExpressions
namespace Aurora.SourceBinding

/-- A source use retains the declaration selected by lexical binding. The
    operational read checks that exact declaration and its active scope; neither
    a value in a coincidentally numbered slot nor an inactive declaration suffices. -/
def SourceLocal.runtimeDeclaration (binding : SourceLocal) : RuntimeLocalDecl :=
  ⟨binding.kind,binding.mutable,binding.scope⟩

def RuntimeLocals.readBound (state : RuntimeLocals) (binding : SourceLocal) : Outcome Value :=
  if state.declarations binding.slot = some binding.runtimeDeclaration then
    state.read binding.slot
  else .trap .type

/-- Independent source operational judgement on the existing raw expression AST.
    It consumes lexical resolution, not a typing or instruction certificate.
    Only shared scalar/nominal primitives determine arithmetic and read outcomes.
    Fault rules deliberately do not evaluate a later operand. -/
inductive RuntimeEvaluates (context : RuntimeExprContext) (state : RuntimeLocals) :
    SourceExpr → RuntimeType → Outcome Value → Prop
  | word : RuntimeEvaluates context state (.word value) (.scalar .word)
      (readScalar .word (some (.word value)))
  | boolean : RuntimeEvaluates context state (.boolean value) (.scalar .boolean) (.value (.boolean value))
  | readVariable : RuntimeVariableBinding context name binding →
      RuntimeEvaluates context state (.name [name]) binding.kind (state.readBound binding)
  | enumValue : RuntimeEnumValue context name identity ordinal →
      RuntimeEvaluates context state (.name name) (.nominal identity)
        (readRuntime (.nominal identity) (some (.nominal identity.name ordinal)))
  | not : RuntimeEvaluates context state inner (.scalar .boolean) outcome →
      RuntimeEvaluates context state (.not inner) (.scalar .boolean) (outcome.then notValue)
  | wordBinaryFault : RuntimeWordOperator operator primitive result →
      RuntimeEvaluates context state left (.scalar .word) (.trap fault) →
      RuntimeEvaluates context state (.binary operator left right) (.scalar result) (.trap fault)
  | wordBinary : RuntimeWordOperator operator primitive result →
      RuntimeEvaluates context state left (.scalar .word) (.value value) →
      RuntimeEvaluates context state right (.scalar .word) outcome →
      RuntimeEvaluates context state (.binary operator left right) (.scalar result)
        (outcome.then (binaryValue primitive value))
  | enumCompareFault {equal : Bool} : RuntimeEvaluates context state left (.nominal identity) (.trap fault) →
      RuntimeEvaluates context state (.binary (.compare (if equal then .eq else .ne)) left right)
        (.scalar .boolean) (.trap fault)
  | enumCompare {equal : Bool} : RuntimeEvaluates context state left (.nominal identity) (.value value) →
      RuntimeEvaluates context state right (.nominal identity) outcome →
      RuntimeEvaluates context state (.binary (.compare (if equal then .eq else .ne)) left right)
        (.scalar .boolean) (outcome.then (compareNominal identity equal value))
  | shiftLeft : RuntimeEvaluates context state left (.scalar .word) outcome → SourceShiftCount right count →
      RuntimeEvaluates context state (.binary .shift left right) (.scalar .word)
        (outcome.then fun value => binaryValue .leftShift value count.runtimeValue)
  | shiftRight : RuntimeEvaluates context state left (.scalar .word) outcome → SourceShiftCount right count →
      RuntimeEvaluates context state (.binary .rightShift left right) (.scalar .word)
        (outcome.then fun value => binaryValue .rightShift value count.runtimeValue)
  | andFault : RuntimeEvaluates context state left (.scalar .boolean) (.trap fault) →
      RuntimeEvaluates context state (.binary .and left right) (.scalar .boolean) (.trap fault)
  | andStop : RuntimeEvaluates context state left (.scalar .boolean) (.value (.boolean false)) →
      RuntimeEvaluates context state (.binary .and left right) (.scalar .boolean) (.value (.boolean false))
  | andContinue : RuntimeEvaluates context state left (.scalar .boolean) (.value (.boolean true)) →
      RuntimeEvaluates context state right (.scalar .boolean) outcome →
      RuntimeEvaluates context state (.binary .and left right) (.scalar .boolean) outcome
  | orFault : RuntimeEvaluates context state left (.scalar .boolean) (.trap fault) →
      RuntimeEvaluates context state (.binary .or left right) (.scalar .boolean) (.trap fault)
  | orStop : RuntimeEvaluates context state left (.scalar .boolean) (.value (.boolean true)) →
      RuntimeEvaluates context state (.binary .or left right) (.scalar .boolean) (.value (.boolean true))
  | orContinue : RuntimeEvaluates context state left (.scalar .boolean) (.value (.boolean false)) →
      RuntimeEvaluates context state right (.scalar .boolean) outcome →
      RuntimeEvaluates context state (.binary .or left right) (.scalar .boolean) outcome

/-- Ordered arguments, without invoking any callee. A first failure prevents the
    remaining arguments from being evaluated. Counts have no argument type. -/
inductive RuntimeArgumentsEvaluate (context : RuntimeExprContext) (state : RuntimeLocals) :
    List SourceExpr → List RuntimeType → Outcome (List Value) → Prop
  | nil : RuntimeArgumentsEvaluate context state [] [] (.value [])
  | fault : RuntimeEvaluates context state first kind (.trap fault) →
      RuntimeArgumentsEvaluate context state (first :: rest) (kind :: kinds) (.trap fault)
  | cons : RuntimeEvaluates context state first kind (.value value) →
      RuntimeArgumentsEvaluate context state rest kinds outcome →
      RuntimeArgumentsEvaluate context state (first :: rest) (kind :: kinds)
        (outcome.then fun values => .value (value :: values))

/-- Metadata and lexical activity are independent of initialized-value validity.
    This interface therefore also covers missing or malformed formal values and
    preserves the old scalar evaluator's faults. -/
def RuntimeBindingsPresent (context : RuntimeExprContext) (state : RuntimeLocals) : Prop :=
  ∀ name binding, RuntimeVariableBinding context name binding →
    state.declarations binding.slot = some binding.runtimeDeclaration ∧ binding.scope ∈ state.scopes

theorem RuntimeLocals.readBound_eq (state : RuntimeLocals) (binding : SourceLocal)
    (declared : state.declarations binding.slot = some binding.runtimeDeclaration)
    (active : binding.scope ∈ state.scopes) :
    state.readBound binding = readRuntime binding.kind (state.values binding.slot) := by
  simp only [RuntimeLocals.readBound, declared, if_pos, RuntimeLocals.read,
    SourceLocal.runtimeDeclaration, active]

end Aurora.SourceBinding
