import SourceBinding.RuntimeBodyControl
namespace Aurora.SourceBinding

theorem RuntimeStatementCode.scope_proof
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementCode program caller leaves members formals result before raw after declaredItems start stop) :
    ScopedStatement members module path formals before raw after declaredItems := by
  cases code <;> assumption

theorem RuntimeStatementsCode.scope_proof
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementsCode program caller leaves members formals result before raw after declaredItems start stop) :
    ScopedStatements members module path formals before raw after declaredItems := by
  induction raw generalizing before after declaredItems start stop with
  | nil => cases code; exact .nil
  | cons first rest ih =>
    cases code with
    | cons head tail => exact .cons head.scope_proof (ih tail)

/-- Scope bookkeeping can change the source continuation's metadata, but only
    equality of its actual values permits retaining the same machine run. -/
theorem RuntimeBodyRun.continued_values
    (run : RuntimeBodyRun program external caller saved world base source start stop accumulator (.continued next) events)
    (same : other.values = next.values) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.continued other) events := by
  obtain ⟨final,actual,value,equal⟩ := run
  refine ⟨final,actual,value,?_⟩
  simpa only [runtimeBodyFrame,same] using equal

end Aurora.SourceBinding
