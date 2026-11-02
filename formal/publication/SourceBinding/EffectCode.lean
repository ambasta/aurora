import SourceBinding.BodySyntax
import SourceBinding.Stateful
import SourceBinding.EnumBinding
namespace Aurora.SourceBinding
open Aurora.Publication

def RuntimeRow (t : Tables) (id : Int) (row : Record) (roles : List Int) : Prop :=
  CodeEdges t id row ∧ row.integer 0 = id ∧ row.integer 5 = 1 ∧
  row.integer 7 = 0 ∧ row.integer 8 = 0 ∧ row.integer 10 = 0 ∧
  operandRoles t row = roles ∧ AllRows (operandsOf t row) (OperandPayload t)
instance (t : Tables) (id : Int) (row : Record) (roles : List Int) :
    Decidable (RuntimeRow t id row roles) := by unfold RuntimeRow; infer_instance

/-- Independent complete record-to-effect meaning. Stores and assertion checks
    are checked forms, never inferred from textual descriptions or treated as pure. -/
def EffectMeaning (t : Tables) (id : Int) (row : Record) : EffectOp → Prop
  | .pure operation => OperationMeaning t id row operation
  | .store kind ordinal => InstructionBinding t id row ∧ CodeEdges t id row ∧
      row.integer 0 = id ∧ row.integer 6 = 33 ∧ operandValue t row 0 = Int.ofNat ordinal ∧
      scalarKind t (operandValue t row 1) = some kind
  | .require => InstructionBinding t id row ∧ CodeEdges t id row ∧ row.integer 0 = id ∧ row.integer 6 = 91
  | .enumConstant identity ordinal => CodeEdges t id row ∧ row.integer 0 = id ∧
      EnumConstantIdentity t row identity ordinal
  | .enumLoad identity slot => RuntimeRow t id row [2,12] ∧ row.integer 9 = 0 ∧
      row.integer 6 = 7 ∧ operandValue t row 0 = Int.ofNat slot ∧
      RuntimeMatchingSlot t id (Int.ofNat slot) (operandValue t row 1) (.nominal identity)
  | .enumBind identity argument slot => RuntimeRow t id row [1,2,12] ∧ row.integer 9 = 0 ∧
      row.integer 6 = 45 ∧ operandValue t row 0 = Int.ofNat argument ∧
      operandValue t row 1 = Int.ofNat slot ∧ row.integer 1 = Int.ofNat argument ∧
      Index (Int.ofNat argument) ((atRow t.callables id).integer 5 - 1).toNat ∧
      slot = 8 * (argument + 1) ∧
      RuntimeMatchingSlot t id (Int.ofNat slot) (operandValue t row 2) (.nominal identity) ∧
      NominalTypeIdentity t ((atRow t.callables id).integer 4 + Int.ofNat argument + 1) identity
  | .enumCompare identity equal => RuntimeRow t id row [14] ∧ row.integer 6 = 14 ∧
      row.integer 9 = (if equal then 0 else 1) ∧
      NominalTypeIdentity t (operandValue t row 0) identity
  | .localStore kind slot => RuntimeRow t id row [2,12] ∧ row.integer 9 = 0 ∧
      row.integer 6 = 8 ∧ operandValue t row 0 = Int.ofNat slot ∧
      RuntimeMatchingSlot t id (Int.ofNat slot) (operandValue t row 1) kind
instance (t : Tables) (id : Int) (row : Record) (operation : EffectOp) :
    Decidable (EffectMeaning t id row operation) := by
  cases operation <;> dsimp [EffectMeaning] <;> infer_instance

structure MeaningfulEffect (t : Tables) (id : Int) (row : Record) where
  operation : EffectOp
  meaning : EffectMeaning t id row operation

/-- Only a candidate: exact nominal cardinality and slot/type facts are checked
    by EffectMeaning, including the SAME table's unique nominal row. -/
