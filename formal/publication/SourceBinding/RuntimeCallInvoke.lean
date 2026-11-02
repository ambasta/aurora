import SourceBinding.RuntimeCallExecution
namespace Aurora.SourceBinding

def runtimeReturnEvents (target : OrdinaryDescriptor) : Outcome Value → List (CallEvent World ExternalFault)
  | .value value => [.ordinaryReturn target value]
  | .trap _ => []

theorem collect_runtime_arguments (kinds : List RuntimeType) (values stack : List Value)
    (size : kinds.length = values.length) (accumulator : Option Value) (base : Machine) (pc : Nat) :
    collectArguments false kinds.length
      (CallFrame.ofMachine (frameState base pc accumulator (values.reverse ++ stack))) = some (values,stack) := by
  have enough : kinds.length ≤ (values.reverse ++ stack).length := by simp only [List.length_append,List.length_reverse]; omega
  have taken : (values.reverse ++ stack).take kinds.length = values.reverse := by
    rw [size]; simpa only [List.length_reverse] using (List.take_left (l₁ := values.reverse) (l₂ := stack))
  have dropped : (values.reverse ++ stack).drop kinds.length = stack := by
    rw [size]; simpa only [List.length_reverse] using (List.drop_left (l₁ := values.reverse) (l₂ := stack))
  simp only [collectArguments,Bool.false_and,Bool.false_eq_true,if_false,CallFrame.ofMachine,frameState,
    if_pos enough,taken,dropped,List.reverse_reverse]

/-- The invocation consumes only its actual argument prefix. A successful
    selected leaf restores every saved caller cell and residual operand;
    a failing leaf remains the active frame, with no fabricated return event. -/
theorem RuntimeCallLeaf.invoke
    (leaf : RuntimeCallLeaf t files root module path) (program : CallProgram)
    (projection : localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (atCall : program caller pc = some (.ordinary leaf.target))
    (base : Machine) (values : List Value) (ready : RuntimeReadyArguments leaf.source.parameters values)
    (saved : List SavedCall) (world : World)
    (external : ExternalRelation World ExternalFault) (functions : List RuntimeSourceLeaf) :
    ∃ outcome,
      RuntimeEvaluatesWith functions leaf.source.context
        (formalSourceLocals leaf.source.parameters (fun index => values[index]?))
        leaf.source.raw leaf.source.result outcome [] ∧
      ∀ accumulator stack, ∃ final, CallRuns program external
        (.running (activeAt caller saved world (frameState base pc accumulator (values.reverse ++ stack))))
        ([.ordinaryInvoke leaf.target values] ++ runtimeReturnEvents leaf.target outcome) final ∧
      RuntimeCallResult base caller saved world (pc+1) stack outcome final := by
  let shared : CallShared World := ⟨base.receiver,world⟩
  let fresh := (freshCallFrame values).inject shared
  obtain ⟨outcome,result,evaluated,bodyRun,related⟩ := leaf.body.executes fresh ready.entry
  have support := related.supported evaluated.supported
  have initial : preparedEntry fresh runtimeParameterSlot 0 = fresh := rfl
  rw [initial,← projection] at bodyRun
  refine ⟨outcome,evaluated.in_environment functions,?_⟩
  intro accumulator stack
  let continuation : CallFrame := CallFrame.ofMachine (frameState base (pc+1) accumulator stack)
  let pushed : SavedCall := ⟨leaf.target,caller,continuation⟩
  have collected := collect_runtime_arguments leaf.source.parameters values stack ready.length accumulator base pc
  have called : callStep (ExternalFault := ExternalFault) program
      (activeAt caller saved world (frameState base pc accumulator (values.reverse ++ stack))) =
      (.running (activeAt leaf.target.id (pushed::saved) world ((freshCallFrame values).inject shared)),
        [.ordinaryInvoke leaf.target values]) := by
    simp only [callStep,activeAt,CallFrame.ofMachine,frameState,atCall]
    change collectArguments false leaf.target.parameters.length _ = _ at collected
    simp only [CallFrame.ofMachine,frameState] at collected
    rw [collected]
    rfl
  have run := bodyRun.call_lift support (pushed::saved) world external
  have full := (CallRuns.one (external := external) (.local called)).trans run
  cases outcome with
  | value value =>
    cases result with
    | next state | trap fault state => cases related.1
    | returned actual state =>
      have same : actual = value := related.1
      subst actual
      have receiver : state.receiver = base.receiver := by
        simpa only [EffectExecution.state,prepared_receiver,CallFrame.inject,shared,fresh] using related.2.2.1
      refine ⟨(finishEffect leaf.target.id (pushed::saved) world (.returned value state)).1,?_,?_⟩
      · simpa only [finishEffect,returnToCaller,activeAt,runtimeReturnEvents] using full
      · simp only [RuntimeCallResult,finishEffect,returnToCaller,activeAt,pushed,continuation,CallFrame.ofMachine,
          frameState,receiver]
  | trap fault =>
    cases result with
    | next state | returned value state => cases related.1
    | trap actual state =>
      cases actual with
      | assertion => cases related.1
      | scalar actual =>
        have same : actual = fault := related.1
        subst actual
        have receiver : state.receiver = base.receiver := by
          simpa only [EffectExecution.state,prepared_receiver,CallFrame.inject,shared,fresh] using related.2.2.1
        refine ⟨.trapped (.local (.scalar fault)) (activeAt leaf.target.id (pushed::saved) world state),?_,
          activeAt leaf.target.id (pushed::saved) world state,rfl,?_⟩
        · simpa only [finishEffect,runtimeReturnEvents] using full
        · change CallShared.mk state.receiver world = _
          rw [receiver]

end Aurora.SourceBinding
