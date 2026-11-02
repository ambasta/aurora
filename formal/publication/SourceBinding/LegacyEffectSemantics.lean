import SourceBinding.RuntimeExpressions
import SourceBinding.RuntimeSourceFunction
import SourceBinding.RuntimeScopeOperations
import SourceBinding.RuntimeFormals
import SourceBinding.RuntimeEvaluationData
namespace Aurora.SourceBinding

/- Frozen PROOF-ONLY migration snapshot. No production semantics/checker imports
   this module. Exact four-way mutual block from public predecessor source:
   local commit 93c35503597b3afb5541f13696d20989f22096ca,
   RuntimeEvaluation.lean SHA256
   138ff77009f1e9f38565dcd403e7994f58fb8b00a4e70316a46235eccdc7b4ae.
   The only changes within the mutual block are the four relation-name renames.
   ScopedStatement(s) remain the exact legacy aliases, INCLUDING dead suffixes.
   This is not an executable interpreter or a second production semantics. -/
mutual
  inductive LegacyEffectEvaluation (functions : List RuntimeSourceFunction) :
      RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value →
      List RuntimeSourceEvent → Prop
    | word : LegacyEffectEvaluation functions context state (.word value) (.scalar .word)
        (readScalar .word (some (.word value))) []
    | boolean : LegacyEffectEvaluation functions context state (.boolean value) (.scalar .boolean)
        (.value (.boolean value)) []
    | readVariable : RuntimeVariableBinding context name binding →
        LegacyEffectEvaluation functions context state (.name [name]) binding.kind (state.readBound binding) []
    | enumValue : RuntimeEnumValue context name identity ordinal →
        LegacyEffectEvaluation functions context state (.name name) (.nominal identity)
          (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) []
    | not : LegacyEffectEvaluation functions context state inner (.scalar .boolean) outcome events →
        LegacyEffectEvaluation functions context state (.not inner) (.scalar .boolean) (outcome.then notValue) events
    | wordBinaryFault : RuntimeWordOperator operator primitive result →
        LegacyEffectEvaluation functions context state left (.scalar .word) (.trap fault) events →
        LegacyEffectEvaluation functions context state (.binary operator left right) (.scalar result) (.trap fault) events
    | wordBinary : RuntimeWordOperator operator primitive result →
        LegacyEffectEvaluation functions context state left (.scalar .word) (.value value) leftEvents →
        LegacyEffectEvaluation functions context state right (.scalar .word) outcome rightEvents →
        LegacyEffectEvaluation functions context state (.binary operator left right) (.scalar result)
          (outcome.then (binaryValue primitive value)) (leftEvents ++ rightEvents)
    | enumCompareFault {equal : Bool} :
        LegacyEffectEvaluation functions context state left (.nominal identity) (.trap fault) events →
        LegacyEffectEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.trap fault) events
    | enumCompare {equal : Bool} :
        LegacyEffectEvaluation functions context state left (.nominal identity) (.value value) leftEvents →
        LegacyEffectEvaluation functions context state right (.nominal identity) outcome rightEvents →
        LegacyEffectEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (outcome.then (compareNominal identity equal value)) (leftEvents ++ rightEvents)
    | shiftLeft : LegacyEffectEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        LegacyEffectEvaluation functions context state (.binary .shift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) events
    | shiftRight : LegacyEffectEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        LegacyEffectEvaluation functions context state (.binary .rightShift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) events
    | andFault : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        LegacyEffectEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.trap fault) events
    | andStop : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) events →
        LegacyEffectEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.value (.boolean false)) events
    | andContinue : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) leftEvents →
        LegacyEffectEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        LegacyEffectEvaluation functions context state (.binary .and left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | orFault : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        LegacyEffectEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.trap fault) events
    | orStop : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) events →
        LegacyEffectEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.value (.boolean true)) events
    | orContinue : LegacyEffectEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) leftEvents →
        LegacyEffectEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        LegacyEffectEvaluation functions context state (.binary .or left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | callArgumentsFault : leaf ∈ functions → leaf.Resolves context name →
        LegacyEffectArgumentEvaluation functions context state sources leaf.parameters (.trap fault) events →
        LegacyEffectEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault) events
    | callValue : leaf ∈ functions → leaf.Resolves context name →
        LegacyEffectArgumentEvaluation functions context state sources leaf.parameters (.value values) argumentEvents →
        LegacyEffectStatementsEvaluation functions leaf.context.members leaf.context.module leaf.context.path
          leaf.context.formals leaf.result ⟨[],0,1,leaf.context.formals.length⟩
          (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.parsed.statements after (.returned value finished) bodyEvents →
        LegacyEffectEvaluation functions context state (.call (.named name) sources) leaf.result (.value value)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents ++ [.returned leaf.key value])
    | callFault : leaf ∈ functions → leaf.Resolves context name →
        LegacyEffectArgumentEvaluation functions context state sources leaf.parameters (.value values) argumentEvents →
        LegacyEffectStatementsEvaluation functions leaf.context.members leaf.context.module leaf.context.path
          leaf.context.formals leaf.result ⟨[],0,1,leaf.context.formals.length⟩
          (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.parsed.statements after (.trapped fault finished) bodyEvents →
        LegacyEffectEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents)

  inductive LegacyEffectArgumentEvaluation (functions : List RuntimeSourceFunction) :
      RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType →
      Outcome (List Value) → List RuntimeSourceEvent → Prop
    | nil : LegacyEffectArgumentEvaluation functions context state [] [] (.value []) []
    | fault : LegacyEffectEvaluation functions context state first kind (.trap fault) events →
        LegacyEffectArgumentEvaluation functions context state (first :: rest) (kind :: kinds) (.trap fault) events
    | cons : LegacyEffectEvaluation functions context state first kind (.value value) firstEvents →
        LegacyEffectArgumentEvaluation functions context state rest kinds outcome restEvents →
        LegacyEffectArgumentEvaluation functions context state (first :: rest) (kind :: kinds)
          (outcome.then fun values => .value (value :: values)) (firstEvents ++ restEvents)
