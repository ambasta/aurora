import Publication.Selection
namespace Aurora.Publication

def OperandPayload (t : Tables) (row : Record) : Prop :=
  if row.integer 1 = 100 then
    row.integer 2 = 0 ∧ row.integer 3 = 0 ∧ nameRange t row 4
  else if row.integer 1 = 8 ∨ row.integer 1 = 21 then
    row.integer 2 = 0 ∧ row.integer 3 = 0 ∧ row.integer 5 = 0 ∧
      Range (row.integer 4) (row.integer 5) t.operands.size
  else if row.integer 1 = 11 then
    row.integer 2 = 0 ∧ row.integer 4 = 0 ∧ row.integer 5 = 0
  else row.integer 3 = 0 ∧ row.integer 4 = 0 ∧ row.integer 5 = 0
instance (t : Tables) (row : Record) : Decidable (OperandPayload t row) := by unfold OperandPayload; infer_instance

def operandsOf (t : Tables) (code : Record) : Array Record :=
  t.operands.extract (code.integer 11).toNat (code.integer 11 + code.integer 12).toNat

def Selectors (row : Record) : Prop :=
  row.integer 5 = 1 ∧ row.integer 10 = 0 ∧
  (if row.integer 6 = 11 then row.integer 7 = 1 ∧ row.integer 8 = 0 ∧ row.integer 9 = 0
   else if row.integer 6 = 12 then row.integer 7 = 0 ∧ row.integer 8 = 1 ∧ row.integer 9 = 0
   else if row.integer 6 = 14 then row.integer 7 = 0 ∧ row.integer 8 = 0 ∧ 0 ≤ row.integer 9 ∧ row.integer 9 ≤ 5
   else row.integer 7 = 0 ∧ row.integer 8 = 0 ∧ row.integer 9 = 0)
instance (row : Record) : Decidable (Selectors row) := by unfold Selectors; infer_instance

def MatchingSlot (t : Tables) (id offset typ : Int) : Prop :=
  ScalarType t typ ∧
  ∃ slot ∈ (frameSlots t (atRow t.callables id)).toList,
    slot.integer 2 = offset ∧ scalarKind t (slot.integer 3) = scalarKind t typ
instance (t : Tables) (id offset typ : Int) : Decidable (MatchingSlot t id offset typ) := by
  unfold MatchingSlot; infer_instance

def MethodBinding (t : Tables) (id : Int) (code : Record) : Prop :=
  (namedCallables t (callName t code)).size = 1 ∧
  operandValue t code 1 = 0 ∧ operandValue t code 3 = 0 ∧ operandValue t code 4 = -1 ∧
  nameBytes t (callee t code) 6 = nameBytes t (atRow t.callables id) 6 ∧
  (callee t code).integer 3 = (atRow t.callables id).integer 3
instance (t : Tables) (id : Int) (code : Record) : Decidable (MethodBinding t id code) := by
  unfold MethodBinding; infer_instance

def ResourceBinding (t : Tables) (id : Int) (code : Record) : Prop :=
  let field := fieldOf t id (operandValue t code 1)
  let typ := atRow t.types (field.integer 2)
  let resource := resourceOf t code
  let method := methodOf t code
  operandValue t code 0 = 0 ∧ operandValue t code 3 = 0 ∧
  Index (operandValue t code 1) (functionFields t id).size ∧
  Index (operandValue t code 4) t.resources.size ∧
  Index (operandValue t code 2) (resource.integer 2).toNat ∧
  typ.integer 1 = 26 ∧ PlainTail typ ∧ (atRow t.catalogs (resource.integer 1)).integer 1 = -1 ∧
  nameBytes t typ 2 = (atRow t.catalogs (resource.integer 1)).blob 2 ∧
  (method.integer 3 = 1 ∨ method.integer 3 = 7) ∧
  (method.integer 4 = 0 ∨ method.integer 6 = 1 ∨ method.integer 6 = 7) ∧
  method.integer 4 ≤ 64 ∧ 0 ≤ method.integer 7 ∧ method.integer 7 ≤ 2 ∧ 0 < (method.blob 8).size
instance (t : Tables) (id : Int) (code : Record) : Decidable (ResourceBinding t id code) := by
  unfold ResourceBinding; infer_instance

