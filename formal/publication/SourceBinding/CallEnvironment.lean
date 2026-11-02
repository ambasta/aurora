import SourceBinding.CallSource
import SourceBinding.CallProjection
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Ordinary occurrences, including unreachable suffixes. -/
inductive OrdinaryOccurs (target : ScalarOrdinary) : List CallPiece → Prop
  | here {arguments : CallArguments target.parameters} :
      OrdinaryOccurs target (.invoke (.ordinary target arguments) :: rest)
  | later : OrdinaryOccurs target rest → OrdinaryOccurs target (piece :: rest)

/-- Lookup returns the actual dependent source/body certificate, not an assumed
    source summary or independently decoded publication. Repeated descriptors may
    reuse the first valid certificate in the SAME root family. -/
def CallLeaves.lookup {shape : CallShapeBinding files root module path member bytes} :
    {pieces : List CallPiece} → CallLeaves shape pieces → (target : ScalarOrdinary) →
      Option (CheckedCallLeaf shape target)
  | _, .nil, _ => none
  | _, .localBody rest, target => rest.lookup target
  | _, @CallLeaves.ordinary _ _ _ _ _ _ _ _ actual _ leaf rest, target =>
    if same : actual = target then some (same ▸ leaf) else rest.lookup target
  | _, .resourceAssert rest, target => rest.lookup target

theorem CallLeaves.lookup_present {shape : CallShapeBinding files root module path member bytes}
    {pieces : List CallPiece} (leaves : CallLeaves shape pieces)
    (occurs : OrdinaryOccurs target pieces) : ∃ leaf, leaves.lookup target = some leaf := by
  induction leaves with
  | nil => cases occurs
  | localBody rest ih => cases occurs with | later prior => exact ih prior
  | resourceAssert rest ih => cases occurs with | later prior => exact ih prior
  | @ordinary rest actual arguments leaf tail ih =>
    by_cases same : actual = target
    · exact ⟨same ▸ leaf,by simp only [CallLeaves.lookup,same,↓reduceDIte]⟩
    · have prior : OrdinaryOccurs target rest := by
        cases occurs with
        | here => exact False.elim (same rfl)
        | later prior => exact prior
      obtain ⟨found,foundEq⟩ := ih prior
      exact ⟨found,by simp only [CallLeaves.lookup,same,↓reduceDIte,foundEq]⟩

def CallFamilyBinding.sourceBodies (family : CallFamilyBinding files root module path member bytes) : SourceCallProgram :=
  fun target => (family.leaves.lookup target).map (fun leaf => leaf.source.body)

theorem CallFamilyBinding.source_body_present
    (family : CallFamilyBinding files root module path member bytes)
    (occurs : OrdinaryOccurs target family.shape.source.pieces) :
    ∃ leaf : CheckedCallLeaf family.shape target,
      family.leaves.lookup target = some leaf ∧ family.sourceBodies target = some leaf.source.body := by
  obtain ⟨leaf,found⟩ := family.leaves.lookup_present occurs
  exact ⟨leaf,found,by simp only [CallFamilyBinding.sourceBodies,found,Option.map_some]⟩
def CallFamilyBinding.program (family : CallFamilyBinding files root module path member bytes) : CallProgram :=
  canonicalCalls (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces)

theorem CallProjectionBinding.root_call
    {family : CallFamilyBinding files root module path member bytes} (projection : CallProjectionBinding family)
    (present : target ∈ pieceTargets family.shape.source.pieces)
    (meaning : InvocationAt (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id pc target) : family.program family.shape.ir.id pc = some (targetOperation target) :=
  canonical_call_complete (projection.compatible.unique family.shape.ir.selected present meaning)

def TypedInvocation.target : TypedInvocation → CallTarget
  | .ordinary target _ => .ordinary target
  | .resourceAssert target _ => .resource target

theorem pieceTargets.member (pieces : List CallPiece) {call : TypedInvocation}
    (member : .invoke call ∈ pieces) : call.target ∈ pieceTargets pieces := by
  induction pieces with
  | nil => cases member
  | cons piece rest ih =>
    cases member with
    | head => cases call <;> exact List.mem_cons_self
    | tail _ later =>
      have prior := ih later
      cases piece with
      | localBody _ => exact prior
      | invoke other => cases other <;> exact List.mem_cons_of_mem _ prior

theorem OrdinaryOccurs.of_member {target : ScalarOrdinary} {arguments : CallArguments target.parameters}
    (member : .invoke (.ordinary target arguments) ∈ pieces) : OrdinaryOccurs target pieces := by
  induction member with
  | head => exact .here
  | tail _ _ ih => exact .later ih
end Aurora.SourceBinding
