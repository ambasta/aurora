import SourceBinding.RuntimeScopeReservation
import SourceBinding.RuntimeFacts
namespace Aurora.SourceBinding

theorem RuntimeLocals.reserve_wellFormed (state : RuntimeLocals) (valid : state.WellFormed)
    (bound : state.nextScope ≤ limit) :
    ({state with nextScope := limit} : RuntimeLocals).WellFormed := by
  rcases valid with ⟨unique,active,declared,values⟩
  exact ⟨unique,fun scope present => Nat.lt_of_lt_of_le (active scope present) bound,
    fun slot declaration present => Nat.lt_of_lt_of_le (declared slot declaration present) bound,values⟩

theorem RuntimeStateAt.reserve
    (valid : RuntimeStateAt members module path formals before ancestors state)
    (visible : after.visible = before.visible) (scope : after.scope = before.scope)
    (slots : before.nextSlot ≤ after.nextSlot) (scopes : before.nextScope ≤ after.nextScope) :
    ∃ next, state.reserveScopes after.nextScope = some next ∧
      RuntimeStateAt members module path formals after ancestors next ∧
      next.declarations = state.declarations ∧ next.values = state.values ∧ next.scopes = state.scopes := by
  rcases valid with ⟨wf,active,cursor,bindings,initialized,fresh⟩
  have bound : state.nextScope ≤ after.nextScope := cursor ▸ scopes
  refine ⟨{state with nextScope := after.nextScope},by simp only [RuntimeLocals.reserveScopes,if_pos bound],
    ?_,rfl,rfl,rfl⟩
  refine ⟨state.reserve_wellFormed wf bound,?_,rfl,?_,?_,?_⟩
  · simpa only [scope] using active
  · simpa only [runtimeStatementContext,visible] using bindings
  · simpa only [runtimeStatementContext,visible] using initialized
  · intro slot lower
    exact fresh slot (by omega)

theorem RuntimeStateAt.enter
    (valid : RuntimeStateAt members module path formals before ancestors state) :
    state.enterAt before.nextScope = some state.enter ∧
    RuntimeStateAt members module path formals (enterLocalScope before) (before.scope::ancestors) state.enter := by
  rcases valid with ⟨wf,active,cursor,bindings,initialized,fresh⟩
  refine ⟨by simp only [RuntimeLocals.enterAt,cursor,if_pos],state.enter_wellFormed wf,?_,?_,?_,?_,?_⟩
  · simp only [RuntimeLocals.enter,enterLocalScope,cursor,active]
  · simp only [RuntimeLocals.enter,enterLocalScope,cursor]
  · intro name binding present
    obtain ⟨declared,wasActive⟩ := bindings name binding present
    exact ⟨declared,List.mem_cons_of_mem _ wasActive⟩
  · exact initialized
  · exact fresh

/-- Static cursor extension never renames a visible binding. This lemma only
    handles metadata; actual initialized values remain a separate invariant. -/
theorem RuntimeVariableBinding.restrict_visible
    (binding : RuntimeVariableBinding (runtimeStatementContext members module path formals after) name declared)
    (visible : after.visible = before.visible) :
    RuntimeVariableBinding (runtimeStatementContext members module path formals before) name declared := by
  simpa only [runtimeStatementContext,visible] using binding

/-- Values and declarations for a fresh local are installed only after its
    actual initializer produced a value of the declared runtime type. -/
