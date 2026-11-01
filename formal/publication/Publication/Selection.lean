import Publication.Bodies
namespace Aurora.Publication

inductive Scalar where
  | boolean | word
  deriving BEq, DecidableEq, Repr

def scalarKind (t : Tables) (id : Int) : Option Scalar :=
  let row := atRow t.types id
  if row.integer 1 == 1 then some .boolean
  else if row.integer 1 == 7 then some .word else none

def PlainTail (row : Record) : Prop :=
  row.integer 4 = 0 ∧ row.integer 5 = 0 ∧ row.integer 6 = 0 ∧ row.integer 7 = 0 ∧ row.integer 8 = 0
instance (row : Record) : Decidable (PlainTail row) := by unfold PlainTail; infer_instance

def ScalarType (t : Tables) (id : Int) : Prop :=
  Index id t.types.size ∧ PlainTail (atRow t.types id) ∧
  (atRow t.types id).integer 3 = 0 ∧
  ((atRow t.types id).integer 1 = 1 ∨ (atRow t.types id).integer 1 = 7)
instance (t : Tables) (id : Int) : Decidable (ScalarType t id) := by unfold ScalarType; infer_instance

def nameBytes (t : Tables) (row : Record) (first : Nat) : ByteArray :=
  t.names.extract (row.integer first).toNat ((row.integer first + row.integer (first + 1)).toNat)

def namedCallables (t : Tables) (name : ByteArray) : Array Record :=
  t.callables.filter (fun r => nameBytes t r 1 == name)

def namedClasses (t : Tables) (name : ByteArray) : Array Record :=
  t.classes.filter (fun r => nameBytes t r 1 == name)

def receiver (t : Tables) (callable : Record) : Record :=
  (namedClasses t (nameBytes t callable 6))[0]?.getD ⟨"", [], false⟩

def functionCode (t : Tables) (id : Int) : Array Record := group t.codes id

def functionFields (t : Tables) (id : Int) : Array Record :=
  group t.fields ((receiver t (atRow t.callables id)).integer 0)

def signature (_t : Tables) (callable : Record) : List Int :=
  (List.range (callable.integer 5).toNat).map (fun i => callable.integer 4 + Int.ofNat i)

def frameSlots (t : Tables) (callable : Record) : Array Record :=
  t.slots.extract (callable.integer 14).toNat (callable.integer 14 + callable.integer 15).toNat

-- Retained-resource descriptors use kind26 and catalogue native names. The
-- catalogue scalar/class/enum mapping is explicitly absent (-1) for these
-- resource identities; this branch does not infer a scalar from that absence.
def matchingResources (t : Tables) (typ : Record) : Array Record :=
  t.resources.filter (fun r => nameBytes t typ 2 == (atRow t.catalogs (r.integer 1)).blob 2)

def SelectedField (t : Tables) (classRow field : Record) : Prop :=
  let typ := atRow t.types (field.integer 2)
  field.integer 5 = 0 ∧ field.integer 6 = 1 ∧ PlainTail typ ∧
  ((ScalarType t (field.integer 2) ∧ field.integer 4 = 1 ∧
      Index (field.integer 3) (classRow.integer 7).toNat ∧
      ScalarType t (classRow.integer 4 + field.integer 3) ∧
      (atRow t.types (classRow.integer 4 + field.integer 3)).integer 1 = typ.integer 1 ∧
      field.integer 7 = (atRow (group t.leaves (classRow.integer 0)) (field.integer 3)).integer 2 ∧
      field.integer 7 % 8 = 0 ∧ field.integer 7 + 8 ≤ classRow.integer 8) ∨
    (typ.integer 1 = 26 ∧ 0 < typ.integer 3 ∧ field.integer 4 = 0 ∧
      (matchingResources t typ).size = 1 ∧
      (atRow t.catalogs ((atRow (matchingResources t typ) 0).integer 1)).integer 1 = -1))
instance (t : Tables) (classRow field : Record) : Decidable (SelectedField t classRow field) := by
  unfold SelectedField; infer_instance

def scalarFields (t : Tables) (id : Int) : Array Record :=
  (functionFields t id).filter (fun r => (atRow t.types (r.integer 2)).integer 1 != 26)