def runtimeTypeCandidate (t : Tables) (typ : Int) : Option RuntimeType :=
  match scalarKind t typ with
  | some scalar => some (.scalar scalar)
  | none =>
    if (atRow t.types typ).integer 1 = 9 then
      let name := nameBytes t (atRow t.types typ) 2
      let rows := t.enums.filter (fun row => nameBytes t row 1 == name)
      some (.nominal ⟨name,(atRow rows 0).integer 3 |>.toNat⟩)
    else none

def nominalCandidate (t : Tables) (typ : Int) : Option NominalIdentity := do
  match (← runtimeTypeCandidate t typ) with
  | .nominal identity => some identity
  | .scalar _ => none

/-- Candidate extraction is untrusted; independent meaning is checked afterward. -/
def effectCandidate (t : Tables) (row : Record) : Option EffectOp := do
  if row.integer 6 = 6 then
    return .enumConstant (← nominalCandidate t (operandValue t row 0)) (operandValue t row 1).toNat
  else if row.integer 6 = 8 then
    return .localStore (← runtimeTypeCandidate t (operandValue t row 1)) (operandValue t row 0).toNat
  else if row.integer 6 = 7 ∧ (scalarKind t (operandValue t row 1)).isNone then
    return .enumLoad (← nominalCandidate t (operandValue t row 1)) (operandValue t row 0).toNat
  else if row.integer 6 = 45 ∧ (scalarKind t (operandValue t row 2)).isNone then
    return .enumBind (← nominalCandidate t (operandValue t row 2))
      (operandValue t row 0).toNat (operandValue t row 1).toNat
  else if row.integer 6 = 14 ∧ (scalarKind t (operandValue t row 0)).isNone then
    return .enumCompare (← nominalCandidate t (operandValue t row 0)) (row.integer 9 == 0)
  else if row.integer 6 = 33 then
    return .store (← scalarKind t (operandValue t row 1)) (operandValue t row 0).toNat
  else if row.integer 6 = 91 then return .require
  else return .pure (← operationCandidate t row)

def decodeEffect (t : Tables) (id : Int) (row : Record) : Option (MeaningfulEffect t id row) := do
  let candidate ← effectCandidate t row
  if meaning : EffectMeaning t id row candidate then return ⟨candidate,meaning⟩ else none

def canonicalEffects (t : Tables) (id : Int) : EffectProgram := fun pc => do
  let row ← (functionCode t id)[pc]?
  if row.integer 1 = Int.ofNat pc then return (← decodeEffect t id row).operation else none

theorem decode_effect_sound (t : Tables) (id : Int) (row : Record)
    (result : MeaningfulEffect t id row) (_accepted : decodeEffect t id row = some result) :
    EffectMeaning t id row result.operation := result.meaning

theorem canonical_effect_sound (t : Tables) (id : Int) (pc : Nat) (operation : EffectOp)
    (accepted : canonicalEffects t id pc = some operation) :
    ∃ row, (functionCode t id)[pc]? = some row ∧ row.integer 1 = Int.ofNat pc ∧
      EffectMeaning t id row operation := by
  unfold canonicalEffects at accepted
  cases rowEq : (functionCode t id)[pc]? with
  | none => simp [rowEq] at accepted
  | some row =>
    simp only [rowEq,bind,Option.bind] at accepted
    split at accepted
    next position =>
      cases resultEq : decodeEffect t id row with
      | none => simp [resultEq] at accepted
      | some result =>
        simp only [resultEq,pure,Option.some.injEq] at accepted
        exact ⟨row,rfl,position,accepted ▸ result.meaning⟩
    next wrong => simp at accepted

/-- Independent body-code relation. Sequence checks even syntactically unreachable
    source suffixes. Every expression uses the pure projection, so stores or
    assertions cannot be silently hidden inside expression lowering. -/