inductive LegacyEffectStatementEvaluation (functions : List RuntimeSourceFunction)
    : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | declarationFault {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.localDecl declaration raw) after (.trapped fault state) events
  | declarationValue {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.initialize binding.slot binding.runtimeDeclaration value = some next →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.localDecl declaration raw) after (.continued next) events
  | assignmentFault : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.assign name raw) before (.trapped fault state) events
  | assignmentValue : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.assign binding.slot value = some next →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.assign name raw) before (.continued next) events
  | returnFault : LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.trap fault) events →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.returnValue raw) before (.trapped fault state) events
  | returnValue : LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.value value) events →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.returnValue raw) before (.returned value state) events
  | branchFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.trap fault) events →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault state) events
  | branchFalse : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean false)) events →
      state.reserveScopes child.nextScope = some next →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) events
  | branchTrueContinue : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyEffectStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.continued finished) bodyEvents →
      finished.leave.reserveScopes child.nextScope = some next →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) (firstEvents ++ bodyEvents)
  | branchTrueReturn : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyEffectStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.returned value finished) bodyEvents →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.returned value finished) (firstEvents ++ bodyEvents)
  | branchTrueFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyEffectEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyEffectStatementsEvaluation functions members module path formals result (enterLocalScope before) entered body child (.trapped fault finished) bodyEvents →
      LegacyEffectStatementEvaluation functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault finished) (firstEvents ++ bodyEvents)
inductive LegacyEffectStatementsEvaluation (functions : List RuntimeSourceFunction)
    : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | nil : LegacyEffectStatementsEvaluation functions members module path formals result before state [] before (.continued state) []
  | next : LegacyEffectStatementEvaluation functions members module path formals result before state first middle (.continued next) firstEvents →
      LegacyEffectStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents →
      LegacyEffectStatementsEvaluation functions members module path formals result before state (first::rest) after outcome (firstEvents++restEvents)
  | returned : LegacyEffectStatementEvaluation functions members module path formals result before state first middle (.returned value final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      LegacyEffectStatementsEvaluation functions members module path formals result before state (first::rest) after (.returned value final) events
  | trapped : LegacyEffectStatementEvaluation functions members module path formals result before state first middle (.trapped fault final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      LegacyEffectStatementsEvaluation functions members module path formals result before state (first::rest) after (.trapped fault final) events
end

end Aurora.SourceBinding
