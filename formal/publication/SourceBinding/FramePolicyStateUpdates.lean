import SourceBinding.FramePolicyState
import SourceBinding.RuntimeFacts
namespace Aurora.SourceBinding.FramePolicyAttachment

/-- Inversion of the actual guarded initializer, not a replacement update rule. -/
theorem initialize_update {state next : RuntimeLocals} {declaration : RuntimeLocalDecl}
    (accepted : state.initialize slot declaration value = some next) :
    state.scopes.head? = some declaration.scope ∧
    readRuntime declaration.kind (some value) = .value value ∧
    next = {state with
      declarations := fun i => if i = slot then some declaration else state.declarations i
      values := fun i => if i = slot then some value else state.values i} := by
  unfold RuntimeLocals.initialize at accepted
  split at accepted
  next => cases accepted
  next active =>
    split at accepted
    next => cases accepted
    next fresh =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp only [checked] at accepted; cases accepted
      | value result =>
        have same := Option.some.inj (readRuntime_preserves _ _ _ checked)
        subst result
        simp only [checked,Option.some.injEq] at accepted
        exact ⟨Decidable.byContradiction active,rfl,accepted.symm⟩

/-- The existing mutable assignment retains all metadata and updates precisely
    one initialized value cell. Its guards are derived from acceptance. -/
theorem assign_update {state next : RuntimeLocals}
    (accepted : state.assign slot value = some next) :
    ∃ declaration, state.declarations slot = some declaration ∧
      declaration.mutable = true ∧ declaration.scope ∈ state.scopes ∧
      readRuntime declaration.kind (some value) = .value value ∧
      next = {state with values := fun i => if i = slot then some value else state.values i} := by
  unfold RuntimeLocals.assign at accepted
  cases found : state.declarations slot with
  | none => simp only [found,bind,Option.bind] at accepted; cases accepted
  | some declaration =>
    simp only [found,bind,Option.bind] at accepted
    split at accepted
    next => cases accepted
    next guards =>
      have mutable : declaration.mutable = true := Decidable.byContradiction (fun absent => guards (Or.inl absent))
      have active : declaration.scope ∈ state.scopes := Decidable.byContradiction (fun absent => guards (Or.inr (Or.inl absent)))
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp only [checked] at accepted; cases accepted
      | value result =>
        have same := Option.some.inj (readRuntime_preserves _ _ _ checked)
        subst result
        simp only [checked,Option.some.injEq] at accepted
        exact ⟨declaration,rfl,mutable,active,checked,accepted.symm⟩

theorem leave_read {state : RuntimeLocals} {binding : SourceLocal}
    (active : binding.scope ∈ state.scopes.tail) :
    state.leave.readBound binding = state.readBound binding := by
  have prior : binding.scope ∈ state.scopes := List.mem_of_mem_tail active
  unfold RuntimeLocals.readBound
  split
  next declared =>
    change state.declarations binding.slot = some binding.runtimeDeclaration at declared
    simp only [RuntimeLocals.leave,RuntimeLocals.read,declared,SourceLocal.runtimeDeclaration,
      active,prior,if_true]
  next absent =>
    change ¬state.declarations binding.slot = some binding.runtimeDeclaration at absent
    simp only [if_neg absent]

theorem initialize_other_read {state next : RuntimeLocals} {binding : SourceLocal} {declaration : RuntimeLocalDecl}
    (accepted : state.initialize slot declaration value = some next)
    (other : binding.slot ≠ slot) : next.readBound binding = state.readBound binding := by
  obtain ⟨head,typed,update⟩ := initialize_update accepted
  rw [update]
  simp only [RuntimeLocals.readBound,RuntimeLocals.read,if_neg other]

theorem initialize_read {state next : RuntimeLocals} {binding : SourceLocal}
    (accepted : state.initialize binding.slot binding.runtimeDeclaration value = some next) :
    next.readBound binding = .value value := by
  obtain ⟨head,typed,update⟩ := initialize_update accepted
  have active : binding.scope ∈ state.scopes := by
    cases shape : state.scopes with
    | nil => simp only [shape,List.head?_nil] at head; cases head
    | cons first rest =>
      simp only [shape,List.head?_cons,Option.some.injEq,SourceLocal.runtimeDeclaration] at head
      rw [← head]
      exact List.mem_cons_self
  rw [update]
  simp only [RuntimeLocals.readBound,RuntimeLocals.read,if_true,SourceLocal.runtimeDeclaration,active]
  exact typed

theorem assign_other_read {state next : RuntimeLocals} {binding : SourceLocal}
    (accepted : state.assign slot value = some next)
    (other : binding.slot ≠ slot) : next.readBound binding = state.readBound binding := by
  obtain ⟨declaration,found,mutable,active,typed,update⟩ := assign_update accepted
  rw [update]
  simp only [RuntimeLocals.readBound,RuntimeLocals.read,if_neg other]

end Aurora.SourceBinding.FramePolicyAttachment
