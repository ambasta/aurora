import SourceBinding.EffectMachineBoundary
namespace Aurora.SourceBinding

/-- Exact receiver load, including absent/malformed cells. The complete code
    certificate must derive this row from the resolved source field. -/
theorem effect_receiver_load
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {base : CallFrame} {saved : List SavedCall} {shared : SourceShared World}
    (atLoad : program caller base.pc = some (.local (.pure (.receiver kind ordinal)))) :
    ∃ final, CallRuns program external (.running ⟨caller,base,saved,shared.toCall⟩) [] final ∧
      EffectExpressionResult pairs caller saved base (base.pc + 1) shared
        (sourceLift (readScalar kind (shared.receiver ordinal))) final := by
  cases checked : readScalar kind (shared.receiver ordinal) with
  | trap fault =>
    refine ⟨.trapped (.local (.scalar fault)) ⟨caller,base,saved,shared.toCall⟩,
      CallRuns.one (.local ?_),?_⟩
    · simp only [callStep,atLoad,localCallStep,effectStep,localProgram,CallFrame.inject,
        SourceShared.toCall,pureView,step,checked,finish,retainState,EffectExecution.state,
        CallFrame.ofMachine,CallShared.commit]
      rfl
    · exact ⟨_,rfl,rfl⟩
  | value value =>
    refine ⟨.running ⟨caller,{base with pc := base.pc + 1,accumulator := some value},saved,shared.toCall⟩,
      CallRuns.one (.local ?_),rfl⟩
    simp only [callStep,atLoad,localCallStep,effectStep,localProgram,CallFrame.inject,
      SourceShared.toCall,pureView,step,checked,finish,retainState,EffectExecution.state,
      CallFrame.ofMachine,CallShared.commit]
    rfl

/-- A failed receiver store produces no store event and retains the exact actual
    pre-store frame/shared state; that shared state may already contain effects. -/
theorem effect_receiver_store_fault
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {base : CallFrame} {saved : List SavedCall} {shared : SourceShared World}
    (atStore : program caller base.pc = some (.local (.store kind ordinal)))
    (checked : readScalar kind base.accumulator = .trap fault) :
    CallRuns program external (.running ⟨caller,base,saved,shared.toCall⟩) []
      (.trapped (.local (.scalar fault)) ⟨caller,base,saved,shared.toCall⟩) := by
  apply CallRuns.one
  apply CallTransition.local
  simp only [callStep,atStore,localCallStep,effectStep,localProgram,CallFrame.inject,checked,
    EffectExecution.state,CallFrame.ofMachine,CallShared.commit]
  rfl

/-- The actual successful receiver store updates precisely one source ordinal,
    emits precisely its store event, advances PC and retains all private data,
    accumulator and world. It is not a source field-authority certificate. -/
theorem effect_receiver_store_value
    {program : CallProgram} {external : ExternalRelation World ExternalFault}
    {caller : Int} {base : CallFrame} {saved : List SavedCall} {shared : SourceShared World}
    (atStore : program caller base.pc = some (.local (.store kind ordinal)))
    (checked : readScalar kind base.accumulator = .value value) :
    CallRuns program external (.running ⟨caller,base,saved,shared.toCall⟩) [.store ⟨ordinal,value⟩]
      (.running ⟨caller,{base with pc := base.pc + 1},saved,(shared.store ordinal value).toCall⟩) := by
  apply CallRuns.one
  apply CallTransition.local
  simp only [callStep,atStore,localCallStep,effectStep,localProgram,CallFrame.inject,checked,
    EffectExecution.state,CallFrame.ofMachine,CallShared.commit,SourceShared.store,SourceShared.toCall]
  rfl

end Aurora.SourceBinding
