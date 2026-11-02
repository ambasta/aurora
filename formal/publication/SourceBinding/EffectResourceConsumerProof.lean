import SourceBinding.EffectResourceStepProof
import SourceBinding.RuntimeFacts
namespace Aurora.SourceBinding

private theorem initialized_values {state next : RuntimeLocals} {declaration : RuntimeLocalDecl}
    (accepted : state.initialize slot declaration value = some next) :
    next.values = fun index => if index = slot then some value else state.values index := by
  unfold RuntimeLocals.initialize at accepted
  split at accepted
  next => cases accepted
  next active =>
    split at accepted
    next => cases accepted
    next fresh =>
      cases checked : readRuntime declaration.kind (some value) with
      | trap fault => simp only [checked] at accepted; cases accepted
      | value actual =>
        have equal := Option.some.inj (readRuntime_preserves _ _ _ checked)
        cases equal
        simp only [checked,Option.some.injEq] at accepted
        cases accepted
        rfl

private theorem local_store_fault
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {frame : CallFrame} {saved : List SavedCall} {shared : CallShared World}
    (atStore : program caller frame.pc = some (.local (.localStore kind slot)))
    (checked : readRuntime kind frame.accumulator = .trap fault) :
    CallTransition program external (.running ⟨caller,frame,saved,shared⟩) []
      (.trapped (.local (.scalar fault)) ⟨caller,frame,saved,shared⟩) := by
  apply CallTransition.local
  simp only [callStep,atStore,localCallStep,localProgram,effectStep,CallFrame.inject,checked,
    EffectExecution.state,CallFrame.ofMachine,CallShared.commit]
  rfl

private theorem local_store_value
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {frame : CallFrame} {saved : List SavedCall} {shared : CallShared World}
    (atStore : program caller frame.pc = some (.local (.localStore kind slot)))
    (checked : readRuntime kind frame.accumulator = .value value) :
    CallTransition program external (.running ⟨caller,frame,saved,shared⟩) []
      (.running ⟨caller,{frame with pc := frame.pc + 1,locals := fun index => if index = slot then some value else frame.locals index},saved,shared⟩) := by
  apply CallTransition.local
  simp only [callStep,atStore,localCallStep,localProgram,effectStep,CallFrame.inject,checked,
    EffectExecution.state,CallFrame.ofMachine,CallShared.commit]
  rfl

private theorem require_fault
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {frame : CallFrame} {saved : List SavedCall} {shared : CallShared World}
    (atRequire : program caller frame.pc = some (.local .require))
    (checked : assertResult frame.accumulator = some fault) :
    CallTransition program external (.running ⟨caller,frame,saved,shared⟩) []
      (.trapped (.local fault) ⟨caller,frame,saved,shared⟩) := by
  apply CallTransition.local
  have localCode : localProgram program caller frame.pc = some .require := by
    simp only [localProgram,atRequire]
  have stepped := require_assertMachine (localProgram program caller) (frame.inject shared) localCode
  simp only [callStep,atRequire,localCallStep]
  rw [stepped]
  simp only [assertMachine,CallFrame.inject,checked,EffectExecution.state,CallFrame.ofMachine,CallShared.commit]
  rfl

private theorem require_value
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {frame : CallFrame} {saved : List SavedCall} {shared : CallShared World}
    (atRequire : program caller frame.pc = some (.local .require))
    (checked : assertResult frame.accumulator = none) :
    CallTransition program external (.running ⟨caller,frame,saved,shared⟩) []
      (.running ⟨caller,{frame with pc := frame.pc + 1,accumulator := none},saved,shared⟩) := by
  apply CallTransition.local
  have localCode : localProgram program caller frame.pc = some .require := by
    simp only [localProgram,atRequire]
  have stepped := require_assertMachine (localProgram program caller) (frame.inject shared) localCode
  simp only [callStep,atRequire,localCallStep]
  rw [stepped]
  simp only [assertMachine,CallFrame.inject,checked,EffectExecution.state,CallFrame.ofMachine,CallShared.commit]
  rfl

/-- Direct resource initializer, including pending/external fault and malformed
    raw responses. Actual initialize acceptance is source-rule evidence, not a
    public successful-store assumption. The full scoped proof must derive it. -/
