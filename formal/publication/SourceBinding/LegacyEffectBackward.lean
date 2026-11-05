import SourceBinding.PureEffectInduction
import SourceBinding.LegacyEffectSemantics
namespace Aurora.SourceBinding

/-- Frozen migration-only instantiation of the production pure elimination
    algebra. Production semantics never import this module. -/
def legacyEffectAlgebra (functions : List RuntimeSourceFunction) :
    PureEffectAlgebra functions (LegacyEffectEvaluation functions)
      (LegacyEffectArgumentEvaluation functions) (LegacyEffectStatementEvaluation functions)
      (LegacyEffectStatementsEvaluation functions) where
  expression_word := @LegacyEffectEvaluation.word functions
  expression_boolean := @LegacyEffectEvaluation.boolean functions
  expression_readVariable := @LegacyEffectEvaluation.readVariable functions
  expression_enumValue := @LegacyEffectEvaluation.enumValue functions
  expression_not := @LegacyEffectEvaluation.not functions
  expression_wordBinaryFault := @LegacyEffectEvaluation.wordBinaryFault functions
  expression_wordBinary := @LegacyEffectEvaluation.wordBinary functions
  expression_enumCompareFault := @LegacyEffectEvaluation.enumCompareFault functions
  expression_enumCompare := @LegacyEffectEvaluation.enumCompare functions
  expression_shiftLeft := @LegacyEffectEvaluation.shiftLeft functions
  expression_shiftRight := @LegacyEffectEvaluation.shiftRight functions
  expression_andFault := @LegacyEffectEvaluation.andFault functions
  expression_andStop := @LegacyEffectEvaluation.andStop functions
  expression_andContinue := @LegacyEffectEvaluation.andContinue functions
  expression_orFault := @LegacyEffectEvaluation.orFault functions
  expression_orStop := @LegacyEffectEvaluation.orStop functions
  expression_orContinue := @LegacyEffectEvaluation.orContinue functions
  expression_callArgumentsFault := @LegacyEffectEvaluation.callArgumentsFault functions
  expression_callValue := @LegacyEffectEvaluation.callValue functions
  expression_callFault := @LegacyEffectEvaluation.callFault functions
  arguments_nil := @LegacyEffectArgumentEvaluation.nil functions
  arguments_fault := @LegacyEffectArgumentEvaluation.fault functions
  arguments_cons := @LegacyEffectArgumentEvaluation.cons functions
  statement_declarationFault := @LegacyEffectStatementEvaluation.declarationFault functions
  statement_declarationValue := @LegacyEffectStatementEvaluation.declarationValue functions
  statement_assignmentFault := @LegacyEffectStatementEvaluation.assignmentFault functions
  statement_assignmentValue := @LegacyEffectStatementEvaluation.assignmentValue functions
  statement_returnFault := @LegacyEffectStatementEvaluation.returnFault functions
  statement_returnValue := @LegacyEffectStatementEvaluation.returnValue functions
  statement_branchFault := @LegacyEffectStatementEvaluation.branchFault functions
  statement_branchFalse := @LegacyEffectStatementEvaluation.branchFalse functions
  statement_branchTrueContinue := @LegacyEffectStatementEvaluation.branchTrueContinue functions
  statement_branchTrueReturn := @LegacyEffectStatementEvaluation.branchTrueReturn functions
  statement_branchTrueFault := @LegacyEffectStatementEvaluation.branchTrueFault functions
  statements_nil := @LegacyEffectStatementsEvaluation.nil functions
  statements_next := @LegacyEffectStatementsEvaluation.next functions
  statements_returned := @LegacyEffectStatementsEvaluation.returned functions
  statements_trapped := @LegacyEffectStatementsEvaluation.trapped functions

theorem EffectEvaluation.legacy_backward
    (evaluated : EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response context
      state raw kind outcome after events) (pure : context = .pure oldContext) :
    ∃ oldOutcome oldEvents,
      LegacyEffectEvaluation functions oldContext state.locals raw kind oldOutcome oldEvents ∧
      outcome = sourceLift oldOutcome ∧ after = state.shared ∧
      events = oldEvents.map RuntimeSourceEvent.toEffect :=
  evaluated.pure_induction (legacyEffectAlgebra functions) oldContext pure

theorem EffectArguments.legacy_backward
    (evaluated : EffectArguments (functions.map RuntimeSourceFunction.toEffect) response context
      state raws kinds outcome after events) (pure : context = .pure oldContext) :
    ∃ oldOutcome oldEvents,
      LegacyEffectArgumentEvaluation functions oldContext state.locals raws kinds oldOutcome oldEvents ∧
      outcome = legacyEffectArguments oldOutcome ∧ after = state.shared ∧
      events = oldEvents.map RuntimeSourceEvent.toEffect :=
  evaluated.pure_induction (legacyEffectAlgebra functions) oldContext pure

theorem EffectStatement.legacy_backward
    (evaluated : EffectStatement (functions.map RuntimeSourceFunction.toEffect) response context
      result before state raw after outcome events) (pure : context = .pure oldContext) :
    ∃ oldOutcome oldEvents,
      LegacyEffectStatementEvaluation functions oldContext.members oldContext.module oldContext.path
        oldContext.formals result before state.locals raw after oldOutcome oldEvents ∧
      outcome = legacyEffectBody state.shared oldOutcome ∧
      events = oldEvents.map RuntimeSourceEvent.toEffect :=
  evaluated.pure_induction (legacyEffectAlgebra functions) oldContext pure

theorem EffectStatements.legacy_backward
    (evaluated : EffectStatements (functions.map RuntimeSourceFunction.toEffect) response context
      result before state raws after outcome events) (pure : context = .pure oldContext) :
    ∃ oldOutcome oldEvents,
      LegacyEffectStatementsEvaluation functions oldContext.members oldContext.module oldContext.path
        oldContext.formals result before state.locals raws after oldOutcome oldEvents ∧
      outcome = legacyEffectBody state.shared oldOutcome ∧
      events = oldEvents.map RuntimeSourceEvent.toEffect :=
  evaluated.pure_induction (legacyEffectAlgebra functions) oldContext pure

end Aurora.SourceBinding
