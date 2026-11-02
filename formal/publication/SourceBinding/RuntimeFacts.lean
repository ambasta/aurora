import SourceBinding.Stateful
namespace Aurora.SourceBinding

theorem readRuntime_preserves (kind : RuntimeType) (input : Option Value) (value : Value)
    (accepted : readRuntime kind input = .value value) : input = some value := by
  cases kind with
  | scalar kind =>
    cases input with
    | none => cases accepted
    | some original =>
      cases kind <;> cases original <;> simp only [readRuntime,readScalar,reduceCtorEq,if_true,if_false] at accepted
      all_goals first | contradiction | (split at accepted <;> cases accepted <;> rfl) | (cases accepted; rfl)
  | nominal identity =>
    cases input with
    | none => cases accepted
    | some original =>
      cases original <;> simp only [readRuntime] at accepted
      all_goals first | contradiction | (split at accepted <;> cases accepted <;> rfl)

theorem readRuntime_typed (kind : RuntimeType) (input : Option Value) (value : Value)
    (accepted : readRuntime kind input = .value value) :
    readRuntime kind (some value) = .value value := by
  rw [readRuntime_preserves kind input value accepted] at accepted
  exact accepted

/-- The old signed-12 numerical behavior is recovered exactly from the shared
    finite-count operation; no source or machine-entry premise was added. -/
theorem leftShift_twelve (word : Nat) :
    binaryValue .leftShift (.word word) .signedCount12 =
      if word < wordLimit then
        if word * 4096 < wordLimit then .value (.word (word * 4096)) else .trap .overflow
      else .trap .range := rfl

theorem checkedAdd_words (left right : Nat) :
    binaryValue .add (.word left) (.word right) =
      if left < wordLimit ∧ right < wordLimit then
        if left + right < wordLimit then .value (.word (left + right)) else .trap .overflow
      else .trap .range := rfl

theorem readRuntime_nominal_closed (identity : NominalIdentity) (input : Option Value) (value : Value)
    (accepted : readRuntime (.nominal identity) input = .value value) :
    ∃ ordinal, ordinal < identity.cases ∧ value = .nominal identity.name ordinal := by
  cases input with
  | none => cases accepted
  | some original =>
    cases original with
    | nominal name ordinal =>
      simp only [readRuntime] at accepted
      split at accepted
      next valid =>
        cases accepted
        exact ⟨ordinal,valid.2,by rw [valid.1]⟩
      next => cases accepted
    | word _ | boolean _ | signedCount4 | signedCount12 | signedCount32 => cases accepted

theorem RuntimeLocals.enter_wellFormed (state : RuntimeLocals) (valid : state.WellFormed) :
    state.enter.WellFormed := by
  rcases valid with ⟨unique,scopes,declared,values⟩
  refine ⟨List.nodup_cons.mpr ⟨?_,unique⟩,?_,?_,?_⟩
  · intro present
    exact Nat.lt_irrefl _ (scopes _ present)
  · intro scope present
    rcases List.mem_cons.mp present with rfl | old
    · exact Nat.lt_succ_self _
    · exact Nat.lt_trans (scopes _ old) (Nat.lt_succ_self _)
  · intro slot declaration present
    exact Nat.lt_trans (declared _ _ present) (Nat.lt_succ_self _)
  · exact values

theorem RuntimeLocals.leave_wellFormed (state : RuntimeLocals) (valid : state.WellFormed) :
    state.leave.WellFormed := by
  rcases valid with ⟨unique,scopes,declared,values⟩
  refine ⟨unique.tail,?_,declared,values⟩
  intro scope present
  exact scopes _ (List.mem_of_mem_tail present)

theorem RuntimeLocals.leave_hides (state : RuntimeLocals) (valid : state.WellFormed)
    (slot : Nat) (declaration : RuntimeLocalDecl) (tail : List Nat)
    (active : state.scopes = declaration.scope :: tail)
    (declared : state.declarations slot = some declaration) :
    state.leave.read slot = .trap .type := by
  have absent : declaration.scope ∉ tail := (List.nodup_cons.mp (active ▸ valid.1)).1
  simp only [RuntimeLocals.read,RuntimeLocals.leave,declared,active,List.tail_cons,if_neg absent]

theorem RuntimeLocals.leave_enter_hides (state : RuntimeLocals) (valid : state.WellFormed)
    (slot : Nat) (declaration : RuntimeLocalDecl) (tail : List Nat)
    (active : state.scopes = declaration.scope :: tail)
    (declared : state.declarations slot = some declaration) :
    state.leave.enter.read slot = .trap .type := by
  have absent : declaration.scope ∉ tail := (List.nodup_cons.mp (active ▸ valid.1)).1
  have old : declaration.scope < state.nextScope := valid.2.2.1 slot declaration declared
  have notCurrent : declaration.scope ≠ state.nextScope := Nat.ne_of_lt old
  have invisible : declaration.scope ∉ state.nextScope :: tail := by
    intro present
    rcases List.mem_cons.mp present with same | wasActive
    · exact notCurrent same
    · exact absent wasActive
  simp only [RuntimeLocals.read,RuntimeLocals.enter,RuntimeLocals.leave,declared,active,
    List.tail_cons,if_neg invisible]

