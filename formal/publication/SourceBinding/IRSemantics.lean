import SourceBinding.IRIdentity
import SourceBinding.ExprCode
namespace Aurora.SourceBinding
open Aurora.Publication

def comparisonCode : CompareOp → Int
  | .eq => 0 | .ne => 1 | .lt => 2 | .gt => 3 | .le => 4 | .ge => 5

def comparisonOf : Int → Option CompareOp
  | 0 => some .eq | 1 => some .ne | 2 => some .lt | 3 => some .gt | 4 => some .le | 5 => some .ge
  | _ => none

/-- The finite count extension checks signed payload and plain i64 type,
    without admitting signed values into the scalar signature profile. -/
def SignedCount (t : Tables) (row : Record) (count : SignedLiteralCount) : Prop :=
  row.integer 6 = 5 ∧ operandRoles t row = [10,12] ∧
  operandValue t row 0 = Int.ofNat count.value ∧
  Index (operandValue t row 1) t.types.size ∧
  (atRow t.types (operandValue t row 1)).integer 1 = 0 ∧
  (atRow t.types (operandValue t row 1)).integer 3 = 0 ∧
  PlainTail (atRow t.types (operandValue t row 1))
instance (t : Tables) (row : Record) (count : SignedLiteralCount) : Decidable (SignedCount t row count) := by
  unfold SignedCount; infer_instance

/-- Extension of raw operand binding only. The legacy D2 scalar transfer checker
    is not advertised as a nominal/local-variable verifier. -/
def RuntimeArithmeticBinding (t : Tables) (id : Int) (row : Record) : Prop :=
  InstructionBinding t id row ∨
  (row.integer 5 = 1 ∧ row.integer 10 = 0 ∧
    AllRows (operandsOf t row) (OperandPayload t) ∧ row.integer 7 = 0 ∧ row.integer 9 = 0 ∧
    ((row.integer 8 = 0 ∧ (SignedCount t row .four ∨ SignedCount t row .thirtyTwo)) ∨
     (row.integer 6 = 12 ∧ operandRoles t row = [14] ∧
      (row.integer 8 = 0 ∨ row.integer 8 = 9) ∧
      ScalarType t (operandValue t row 0) ∧ scalarKind t (operandValue t row 0) = some .word)))
instance (t : Tables) (id : Int) (row : Record) : Decidable (RuntimeArithmeticBinding t id row) := by
  unfold RuntimeArithmeticBinding; infer_instance

/-- Independent canonical record→operation relation. In particular u64 constants
    use the UNSIGNED payload (operand field3), never signed operandValue(field2). -/
def OperationMeaning (t : Tables) (id : Int) (row : Record) (operation : Op) : Prop :=
  RuntimeArithmeticBinding t id row ∧ CodeEdges t id row ∧ row.integer 0 = id ∧
  match operation with
  | .constant .word (.word value) => row.integer 6 = 5 ∧
      scalarKind t (operandValue t row 1) = some .word ∧
      (operand t row 0).integer 1 = 11 ∧ (operand t row 0).integer 3 = Int.ofNat value ∧ value < wordLimit
  | .constant .boolean (.boolean value) => row.integer 6 = 5 ∧
      scalarKind t (operandValue t row 1) = some .boolean ∧
      (operand t row 0).integer 1 = 10 ∧ operandValue t row 0 = (if value then 1 else 0)
  | .constant _ _ => False
  | .count12 => SignedCount12 t row
  | .count4 => SignedCount t row .four
  | .count32 => SignedCount t row .thirtyTwo
  | .load kind slot => row.integer 6 = 7 ∧ operandValue t row 0 = Int.ofNat slot ∧
      scalarKind t (operandValue t row 1) = some kind
  | .receiver kind ordinal => row.integer 6 = 32 ∧ operandValue t row 0 = Int.ofNat ordinal ∧
      scalarKind t (operandValue t row 1) = some kind
  | .push => row.integer 6 = 9
  | .negate => row.integer 6 = 11 ∧ row.integer 7 = 1
  | .binary .add => row.integer 6 = 12 ∧ row.integer 8 = 0
  | .binary .leftShift => row.integer 6 = 12 ∧ row.integer 8 = 8
  | .binary .rightShift => row.integer 6 = 12 ∧ row.integer 8 = 9
  | .binary .sub => row.integer 6 = 12 ∧ row.integer 8 = 1
  | .binary .bitAnd => row.integer 6 = 12 ∧ row.integer 8 = 5
  | .binary .bitOr => row.integer 6 = 12 ∧ row.integer 8 = 6
  | .binary (.compare comparison) => row.integer 6 = 14 ∧ row.integer 9 = comparisonCode comparison
  | .bind kind argument slot => row.integer 6 = 45 ∧ operandValue t row 0 = Int.ofNat argument ∧
      operandValue t row 1 = Int.ofNat slot ∧ scalarKind t (operandValue t row 2) = some kind
  | .label => row.integer 6 = 40
  | .jump target => row.integer 6 = 41 ∧ row.integer 3 = Int.ofNat target
  | .branchFalse target => row.integer 6 = 42 ∧ row.integer 3 = Int.ofNat target
  | .ret => row.integer 6 = 43
