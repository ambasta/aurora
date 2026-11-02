import SourceBinding.RuntimeExpressions
import SourceBinding.RuntimeSourceFunction
import SourceBinding.RuntimeScopeOperations
import SourceBinding.RuntimeFormals
import SourceBinding.RuntimeEvaluationData
namespace Aurora.SourceBinding

/- ONE source judgement on the existing raw AST. The environment contains actual
    parsed source functions, not IR outcomes or successful-call summaries.
    Arguments are evaluated once in order. A fault emits no fictitious return. -/
mutual
  inductive RuntimeEvaluation (functions : List RuntimeSourceFunction) :
      RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value →
      List RuntimeSourceEvent → Prop
    | word : RuntimeEvaluation functions context state (.word value) (.scalar .word)
        (readScalar .word (some (.word value))) []
    | boolean : RuntimeEvaluation functions context state (.boolean value) (.scalar .boolean)
        (.value (.boolean value)) []
    | readVariable : RuntimeVariableBinding context name binding →
        RuntimeEvaluation functions context state (.name [name]) binding.kind (state.readBound binding) []
    | enumValue : RuntimeEnumValue context name identity ordinal →
        RuntimeEvaluation functions context state (.name name) (.nominal identity)
          (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) []
    | not : RuntimeEvaluation functions context state inner (.scalar .boolean) outcome events →
        RuntimeEvaluation functions context state (.not inner) (.scalar .boolean) (outcome.then notValue) events
    | wordBinaryFault : RuntimeWordOperator operator primitive result →
        RuntimeEvaluation functions context state left (.scalar .word) (.trap fault) events →
        RuntimeEvaluation functions context state (.binary operator left right) (.scalar result) (.trap fault) events
    | wordBinary : RuntimeWordOperator operator primitive result →
        RuntimeEvaluation functions context state left (.scalar .word) (.value value) leftEvents →
        RuntimeEvaluation functions context state right (.scalar .word) outcome rightEvents →
        RuntimeEvaluation functions context state (.binary operator left right) (.scalar result)
          (outcome.then (binaryValue primitive value)) (leftEvents ++ rightEvents)
    | enumCompareFault {equal : Bool} :
        RuntimeEvaluation functions context state left (.nominal identity) (.trap fault) events →
        RuntimeEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.trap fault) events
    | enumCompare {equal : Bool} :
        RuntimeEvaluation functions context state left (.nominal identity) (.value value) leftEvents →
        RuntimeEvaluation functions context state right (.nominal identity) outcome rightEvents →
        RuntimeEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (outcome.then (compareNominal identity equal value)) (leftEvents ++ rightEvents)
    | shiftLeft : RuntimeEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        RuntimeEvaluation functions context state (.binary .shift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) events
    | shiftRight : RuntimeEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        RuntimeEvaluation functions context state (.binary .rightShift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) events
    | andFault : RuntimeEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        RuntimeEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.trap fault) events
    | andStop : RuntimeEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) events →
        RuntimeEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.value (.boolean false)) events
    | andContinue : RuntimeEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) leftEvents →
        RuntimeEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        RuntimeEvaluation functions context state (.binary .and left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | orFault : RuntimeEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        RuntimeEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.trap fault) events
    | orStop : RuntimeEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) events →
        RuntimeEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.value (.boolean true)) events
    | orContinue : RuntimeEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) leftEvents →
        RuntimeEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        RuntimeEvaluation functions context state (.binary .or left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | callArgumentsFault : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentEvaluation functions context state sources leaf.parameters (.trap fault) events →
        RuntimeEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault) events
    | callValue : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentEvaluation functions context state sources leaf.parameters (.value values) argumentEvents →
        RuntimeStatementsEvaluation functions leaf.context.members leaf.context.module leaf.context.path
          leaf.context.formals leaf.result ⟨[],0,1,leaf.context.formals.length⟩
          (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.parsed.statements after (.returned value finished) bodyEvents →
        RuntimeEvaluation functions context state (.call (.named name) sources) leaf.result (.value value)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents ++ [.returned leaf.key value])
    | callFault : leaf ∈ functions → leaf.Resolves context name →
        RuntimeArgumentEvaluation functions context state sources leaf.parameters (.value values) argumentEvents →
        RuntimeStatementsEvaluation functions leaf.context.members leaf.context.module leaf.context.path
          leaf.context.formals leaf.result ⟨[],0,1,leaf.context.formals.length⟩
          (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.parsed.statements after (.trapped fault finished) bodyEvents →
        RuntimeEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents)

  inductive RuntimeArgumentEvaluation (functions : List RuntimeSourceFunction) :
      RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType →
      Outcome (List Value) → List RuntimeSourceEvent → Prop
    | nil : RuntimeArgumentEvaluation functions context state [] [] (.value []) []
    | fault : RuntimeEvaluation functions context state first kind (.trap fault) events →
        RuntimeArgumentEvaluation functions context state (first :: rest) (kind :: kinds) (.trap fault) events
    | cons : RuntimeEvaluation functions context state first kind (.value value) firstEvents →
        RuntimeArgumentEvaluation functions context state rest kinds outcome restEvents →
        RuntimeArgumentEvaluation functions context state (first :: rest) (kind :: kinds)
          (outcome.then fun values => .value (value :: values)) (firstEvents ++ restEvents)