inductive BodyCode (program : EffectProgram) (slots : Nat → Nat) : EffectBody → Nat → Nat → Prop
  | skip : BodyCode program slots .skip start start
  | seq : BodyCode program slots first start middle → BodyCode program slots rest middle stop →
      BodyCode program slots (.seq first rest) start stop
  | assign {kind : GuardType} {value : GuardExpr kind} : ExprCode (pureView program) slots value start middle →
      program middle = some (.store kind ordinal) →
      BodyCode program slots (.assign kind ordinal value) start (middle + 1)
  | require : ExprCode (pureView program) slots condition start middle → program middle = some .require →
      BodyCode program slots (.require condition) start (middle + 1)
  | returnValue {kind : GuardType} {value : GuardExpr kind} : ExprCode (pureView program) slots value start middle → program middle = some (.pure .ret) →
      BodyCode program slots (.returnValue kind value) start (middle + 1)
  | branchJoined : ExprCode (pureView program) slots condition start conditionEnd →
      program conditionEnd = some (.pure (.branchFalse (bodyEnd + 1))) →
      BodyCode program slots body (conditionEnd + 1) bodyEnd →
      program bodyEnd = some (.pure (.jump (bodyEnd + 2))) →
      program (bodyEnd + 1) = some (.pure .label) → program (bodyEnd + 2) = some (.pure .label) →
      BodyCode program slots (.branch condition body) start (bodyEnd + 3)
  | branchSingle : ExprCode (pureView program) slots condition start conditionEnd →
      program conditionEnd = some (.pure (.branchFalse bodyEnd)) →
      BodyCode program slots body (conditionEnd + 1) bodyEnd → program bodyEnd = some (.pure .label) →
      BodyCode program slots (.branch condition body) start (bodyEnd + 1)

structure CheckedBodyCode (program : EffectProgram) (slots : Nat → Nat) (body : EffectBody) (start : Nat) where
  stop : Nat
  code : BodyCode program slots body start stop

/-- Structural translation validation may reject alternative valid compiler
    lowerings. Neither callable IDs nor workload PCs/field ordinals are fixed. -/
def checkBodyCode (program : EffectProgram) (slots : Nat → Nat) :
    (body : EffectBody) → (start : Nat) → Option (CheckedBodyCode program slots body start)
  | .skip, start => some ⟨start,.skip⟩
  | .seq first rest, start => do
    let head ← checkBodyCode program slots first start
    let tail ← checkBodyCode program slots rest head.stop
    return ⟨tail.stop,.seq head.code tail.code⟩
  | .assign kind ordinal value, start => do
    let expression ← checkExprCode (pureView program) slots value start
    if store : program expression.stop = some (.store kind ordinal) then
      return ⟨expression.stop + 1,.assign expression.grammar store⟩
    else none
  | .require condition, start => do
    let expression ← checkExprCode (pureView program) slots condition start
    if require : program expression.stop = some .require then
      return ⟨expression.stop + 1,.require expression.grammar require⟩
    else none
  | .returnValue _ value, start => do
    let expression ← checkExprCode (pureView program) slots value start
    if ret : program expression.stop = some (.pure .ret) then
      return ⟨expression.stop + 1,.returnValue expression.grammar ret⟩
    else none
  | .branch condition body, start => do
    let expression ← checkExprCode (pureView program) slots condition start
    let checked ← checkBodyCode program slots body (expression.stop + 1)
    if branch : program expression.stop = some (.pure (.branchFalse (checked.stop + 1))) then
      if jump : program checked.stop = some (.pure (.jump (checked.stop + 2))) then
        if falseLabel : program (checked.stop + 1) = some (.pure .label) then
          if endLabel : program (checked.stop + 2) = some (.pure .label) then
            return ⟨checked.stop + 3,.branchJoined expression.grammar branch checked.code jump falseLabel endLabel⟩
          else none
        else none
      else none
    else if branch : program expression.stop = some (.pure (.branchFalse checked.stop)) then
      if label : program checked.stop = some (.pure .label) then
        return ⟨checked.stop + 1,.branchSingle expression.grammar branch checked.code label⟩
      else none
    else none

theorem check_body_code_sound (program : EffectProgram) (slots : Nat → Nat) (body : EffectBody) (start : Nat)
    (result : CheckedBodyCode program slots body start)
    (_accepted : checkBodyCode program slots body start = some result) :
    BodyCode program slots body start result.stop := result.code

end Aurora.SourceBinding
