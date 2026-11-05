import SourceBinding.RuntimeStatementCode
import SourceBinding.RuntimeStatementEvaluation
namespace Aurora.SourceBinding

theorem RuntimeNoFallthrough.effect_not_continued
    (terminal : RuntimeNoFallthrough statements)
    (evaluated : EffectStatements functions response context result before initial statements after
      (.continued final) events) : False := by
  induction terminal generalizing before initial after final events with
  | returned => cases evaluated with
    | next first rest => cases first
  | later tail ih => cases evaluated with
    | next first rest => exact ih rest

/-- Structural terminal coverage excludes only normal fallthrough. It does not
    exclude source faults, require a chosen return value, or describe native
    execution outside the checked body. -/
theorem RuntimeNoFallthrough.not_continued (terminal : RuntimeNoFallthrough statements) :
    ¬ RuntimeStatementsEvaluate functions members module path formals result
      before initial statements after (.continued final) events := by
  intro evaluated
  exact terminal.effect_not_continued
    (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])

theorem RuntimeNoFallthrough.outcome {outcome : RuntimeBodyOutcome}
    (terminal : RuntimeNoFallthrough statements)
    (evaluated : RuntimeStatementsEvaluate functions members module path formals result
      before initial statements after outcome events) :
    ∀ final, outcome ≠ .continued final := by
  intro final equal
  subst outcome
  exact terminal.not_continued evaluated

end Aurora.SourceBinding