/-- Supported operand/type/callee relationships, not value execution or effects. -/
def InstructionBinding (t : Tables) (id : Int) (code : Record) : Prop :=
  let v := operandValue t code
  let f := code.integer 6
  (if f = 5 then operandRoles t code = [10, 12] ∨ operandRoles t code = [11, 12]
   else rolesFor f = some (operandRoles t code)) ∧ Selectors code ∧
  AllRows (operandsOf t code) (OperandPayload t) ∧
  (if f = 5 then ScalarType t (v 1) ∧
      ((scalarKind t (v 1) = some .boolean ∧ (operand t code 0).integer 1 = 10 ∧
        0 ≤ v 0 ∧ v 0 ≤ 1) ∨
       (scalarKind t (v 1) = some .word ∧ (operand t code 0).integer 1 = 11))
   else if f = 7 then MatchingSlot t id (v 0) (v 1)
   else if f = 11 then ScalarType t (v 0) ∧ scalarKind t (v 0) = some .boolean
   else if f = 12 ∨ f = 14 then ScalarType t (v 0) ∧ scalarKind t (v 0) = some .word
   else if f = 32 ∨ f = 33 then
     Index (v 0) (functionFields t id).size ∧ ScalarType t (v 1) ∧
     scalarKind t ((fieldOf t id (v 0)).integer 2) = scalarKind t (v 1)
   else if f = 38 then MethodBinding t id code
   else if f = 45 then
     v 0 = code.integer 1 ∧ Index (v 0) ((atRow t.callables id).integer 5 - 1).toNat ∧
     v 1 = 8 * (v 0 + 1) ∧ MatchingSlot t id (v 1) (v 2) ∧
     scalarKind t (v 2) = scalarKind t ((atRow t.callables id).integer 4 + v 0 + 1)
   else if f = 89 then ResourceBinding t id code
   else if f = 40 ∨ f = 41 ∨ f = 42 then 0 ≤ v 0
   else True)
instance (t : Tables) (id : Int) (code : Record) : Decidable (InstructionBinding t id code) := by
  unfold InstructionBinding; infer_instance

def parameterPrefix (t : Tables) (id : Int) : Prop :=
  let count := ((atRow t.callables id).integer 5 - 1).toNat
  let code := functionCode t id
  count ≤ code.size ∧
  ∀ entry ∈ code.toList.zipIdx,
    entry.2 < count → entry.1.integer 6 = 45
instance (t : Tables) (id : Int) : Decidable (parameterPrefix t id) := by
  unfold parameterPrefix; infer_instance

def falls (row : Record) : Bool := row.integer 6 != 41 && row.integer 6 != 43

def labelRows (t : Tables) (id : Int) : Array Record :=
  (functionCode t id).filter (fun r => r.integer 6 == 40)

def expectedLeader (t : Tables) (id : Int) (code : Record) : Bool :=
  let previous := atRow (functionCode t id) (code.integer 1 - 1)
  code.integer 1 == 0 || code.integer 6 == 40 ||
    previous.integer 6 == 41 || previous.integer 6 == 42 || previous.integer 6 == 43

def CodeEdges (t : Tables) (id : Int) (code : Record) : Prop :=
  let body := functionCode t id
  code.integer 4 = 4 + (if falls code then 2 else 0) + (if expectedLeader t id code then 1 else 0) ∧
  (falls code = true → code.integer 1 + 1 < Int.ofNat body.size) ∧
  (if code.integer 6 = 41 ∨ code.integer 6 = 42 then
    Index (code.integer 3) body.size ∧ code.integer 1 < code.integer 3 ∧
    (atRow body (code.integer 3)).integer 6 = 40 ∧
    operandValue t (atRow body (code.integer 3)) 0 = operandValue t code 0
   else code.integer 3 = -1)
instance (t : Tables) (id : Int) (code : Record) : Decidable (CodeEdges t id code) := by
  unfold CodeEdges; infer_instance

/-- Normal-success edges only. Require may also fail; native/external outcomes
    and value semantics are outside this structural relation. -/
def NormalEdge (body : Array Record) (source target : Nat) : Prop :=
  let row := atRow body (Int.ofNat source)
  source < body.size ∧ target < body.size ∧
  ((falls row = true ∧ target = source + 1) ∨
    ((row.integer 6 = 41 ∨ row.integer 6 = 42) ∧ row.integer 3 = Int.ofNat target))
instance (body : Array Record) (source target : Nat) : Decidable (NormalEdge body source target) := by
  unfold NormalEdge; infer_instance

def Predecessors (t : Tables) (id : Int) : Prop :=
  let body := functionCode t id
  ∀ position ∈ List.range body.size,
    position = 0 ∨ ∃ previous ∈ List.range position, NormalEdge body previous position
instance (t : Tables) (id : Int) : Decidable (Predecessors t id) := by unfold Predecessors; infer_instance

inductive Reachable (t : Tables) (id : Int) : Nat → Prop
  | entry : Reachable t id 0
  | step : Reachable t id previous → NormalEdge (functionCode t id) previous position → Reachable t id position

theorem predecessors_reachable {t : Tables} {id : Int} (covered : Predecessors t id)
    (position : Nat) (bound : position < (functionCode t id).size) : Reachable t id position := by
  induction position using Nat.strongRecOn with
  | ind position ih =>
    rcases covered position (List.mem_range.mpr bound) with entry | ⟨previous, prior, edge⟩
    · subst position; exact .entry
    · have smaller := List.mem_range.mp prior
      exact .step (ih previous smaller (Nat.lt_trans smaller bound)) edge

def FunctionBindings (t : Tables) (id : Int) : Prop :=
  FunctionShape t id ∧ parameterPrefix t id ∧ Predecessors t id ∧
  AllRows (functionCode t id) (InstructionBinding t id) ∧ AllRows (functionCode t id) (CodeEdges t id) ∧
  (labelRows t id).toList.Pairwise (fun a b => operandValue t a 0 ≠ operandValue t b 0)
instance (t : Tables) (id : Int) : Decidable (FunctionBindings t id) := by unfold FunctionBindings; infer_instance

end Aurora.Publication
