import SourceBinding.RuntimeEvaluationResults
import SourceBinding.RuntimeInitialState
namespace Aurora.SourceBinding.FramePolicyAttachment

/-- Exact formal metadata and read semantics, including missing/malformed
    argument values. Names do not change the checked physical slot. -/
theorem formal_read (found : kinds[index]? = some kind) :
    (formalSourceLocals kinds arguments).readBound
      ⟨name,kind,false,0,runtimeParameterSlot index⟩ = readRuntime kind (arguments index) := by
  have bound := (List.getElem?_eq_some_iff.mp found).1
  have selected := (List.getElem?_eq_some_iff.mp found).2
  have remainder : runtimeParameterSlot index % 8 = 0 := by unfold runtimeParameterSlot; omega
  have positive : 0 < runtimeParameterSlot index := by unfold runtimeParameterSlot; omega
  have quotient : runtimeParameterSlot index / 8 - 1 = index := by unfold runtimeParameterSlot; omega
  simp [RuntimeLocals.readBound,SourceLocal.runtimeDeclaration,formalSourceLocals,
    remainder,positive,quotient,bound,selected,RuntimeLocals.read]

/-- Reserving skipped scopes cannot change any read, including faults. -/
theorem reserve_read {state next : RuntimeLocals} {binding : SourceLocal} (accepted : state.reserveScopes limit = some next) :
    next.readBound binding = state.readBound binding := by
  unfold RuntimeLocals.reserveScopes at accepted
  split at accepted
  next => cases accepted; rfl
  next => cases accepted

/-- Entering a fresh scope preserves reads of a declaration already active.
    This does not assert that previously out-of-scope reads stay faults. -/
theorem enter_read {state next : RuntimeLocals} {binding : SourceLocal} (active : binding.scope ∈ state.scopes)
    (accepted : state.enterAt scope = some next) :
    next.readBound binding = state.readBound binding := by
  unfold RuntimeLocals.enterAt at accepted
  split at accepted
  next =>
    cases accepted
    unfold RuntimeLocals.readBound
    split
    next declared =>
      simp only [RuntimeLocals.enter] at declared
      simp only [RuntimeLocals.enter,RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration,
        active,List.mem_cons,or_true,if_true]
    next absent =>
      change ¬ state.declarations binding.slot = some binding.runtimeDeclaration at absent
      simp only [if_neg absent]
  next => cases accepted

end Aurora.SourceBinding.FramePolicyAttachment
