import SourceBinding.RuntimeStatementCode
import SourceBinding.RuntimeStatementEvaluation
namespace Aurora.SourceBinding

/-- Structural terminal coverage excludes only normal fallthrough. It does not
    exclude source faults, require a chosen return value, or describe native
    execution outside the checked body. -/
theorem RuntimeNoFallthrough.not_continued (terminal : RuntimeNoFallthrough statements) :
    ¬ RuntimeStatementsEvaluate functions members module path formals result
      before initial statements after (.continued final) events := by
  induction terminal generalizing before initial after final events with
  | returned =>
    intro evaluated
    cases evaluated with
    | next first rest => cases first
  | later tail ih =>
    intro evaluated
    cases evaluated with
    | next first rest => exact ih rest

theorem RuntimeNoFallthrough.outcome {outcome : RuntimeBodyOutcome}
    (terminal : RuntimeNoFallthrough statements)
    (evaluated : RuntimeStatementsEvaluate functions members module path formals result
      before initial statements after outcome events) :
    ∀ final, outcome ≠ .continued final := by
  intro final equal
  subst outcome
  exact terminal.not_continued evaluated

end Aurora.SourceBinding
