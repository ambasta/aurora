import SourceBinding.RuntimePureConstructors
import SourceBinding.PureEffectInduction
import SourceBinding.EffectPureEmbeddingFacts
namespace Aurora.SourceBinding

private def pureShared : SourceShared PUnit := ⟨fun _ => none, PUnit.unit⟩

variable {functions : List RuntimeSourceFunction}
  {Expression : RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value → List RuntimeSourceEvent → Prop}
  {Arguments : RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType → Outcome (List Value) → List RuntimeSourceEvent → Prop}
  {Statement : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop}
  {Statements : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop}

/-- Eliminate the uniform pure specialization using proved constructor closure.
    This is a proposition algebra, not another source evaluation relation. -/
theorem PureRuntimeEvaluation.induct
    (evaluated : PureRuntimeEvaluation functions context state raw kind outcome events)
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements) :
    Expression context state raw kind outcome events := by
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) pureShared
  rcases actual.pure_induction algebra context rfl with
    ⟨oldOutcome,oldEvents,property,same,_,trace⟩
  have outcomes := sourceLift_injective same
  have traces := RuntimeSourceEvent.map_toEffect_injective trace
  cases outcomes
  cases traces
  exact property

/-- Eliminate the uniform pure specialization using proved constructor closure.
    This is a proposition algebra, not another source evaluation relation. -/
theorem PureRuntimeArgumentEvaluation.induct
    (evaluated : PureRuntimeArgumentEvaluation functions context state raws kinds outcome events)
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements) :
    Arguments context state raws kinds outcome events := by
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) pureShared
  rcases actual.pure_induction algebra context rfl with
    ⟨oldOutcome,oldEvents,property,same,_,trace⟩
  have outcomes := legacyEffectArguments_injective same
  have traces := RuntimeSourceEvent.map_toEffect_injective trace
  cases outcomes
  cases traces
  exact property

/-- Eliminate the uniform pure specialization using proved constructor closure.
    This is a proposition algebra, not another source evaluation relation. -/
theorem PureRuntimeStatementEvaluation.induct
    (evaluated : PureRuntimeStatementEvaluation functions members module path formals result before state raw after outcome events)
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements) :
    Statement members module path formals result before state raw after outcome events := by
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) pureShared []
  rcases actual.pure_induction algebra ⟨members,module,path,formals,[]⟩ rfl with
    ⟨oldOutcome,oldEvents,property,same,trace⟩
  have outcomes := legacyEffectBody_injective pureShared same
  have traces := RuntimeSourceEvent.map_toEffect_injective trace
  cases outcomes
  cases traces
  exact property

/-- Eliminate the uniform pure specialization using proved constructor closure.
    This is a proposition algebra, not another source evaluation relation. -/
theorem PureRuntimeStatementsEvaluation.induct
    (evaluated : PureRuntimeStatementsEvaluation functions members module path formals result before state raws after outcome events)
    (algebra : PureEffectAlgebra functions Expression Arguments Statement Statements) :
    Statements members module path formals result before state raws after outcome events := by
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) pureShared []
  rcases actual.pure_induction algebra ⟨members,module,path,formals,[]⟩ rfl with
    ⟨oldOutcome,oldEvents,property,same,trace⟩
  have outcomes := legacyEffectBody_injective pureShared same
  have traces := RuntimeSourceEvent.map_toEffect_injective trace
  cases outcomes
  cases traces
  exact property

end Aurora.SourceBinding
