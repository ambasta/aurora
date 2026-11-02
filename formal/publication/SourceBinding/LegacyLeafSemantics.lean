import SourceBinding.RuntimeEvaluationData
namespace Aurora.SourceBinding

/- Frozen proof-only migration witness from commit
5915e195c7caa0599138acb8095939688c252560. Exact old constructor bodies below
are renamed only; no evaluator or AST is added to production.
RuntimeEvaluation source blob: 83e26c615c2d9ddf0e533aa73aa5bfca2705d878.
RuntimeStatementEvaluation blob: 2473458b3632b03c3d15091796dc931727d4e93b.
No production module may import this migration witness. -/

mutual
  inductive LegacyLeafEvaluation (functions : List RuntimeSourceLeaf) :
      RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value →
      List RuntimeSourceEvent → Prop
    | word : LegacyLeafEvaluation functions context state (.word value) (.scalar .word)
        (readScalar .word (some (.word value))) []
    | boolean : LegacyLeafEvaluation functions context state (.boolean value) (.scalar .boolean)
        (.value (.boolean value)) []
    | readVariable : RuntimeVariableBinding context name binding →
        LegacyLeafEvaluation functions context state (.name [name]) binding.kind (state.readBound binding) []
    | enumValue : RuntimeEnumValue context name identity ordinal →
        LegacyLeafEvaluation functions context state (.name name) (.nominal identity)
          (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) []
    | not : LegacyLeafEvaluation functions context state inner (.scalar .boolean) outcome events →
        LegacyLeafEvaluation functions context state (.not inner) (.scalar .boolean) (outcome.then notValue) events
    | wordBinaryFault : RuntimeWordOperator operator primitive result →
        LegacyLeafEvaluation functions context state left (.scalar .word) (.trap fault) events →
        LegacyLeafEvaluation functions context state (.binary operator left right) (.scalar result) (.trap fault) events
    | wordBinary : RuntimeWordOperator operator primitive result →
        LegacyLeafEvaluation functions context state left (.scalar .word) (.value value) leftEvents →
        LegacyLeafEvaluation functions context state right (.scalar .word) outcome rightEvents →
        LegacyLeafEvaluation functions context state (.binary operator left right) (.scalar result)
          (outcome.then (binaryValue primitive value)) (leftEvents ++ rightEvents)
    | enumCompareFault {equal : Bool} :
        LegacyLeafEvaluation functions context state left (.nominal identity) (.trap fault) events →
        LegacyLeafEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.trap fault) events
    | enumCompare {equal : Bool} :
        LegacyLeafEvaluation functions context state left (.nominal identity) (.value value) leftEvents →
        LegacyLeafEvaluation functions context state right (.nominal identity) outcome rightEvents →
        LegacyLeafEvaluation functions context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (outcome.then (compareNominal identity equal value)) (leftEvents ++ rightEvents)
    | shiftLeft : LegacyLeafEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        LegacyLeafEvaluation functions context state (.binary .shift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .leftShift value count.runtimeValue) events
    | shiftRight : LegacyLeafEvaluation functions context state left (.scalar .word) outcome events → SourceShiftCount right count →
        LegacyLeafEvaluation functions context state (.binary .rightShift left right) (.scalar .word)
          (outcome.then fun value => binaryValue .rightShift value count.runtimeValue) events
    | andFault : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        LegacyLeafEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.trap fault) events
    | andStop : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) events →
        LegacyLeafEvaluation functions context state (.binary .and left right) (.scalar .boolean) (.value (.boolean false)) events
    | andContinue : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) leftEvents →
        LegacyLeafEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        LegacyLeafEvaluation functions context state (.binary .and left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | orFault : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.trap fault) events →
        LegacyLeafEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.trap fault) events
    | orStop : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.value (.boolean true)) events →
        LegacyLeafEvaluation functions context state (.binary .or left right) (.scalar .boolean) (.value (.boolean true)) events
    | orContinue : LegacyLeafEvaluation functions context state left (.scalar .boolean) (.value (.boolean false)) leftEvents →
        LegacyLeafEvaluation functions context state right (.scalar .boolean) outcome rightEvents →
        LegacyLeafEvaluation functions context state (.binary .or left right) (.scalar .boolean) outcome (leftEvents ++ rightEvents)
    | callArgumentsFault : leaf ∈ functions → leaf.Resolves context name →
        LegacyLeafArguments functions context state sources leaf.parameters (.trap fault) events →
        LegacyLeafEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault) events
    | callValue : leaf ∈ functions → leaf.Resolves context name →
        LegacyLeafArguments functions context state sources leaf.parameters (.value values) argumentEvents →
        LegacyLeafEvaluation functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.raw leaf.result (.value value) bodyEvents →
        LegacyLeafEvaluation functions context state (.call (.named name) sources) leaf.result (.value value)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents ++ [.returned leaf.key value])
    | callFault : leaf ∈ functions → leaf.Resolves context name →
        LegacyLeafArguments functions context state sources leaf.parameters (.value values) argumentEvents →
        LegacyLeafEvaluation functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
          leaf.raw leaf.result (.trap fault) bodyEvents →
        LegacyLeafEvaluation functions context state (.call (.named name) sources) leaf.result (.trap fault)
          (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents)

  inductive LegacyLeafArguments (functions : List RuntimeSourceLeaf) :
      RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType →
      Outcome (List Value) → List RuntimeSourceEvent → Prop
    | nil : LegacyLeafArguments functions context state [] [] (.value []) []
    | fault : LegacyLeafEvaluation functions context state first kind (.trap fault) events →
        LegacyLeafArguments functions context state (first :: rest) (kind :: kinds) (.trap fault) events
    | cons : LegacyLeafEvaluation functions context state first kind (.value value) firstEvents →
        LegacyLeafArguments functions context state rest kinds outcome restEvents →
        LegacyLeafArguments functions context state (first :: rest) (kind :: kinds)
          (outcome.then fun values => .value (value :: values)) (firstEvents ++ restEvents)
