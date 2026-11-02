import SourceBinding.RuntimeStateFacts
import SourceBinding.RuntimeEntry
namespace Aurora.SourceBinding

theorem formal_runtime_value (bound : index < kinds.length) :
    (formalRuntimeLocals kinds base).values (runtimeParameterSlot index) = base.arguments index := by
  have remainder : runtimeParameterSlot index % 8 = 0 := by unfold runtimeParameterSlot; omega
  have positive : 0 < runtimeParameterSlot index := by unfold runtimeParameterSlot; omega
  have quotient : runtimeParameterSlot index / 8 - 1 = index := by unfold runtimeParameterSlot; omega
  simp only [formalRuntimeLocals,formalSourceLocals,remainder,positive,quotient,bound,and_self,if_true]

theorem formal_runtime_wellFormed (arguments : RuntimeEntryArguments kinds base.arguments) :
    (formalRuntimeLocals kinds base).WellFormed := by
  refine ⟨by change ([0] : List Nat).Nodup; decide,?_,?_,?_⟩
  · intro scope present
    simp only [formalRuntimeLocals,formalSourceLocals,List.mem_singleton] at present
    subst scope
    exact Nat.zero_lt_succ _
  · intro slot declaration present
    simp only [formalRuntimeLocals,formalSourceLocals] at present
    split at present
    next shape =>
      cases found : kinds[slot/8-1]? with
      | none => simp only [found,Option.map_none] at present; cases present
      | some kind =>
        simp only [found,Option.map_some,Option.some.injEq] at present
        subst declaration
        exact Nat.zero_lt_succ _
    next => cases present
  · intro slot value present
    simp only [formalRuntimeLocals,formalSourceLocals] at present
    split at present
    next shape =>
      let kind := kinds[slot/8-1]'shape.2.2
      have found : kinds[slot/8-1]? = some kind := List.getElem?_eq_some_iff.mpr ⟨shape.2.2,rfl⟩
      obtain ⟨actual,argumentEq,typed⟩ := arguments (slot/8-1) kind found
      have same : actual = value := Option.some.inj (argumentEq.symm.trans present)
      subst actual
      refine ⟨⟨kind,false,0⟩,?_,typed⟩
      have admissible : slot % 8 = 0 ∧ 0 < slot := ⟨shape.1,shape.2.1⟩
      simp only [formalRuntimeLocals,formalSourceLocals,if_pos admissible,found,Option.map_some]
    next => cases present

theorem runtime_initial_state
    (valid : RuntimeContextValid ⟨members,module,path,formals,[]⟩)
    (signature : RuntimeSignature t members module path first (formals.map (·.type)) kinds)
    (arguments : RuntimeEntryArguments kinds base.arguments) :
    RuntimeStateAt members module path formals ⟨[],0,1,formals.length⟩ [] (formalRuntimeLocals kinds base) := by
  have sizes : kinds.length = formals.length := by simpa only [List.length_map] using signature.length
  refine ⟨formal_runtime_wellFormed arguments,rfl,rfl,runtime_formal_bindings valid signature rfl,?_,?_⟩
  · intro name binding found
    cases found with
    | formal present named typ clear =>
      have sourceAt := congrArg (Option.map (·.type)) present
      rw [← List.getElem?_map] at sourceAt
      obtain ⟨kind,kindAt,declared⟩ := signature.lookup sourceAt
      have same := typ.unique valid.scope declared
      subst kind
      obtain ⟨value,valueEq,typed⟩ := arguments _ _ kindAt
      refine ⟨value,?_,typed⟩
      exact (formal_runtime_value (List.getElem?_eq_some_iff.mp kindAt).1).trans valueEq
    | localValue present _ _ => cases present
  · intro slot lower
    change 8*(formals.length+1) ≤ slot at lower
    have missing : kinds[slot/8-1]? = none := List.getElem?_eq_none (by omega)
    constructor
    · simp only [formalRuntimeLocals,formalSourceLocals]
      split <;> simp only [missing,Option.map_none]
    · simp only [formalRuntimeLocals,formalSourceLocals]
      split
      next shape => omega
      next => rfl

end Aurora.SourceBinding
