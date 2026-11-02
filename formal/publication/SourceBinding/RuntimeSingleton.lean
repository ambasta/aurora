import SourceBinding.RuntimeEvaluation
namespace Aurora.SourceBinding

theorem runtime_singleton_return_iff :
    RuntimeStatementsEvaluation functions members module path formals result before state
      [.returnValue raw] after (.returned value final) events ↔
    after = before ∧ final = state ∧
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result (.value value) events := by
  constructor
  · intro evaluated
    cases evaluated with
    | next first rest => cases first
    | returned first tail =>
      cases first with
      | returnValue expression => cases tail; exact ⟨rfl,rfl,expression⟩
  · rintro ⟨rfl,rfl,evaluated⟩
    exact .returned (.returnValue evaluated) .nil

theorem runtime_singleton_trap_iff :
    RuntimeStatementsEvaluation functions members module path formals result before state
      [.returnValue raw] after (.trapped fault final) events ↔
    after = before ∧ final = state ∧
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result (.trap fault) events := by
  constructor
  · intro evaluated
    cases evaluated with
    | next first rest => cases first
    | trapped first tail =>
      cases first with
      | returnFault expression => cases tail; exact ⟨rfl,rfl,expression⟩
  · rintro ⟨rfl,rfl,evaluated⟩
    exact .trapped (.returnFault evaluated) .nil

theorem RuntimeSourceLeaf.initial_context (leaf : RuntimeSourceLeaf) :
    runtimeStatementContext leaf.context.members leaf.context.module leaf.context.path leaf.context.formals
      ⟨[],0,1,leaf.context.formals.length⟩ = leaf.context := by
  unfold runtimeStatementContext
  rw [← leaf.visible]

/-- Exact old call introduction, including arbitrary nested calls in the leaf
    body. This is not the certified call-free construction's empty-env shortcut. -/
theorem RuntimeEvaluatesWith.callValue (member : leaf ∈ functions) (resolves : leaf.Resolves context name)
    (args : RuntimeArgumentsEvaluateWith functions context state sources leaf.parameters (.value values) argumentEvents)
    (body : RuntimeEvaluatesWith functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
      leaf.raw leaf.result (.value value) bodyEvents) :
    RuntimeEvaluatesWith functions context state (.call (.named name) sources) leaf.result (.value value)
      (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents ++ [.returned leaf.key value]) := by
  apply RuntimeEvaluation.callValue (leaf := leaf.toFunction) (functions := functions.map RuntimeSourceLeaf.toFunction) (List.mem_map.mpr ⟨leaf,member,rfl⟩) resolves args
  rw [leaf.toFunction_body]
  apply runtime_singleton_return_iff.mpr
  exact ⟨rfl,rfl,by simpa only [RuntimeSourceLeaf.toFunction,leaf.initial_context] using body⟩

theorem RuntimeEvaluatesWith.callFault (member : leaf ∈ functions) (resolves : leaf.Resolves context name)
    (args : RuntimeArgumentsEvaluateWith functions context state sources leaf.parameters (.value values) argumentEvents)
    (body : RuntimeEvaluatesWith functions leaf.context (formalSourceLocals leaf.parameters (fun index => values[index]?))
      leaf.raw leaf.result (.trap fault) bodyEvents) :
    RuntimeEvaluatesWith functions context state (.call (.named name) sources) leaf.result (.trap fault)
      (argumentEvents ++ [.invoke leaf.key values] ++ bodyEvents) := by
  apply RuntimeEvaluation.callFault (leaf := leaf.toFunction) (functions := functions.map RuntimeSourceLeaf.toFunction) (List.mem_map.mpr ⟨leaf,member,rfl⟩) resolves args
  rw [leaf.toFunction_body]
  apply runtime_singleton_trap_iff.mpr
  exact ⟨rfl,rfl,by simpa only [RuntimeSourceLeaf.toFunction,leaf.initial_context] using body⟩

end Aurora.SourceBinding
