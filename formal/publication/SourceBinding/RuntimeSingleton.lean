import SourceBinding.RuntimeEvaluation
namespace Aurora.SourceBinding

private theorem effect_singleton_return
    (evaluated : EffectStatements functions response context result before state
      [.returnValue raw] after (.returned value final) events) :
    after = before ∧ final.locals = state.locals ∧
      EffectEvaluation functions response (context.atCursor before) state raw result
        (.value (some value)) final.shared events := by
  cases evaluated with
  | next first rest => cases first
  | returned first tail =>
    cases first with
    | returnValue expression => cases tail; exact ⟨rfl,rfl,expression⟩

private theorem effect_singleton_trap
    (evaluated : EffectStatements functions response context result before state
      [.returnValue raw] after (.stopped (.localFault (.scalar fault)) final) events) :
    after = before ∧ final.locals = state.locals ∧
      EffectEvaluation functions response (context.atCursor before) state raw result
        (.stopped (.localFault (.scalar fault))) final.shared events := by
  cases evaluated with
  | next first rest => cases first
  | stopped first tail =>
    cases first with
    | returnStop expression => cases tail; exact ⟨rfl,rfl,expression⟩
    | returnMissing expression => exact False.elim expression.outcome_typed

theorem runtime_singleton_return_iff :
    RuntimeStatementsEvaluation functions members module path formals result before state
      [.returnValue raw] after (.returned value final) events ↔
    after = before ∧ final = state ∧
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result (.value value) events := by
  constructor
  · intro evaluated
    have initial := effect_singleton_return
      (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])
    refine ⟨initial.1,initial.2.1,?_⟩
    intro World ExternalFault response shared
    exact (effect_singleton_return (evaluated World ExternalFault response shared [])).2.2
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
    have initial := effect_singleton_trap
      (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])
    refine ⟨initial.1,initial.2.1,?_⟩
    intro World ExternalFault response shared
    exact (effect_singleton_trap (evaluated World ExternalFault response shared [])).2.2
  · rintro ⟨rfl,rfl,evaluated⟩
    exact .trapped (.returnFault evaluated) .nil

/-- Any actual singleton return derivation returns or traps at its expression;
    continuing normally is impossible, without a readiness assumption. -/
theorem runtime_singleton_cases
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result before state
      [.returnValue raw] after outcome events) :
    ∃ expressionOutcome,
      RuntimeEvaluation functions (runtimeStatementContext members module path formals before)
        state raw result expressionOutcome events ∧ after = before ∧
      outcome = match expressionOutcome with
        | .value value => .returned value state
        | .trap fault => .trapped fault state := by
  cases outcome with
  | continued final =>
    have actual := evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ []
    generalize traceEq : events.map (RuntimeSourceEvent.toEffect (World := PUnit) (ExternalFault := PUnit)) = actualEvents at actual
    cases actual with
    | next first rest => cases first
  | returned value final =>
    obtain ⟨endpoint,stateEq,expression⟩ := runtime_singleton_return_iff.mp evaluated
    cases stateEq
    exact ⟨.value value,expression,endpoint,rfl⟩
  | trapped fault final =>
    obtain ⟨endpoint,stateEq,expression⟩ := runtime_singleton_trap_iff.mp evaluated
    cases stateEq
    exact ⟨.trap fault,expression,endpoint,rfl⟩

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
