import SourceBinding.CallSource
import SourceBinding.CallProjection
namespace Aurora.SourceBinding

/-- Ordinary occurrences, including unreachable suffixes. -/
inductive OrdinaryOccurs (target : OrdinaryDescriptor) : List CallPiece → Prop
  | here {arguments : CallArguments target.parameters} :
      OrdinaryOccurs target (.invoke (.ordinary target arguments) :: rest)
  | later : OrdinaryOccurs target rest → OrdinaryOccurs target (piece :: rest)

/-- Lookup returns the actual dependent source/body certificate, not an assumed
    source summary or independently decoded publication. Repeated descriptors may
    reuse the first valid certificate in the SAME root family. -/
def CallLeaves.lookup {shape : CallShapeBinding files root module path member bytes} :
    {pieces : List CallPiece} → CallLeaves shape pieces → (target : OrdinaryDescriptor) →
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
end Aurora.SourceBinding
