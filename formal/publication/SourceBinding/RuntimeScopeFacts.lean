import SourceBinding.RuntimeStateFacts
import SourceBinding.LocalCursorFacts
namespace Aurora.SourceBinding

theorem RuntimeVariableBinding.extend_visible
    (found : RuntimeVariableBinding (runtimeStatementContext members module path formals before) name binding)
    (included : ∀ item ∈ before.visible, item ∈ after.visible)
    (clear : ∀ item ∈ after.visible, item.name ∉ formals.map (·.name)) :
    RuntimeVariableBinding (runtimeStatementContext members module path formals after) name binding := by
  cases found with
  | formal present named typ absent =>
    refine .formal present named typ ?_
    intro overlap
    obtain ⟨item,itemPresent,itemName⟩ := List.mem_map.mp overlap
    have declarationPresent := List.getElem?_eq_some_iff.mp present
    have formalMember := List.mem_iff_getElem.mpr ⟨_,declarationPresent.1,declarationPresent.2⟩
    exact clear item itemPresent (List.mem_map.mpr ⟨_,formalMember,named.trans itemName.symm⟩)
  | localValue present named absent => exact .localValue (included _ present) named absent

/-- A normal branch exit hides its locals but retains their bytes. The prior
    state supplies only scope-age facts; current values come from the completed
    branch state, so assignments are not rolled back. -/
theorem RuntimeStateAt.leave_restore
    (beforeValid : RuntimeStateAt members module path formals before ancestors initial)
    (bodyScope : ScopedStatements members module path formals (enterLocalScope before) body child declaredItems)
    (clear : ∀ item ∈ child.visible, item.name ∉ formals.map (·.name))
    (finished : RuntimeStateAt members module path formals child (before.scope::ancestors) state) :
    RuntimeStateAt members module path formals (leaveLocalScope before child) ancestors state.leave := by
  rcases finished with ⟨wf,active,cursor,bindings,initialized,fresh⟩
  have included : ∀ item ∈ before.visible, item ∈ child.visible := bodyScope.visible_subset
  have childScope : child.scope = before.nextScope := bodyScope.scope_eq
  refine ⟨state.leave_wellFormed wf,?_,cursor,?_,?_,fresh⟩
  · simp only [RuntimeLocals.leave,active,List.tail_cons,leaveLocalScope]
  · intro name binding present
    have prior : RuntimeVariableBinding (runtimeStatementContext members module path formals before) name binding := present.restrict_visible rfl
    have extended := prior.extend_visible included clear
    obtain ⟨declared,live⟩ := bindings name binding extended
    have oldDeclared := (beforeValid.2.2.2.1 name binding prior).1
    have age := beforeValid.1.2.2.1 binding.slot binding.runtimeDeclaration oldDeclared
    have different : binding.scope ≠ child.scope := by
      rw [childScope]
      change binding.scope < initial.nextScope at age
      rw [beforeValid.2.2.1] at age
      exact Nat.ne_of_lt age
    refine ⟨declared,?_⟩
    rw [active] at live
    rcases List.mem_cons.mp live with same | parent
    · exact False.elim (different same)
    · simpa only [RuntimeLocals.leave,active,List.tail_cons] using parent
  · intro name binding present
    have prior : RuntimeVariableBinding (runtimeStatementContext members module path formals before) name binding := present.restrict_visible rfl
    exact initialized name binding (prior.extend_visible included clear)

end Aurora.SourceBinding
