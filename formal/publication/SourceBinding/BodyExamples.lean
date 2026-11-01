import SourceBinding.BodyBinding
namespace Aurora.SourceBinding
open Aurora.Publication

-- Workload-specific native controls, never checker logic or theorem premises.
private def namedIndex (decls : List Formal) (name : String) (kind : GuardType) : IO Nat := do
  match decls.zipIdx.filter (fun entry => entry.1.name == name.toUTF8) with
  | [(decl,index)] =>
    unless decl.type == guardSourceType kind do throw (IO.userError s!"body example scalar type: {name}")
    return index
  | _ => throw (IO.userError s!"body example missing/ambiguous declaration: {name}")

private def defaults (decls : List Formal) (index : Nat) : Option Value := do
  let decl ← decls[index]?
  if decl.type == guardSourceType .word then return .word 0
  else if decl.type == guardSourceType .boolean then return .boolean false
  else none

/-- Fixture fuel only: exhaustion is a failure, not a termination theorem. -/
private def runFuel (program : EffectProgram) : Nat → Machine → Option (List StoreEvent × EffectExecution)
  | 0, _ => none
  | fuel + 1, state =>
    let current := effectStep program state
    match current.execution with
    | .next next => do
      let (later,terminal) ← runFuel program fuel next
      return (current.stores ++ later,terminal)
    | terminal => some (current.stores,terminal)

private structure Scenario where
  name : String
  initialized : Bool := true
  poison : Bool := false
  operation : Nat := 0
  staged : Nat := 0
  slot : Nat := 2
  audit : Bool := false
  succeeds : Bool

/-- Evaluate the SAME selected source body and canonical complete IR body, then
    compare terminal values/faults, ALL declared receiver fields and ordered stores.
    Concrete success remains native evidence, not kernel admission of full bytes. -/
def runBodyExamples (checked : BodyBinding files root module path member bytes) : IO Unit := do
  let decls := fields checked.source.selected.selected.classDecl.members
  let formals := checked.source.selected.selected.method.function.formals
  let sourceMember := checked.source.selected.selected.method.function.name
  let enter := sourceMember == "enter".toUTF8
  unless enter || sourceMember == "leave".toUTF8 do throw (IO.userError "body examples support enter/leave only")
  let initialized ← namedIndex decls "initialized" .boolean
  let poison ← namedIndex decls "poison" .boolean
  let operation ← namedIndex decls "operation" .word
  let staged ← namedIndex decls "staged_count" .word
  let active ← namedIndex decls "active_slot" .word
  let slot ← if enter then namedIndex formals "slot" .word else pure 0
  let audit ← if enter then namedIndex formals "audit_only" .boolean else pure 0
  let cases : List Scenario := if enter then [
      { name := "ordinary enter", succeeds := true },
      { name := "audit enter", audit := true, succeeds := true },
      { name := "uninitialized refusal", initialized := false, succeeds := false },
      { name := "poison refusal", poison := true, succeeds := false },
      { name := "active operation refusal", operation := 1, succeeds := false },
      { name := "staged work refusal", staged := 1, succeeds := false },
      { name := "slot limit refusal", slot := 4, succeeds := false },
      { name := "maximum u64 slot refusal", slot := 18446744073709551615, succeeds := false }]
    else [
      { name := "leave success", operation := 1, succeeds := true },
      { name := "inactive leave refusal", operation := 0, succeeds := false },
      { name := "staged leave refusal", operation := 1, staged := 1, succeeds := false }]
  let program := canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id
  for scenario in cases do
    let receiver := fun index =>
      if index == initialized then some (.boolean scenario.initialized)
      else if index == poison then some (.boolean scenario.poison)
      else if index == operation then some (.word scenario.operation)
      else if index == staged then some (.word scenario.staged)
      else if index == active then some (.word 3)
      else defaults decls index
    let arguments := fun index =>
      if enter && index == slot then some (.word scenario.slot)
      else if enter && index == audit then some (.boolean scenario.audit)
      else defaults formals index
    let base : Machine := ⟨0,none,[],fun _ => none,receiver,arguments⟩
    let expected := evalBody checked.source.method.body (entrySource base checked.bindings.length)
    let some (events,actual) := runFuel program (checked.stop * 4 + 16) (preparedEntry base (parameterSlot checked.bindings) 0) |
      throw (IO.userError s!"body example exhausted: {scenario.name}")
    let terminalsMatch : Bool := match expected.execution,actual with
      | .returned a _,.returned b state => scenario.succeeds && a == .boolean true && a == b && state.stack.isEmpty
      | .trap .assertion _,.trap .assertion _ => !scenario.succeeds
      | _, _ => false
    unless terminalsMatch do throw (IO.userError s!"body terminal mismatch: {scenario.name}")
    let policyEvents : List StoreEvent := if !scenario.succeeds then [] else if enter then
      [⟨active,.word scenario.slot⟩,⟨operation,.word 1⟩] ++ (if scenario.audit then [⟨operation,.word 2⟩] else [])
      else [⟨operation,.word 0⟩,⟨active,.word 3⟩]
    unless events == expected.stores && events == policyEvents do
      throw (IO.userError s!"body ordered-store mismatch: {scenario.name}")
    for index in List.range decls.length do
      unless actual.state.receiver index == expected.execution.state.fields index do
        throw (IO.userError s!"body final receiver mismatch: {scenario.name}/{index}")
      if !scenario.succeeds || (index != operation && index != active) then
        unless actual.state.receiver index == receiver index do
          throw (IO.userError s!"body changed unrelated/refused field: {scenario.name}/{index}")
    IO.println s!"BODY-VALUE case={scenario.name} stores={events.length} terminal={(if scenario.succeeds then "return-true" else "assertion-failure")}"
  IO.println s!"NATIVE body examples: {cases.length} passed; actual typed source/canonical IR, ordered stores and final receiver compared"
end Aurora.SourceBinding
