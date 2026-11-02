import SourceBinding.ArgumentCode
import SourceBinding.EntryBinding
namespace Aurora.SourceBinding
open Aurora.Publication

inductive CallTarget where
  | ordinary (target : OrdinaryDescriptor)
  | resource (target : ResourceDescriptor)

/-- Exact raw-call identity and calling signature. The meaning contains no
    operational postcondition, external success or preservation assumption. -/
def CallMeaning (t : Tables) (caller : Int) (row : Record) : CallTarget → Prop
  | .ordinary target =>
    InstructionBinding t caller row ∧ CodeEdges t caller row ∧ row.integer 0 = caller ∧ row.integer 6 = 38 ∧
    Index target.id t.callables.size ∧ (callee t row).integer 0 = target.id ∧
    callName t row = nameBytes t (atRow t.callables target.id) 1 ∧
    (argumentTypes t row).map (Option.map RuntimeType.scalar) = target.parameters.map some ∧
    (callResult t row).map RuntimeType.scalar = some target.result
  | .resource target =>
    InstructionBinding t caller row ∧ CodeEdges t caller row ∧ row.integer 0 = caller ∧ row.integer 6 = 89 ∧
    operandValue t row 1 = Int.ofNat target.fieldOrdinal ∧ operandValue t row 2 = target.method ∧
    operandValue t row 4 = target.resource ∧ ResourceDescriptorMatches t caller target.sourceType target ∧
    argumentTypes t row = target.parameters.map some ∧ callResult t row = some target.result
theorem scalar_signature_exact (types : List (Option GuardType)) (kinds : List GuardType) :
    types.map (Option.map RuntimeType.scalar) = (kinds.map RuntimeType.scalar).map some ↔
      types = kinds.map some := by
  have injective : ∀ a b : Option GuardType,
      a.map RuntimeType.scalar = b.map RuntimeType.scalar → a = b := by
    intro a b same
    cases a <;> cases b <;> simp only [Option.map_none,Option.map_some,reduceCtorEq,Option.some.injEq,
      RuntimeType.scalar.injEq] at same ⊢
    all_goals first | contradiction | exact same | rfl
  rw [← List.map_inj_right injective]
  simp only [List.map_map]
  rfl

theorem scalar_result_exact (value : Option GuardType) (kind : GuardType) :
    value.map RuntimeType.scalar = some (.scalar kind) ↔ value = some kind := by
  cases value <;> simp only [Option.map_none,Option.map_some,reduceCtorEq,Option.some.injEq,
    RuntimeType.scalar.injEq]

/-- The old MethodCall profile admits exactly the same scalar signatures. The
    runtime descriptor extension neither coerces nor drops a nominal type. -/
theorem CallMeaning.scalar_profile (t : Tables) (caller : Int) (row : Record) (target : ScalarOrdinary) :
    CallMeaning t caller row (.ordinary target.descriptor) ↔
      InstructionBinding t caller row ∧ CodeEdges t caller row ∧ row.integer 0 = caller ∧ row.integer 6 = 38 ∧
      Index target.id t.callables.size ∧ (callee t row).integer 0 = target.id ∧
      callName t row = nameBytes t (atRow t.callables target.id) 1 ∧
      argumentTypes t row = target.parameters.map some ∧ callResult t row = some target.result := by
  simp only [CallMeaning,target.parameters_exact,target.result_exact,scalar_signature_exact,scalar_result_exact,
    ScalarOrdinary.id]

instance (t : Tables) (caller : Int) (row : Record) (target : CallTarget) :
    Decidable (CallMeaning t caller row target) := by cases target <;> unfold CallMeaning <;> infer_instance

def InvocationAt (t : Tables) (caller : Int) (pc : Nat) (target : CallTarget) : Prop :=
  match (functionCode t caller)[pc]? with
  | none => False
  | some row => row.integer 1 = Int.ofNat pc ∧ CallMeaning t caller row target
instance (t : Tables) (caller : Int) (pc : Nat) (target : CallTarget) :
    Decidable (InvocationAt t caller pc target) := by unfold InvocationAt; split <;> infer_instance

inductive CallPieceCode (t : Tables) (caller : Int) (slots : Nat → Nat) : CallPiece → Nat → Nat → Prop
  | localBody : BodyCode (canonicalEffects t caller) slots body start stop →
      CallPieceCode t caller slots (.localBody body) start stop
  | ordinary {target : ScalarOrdinary} {arguments : CallArguments target.parameters} : ArgumentsCode (pureView (canonicalEffects t caller)) slots false arguments start middle →
      InvocationAt t caller middle (.ordinary target) →
      CallPieceCode t caller slots (.invoke (.ordinary target arguments)) start (middle + 1)
  | resourceAssert {target : ResourceDescriptor} {arguments : CallArguments target.parameters} : ArgumentsCode (pureView (canonicalEffects t caller)) slots true arguments start middle →
      InvocationAt t caller middle (.resource target) → target.result = .boolean →
      canonicalEffects t caller (middle + 1) = some .require →
      CallPieceCode t caller slots (.invoke (.resourceAssert target arguments)) start (middle + 2)

structure CheckedCallPiece (t : Tables) (caller : Int) (slots : Nat → Nat) (piece : CallPiece) (start : Nat) where
  stop : Nat
  code : CallPieceCode t caller slots piece start stop

