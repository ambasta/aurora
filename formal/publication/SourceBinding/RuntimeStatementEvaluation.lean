import SourceBinding.RuntimeScopeReservation
namespace Aurora.SourceBinding

/-- A terminal source statement retains the state at that point. Returning or
    trapping does not invent lexical cleanup, rollback or machine unwinding. -/
inductive RuntimeBodyOutcome where
  | continued (state : RuntimeLocals)
  | returned (value : Value) (state : RuntimeLocals)
  | trapped (fault : Fault) (state : RuntimeLocals)

/- Independent source statement semantics over the SAME raw statement tree.
   ScopedStatement(s) supplies source-only declaration/cursor identity. It does
   not supply expression results, machine code or successful initialization.
   All expressions delegate the existing judgement and shared primitives. -/
mutual
inductive RuntimeStatementEvaluates (functions : List RuntimeSourceLeaf)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType) :
    LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | declarationFault {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      RuntimeStatementEvaluates functions members module path formals result before state (.localDecl declaration raw) after (.trapped fault state) events
  | declarationValue {declaration : Formal} :
      ScopedStatement members module path formals before (.localDecl declaration raw) after [binding] →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.initialize binding.slot binding.runtimeDeclaration value = some next →
      RuntimeStatementEvaluates functions members module path formals result before state (.localDecl declaration raw) after (.continued next) events
  | assignmentFault : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw binding.kind (.trap fault) events →
      RuntimeStatementEvaluates functions members module path formals result before state (.assign name raw) before (.trapped fault state) events
  | assignmentValue : binding ∈ before.visible → binding.name = name → binding.mutable = true →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw binding.kind (.value value) events →
      state.assign binding.slot value = some next →
      RuntimeStatementEvaluates functions members module path formals result before state (.assign name raw) before (.continued next) events
  | returnFault : RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw result (.trap fault) events →
      RuntimeStatementEvaluates functions members module path formals result before state (.returnValue raw) before (.trapped fault state) events
  | returnValue : RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state raw result (.value value) events →
      RuntimeStatementEvaluates functions members module path formals result before state (.returnValue raw) before (.returned value state) events
  | branchFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.trap fault) events →
      RuntimeStatementEvaluates functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault state) events
  | branchFalse : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean false)) events →
      state.reserveScopes child.nextScope = some next →
      RuntimeStatementEvaluates functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) events
  | branchTrueContinue : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluate functions members module path formals result (enterLocalScope before) entered body child (.continued finished) bodyEvents →
      finished.leave.reserveScopes child.nextScope = some next →
      RuntimeStatementEvaluates functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.continued next) (firstEvents ++ bodyEvents)
  | branchTrueReturn : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluate functions members module path formals result (enterLocalScope before) entered body child (.returned value finished) bodyEvents →
      RuntimeStatementEvaluates functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.returned value finished) (firstEvents ++ bodyEvents)
  | branchTrueFault : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
      RuntimeEvaluatesWith functions (runtimeStatementContext members module path formals before) state condition (.scalar .boolean) (.value (.boolean true)) firstEvents →
      state.enterAt before.nextScope = some entered →
      RuntimeStatementsEvaluate functions members module path formals result (enterLocalScope before) entered body child (.trapped fault finished) bodyEvents →
      RuntimeStatementEvaluates functions members module path formals result before state (.ifThen condition body)
        (leaveLocalScope before child) (.trapped fault finished) (firstEvents ++ bodyEvents)
inductive RuntimeStatementsEvaluate (functions : List RuntimeSourceLeaf)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType) :
    LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop
  | nil : RuntimeStatementsEvaluate functions members module path formals result before state [] before (.continued state) []
  | next : RuntimeStatementEvaluates functions members module path formals result before state first middle (.continued next) firstEvents →
      RuntimeStatementsEvaluate functions members module path formals result middle next rest after outcome restEvents →
      RuntimeStatementsEvaluate functions members module path formals result before state (first::rest) after outcome (firstEvents++restEvents)
  | returned : RuntimeStatementEvaluates functions members module path formals result before state first middle (.returned value final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      RuntimeStatementsEvaluate functions members module path formals result before state (first::rest) after (.returned value final) events
  | trapped : RuntimeStatementEvaluates functions members module path formals result before state first middle (.trapped fault final) events →
      ScopedStatements members module path formals middle rest after declaredItems →
      RuntimeStatementsEvaluate functions members module path formals result before state (first::rest) after (.trapped fault final) events
end

end Aurora.SourceBinding