def SignatureSlot (t : Tables) (callable : Record) (entry : Record × Nat) : Prop :=
  entry.1.integer 1 = 10 ∧ entry.1.integer 2 = Int.ofNat (8 * (entry.2 + 1)) ∧
  ScalarType t (entry.1.integer 3) ∧
  scalarKind t (entry.1.integer 3) = scalarKind t (callable.integer 4 + Int.ofNat entry.2 + 1) ∧
  entry.1.integer 4 = 0 ∧ entry.1.integer 5 = 0 ∧
  entry.1.integer 2 ≤ callable.integer 13
instance (t : Tables) (callable : Record) (entry : Record × Nat) :
    Decidable (SignatureSlot t callable entry) := by unfold SignatureSlot; infer_instance

/-- Initial supported subset: scalar explicit parameters, one mutable receiver,
    no borrowed roots, constructors, nested aggregate fields or local slots.
    Resource extents are NOT represented here and are not certified. -/
def FunctionShape (t : Tables) (id : Int) : Prop :=
  let callable := atRow t.callables id
  let cls := receiver t callable
  let fs := functionFields t id
  let scalar := scalarFields t id
  Index id t.callables.size ∧
  (namedClasses t (nameBytes t callable 6)).size = 1 ∧
  (callable.integer 8 = 1 ∨ callable.integer 8 = 5) ∧
  callable.integer 9 = 0 ∧ callable.integer 10 = 0 ∧ callable.integer 11 = 1 ∧ callable.integer 12 = 0 ∧
  (∀ typ ∈ signature t callable, ScalarType t typ) ∧
  callable.integer 15 = callable.integer 5 - 1 ∧
  (∀ entry ∈ (frameSlots t callable).toList.zipIdx, SignatureSlot t callable entry) ∧
  cls.integer 3 = 7 ∧ cls.integer 5 = cls.integer 7 ∧
  AllRows fs (SelectedField t cls) ∧ Dense scalar 3 ∧ Int.ofNat scalar.size = cls.integer 7 ∧
  scalar.toList.Pairwise (fun a b => a.integer 7 + 8 ≤ b.integer 7) ∧
  (group t.bodies id).size = 1 ∧ (atRow (group t.bodies id) 0).integer 2 = 0 ∧
  0 < (functionCode t id).size ∧ (functionCode t id).size ≤ 4096
instance (t : Tables) (id : Int) : Decidable (FunctionShape t id) := by unfold FunctionShape; infer_instance

/-- Canonical operand payload from the full global pool, not pretty listing text. -/
def operand (t : Tables) (code : Record) (index : Nat) : Record :=
  atRow t.operands (code.integer 11 + Int.ofNat index)
def operandValue (t : Tables) (code : Record) (index : Nat) : Int :=
  (operand t code index).integer 2

def operandRoles (t : Tables) (code : Record) : List Int :=
  ((t.operands.extract (code.integer 11).toNat (code.integer 11 + code.integer 12).toNat).toList).map
    (fun r => r.integer 1)

def rolesFor : Int → Option (List Int)
  | 7 => some [2, 12]
  | 9 | 43 | 91 => some []
  | 11 | 12 | 14 => some [14]
  | 32 | 33 => some [23, 12]
  | 38 => some [100, 26, 21, 6, 27, 8]
  | 40 => some [29]
  | 41 | 42 => some [30]
  | 45 => some [1, 2, 12]
  | 89 => some [24, 23, 106, 6, 105]
  | _ => none

def callName (t : Tables) (code : Record) : ByteArray :=
  nameBytes t (operand t code 0) 4

def callee (t : Tables) (code : Record) : Record :=
  (namedCallables t (callName t code))[0]?.getD ⟨"", [], false⟩

def fieldOf (t : Tables) (id : Int) (field : Int) : Record :=
  atRow (functionFields t id) field

def resourceOf (t : Tables) (code : Record) : Record :=
  atRow t.resources (operandValue t code 4)
def methodOf (t : Tables) (code : Record) : Record :=
  atRow (group t.methods (operandValue t code 4)) (operandValue t code 2)

end Aurora.Publication
