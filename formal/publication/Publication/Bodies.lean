import Publication.Structure
namespace Aurora.Publication

structure OpenBody where
  id : Int
  count : Nat
  position : Nat
  deriving DecidableEq
structure BodyState where
  active : Option OpenBody := none
  completed : Nat := 0
  done : Bool := false
  deriving DecidableEq

/-- Declarative retained-body framing, including every published code position.
    This does not assign execution semantics to opaque instruction forms. -/
inductive BodyStep (callables : Nat) : BodyState → Record → BodyState → Prop
  | open : state.done = false → state.active = none → row.tag = "ir-body" →
      Index (row.integer 0) callables → 0 < row.integer 1 → row.integer 1 ≤ 65536 →
      0 ≤ row.integer 2 → row.integer 2 ≤ row.integer 1 →
      BodyStep callables state row { state with active := some ⟨row.integer 0, (row.integer 1).toNat, 0⟩ }
  | code : state.done = false → state.active = some body → row.tag = "ir-code" →
      row.integer 0 = body.id → row.integer 1 = Int.ofNat body.position →
      body.position < body.count → BodyStep callables state row
        { state with active := some { body with position := body.position + 1 } }
  | close : state.done = false → state.active = some body → row.tag = "ir-end-body" →
      row.integer 0 = body.id → row.integer 1 = Int.ofNat body.count →
      body.position = body.count → BodyStep callables state row
        { state with active := none, completed := state.completed + 1 }
  | finish : state.done = false → state.active = none → row.tag = "ir-end" →
      row.integer 0 = Int.ofNat state.completed →
      BodyStep callables state row { state with done := true }

structure BodyNext (callables : Nat) (state : BodyState) (row : Record) where
  next : BodyState
  grammar : BodyStep callables state row next

def bodyStep (callables : Nat) (state : BodyState) (row : Record) :
    Option (BodyNext callables state row) :=
  if live : state.done = false then
    match active : state.active with
    | none =>
      if opening : row.tag = "ir-body" then
        if id : Index (row.integer 0) callables then
          if positive : 0 < row.integer 1 then
            if bounded : row.integer 1 ≤ 65536 then
              if marker : 0 ≤ row.integer 2 ∧ row.integer 2 ≤ row.integer 1 then
                some ⟨_, .open live active opening id positive bounded marker.1 marker.2⟩
              else none
            else none
          else none
        else none
      else if ending : row.tag = "ir-end" then
        if count : row.integer 0 = Int.ofNat state.completed then
          some ⟨_, .finish live active ending count⟩
        else none
      else none
    | some body =>
      if code : row.tag = "ir-code" then
        if id : row.integer 0 = body.id then
          if pos : row.integer 1 = Int.ofNat body.position then
            if bound : body.position < body.count then
              some ⟨_, .code live active code id pos bound⟩
            else none
          else none
        else none
      else if closing : row.tag = "ir-end-body" then
        if id : row.integer 0 = body.id then
          if count : row.integer 1 = Int.ofNat body.count then
            if finished : body.position = body.count then
              some ⟨_, .close live active closing id count finished⟩
            else none
          else none
        else none
      else none
  else none

inductive BodyTrace (callables : Nat) : BodyState → List Record → BodyState → Prop
  | nil : BodyTrace callables state [] state
  | cons : BodyStep callables state row next → BodyTrace callables next remaining finish →
      BodyTrace callables state (row :: remaining) finish

structure BodyResult (callables : Nat) (state : BodyState) (records : List Record) where
  finish : BodyState
  grammar : BodyTrace callables state records finish

def bodyTrace (callables : Nat) : (state : BodyState) → (records : List Record) →
    Option (BodyResult callables state records)
  | state, [] => some ⟨state, .nil⟩
  | state, row :: rest => do
    let next ← bodyStep callables state row
    let tail ← bodyTrace callables next.next rest
    return ⟨tail.finish, .cons next.grammar tail.grammar⟩

def bodyRecords (t : Tables) : List Record :=
  t.all.filter (fun r => !r.display && phase r.tag ≥ 12)

inductive BodiesComplete (t : Tables) : Prop
  | intro (finish : BodyState) : BodyTrace t.callables.size {} (bodyRecords t) finish →
      finish.done = true → finish.active = none → BodiesComplete t

structure CheckedStructure (t : Tables) : Prop where
  framing : envelope t
  counts : poolCounts t
  identities : poolIdentities t
  references : poolReferences t
  bodies : BodiesComplete t

/-- Proof-producing checks of independent finite predicates. -/
def checkStructure (t : Tables) : Option { _witness : Unit // CheckedStructure t } := do
  if framing : envelope t then
    if counts : poolCounts t then
      if identities : poolIdentities t then
        if references : poolReferences t then
          let body ← bodyTrace t.callables.size {} (bodyRecords t)
          if done : body.finish.done = true then
            if closed : body.finish.active = none then
              return ⟨(), ⟨framing, counts, identities, references,
                .intro body.finish body.grammar done closed⟩⟩
            else none
          else none
        else none
      else none
    else none
  else none

theorem structure_sound (t : Tables) (result : { _witness : Unit // CheckedStructure t })
    (_accepted : checkStructure t = some result) : CheckedStructure t := result.property

end Aurora.Publication

namespace Aurora.Publication
/-- This is the byte-backed endpoint. CheckedStructure by itself is only a
    predicate on tables; these tables are definitionally projected from the
    very records related to this input's complete byte framing. -/
structure CheckedArtifact (input : ByteArray) where
  document : ParsedDocument input
  structureProof : CheckedStructure (tables document.reversed.reverse)

def decodeArtifact (limits : Limits) (input : ByteArray) : Option (CheckedArtifact input) := do
  let document ← documentText limits input
  let checked ← checkStructure (tables document.reversed.reverse)
  return ⟨document, checked.property⟩

theorem artifact_sound (limits : Limits) (input : ByteArray) (result : CheckedArtifact input)
    (_accepted : decodeArtifact limits input = some result) :
    WireDocument input result.document.reversed ∧
      CheckedStructure (tables result.document.reversed.reverse) :=
  ⟨result.document.grammar, result.structureProof⟩
end Aurora.Publication