end

mutual
inductive LegacyLeafStatement (functions : List RuntimeSourceLeaf)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType) :
    LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | declarationFault {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      LegacyLeafStatement functions members module path formals result before state (.localDecl declaration raw) after (.trapped fault state) events
  | declarationValue {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.initialize binding.slot binding.runtimeDeclaration value = some next →
      LegacyLeafStatement functions members module path formals result before state (.localDecl declaration raw) after (.continued next) events
  | assignmentFault : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      LegacyLeafStatement functions members module path formals result before state (.assign name raw) before (.trapped fault state) events
  | assignmentValue : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.assign binding.slot value = some next →
      LegacyLeafStatement functions members module path formals result before state (.assign name raw) before (.continued next) events
  | returnFault : LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.trap fault) events →
      LegacyLeafStatement functions members module path formals result before state (.returnValue raw) before (.trapped fault state) events
  | returnValue : LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state raw result (.value value) events →
      LegacyLeafStatement functions members module path formals result before state (.returnValue raw) before (.returned value state) events
  | branchFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.trap fault) events →
      LegacyLeafStatement functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault state) events
  | branchFalse : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean false)) events →
      state.reserveScopes child.nextScope = some next →
      LegacyLeafStatement functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) events
  | branchTrueContinue : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyLeafStatements functions members module path formals result (enterLocalScope before) entered body child (.continued finished) bodyEvents →
      finished.leave.reserveScopes child.nextScope = some next →
      LegacyLeafStatement functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) (firstEvents ++ bodyEvents)
  | branchTrueReturn : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyLeafStatements functions members module path formals result (enterLocalScope before) entered body child (.returned value finished) bodyEvents →
      LegacyLeafStatement functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.returned value finished) (firstEvents ++ bodyEvents)
  | branchTrueFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      LegacyLeafEvaluation functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      LegacyLeafStatements functions members module path formals result (enterLocalScope before) entered body child (.trapped fault finished) bodyEvents →
      LegacyLeafStatement functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault finished) (firstEvents ++ bodyEvents)
inductive LegacyLeafStatements (functions : List RuntimeSourceLeaf)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType) :
    LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | nil : LegacyLeafStatements functions members module path formals result before state [] before (.continued state) []
  | next : LegacyLeafStatement functions members module path formals result before state first middle (.continued next) firstEvents →
      LegacyLeafStatements functions members module path formals result middle next rest after outcome restEvents →
      LegacyLeafStatements functions members module path formals result before state (first::rest) after outcome (firstEvents++restEvents)
  | returned : LegacyLeafStatement functions members module path formals result before state first middle (.returned value final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      LegacyLeafStatements functions members module path formals result before state (first::rest) after (.returned value final) events
  | trapped : LegacyLeafStatement functions members module path formals result before state first middle (.trapped fault final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      LegacyLeafStatements functions members module path formals result before state (first::rest) after (.trapped fault final) events
end

end Aurora.SourceBinding