theorem RuntimeLocals.assign_metadata (state next : RuntimeLocals) (slot : Nat) (value : Value)
    (accepted : state.assign slot value = some next) :
    next.declarations = state.declarations ∧ next.scopes = state.scopes ∧ next.nextScope = state.nextScope := by
  unfold RuntimeLocals.assign at accepted
  cases found : state.declarations slot with
  | none => simp [found] at accepted
  | some declaration =>
    simp only [found,bind,Option.bind] at accepted
    split at accepted
    next => cases accepted
    next =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp [checked] at accepted
      | value result =>
        simp only [checked,Option.some.injEq] at accepted
        subst next
        exact ⟨rfl,rfl,rfl⟩

theorem RuntimeLocals.assign_wellFormed (state next : RuntimeLocals) (slot : Nat) (value : Value)
    (valid : state.WellFormed) (accepted : state.assign slot value = some next) : next.WellFormed := by
  rcases valid with ⟨unique,scopes,declared,values⟩
  unfold RuntimeLocals.assign at accepted
  cases found : state.declarations slot with
  | none => simp [found] at accepted
  | some declaration =>
    simp only [found,bind,Option.bind] at accepted
    split at accepted
    next => cases accepted
    next =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp [checked] at accepted
      | value result =>
        simp only [checked,Option.some.injEq] at accepted
        subst next
        refine ⟨unique,scopes,declared,?_⟩
        intro i stored present
        by_cases same : i = slot
        · subst i
          simp only [if_true,Option.some.injEq] at present
          subst stored
          exact ⟨declaration,found,readRuntime_typed _ _ _ checked⟩
        · exact values i stored (by simpa only [if_neg same] using present)

theorem RuntimeLocals.initialize_wellFormed (state next : RuntimeLocals) (slot : Nat)
    (declaration : RuntimeLocalDecl) (value : Value) (valid : state.WellFormed)
    (accepted : state.initialize slot declaration value = some next) : next.WellFormed := by
  rcases valid with ⟨unique,scopes,declared,values⟩
  unfold RuntimeLocals.initialize at accepted
  split at accepted
  next => cases accepted
  next active =>
    split at accepted
    next => cases accepted
    next fresh =>
      have head : state.scopes.head? = some declaration.scope := Decidable.byContradiction active
      have scopeBound : declaration.scope < state.nextScope :=
        scopes _ (by
          cases shape : state.scopes with
          | nil => simp [shape] at head
          | cons first rest =>
            simp only [shape,List.head?_cons,Option.some.injEq] at head
            subst first
            exact List.mem_cons_self)
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp [checked] at accepted
      | value result =>
        simp only [checked,Option.some.injEq] at accepted
        subst next
        refine ⟨unique,scopes,?_,?_⟩
        · intro i entry present
          by_cases same : i = slot
          · subst i
            simp only [if_true,Option.some.injEq] at present
            subst entry
            exact scopeBound
          · exact declared i entry (by simpa only [if_neg same] using present)
        · intro i stored present
          by_cases same : i = slot
          · subst i
            simp only [if_true,Option.some.injEq] at present
            subst stored
            exact ⟨declaration,by simp only [if_true],readRuntime_typed _ _ _ checked⟩
          · obtain ⟨entry,hasEntry,typed⟩ := values i stored (by simpa only [if_neg same] using present)
            exact ⟨entry,by simpa only [if_neg same] using hasEntry,typed⟩

/-- The actual IR local-store transition preserves accumulator, operand stack,
    arguments and receiver, and emits no receiver-store event. -/
theorem localStore_step (program : EffectProgram) (state : Machine) (kind : RuntimeType)
    (slot : Nat) (value : Value)
    (code : program state.pc = some (.localStore kind slot))
    (typed : readRuntime kind state.accumulator = .value value) :
    effectStep program state = ⟨.next {state with
      pc := state.pc + 1
      locals := fun i => if i = slot then some value else state.locals i},[]⟩ := by
  simp only [effectStep,code,typed]

theorem enumConstant_step (program : EffectProgram) (state : Machine)
    (identity : NominalIdentity) (ordinal : Nat)
    (code : program state.pc = some (.enumConstant identity ordinal))
    (bound : ordinal < identity.cases) :
    effectStep program state = ⟨.next (frameState state (state.pc + 1)
      (some (.nominal identity.name ordinal)) state.stack),[]⟩ := by
  simp only [effectStep,code,readRuntime_nominal identity ordinal bound,finish,retainState]

end Aurora.SourceBinding
