import SourceBinding.CallFootprint
open Aurora.SourceBinding
namespace CallFootprintFixtures
-- Synthetic AST controls; actual parsed-source receipt is kept separately.
def read : GuardExpr .word := .field .word "field".toUTF8 7
def guard : GuardExpr .boolean := .compare .eq read (.wordLit 3)
def body : EffectBody := .seq (.assign .word 9 (.wordLit 4))
  (.seq (.require (.boolLit false)) (.assign .word 7 (.wordLit 8)))
def state : SourceState := ⟨fun _ => some (.word 3),fun _ => none⟩

example : 7 ∈ guardReads guard := by decide
example : 7 ∈ bodyWrites body := by decide
example : 9 ∈ bodyWrites body := by decide
example : (evalBody body state).stores = [⟨9,.word 4⟩] := by decide
example (left right : SourceState) (parameters : left.parameters = right.parameters)
    (field : left.fields 7 = right.fields 7) : evalGuard left guard = evalGuard right guard := by
  apply evalGuard_read_congr guard left right parameters
  intro index member
  have same : index = 7 := by simpa [guard,read,guardReads] using member
  exact same ▸ field

#eval do
  let checks : List (String × Bool) := [
    ("both short circuit arms counted",guardReads (.or (.boolLit true) guard) == [7]),
    ("unreachable write still counted",bodyWrites body == [9,7]),
    ("fault keeps earlier store only",(evalBody body state).stores == ([⟨9,.word 4⟩] : List StoreEvent)),
    ("disjoint field unchanged",applyStores state.fields (evalBody body state).stores 7 == state.fields 7),
    ("written field changes",applyStores state.fields (evalBody body state).stores 9 == (some (.word 4) : Option Value)),
    ("guard trap congruence",evalGuard ⟨fun _ => none,state.parameters⟩ guard == (Outcome.trap Fault.type : Outcome Value))]
  for (label,passed) in checks do
    unless passed do throw (IO.userError label)
  IO.println s!"call footprint controls: {checks.length} passed"
end CallFootprintFixtures