theorem SourceResourceInitialize.machine_run
    {state : SourceEffectState World} {response : SourceExternalRelation World ExternalFault}
    {external : ExternalRelation World ExternalFault}
    {ordinary : EffectOrdinaryPairs} {resources : EffectResourcePairs} {fields : EffectFieldPairs}
    {program : CallProgram} {caller : Int} {base : CallFrame} {saved : List SavedCall}
    (evaluated : SourceResourceInitialize response key arguments binding state outcome sourceEvents)
    (paired : (key,target) ∈ resources)
    (related : EffectExternalRelated resources response external)
    (atCall : program caller base.pc = some (.resource target))
    (collected : collectArguments true target.parameters.length base = some (arguments,stack))
    (locals : base.locals = state.locals.values)
    (atStore : program caller (base.pc + 1) = some (.local (.localStore binding.kind binding.slot))) :
    ∃ machineEvents final,
      CallRuns program external (.running ⟨caller,base,saved,state.shared.toCall⟩) machineEvents final ∧
      EffectMachineTraceRelated ordinary resources fields sourceEvents machineEvents ∧
      EffectBodyResult resources program caller saved {base with stack := stack}
        (base.pc + 2) outcome final := by
  cases evaluated with
  | stopped step =>
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    exact ⟨events,final,run,trace,result⟩
  | malformed step checked =>
    rename_i raw after fault
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    cases result
    refine ⟨events,.trapped (.local (.scalar fault))
      ⟨caller,{base with pc := base.pc + 1,accumulator := raw,stack := stack},saved,after.toCall⟩,?_,trace,?_⟩
    · simpa only [List.append_nil] using run.trans (CallRuns.one (local_store_fault atStore checked))
    · exact ⟨_,rfl,rfl⟩
  | initialized step checked installed =>
    rename_i raw after value next
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    cases result
    have values := initialized_values installed
    refine ⟨events,.running ⟨caller,
      {base with pc := base.pc + 2,accumulator := raw,stack := stack,locals := next.values},saved,after.toCall⟩,?_,trace,raw,rfl⟩
    simpa only [List.append_nil,locals,values,Nat.add_assoc] using
      run.trans (CallRuns.one (local_store_value atStore checked))

/-- Direct resource require. A false or malformed response faults at the actual
    consumer, retaining the response's shared state and suspended continuation. -/
theorem SourceResourceAssert.machine_run
    {state : SourceEffectState World} {response : SourceExternalRelation World ExternalFault}
    {external : ExternalRelation World ExternalFault}
    {ordinary : EffectOrdinaryPairs} {resources : EffectResourcePairs} {fields : EffectFieldPairs}
    {program : CallProgram} {caller : Int} {base : CallFrame} {saved : List SavedCall}
    (evaluated : SourceResourceAssert response key arguments state outcome sourceEvents)
    (paired : (key,target) ∈ resources)
    (related : EffectExternalRelated resources response external)
    (atCall : program caller base.pc = some (.resource target))
    (collected : collectArguments true target.parameters.length base = some (arguments,stack))
    (locals : base.locals = state.locals.values)
    (atRequire : program caller (base.pc + 1) = some (.local .require)) :
    ∃ machineEvents final,
      CallRuns program external (.running ⟨caller,base,saved,state.shared.toCall⟩) machineEvents final ∧
      EffectMachineTraceRelated ordinary resources fields sourceEvents machineEvents ∧
      EffectBodyResult resources program caller saved {base with stack := stack}
        (base.pc + 2) outcome final := by
  cases evaluated with
  | stopped step =>
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    exact ⟨events,final,run,trace,result⟩
  | failed step checked =>
    rename_i raw after fault
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    cases result
    refine ⟨events,.trapped (.local fault)
      ⟨caller,{base with pc := base.pc + 1,accumulator := raw,stack := stack},saved,after.toCall⟩,?_,trace,?_⟩
    · simpa only [List.append_nil] using run.trans (CallRuns.one (require_fault atRequire checked))
    · exact ⟨_,rfl,rfl⟩
  | passed step checked =>
    rename_i raw after
    obtain ⟨events,final,run,trace,result⟩ := step.response_run (saved := saved) paired related atCall collected
    cases result
    refine ⟨events,.running ⟨caller,
      {base with pc := base.pc + 2,accumulator := none,stack := stack},saved,after.toCall⟩,?_,trace,none,?_⟩
    · simpa only [List.append_nil,Nat.add_assoc] using run.trans (CallRuns.one (require_value atRequire checked))
    · simp only [locals]

end Aurora.SourceBinding