instance (t : Tables) (id : Int) (row : Record) (operation : Op) :
    Decidable (OperationMeaning t id row operation) := by
  cases operation <;> dsimp [OperationMeaning]
  all_goals first | infer_instance | (split <;> infer_instance)

/-- Untrusted candidate projection; every returned operation is checked above. -/
def operationCandidate (t : Tables) (row : Record) : Option Op := do
  let v := operandValue t row
  match row.integer 6 with
  | 5 =>
    if SignedCount12 t row then return .count12
    if SignedCount t row .four then return .count4
    if SignedCount t row .thirtyTwo then return .count32
    let kind ← scalarKind t (v 1)
    match kind with
    | .word => return .constant .word (.word ((operand t row 0).integer 3).toNat)
    | .boolean => return .constant .boolean (.boolean (v 0 == 1))
  | 7 => return .load (← scalarKind t (v 1)) (v 0).toNat
  | 32 => return .receiver (← scalarKind t (v 1)) (v 0).toNat
  | 9 => return .push
  | 11 => return .negate
  | 12 => match row.integer 8 with
    | 0 => return .binary .add
    | 1 => return .binary .sub
    | 5 => return .binary .bitAnd
    | 6 => return .binary .bitOr
    | 8 => return .binary .leftShift
    | 9 => return .binary .rightShift
    | _ => none
  | 14 => return .binary (.compare (← comparisonOf (row.integer 9)))
  | 45 => return .bind (← scalarKind t (v 2)) (v 0).toNat (v 1).toNat
  | 40 => return .label
  | 41 => return .jump (row.integer 3).toNat
  | 42 => return .branchFalse (row.integer 3).toNat
  | 43 => return .ret
  | _ => none

structure MeaningfulOperation (t : Tables) (id : Int) (row : Record) where
  operation : Op
  meaning : OperationMeaning t id row operation

def decodeOperation (t : Tables) (id : Int) (row : Record) : Option (MeaningfulOperation t id row) := do
  let candidate ← operationCandidate t row
  if meaning : OperationMeaning t id row candidate then return ⟨candidate,meaning⟩ else none

def canonicalProgram (t : Tables) (id : Int) : Program := fun pc => do
  let row ← (functionCode t id)[pc]?
  if row.integer 1 = Int.ofNat pc then
    let decoded ← decodeOperation t id row
    return decoded.operation
  else none

/-- Canonical meaning applies to the exact row at this normalized PC. -/
theorem decode_operation_sound (t : Tables) (id : Int) (row : Record)
    (result : MeaningfulOperation t id row) (_accepted : decodeOperation t id row = some result) :
    OperationMeaning t id row result.operation := result.meaning

theorem canonical_program_sound (t : Tables) (id : Int) (pc : Nat) (op : Op)
    (accepted : canonicalProgram t id pc = some op) :
    ∃ row, (functionCode t id)[pc]? = some row ∧ row.integer 1 = Int.ofNat pc ∧ OperationMeaning t id row op := by
  unfold canonicalProgram at accepted
  cases rowEq : (functionCode t id)[pc]? with
  | none => simp [rowEq] at accepted
  | some row =>
    simp only [rowEq, bind, Option.bind] at accepted
    split at accepted
    next position =>
      cases resultEq : decodeOperation t id row with
      | none => simp [resultEq] at accepted
      | some result =>
        simp only [resultEq, pure, Option.some.injEq] at accepted
        exact ⟨row,rfl,position,accepted ▸ result.meaning⟩
    next wrong => simp at accepted

end Aurora.SourceBinding
