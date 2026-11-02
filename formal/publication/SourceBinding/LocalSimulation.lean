import SourceBinding.RuntimeFacts
namespace Aurora.SourceBinding

def LocalsRelated (source : RuntimeLocals) (machine : Machine) : Prop :=
  ∀ slot, machine.locals slot = source.values slot

private theorem initialized_values (source next : RuntimeLocals) (slot : Nat)
    (declaration : RuntimeLocalDecl) (value : Value)
    (accepted : source.initialize slot declaration value = some next) :
    readRuntime declaration.kind (some value) = .value value ∧
    next.values = (fun i => if i = slot then some value else source.values i) := by
  unfold RuntimeLocals.initialize at accepted
  split at accepted
  next => cases accepted
  next =>
    split at accepted
    next => cases accepted
    next =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp [checked] at accepted
      | value result =>
        have same := Option.some.inj (readRuntime_preserves _ _ _ checked)
        subst result
        simp only [checked,Option.some.injEq] at accepted
        subst next
        exact ⟨rfl,rfl⟩

private theorem assigned_values (source next : RuntimeLocals) (slot : Nat) (value : Value)
    (accepted : source.assign slot value = some next) :
    ∃ declaration, source.declarations slot = some declaration ∧
      readRuntime declaration.kind (some value) = .value value ∧
      next.values = (fun i => if i = slot then some value else source.values i) := by
  unfold RuntimeLocals.assign at accepted
  cases found : source.declarations slot with
  | none => simp [found] at accepted
  | some declaration =>
    simp only [found,bind,Option.bind] at accepted
    split at accepted
    next => cases accepted
    next =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp [checked] at accepted
      | value result =>
        have same := Option.some.inj (readRuntime_preserves _ _ _ checked)
        subst result
        simp only [checked,Option.some.injEq] at accepted
        subst next
        exact ⟨declaration,rfl,checked,rfl⟩

/-- This is one primitive source/IR simulation, not a complete body theorem:
    source initialization guards produce the typed value written by the actual
    canonical local-store operation. The RHS has already been evaluated. -/
theorem local_initialization_simulates (source next : RuntimeLocals) (machine : Machine)
    (program : EffectProgram) (slot : Nat) (declaration : RuntimeLocalDecl) (value : Value)
    (valid : source.WellFormed) (related : LocalsRelated source machine)
    (accepted : source.initialize slot declaration value = some next)
    (code : program machine.pc = some (.localStore declaration.kind slot))
    (accumulator : machine.accumulator = some value) :
    next.WellFormed ∧ ∃ final,
      effectStep program machine = ⟨.next final,[]⟩ ∧ LocalsRelated next final ∧
      final.receiver = machine.receiver ∧ final.arguments = machine.arguments ∧
      final.stack = machine.stack ∧ final.accumulator = machine.accumulator := by
  obtain ⟨typed,values⟩ := initialized_values source next slot declaration value accepted
  refine ⟨source.initialize_wellFormed next slot declaration value valid accepted,
    {machine with
      pc := machine.pc + 1
      locals := fun i => if i = slot then some value else machine.locals i},?_,?_,rfl,rfl,rfl,rfl⟩
  · exact localStore_step program machine declaration.kind slot value code (accumulator ▸ typed)
  · intro i
    rw [values]
    change (if i = slot then some value else machine.locals i) = _
    by_cases same : i = slot
    · simp only [if_pos same]
    · simp only [if_neg same,related i]

/-- Reassignment uses source declaration visibility/mutability/initialization,
    not a raw slot flag. The machine performs the same checked local store. -/
theorem local_assignment_simulates (source next : RuntimeLocals) (machine : Machine)
    (program : EffectProgram) (slot : Nat) (declaration : RuntimeLocalDecl) (value : Value)
    (valid : source.WellFormed) (related : LocalsRelated source machine)
    (declared : source.declarations slot = some declaration)
    (accepted : source.assign slot value = some next)
    (code : program machine.pc = some (.localStore declaration.kind slot))
    (accumulator : machine.accumulator = some value) :
    next.WellFormed ∧ ∃ final,
      effectStep program machine = ⟨.next final,[]⟩ ∧ LocalsRelated next final ∧
      final.receiver = machine.receiver ∧ final.arguments = machine.arguments ∧
      final.stack = machine.stack ∧ final.accumulator = machine.accumulator := by
  obtain ⟨actual,found,typed,values⟩ := assigned_values source next slot value accepted
  have same : actual = declaration := Option.some.inj (found.symm.trans declared)
  subst actual
  refine ⟨source.assign_wellFormed next slot value valid accepted,
    {machine with
      pc := machine.pc + 1
      locals := fun i => if i = slot then some value else machine.locals i},?_,?_,rfl,rfl,rfl,rfl⟩
  · exact localStore_step program machine declaration.kind slot value code (accumulator ▸ typed)
  · intro i
    rw [values]
    change (if i = slot then some value else machine.locals i) = _
    by_cases same : i = slot
    · simp only [if_pos same]
    · simp only [if_neg same,related i]

end Aurora.SourceBinding
