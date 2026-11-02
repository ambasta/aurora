import SourceBinding.RuntimeCalleeExecution
import SourceBinding.RuntimeArgumentCollection
namespace Aurora.SourceBinding

/-- Execute a certified callee body, including its real ret. The body's source
    result is chosen before every caller continuation context. -/
theorem RuntimeCallable.invoke_uniform
    (callable : RuntimeCallable t files root module path)
    (executes : RuntimeCalleeExecutes program nodes callable World ExternalFault)
    (atCall : program caller pc = some (.ordinary callable.target))
    (values : List Value) (ready : RuntimeReadyArguments callable.source.parameters values) :
    ∃ outcome finalSource sourceEvents machineEvents,
      RuntimeStatementsEvaluation (nodes.map (·.source))
        callable.source.context.members callable.source.context.module callable.source.context.path
        callable.source.context.formals callable.source.result
        ⟨[],0,1,callable.source.context.formals.length⟩
        (formalSourceLocals callable.source.parameters (fun index => values[index]?))
        callable.source.parsed.statements callable.identified.details.lexical.lexical.after
        (match outcome with | .value value => .returned value finalSource | .trap fault => .trapped fault finalSource) sourceEvents ∧
      RuntimeCallTraceRelated nodes sourceEvents machineEvents ∧
      ∀ (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault)
        accumulator stack, ∃ final, CallRuns program external
          (.running (activeAt caller saved world (frameState base pc accumulator (values.reverse ++ stack))))
          ([.ordinaryInvoke callable.target values] ++ machineEvents ++ runtimeReturnEvents callable.target outcome) final ∧
          RuntimeCallResult base caller saved world (pc+1) stack outcome final := by
  obtain ⟨bodyOut,se,me,evaluated,trace,terminal,run⟩ := executes values ready
  have invokeStep : ∀ (base : Machine) (saved : List SavedCall) (world : World) accumulator stack,
      callStep (ExternalFault := ExternalFault) program
        (activeAt caller saved world (frameState base pc accumulator (values.reverse++stack))) =
      (.running (activeAt callable.target.id
          (⟨callable.target,caller,CallFrame.ofMachine (frameState base (pc+1) accumulator stack)⟩::saved) world
          ((freshCallFrame values).inject ⟨base.receiver,world⟩)),[.ordinaryInvoke callable.target values]) := by
    intro base saved world accumulator stack
    have collected := collect_runtime_arguments callable.source.parameters values stack ready.length accumulator base pc
    simp only [callStep,activeAt,CallFrame.ofMachine,frameState,atCall]
    change collectArguments false callable.target.parameters.length _ = _ at collected
    simp only [CallFrame.ofMachine,frameState] at collected
    rw [collected]
    rfl
  cases bodyOut with
  | continued state => exact False.elim (terminal state rfl)
  | returned value state =>
    refine ⟨.value value,state,se,me,evaluated,trace,?_⟩
    intro base saved world external accumulator stack
    let fresh := (freshCallFrame values).inject (⟨base.receiver,world⟩ : CallShared World)
    let pushed : SavedCall := ⟨callable.target,caller,CallFrame.ofMachine (frameState base (pc+1) accumulator stack)⟩
    obtain ⟨final,bodyRun,pc',ret,equal⟩ := run ⟨base.receiver,world⟩ (pushed::saved) external
    subst final
    have last : EffectRuns (localProgram program callable.target.id)
        (runtimeBodyFrame fresh state pc' (some value)) []
        (.returned value (runtimeBodyFrame fresh state pc' (some value))) := by
      apply EffectRuns.returned
      simp only [effectStep,runtimeBodyFrame,ret,pureView,step,retainState]
    have completed := bodyRun.trans (last.call_lift (by trivial) (pushed::saved) world external)
    have called := CallRuns.one (external := external) (.local (invokeStep base saved world accumulator stack))
    refine ⟨(finishEffect callable.target.id (pushed::saved) world (.returned value (runtimeBodyFrame fresh state pc' (some value)))).1,?_,?_⟩
    · simpa only [List.map_nil,List.nil_append,finishEffect,returnToCaller,activeAt,runtimeReturnEvents,
        List.append_assoc] using called.trans completed
    · simp only [RuntimeCallResult,finishEffect,returnToCaller,activeAt,pushed,CallFrame.ofMachine,
        frameState,runtimeBodyFrame,fresh,CallFrame.inject]
  | trapped fault state =>
    refine ⟨.trap fault,state,se,me,evaluated,trace,?_⟩
    intro base saved world external accumulator stack
    let pushed : SavedCall := ⟨callable.target,caller,CallFrame.ofMachine (frameState base (pc+1) accumulator stack)⟩
    obtain ⟨final,bodyRun,active,equal,shared⟩ := run ⟨base.receiver,world⟩ (pushed::saved) external
    subst final
    refine ⟨_,?_,active,rfl,shared⟩
    have called := CallRuns.one (external := external) (.local (invokeStep base saved world accumulator stack))
    simpa only [runtimeReturnEvents,List.append_nil] using called.trans bodyRun

end Aurora.SourceBinding
