import SourceBinding.FreeSelection
import SourceBinding.IRIdentity
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Restricted root-entry/linkage convention, not compiler resolver fidelity. -/
def freeSymbol (root module path : Name) (name : ByteArray) : ByteArray :=
  if module = root ∧ path = [] then name else
    "__au_f_m".toUTF8 ++ namePrefix module ++ "_n".toUTF8 ++ namePrefix path ++
      "_d".toUTF8 ++ lengthName name

/-- Scalar free callable: no fabricated receiver and no inherited class-only slice certificate. -/
def FreeFunctionShape (t : Tables) (id : Int) : Prop :=
  let c := atRow t.callables id
  Index id t.callables.size ∧ nameBytes t c 6 = ByteArray.empty ∧
  c.integer 8 = 0 ∧ c.integer 9 = 0 ∧ c.integer 10 = 0 ∧ c.integer 11 = 0 ∧ c.integer 12 = 0 ∧
  (∀ typ ∈ signature t c, ScalarType t typ) ∧
  c.integer 15 = c.integer 5 - 1 ∧
  (∀ entry ∈ (frameSlots t c).toList.zipIdx, SignatureSlot t c entry) ∧
  (Aurora.Publication.group t.bodies id).size = 1 ∧ (atRow (Aurora.Publication.group t.bodies id) 0).integer 2 = 0 ∧
  0 < (functionCode t id).size ∧ (functionCode t id).size ≤ 4096
instance (t : Tables) (id : Int) : Decidable (FreeFunctionShape t id) := by
  unfold FreeFunctionShape; infer_instance

def FreeIdentity (t : Tables) (id : Int) (root module path : Name) (name : ByteArray)
    (function : Function) : Prop :=
  let c := atRow t.callables id
  module ≠ [] ∧ function.name = name ∧ function.mode = .ordinary ∧
  nameBytes t c 1 = freeSymbol root module path name ∧
  (namedCallables t (freeSymbol root module path name)).size = 1 ∧
  (c.integer 3 = 0 ↔ module = root) ∧
  c.integer 5 = Int.ofNat (function.formals.length + 1) ∧
  TypeIdentity t function.result (c.integer 4) ∧
  (∀ entry ∈ function.formals.zipIdx,
    TypeIdentity t entry.1.type (c.integer 4 + Int.ofNat entry.2 + 1)) ∧
  FreeFunctionShape t id
instance (t : Tables) (id : Int) (root module path : Name) (name : ByteArray) (function : Function) :
    Decidable (FreeIdentity t id root module path name function) := by
  unfold FreeIdentity; infer_instance

structure IdentifiedFree (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) where
  selected : CheckedFreeSelection files root module path name
  id : Int
  identity : FreeIdentity t id root module path name selected.function.function

def identifyFree (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) :
    Option (IdentifiedFree t files root module path name) := do
  let selected ← checkFreeSelection files root module path name
  let id := ((namedCallables t (freeSymbol root module path name))[0]?.getD (⟨"",[],false⟩ : Record)).integer 0
  if identity : FreeIdentity t id root module path name selected.function.function then
    return ⟨selected,id,identity⟩
  else none

end Aurora.SourceBinding