def checkCallPiece (t : Tables) (caller : Int) (slots : Nat → Nat) :
    (piece : CallPiece) → (start : Nat) → Option (CheckedCallPiece t caller slots piece start)
  | .localBody body, start => do
    let checked ← checkBodyCode (canonicalEffects t caller) slots body start
    return ⟨checked.stop,.localBody checked.code⟩
  | .invoke (.ordinary target arguments), start => do
    let checked ← checkArguments (pureView (canonicalEffects t caller)) slots false arguments start
    if meaning : InvocationAt t caller checked.stop (.ordinary target) then
      return ⟨checked.stop + 1,.ordinary checked.code meaning⟩
    else none
  | .invoke (.resourceAssert target arguments), start => do
    let checked ← checkArguments (pureView (canonicalEffects t caller)) slots true arguments start
    if meaning : InvocationAt t caller checked.stop (.resource target) then
      if boolean : target.result = .boolean then
        if require : canonicalEffects t caller (checked.stop + 1) = some .require then
          return ⟨checked.stop + 2,.resourceAssert checked.code meaning boolean require⟩
        else none
      else none
    else none

/-- Every piece and every administrative label is covered, including syntax and
    rows following early returns. No terminal-path shortcut truncates checking. -/
inductive CallPiecesCode (t : Tables) (caller : Int) (slots : Nat → Nat) : List CallPiece → Nat → Nat → Prop
  | nil : LabelRun (pureView (canonicalEffects t caller)) start stop → CallPiecesCode t caller slots [] start stop
  | cons : LabelRun (pureView (canonicalEffects t caller)) start afterLabels →
      CallPieceCode t caller slots piece afterLabels middle → CallPiecesCode t caller slots rest middle stop →
      CallPiecesCode t caller slots (piece :: rest) start stop
structure CheckedCallPieces (t : Tables) (caller : Int) (slots : Nat → Nat) (pieces : List CallPiece) (start : Nat) where
  stop : Nat
  code : CallPiecesCode t caller slots pieces start stop

def checkCallPieces (t : Tables) (caller : Int) (slots : Nat → Nat) :
    (pieces : List CallPiece) → (start : Nat) → Option (CheckedCallPieces t caller slots pieces start)
  | [], start =>
    let labels := checkLabels (pureView (canonicalEffects t caller)) (functionCode t caller).size start
    some ⟨labels.stop,.nil labels.code⟩
  | piece :: rest, start => do
    let labels := checkLabels (pureView (canonicalEffects t caller)) (functionCode t caller).size start
    let first ← checkCallPiece t caller slots piece labels.stop
    let tail ← checkCallPieces t caller slots rest first.stop
    return ⟨tail.stop,.cons labels.code first.code tail.code⟩

/-- Closure membership is explicit and uses the SAME decoded root slice. Call-free
    body certificates for these targets are a separate composition obligation. -/
def TargetSelected (selected : List Int) : CallPiece → Prop
  | .invoke (.ordinary target _) => target.id ∈ selected
  | _ => True
instance (selected : List Int) (piece : CallPiece) : Decidable (TargetSelected selected piece) := by
  cases piece with
  | localBody body => exact isTrue trivial
  | invoke call => cases call <;> unfold TargetSelected <;> infer_instance

def TargetsSelected (selected : List Int) (pieces : List CallPiece) : Prop :=
  ∀ piece ∈ pieces, TargetSelected selected piece
instance (selected : List Int) (pieces : List CallPiece) : Decidable (TargetsSelected selected pieces) := by
  unfold TargetsSelected; infer_instance

structure CallShapeBinding (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) where
  selected : CheckedSelection files root module path member
  ir : BoundIR files root module path member selected bytes
  source : CallMethod (tables ir.publication.artifact.document.reversed.reverse) ir.id module path
    selected.selected.classDecl.members selected.selected.file.file.bytes selected.selected.method.function
  bindings : List ParameterBinding
  stop : Nat
  entry : EntryCode (pureView (canonicalEffects (tables ir.publication.artifact.document.reversed.reverse) ir.id))
    selected.selected.method.function.formals bindings
  code : CallPiecesCode (tables ir.publication.artifact.document.reversed.reverse) ir.id (parameterSlot bindings)
    source.pieces selected.selected.method.function.formals.length stop
  complete : stop = (functionCode (tables ir.publication.artifact.document.reversed.reverse) ir.id).size
  targets : TargetsSelected ir.publication.slice.selected source.pieces

def bindCallShape (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) :
    Option (CallShapeBinding files root module path member bytes) := do
  let selected ← checkedSelection files root module path member
  let ir ← bindIR files root module path member selected bytes
  let t := tables ir.publication.artifact.document.reversed.reverse
  let source ← callMethod t ir.id module path selected.selected.classDecl.members
    selected.selected.file.file.bytes selected.selected.method.function
  let entry ← checkEntry (pureView (canonicalEffects t ir.id)) selected.selected.method.function.formals
  let pieces ← checkCallPieces t ir.id (parameterSlot entry.bindings) source.pieces
    selected.selected.method.function.formals.length
  if complete : pieces.stop = (functionCode t ir.id).size then
    if targets : TargetsSelected ir.publication.slice.selected source.pieces then
      return ⟨selected,ir,source,entry.bindings,pieces.stop,entry.code,pieces.code,complete,targets⟩
    else none
  else none

theorem call_shape_complete (checked : CallShapeBinding files root module path member bytes) :
    GraphReady files root ∧
    CallPiecesCode (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id
      (parameterSlot checked.bindings) checked.source.pieces checked.selected.selected.method.function.formals.length
      checked.stop ∧ checked.stop = (functionCode (tables checked.ir.publication.artifact.document.reversed.reverse)
        checked.ir.id).size ∧ TargetsSelected checked.ir.publication.slice.selected checked.source.pieces :=
  ⟨checked.selected.graph,checked.code,checked.complete,checked.targets⟩
end Aurora.SourceBinding