inductive RuntimeStatementEvaluation (functions : List RuntimeSourceFunction)
    : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | declarationFault {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      RuntimeStatementEvaluation functions members module path formals result before state (.localDecl declaration raw) after (.trapped fault state) events
  | declarationValue {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.initialize binding.slot binding.runtimeDeclaration value = some next →
      RuntimeStatementEvaluation functions members module path formals result before state (.localDecl declaration raw) after (.continued next) events
  | assignmentFault : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      RuntimeStatementEvaluation functions members module path formals result before state (.assign name raw) before (.trapped fault state) events
  | assignmentValue : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.assign binding.slot value = some next →
      RuntimeStatementEvaluation functions members module path formals result before state (.assign name raw) before (.continued next) events
  | returnFault : RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.trap fault) events →
      RuntimeStatementEvaluation functions members module path formals result before state (.returnValue raw) before (.trapped fault state) events
  | returnValue : RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.value value) events →
      RuntimeStatementEvaluation functions members module path formals result before state (.returnValue raw) before (.returned value state) events
  | branchFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.trap fault) events →
      RuntimeStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault state) events
  | branchFalse : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean false)) events →
      state.reserveScopes child.nextScope = some next →
      RuntimeStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) events
  | branchTrueContinue : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.continued finished) bodyEvents →
      finished.leave.reserveScopes child.nextScope = some next →
      RuntimeStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) (firstEvents ++ bodyEvents)
  | branchTrueReturn : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.returned value finished) bodyEvents →
      RuntimeStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.returned value finished) (firstEvents ++ bodyEvents)
  | branchTrueFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.trapped fault finished) bodyEvents →
      RuntimeStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault finished) (firstEvents ++ bodyEvents)
inductive RuntimeStatementsEvaluation (functions : List RuntimeSourceFunction)
    : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | nil : RuntimeStatementsEvaluation functions members module path formals result before state [] before (.continued state) []
  | next : RuntimeStatementEvaluation functions members module path formals result before state first middle (.continued next) firstEvents →
      RuntimeStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents →
      RuntimeStatementsEvaluation functions members module path formals result before state (first::rest) after outcome (firstEvents++restEvents)
  | returned : RuntimeStatementEvaluation functions members module path formals result before state first middle (.returned value final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      RuntimeStatementsEvaluation functions members module path formals result before state (first::rest) after (.returned value final) events
  | trapped : RuntimeStatementEvaluation functions members module path formals result before state first middle (.trapped fault final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      RuntimeStatementsEvaluation functions members module path formals result before state (first::rest) after (.trapped fault final) events
end

/-- Exact old leaf profiles. Global preservation is proved independently against
    the frozen proof-only relations, not asserted merely by these aliases. -/
abbrev RuntimeEvaluatesWith (functions : List RuntimeSourceLeaf) :=
  RuntimeEvaluation (functions.map RuntimeSourceLeaf.toFunction)
abbrev RuntimeArgumentsEvaluateWith (functions : List RuntimeSourceLeaf) :=
  RuntimeArgumentEvaluation (functions.map RuntimeSourceLeaf.toFunction)
abbrev RuntimeStatementEvaluates (functions : List RuntimeSourceLeaf) :=
  RuntimeStatementEvaluation (functions.map RuntimeSourceLeaf.toFunction)
abbrev RuntimeStatementsEvaluate (functions : List RuntimeSourceLeaf) :=
  RuntimeStatementsEvaluation (functions.map RuntimeSourceLeaf.toFunction)

/-- Conservative old profile: empty function environment and empty call trace.
    This is a specialization of the ONE judgement, not a parallel evaluator. -/
abbrev RuntimeEvaluates (context : RuntimeExprContext) (state : RuntimeLocals)
    (raw : SourceExpr) (kind : RuntimeType) (outcome : Outcome Value) : Prop :=
  RuntimeEvaluatesWith [] context state raw kind outcome []
abbrev RuntimeArgumentsEvaluate (context : RuntimeExprContext) (state : RuntimeLocals)
    (raws : List SourceExpr) (kinds : List RuntimeType) (outcome : Outcome (List Value)) : Prop :=
  RuntimeArgumentsEvaluateWith [] context state raws kinds outcome []

abbrev RuntimeEvaluates.readVariable (binding : RuntimeVariableBinding context name declared) :
    RuntimeEvaluates context state (.name [name]) declared.kind (state.readBound declared) :=
  RuntimeEvaluation.readVariable binding

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
