import SourceBinding.RuntimeBodyBinding
namespace Aurora.SourceBinding

theorem RuntimeStatementCode.initial_context
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementCode program caller leaves members formals result before raw after declaredItems start stop) :
    RuntimeContextValid (runtimeStatementContext members module path formals before) := by
  cases code <;> assumption

theorem RuntimeStatementsCode.initial_context
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementsCode program caller leaves members formals result before raw after declaredItems start stop)
    (terminal : RuntimeNoFallthrough raw) :
    RuntimeContextValid (runtimeStatementContext members module path formals before) := by
  cases terminal with
  | returned => cases code with
    | cons head tail => exact head.initial_context
  | later rest => cases code with
    | cons head tail => exact head.initial_context

/-- The public complete-body endpoint derives its initial context validity from
    the actual checked first statement, not from a supplied namespace/local map.
    Structural terminal coverage excludes the empty-body case. -/
theorem RuntimeBodyCertificate.initial_context
    {identified : IdentifiedRuntimeFree t files root module path name}
    (checked : RuntimeBodyCertificate identified) :
    RuntimeContextValid (runtimeStatementContext identified.selected.scope.members module path
      identified.selected.function.function.formals
      ⟨[],0,1,identified.selected.function.function.formals.length⟩) :=
  checked.code.initial_context checked.noFallthrough

end Aurora.SourceBinding
