import SourceBinding.RuntimeReturnBinding
namespace Aurora.SourceBinding

/-- A return expression in the SAME parsed statement tree. Traversing a prior
    statement advances the exact lexical slot/scope cursor, even when execution
    would skip that statement. This relation is NOT dynamic reachability. -/
inductive ScopedReturnAt (members : List Declaration) (module path : Name)
    (formals : List Formal) : LocalContext → List SourceStatement → LocalContext → SourceExpr → Prop
  | here : ScopedReturnAt members module path formals before (.returnValue raw :: rest) before raw
  | later : ScopedStatement members module path formals before first middle declaredItems →
      ScopedReturnAt members module path formals middle rest selected raw →
      ScopedReturnAt members module path formals before (first :: rest) selected raw
  | branch : ScopedReturnAt members module path formals (enterLocalScope before) body selected raw →
      ScopedReturnAt members module path formals before (.ifThen condition body :: rest) selected raw

structure SelectedScopedReturn (members : List Declaration) (module path : Name)
    (formals : List Formal) (before : LocalContext) (statements : List SourceStatement) where
  context : LocalContext
  raw : SourceExpr
  source : ScopedReturnAt members module path formals before statements context raw

/-- Each path component is a zero-based statement index; intermediate components
    select an if-body, and the final component must select a return. Nothing is
    extracted by searching source text or scanning a detached body substring. -/
def selectScopedReturn (members : List Declaration) (module path : Name) (formals : List Formal) :
    (fuel : Nat) → (before : LocalContext) → (statements : List SourceStatement) → List Nat →
    Option (SelectedScopedReturn members module path formals before statements)
  | 0, _, _, _ => none
  | _ + 1, before, .returnValue raw :: _, [0] => some ⟨before,raw,.here⟩
  | fuel + 1, before, .ifThen _ body :: _, 0 :: indices => do
    let nested ← selectScopedReturn members module path formals fuel (enterLocalScope before) body indices
    return ⟨nested.context,nested.raw,.branch nested.source⟩
  | fuel + 1, before, first :: rest, (index + 1) :: indices => do
    let head ← scopeStatement members module path formals 4096 before first
    let tail ← selectScopedReturn members module path formals fuel head.after rest (index :: indices)
    return ⟨tail.context,tail.raw,.later head.grammar tail.source⟩
  | _, _, _, _ => none

structure RuntimeReturnOccurrence (identified : IdentifiedRuntimeFree t files root module path name) where
  selected : SelectedScopedReturn identified.selected.scope.members module path
    identified.selected.function.function.formals
    ⟨[],0,1,identified.selected.function.function.formals.length⟩
    identified.details.lexical.parsed.statements
  valid : RuntimeContextValid ⟨identified.selected.scope.members,module,path,
    identified.selected.function.function.formals,selected.context.visible⟩

def RuntimeReturnOccurrence.context {identified : IdentifiedRuntimeFree t files root module path name} (occurrence : RuntimeReturnOccurrence identified) : RuntimeExprContext :=
  ⟨identified.selected.scope.members,module,path,identified.selected.function.function.formals,
    occurrence.selected.context.visible⟩

def checkRuntimeReturnOccurrence (identified : IdentifiedRuntimeFree t files root module path name)
    (indices : List Nat) : Option (RuntimeReturnOccurrence identified) := do
  let selected ← selectScopedReturn identified.selected.scope.members module path
    identified.selected.function.function.formals 4096
    ⟨[],0,1,identified.selected.function.function.formals.length⟩
    identified.details.lexical.parsed.statements indices
  let valid ← checkRuntimeContext ⟨identified.selected.scope.members,module,path,
    identified.selected.function.function.formals,selected.context.visible⟩
  return ⟨selected,valid.property⟩

/-- Complete byte-backed syntax and exact scoped membership are retained. The
    selected return need not be executed, and no IR placement is asserted here. -/
theorem RuntimeReturnOccurrence.source_bound
    {identified : IdentifiedRuntimeFree t files root module path name}
    (occurrence : RuntimeReturnOccurrence identified) :
    GraphReady files root ∧
    StatementsSyntax identified.selected.file.file.bytes false identified.selected.function.function.body.tokens
      identified.details.lexical.parsed.statements [] ∧
    ScopedReturnAt identified.selected.scope.members module path identified.selected.function.function.formals
      ⟨[],0,1,identified.selected.function.function.formals.length⟩
      identified.details.lexical.parsed.statements occurrence.selected.context occurrence.selected.raw :=
  ⟨identified.selected.graph,identified.details.lexical.parsed.grammar,occurrence.selected.source⟩

end Aurora.SourceBinding