theorem RuntimeStateAt.initialize
    (valid : RuntimeStateAt members module path formals before ancestors state)
    (typed : readRuntime kind (some value) = .value value) :
    ∃ next, state.initialize (8*(before.nextSlot+1)) ⟨kind,mutable,before.scope⟩ value = some next ∧
      RuntimeStateAt members module path formals
        (addLocal before (declaredLocal before name kind mutable)) ancestors next ∧
      next.values = (fun i => if i=8*(before.nextSlot+1) then some value else state.values i) := by
  rcases valid with ⟨wf,active,cursor,bindings,initialized,fresh⟩
  let slot := 8*(before.nextSlot+1)
  let binding := declaredLocal before name kind mutable
  let declaration : RuntimeLocalDecl := ⟨kind,mutable,before.scope⟩
  obtain ⟨emptyDecl,emptyValue⟩ := fresh slot (Nat.le_refl _)
  let next : RuntimeLocals := {state with
    declarations := fun i => if i=slot then some declaration else state.declarations i
    values := fun i => if i=slot then some value else state.values i}
  have accepted : state.initialize slot declaration value = some next := by
    simp only [RuntimeLocals.initialize,next,active,List.head?_cons,declaration,ne_eq,not_true_eq_false,if_false,
      emptyDecl,emptyValue,or_self,typed]
  have oldNotFresh : ∀ n old, RuntimeVariableBinding (runtimeStatementContext members module path formals before) n old → old.slot ≠ slot := by
    intro n old found equal
    have declared := (bindings n old found).1
    rw [equal,emptyDecl] at declared
    cases declared
  have transferred : ∀ n old,
      RuntimeVariableBinding (runtimeStatementContext members module path formals before) n old →
      next.declarations old.slot = some old.runtimeDeclaration ∧ old.scope ∈ next.scopes ∧
      ∃ v, next.values old.slot = some v ∧ readRuntime old.kind (some v) = .value v := by
    intro n old found
    obtain ⟨declared,live⟩ := bindings n old found
    obtain ⟨v,present,typed⟩ := initialized n old found
    have different := oldNotFresh n old found
    exact ⟨by simp only [next,if_neg different,declared],live,v,by simp only [next,if_neg different,present],typed⟩
  refine ⟨next,accepted,⟨state.initialize_wellFormed next slot declaration value wf accepted,active,cursor,?_,?_,?_⟩,rfl⟩
  · intro n old found
    cases found with
    | formal present named typ clear =>
      have prior : RuntimeVariableBinding (runtimeStatementContext members module path formals before) n _ :=
        .formal present named typ (fun bad => clear (List.mem_cons_of_mem _ bad))
      exact ⟨(transferred n _ prior).1,(transferred n _ prior).2.1⟩
    | localValue present named clear =>
      rcases List.mem_cons.mp present with same | oldPresent
      · subst old
        exact ⟨by simp only [next,declaredLocal,SourceLocal.runtimeDeclaration,slot,declaration,if_true],
          by rw [active]; exact List.mem_cons_self⟩
      · exact ⟨(transferred n _ (.localValue oldPresent named clear)).1,
          (transferred n _ (.localValue oldPresent named clear)).2.1⟩
  · intro n old found
    cases found with
    | formal present named typ clear =>
      exact (transferred n _ (.formal present named typ (fun bad => clear (List.mem_cons_of_mem _ bad)))).2.2
    | localValue present named clear =>
      rcases List.mem_cons.mp present with same | oldPresent
      · subst old
        exact ⟨value,by simp only [next,declaredLocal,slot,if_true],typed⟩
      · exact (transferred n _ (.localValue oldPresent named clear)).2.2
  · intro i lower
    have different : i ≠ slot := by simp only [addLocal] at lower; omega
    have prior := fresh i (by simp only [addLocal] at lower; omega)
    exact ⟨by simpa only [next,if_neg different] using prior.1,
      by simpa only [next,if_neg different] using prior.2⟩

theorem RuntimeStateAt.assign
    (valid : RuntimeStateAt members module path formals cursor ancestors state)
    (found : RuntimeVariableBinding (runtimeStatementContext members module path formals cursor) name binding)
    (mutable : binding.mutable = true)
    (typed : readRuntime binding.kind (some value) = .value value) :
    ∃ next, state.assign binding.slot value = some next ∧
      RuntimeStateAt members module path formals cursor ancestors next ∧
      next.values = (fun i => if i=binding.slot then some value else state.values i) := by
  rcases valid with ⟨wf,active,position,bindings,initialized,fresh⟩
  obtain ⟨declared,live⟩ := bindings name binding found
  obtain ⟨old,hasOld,_⟩ := initialized name binding found
  let next : RuntimeLocals := {state with values := fun i => if i=binding.slot then some value else state.values i}
  have accepted : state.assign binding.slot value = some next := by
    simp only [RuntimeLocals.assign,declared,bind,Option.bind,SourceLocal.runtimeDeclaration,
      mutable,ne_eq,not_true_eq_false,live,not_true_eq_false,hasOld,reduceCtorEq,or_self,if_false,typed]
    rfl
  have nextWF := state.assign_wellFormed next binding.slot value wf accepted
  refine ⟨next,accepted,⟨nextWF,active,position,bindings,?_,?_⟩,rfl⟩
  · intro n item present
    obtain ⟨oldValue,oldPresent,_⟩ := initialized n item present
    have existsValue : ∃ v, next.values item.slot = some v := by
      by_cases same : item.slot = binding.slot
      · exact ⟨value,by simp only [next,if_pos same]⟩
      · exact ⟨oldValue,by simp only [next,if_neg same,oldPresent]⟩
    obtain ⟨v,valueEq⟩ := existsValue
    obtain ⟨decl,declEq,typeEq⟩ := nextWF.2.2.2 item.slot v valueEq
    have named := (bindings n item present).1
    have same : decl = item.runtimeDeclaration := Option.some.inj (declEq.symm.trans named)
    subst decl
    exact ⟨v,valueEq,typeEq⟩
  · intro i lower
    obtain ⟨noneDecl,noneValue⟩ := fresh i lower
    have different : i ≠ binding.slot := by
      intro same
      rw [same,declared] at noneDecl
      cases noneDecl
    exact ⟨noneDecl,by simp only [next,if_neg different,noneValue]⟩

end Aurora.SourceBinding
