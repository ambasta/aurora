import SourceBinding.RuntimePureInduction
namespace Aurora.SourceBinding

/-- The original APIs are uniform specializations of the one effectful source
    judgment. Global preservation is proved in the isolated migration audit. -/
abbrev RuntimeEvaluation := PureRuntimeEvaluation
abbrev RuntimeArgumentEvaluation := PureRuntimeArgumentEvaluation
abbrev RuntimeStatementEvaluation := PureRuntimeStatementEvaluation
abbrev RuntimeStatementsEvaluation := PureRuntimeStatementsEvaluation
abbrev RuntimeEvaluation.word := @PureRuntimeEvaluation.word
abbrev RuntimeEvaluation.boolean := @PureRuntimeEvaluation.boolean
abbrev RuntimeEvaluation.readVariable := @PureRuntimeEvaluation.readVariable
abbrev RuntimeEvaluation.enumValue := @PureRuntimeEvaluation.enumValue
abbrev RuntimeEvaluation.not := @PureRuntimeEvaluation.not
abbrev RuntimeEvaluation.wordBinaryFault := @PureRuntimeEvaluation.wordBinaryFault
abbrev RuntimeEvaluation.wordBinary := @PureRuntimeEvaluation.wordBinary
abbrev RuntimeEvaluation.enumCompareFault := @PureRuntimeEvaluation.enumCompareFault
abbrev RuntimeEvaluation.enumCompare := @PureRuntimeEvaluation.enumCompare
abbrev RuntimeEvaluation.shiftLeft := @PureRuntimeEvaluation.shiftLeft
abbrev RuntimeEvaluation.shiftRight := @PureRuntimeEvaluation.shiftRight
abbrev RuntimeEvaluation.andFault := @PureRuntimeEvaluation.andFault
abbrev RuntimeEvaluation.andStop := @PureRuntimeEvaluation.andStop
abbrev RuntimeEvaluation.andContinue := @PureRuntimeEvaluation.andContinue
abbrev RuntimeEvaluation.orFault := @PureRuntimeEvaluation.orFault
abbrev RuntimeEvaluation.orStop := @PureRuntimeEvaluation.orStop
abbrev RuntimeEvaluation.orContinue := @PureRuntimeEvaluation.orContinue
abbrev RuntimeEvaluation.callArgumentsFault := @PureRuntimeEvaluation.callArgumentsFault
abbrev RuntimeEvaluation.callValue := @PureRuntimeEvaluation.callValue
abbrev RuntimeEvaluation.callFault := @PureRuntimeEvaluation.callFault
abbrev RuntimeArgumentEvaluation.nil := @PureRuntimeArgumentEvaluation.nil
abbrev RuntimeArgumentEvaluation.fault := @PureRuntimeArgumentEvaluation.fault
abbrev RuntimeArgumentEvaluation.cons := @PureRuntimeArgumentEvaluation.cons
abbrev RuntimeStatementEvaluation.declarationFault := @PureRuntimeStatementEvaluation.declarationFault
abbrev RuntimeStatementEvaluation.declarationValue := @PureRuntimeStatementEvaluation.declarationValue
abbrev RuntimeStatementEvaluation.assignmentFault := @PureRuntimeStatementEvaluation.assignmentFault
abbrev RuntimeStatementEvaluation.assignmentValue := @PureRuntimeStatementEvaluation.assignmentValue
abbrev RuntimeStatementEvaluation.returnFault := @PureRuntimeStatementEvaluation.returnFault
abbrev RuntimeStatementEvaluation.returnValue := @PureRuntimeStatementEvaluation.returnValue
abbrev RuntimeStatementEvaluation.branchFault := @PureRuntimeStatementEvaluation.branchFault
abbrev RuntimeStatementEvaluation.branchFalse := @PureRuntimeStatementEvaluation.branchFalse
abbrev RuntimeStatementEvaluation.branchTrueContinue := @PureRuntimeStatementEvaluation.branchTrueContinue
abbrev RuntimeStatementEvaluation.branchTrueReturn := @PureRuntimeStatementEvaluation.branchTrueReturn
abbrev RuntimeStatementEvaluation.branchTrueFault := @PureRuntimeStatementEvaluation.branchTrueFault
abbrev RuntimeStatementsEvaluation.nil := @PureRuntimeStatementsEvaluation.nil
abbrev RuntimeStatementsEvaluation.next := @PureRuntimeStatementsEvaluation.next
abbrev RuntimeStatementsEvaluation.returned := @PureRuntimeStatementsEvaluation.returned
abbrev RuntimeStatementsEvaluation.trapped := @PureRuntimeStatementsEvaluation.trapped

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
