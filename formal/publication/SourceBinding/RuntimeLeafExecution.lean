import SourceBinding.RuntimeCalleeExecution
import SourceBinding.RuntimeCallLeafProof
import SourceBinding.RuntimeSingleton
namespace Aurora.SourceBinding

private theorem singleton_scope (proof : ScopedStatements members module path formals before statements after items)
    (same : statements = [.returnValue raw]) : after = before := by
  subst statements
  cases proof with
  | cons first tail => cases first; cases tail; rfl

private theorem machine_ext (a b : Machine) (pc : a.pc = b.pc)
    (acc : a.accumulator = b.accumulator) (stack : a.stack = b.stack)
    (locals : a.locals = b.locals) (receiver : a.receiver = b.receiver)
    (arguments : a.arguments = b.arguments) : a = b := by
  cases a; cases b; simp_all

/-- The old complete singleton certificate supplies the internal generic callee
    hypothesis constructively. No membership, rank, or callee result is assumed. -/
theorem RuntimeCallLeaf.callee_executes
    (leaf : RuntimeCallLeaf t files root module path) (program : CallProgram)
    (projection : localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (nodes : List (RuntimeCallable t files root module path)) :
    RuntimeCalleeExecutes program nodes leaf.toCallable World ExternalFault := by
  intro values ready
  let seed : Machine := ⟨0,none,[],fun _ => none,fun _ => none,fun index => values[index]?⟩
  let source := formalRuntimeLocals leaf.body.parameters.kinds seed
  have bound := runtime_formal_bindings (base := seed) leaf.body.valid leaf.body.parameters.grammar rfl
  obtain ⟨outcome,evaluated,run⟩ := leaf.body.expression.evaluates_uniform source bound
  have globalEval := RuntimeEvaluation.in_environment evaluated (nodes.map (·.source))
  have after : leaf.identified.details.lexical.lexical.after =
      (⟨[],0,1,leaf.source.context.formals.length⟩ : LocalContext) := by
    exact singleton_scope leaf.identified.details.lexical.lexical.grammar leaf.body.source
  have sourceContext := leaf.source.initial_context
  cases outcome with
  | value value =>
    refine ⟨.returned value source,[],[],?_,.nil,?_,?_⟩
    · change RuntimeStatementsEvaluation _ _ _ _ _ _ _ source _ _ _ _
      simp only [RuntimeCallLeaf.toCallable_source, RuntimeSourceLeaf.toFunction]
      rw [leaf.source.singleton]
      apply runtime_singleton_return_iff.mpr
      exact ⟨after,rfl,by simpa only [sourceContext] using globalEval⟩
    · intro state impossible; cases impossible
    · intro shared saved external
      let base := (freshCallFrame values).inject shared
      let prepared := preparedEntry base runtimeParameterSlot leaf.body.parameters.kinds.length
      have actual := run prepared (formal_prepared_values _ base) none []
      change EffectRuns _ (frameState (preparedEntry base runtimeParameterSlot leaf.body.parameters.kinds.length) _ none []) [] _ at actual
      rw [prepared_frame] at actual
      have entryRun := runtime_entry_runs leaf.body.entry base ready.entry
      have full := entryRun.trans actual
      rw [← projection] at full
      have lifted := full.call_lift (by trivial) saved shared.world external
      refine ⟨.running (activeAt leaf.target.id saved shared.world (frameState prepared leaf.body.stop (some value) [])),?_,?_⟩
      · simpa only [List.map_nil,List.nil_append,finishEffect] using lifted
      · refine ⟨leaf.body.stop,?_,?_⟩
        · change localProgram program leaf.target.id leaf.body.stop = _
          rw [projection]; exact leaf.body.returns
        · congr 2
          apply machine_ext <;> simp only [frameState,runtimeBodyFrame,prepared,base,
            prepared_receiver,prepared_arguments,freshCallFrame,CallFrame.inject]
          funext slot
          exact formal_prepared_values _ base slot
  | trap fault =>
    refine ⟨.trapped fault source,[],[],?_,.nil,?_,?_⟩
    · change RuntimeStatementsEvaluation _ _ _ _ _ _ _ source _ _ _ _
      simp only [RuntimeCallLeaf.toCallable_source, RuntimeSourceLeaf.toFunction]
      rw [leaf.source.singleton]
      apply runtime_singleton_trap_iff.mpr
      exact ⟨after,rfl,by simpa only [sourceContext] using globalEval⟩
    · intro state impossible; cases impossible
    · intro shared saved external
      let base := (freshCallFrame values).inject shared
      let prepared := preparedEntry base runtimeParameterSlot leaf.body.parameters.kinds.length
      obtain ⟨final,actual,locals,receiver,arguments⟩ := run prepared (formal_prepared_values _ base) none []
      rw [prepared_frame] at actual
      have entryRun := runtime_entry_runs leaf.body.entry base ready.entry
      have full := entryRun.trans actual
      rw [← projection] at full
      have supported : LocalSupported (.trap (.scalar fault) final) := by
        have supported := evaluated.supported
        cases fault <;> first | trivial | exact supported
      have lifted := full.call_lift supported saved shared.world external
      refine ⟨.trapped (.local (.scalar fault)) (activeAt leaf.target.id saved shared.world final),?_,?_⟩
      · simpa only [List.map_nil,List.nil_append,finishEffect] using lifted
      · refine ⟨_,rfl,?_⟩
        change (⟨final.receiver,shared.world⟩ : CallShared World) = _
        rw [receiver]
        simp only [prepared,prepared_receiver,base,CallFrame.inject]

end Aurora.SourceBinding
