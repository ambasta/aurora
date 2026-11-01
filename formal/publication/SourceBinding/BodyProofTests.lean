import SourceBinding.BodyBinding
open Aurora.SourceBinding
namespace BodyProofFixtures

def empty : SourceState := ⟨fun _ => some (.word 0),fun _ => none⟩
def writeThenFail : EffectBody := .seq (.assign .word 0 (.wordLit 7))
  (.seq (.require (.compare .eq (.field .word "x".toUTF8 0) (.wordLit 7)))
    (.seq (.require (.boolLit false)) (.returnValue .boolean (.boolLit true))))
example : (evalBody writeThenFail empty).stores = [⟨0,.word 7⟩] := by rfl
example : (evalBody writeThenFail empty).execution.state.fields 0 = some (.word 7) := by rfl
example : (evalBody writeThenFail empty).execution =
    .trap .assertion ⟨fun index => if index = 0 then some (.word 7) else empty.fields index,empty.parameters⟩ := by rfl

private def runFuel (program : EffectProgram) : Nat → Machine → Option EffectStep
  | 0, _ => none
  | fuel + 1, state => do
    let first := effectStep program state
    match first.execution with
    | .next next =>
      let later ← runFuel program fuel next
      return ⟨later.execution,first.stores ++ later.stores⟩
    | _ => return first

private def parsed (body : String) : Option EffectBody := do
  let input := ("module r; class C { u64 x; u64 y; auto f() -> bool { " ++ body ++ " } };").toUTF8
  let file ← namedSource input
  let selected ← selectBody [⟨input,file⟩] ["r".toUTF8] ["r".toUTF8] ["C".toUTF8] "f".toUTF8
  return selected.method.body

def operations : List EffectOp := [
  .pure (.constant .word (.word 7)),.store .word 0,
  .pure (.receiver .word 0),.pure .push,.pure (.constant .word (.word 7)),.pure (.binary (.compare .eq)),.require,
  .pure (.constant .boolean (.boolean false)),.require,
  .pure (.constant .boolean (.boolean true)),.pure .ret]

#eval do
  let some body := parsed "x = 7u64; builtin::require(x == 7u64); builtin::require(false); return true;"
    | throw (IO.userError "stateful source fixture failed")
  let program : EffectProgram := fun pc => operations[pc]?
  let some checked := checkBodyCode program id body 0 | throw (IO.userError "body correspondence failed")
  unless checked.stop == operations.length do throw (IO.userError "incomplete body accepted")
  let source := evalBody body empty
  let base : Machine := ⟨0,none,[],fun _ => none,empty.fields,empty.parameters⟩
  let some actual := runFuel program 32 base | throw (IO.userError "fixture failed to terminate")
  match source.execution,actual.execution with
  | .trap .assertion current,.trap .assertion machine =>
    unless current.fields 0 == some (Value.word 7) && machine.receiver 0 == some (Value.word 7) &&
      source.stores == ([⟨0,Value.word 7⟩] : List StoreEvent) && actual.stores == source.stores do
      throw (IO.userError "write or ordered trace rolled back")
    unless machine.pc == 8 do throw (IO.userError "later read ignored current store or wrong assertion failed")
  | _,_ => throw (IO.userError "required assertion failure missing")
  let some before := parsed "x = 1u64; y = 2u64; return true;" | throw (IO.userError "ordered source failed")
  let some after := parsed "y = 2u64; x = 1u64; return true;" | throw (IO.userError "reordered source failed")
  let a := evalBody before empty
  let b := evalBody after empty
  unless a.execution.state.fields 0 == b.execution.state.fields 0 &&
    a.execution.state.fields 1 == b.execution.state.fields 1 && a.stores != b.stores do
    throw (IO.userError "store order was erased by final-state equality")
  IO.println "NATIVE body execution fixtures: current read, retained failure, exact stop, and ordered traces passed"
end BodyProofFixtures
