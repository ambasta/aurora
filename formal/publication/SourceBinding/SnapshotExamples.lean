import SourceBinding.SemanticBinding
namespace Aurora.SourceBinding
open Aurora.Publication

-- Workload-specific VALUE fixtures only. These names and values are not checker
-- logic, theorem premises, golden ASTs, or evidence of concrete kernel admission.
private def exampleWordIndex (decls : List Formal) (name : String) : IO Nat := do
  match decls.zipIdx.filter (fun entry => entry.1.name == name.toUTF8) with
  | [(decl,index)] =>
    unless decl.type == guardSourceType .word do
      throw (IO.userError s!"snapshot example requires u64: {name}")
    return index
  | _ => throw (IO.userError s!"snapshot example name missing/ambiguous: {name}")

private def exampleDefaults (decls : List Formal) (index : Nat) : Option Value := do
  let decl ← decls[index]?
  if decl.type == guardSourceType .word then return .word 0
  else if decl.type == guardSourceType .boolean then return .boolean false
  else none -- Resource/non-scalar fields have no invented scalar value.

/-- Executes the selected actual-source guard and actual canonical IR prefix on
    concrete bounded inputs. Success is a native value-control receipt, not a
    kernel proof for the full bytes or a claim about enter/fill/leave effects. -/
def runSnapshotExamples (checked : SafeSemanticBinding files root module path member bytes) : IO Unit := do
  let semantic := checked.semantic
  let members := semantic.source.selected.selected.classDecl.members
  let declarations := fields members
  let formals := semantic.source.selected.selected.method.function.formals
  let phase ← exampleWordIndex declarations "snapshot_phase"
  let epochField ← exampleWordIndex declarations "snapshot_epoch"
  let byteField ← exampleWordIndex declarations "snapshot_bytes"
  let epochArg ← exampleWordIndex formals "epoch"
  let offsetArg ← exampleWordIndex formals "offset"
  let countArg ← exampleWordIndex formals "count"
  let program := canonicalProgram (tables semantic.ir.publication.artifact.document.reversed.reverse) semantic.ir.id
  let cut := semantic.endExpr + 4
  let cases : List (String × Nat × Nat × Nat × Nat × Bool) := [
    ("admission",1,7,0,1,false),
    ("phase refusal",2,7,0,1,true),
    ("epoch refusal",1,8,0,1,true),
    ("zero count refusal",1,7,0,0,true),
    ("offset beyond bytes skips underflow",1,7,65,1,true),
    ("count beyond bytes refusal",1,7,0,65,true),
    ("end offset with nonzero count refusal",1,7,64,1,true)]
  for (label,phaseValue,epochValue,offsetValue,countValue,reject) in cases do
    let receiver := fun index =>
      if index == phase then some (.word phaseValue)
      else if index == epochField then some (.word 7)
      else if index == byteField then some (.word 64)
      else exampleDefaults declarations index
    let arguments := fun index =>
      if index == epochArg then some (.word epochValue)
      else if index == offsetArg then some (.word offsetValue)
      else if index == countArg then some (.word countValue)
      else exampleDefaults formals index
    let base : Machine := ⟨0,none,[],fun _ => none,receiver,arguments⟩
    let source := entrySource base semantic.bindings.length
    unless evalGuard source semantic.source.method.guard == .value (.boolean reject) do
      throw (IO.userError s!"snapshot source value mismatch: {label}")
    let initial := preparedEntry base (parameterSlot semantic.bindings) 0
    let actual := firstExitFuel program cut (cut + 16) initial
    let matched : Bool := match actual with
      | some (.next final) => !reject && final.pc == cut && final.accumulator == some (.boolean false) && final.stack.isEmpty
      | some (.returned (.boolean false)) => reject
      | _ => false
    unless matched do throw (IO.userError s!"snapshot IR first-exit mismatch/trap/exhaustion: {label}")
  IO.println s!"NATIVE snapshot value examples: {cases.length} passed; actual selected guard/prefix, no tail effects claim"
end Aurora.SourceBinding
