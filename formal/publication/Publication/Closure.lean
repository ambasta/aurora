import Publication.Typing
namespace Aurora.Publication

def callees (t : Tables) (id : Int) : List Int :=
  ((functionCode t id).toList.filter (fun code => code.integer 6 == 38)).map
    (fun code => (callee t code).integer 0)

/-- Candidate discovery only: the result is independently checked below.
    Visit/count exhaustion rejects; recursion in a call graph is not unfolded. -/
def discover (t : Tables) : (fuel : Nat) → List Int → List Int → Option (List Int)
  | 0, _, _ => none
  | _ + 1, [], selected => some selected
  | fuel + 1, id :: pending, selected =>
    if id ∈ selected then discover t fuel pending selected
    else if selected.length < 128 then discover t fuel (callees t id ++ pending) (id :: selected)
    else none

def RootsBound (t : Tables) (roots : List ByteArray) (selected : List Int) : Prop :=
  roots ≠ [] ∧ ∀ name ∈ roots,
    (namedCallables t name).size = 1 ∧
    ((namedCallables t name)[0]?.getD (⟨"", [], false⟩ : Record)).integer 0 ∈ selected
instance (t : Tables) (roots : List ByteArray) (selected : List Int) :
    Decidable (RootsBound t roots selected) := by unfold RootsBound; infer_instance

def CallsClosed (t : Tables) (selected : List Int) : Prop :=
  ∀ id ∈ selected, ∀ code ∈ (functionCode t id).toList,
    code.integer 6 = 38 → (callee t code).integer 0 ∈ selected
instance (t : Tables) (selected : List Int) : Decidable (CallsClosed t selected) := by
  unfold CallsClosed; infer_instance

inductive AllFunctions (t : Tables) : List Int → Prop
  | nil : AllFunctions t []
  | cons : FunctionTyped t fid → AllFunctions t rest → AllFunctions t (fid :: rest)

def allFunctions (t : Tables) : (selected : List Int) → Option { _witness : Unit // AllFunctions t selected }
  | [] => some ⟨(), .nil⟩
  | id :: rest => do
    let head ← checkFunction t id
    let tail ← allFunctions t rest
    return ⟨(), .cons head.property tail.property⟩

/-- Every listed external occurrence comes from a complete selected body.
    Its supplied catalogue contract is structural only, never an effect promise. -/
structure ExternalOccurrence where
  caller : Int
  position : Int
  resource : Int
  method : Int

def externalOccurrences (t : Tables) (selected : List Int) : List ExternalOccurrence :=
  selected.flatMap fun id =>
    ((functionCode t id).toList.filter (fun r => r.integer 6 == 89)).map fun r =>
      ⟨id, r.integer 1, operandValue t r 4, operandValue t r 2⟩

structure ClosedSlice (t : Tables) (roots : List ByteArray) where
  selected : List Int
  unique : selected.Nodup
  rootsBound : RootsBound t roots selected
  functions : AllFunctions t selected
  callsClosed : CallsClosed t selected

def selectSlice (t : Tables) (roots : List ByteArray) : Option (ClosedSlice t roots) := do
  let rootIds := roots.map fun name => ((namedCallables t name)[0]?.getD (⟨"", [], false⟩ : Record)).integer 0
  let selected ← discover t 65536 rootIds []
  if unique : selected.Nodup then
    if rootsBound : RootsBound t roots selected then
      let functions ← allFunctions t selected
      if callsClosed : CallsClosed t selected then
        return ⟨selected, unique, rootsBound, functions.property, callsClosed⟩
      else none
    else none
  else none

structure CheckedSlice (input : ByteArray) (roots : List ByteArray) where
  artifact : CheckedArtifact input
  slice : ClosedSlice (tables artifact.document.reversed.reverse) roots

def decodeSlice (limits : Limits) (input : ByteArray) (roots : List ByteArray) :
    Option (CheckedSlice input roots) := do
  let artifact ← decodeArtifact limits input
  let slice ← selectSlice (tables artifact.document.reversed.reverse) roots
  return ⟨artifact, slice⟩

theorem AllFunctions.member {t : Tables} {selected : List Int} (functions : AllFunctions t selected)
    {id : Int} (member : id ∈ selected) : FunctionTyped t id := by
  induction functions with
  | nil => simp at member
  | cons head tail ih =>
    rcases List.mem_cons.mp member with equal | later
    · simpa [equal] using head
    · exact ih later

theorem slice_sound (limits : Limits) (input : ByteArray) (roots : List ByteArray)
    (result : CheckedSlice input roots) (_accepted : decodeSlice limits input roots = some result) :
    WireDocument input result.artifact.document.reversed ∧
    CheckedStructure (tables result.artifact.document.reversed.reverse) ∧
    RootsBound (tables result.artifact.document.reversed.reverse) roots result.slice.selected ∧
    CallsClosed (tables result.artifact.document.reversed.reverse) result.slice.selected ∧
    (∀ id ∈ result.slice.selected, FunctionTyped (tables result.artifact.document.reversed.reverse) id) :=
  ⟨result.artifact.document.grammar, result.artifact.structureProof, result.slice.rootsBound,
    result.slice.callsClosed, fun _ member => result.slice.functions.member member⟩

end Aurora.Publication
