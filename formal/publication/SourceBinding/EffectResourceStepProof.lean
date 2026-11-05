import SourceBinding.EffectMachineTrace
import SourceBinding.ResourceStatementRules
namespace Aurora.SourceBinding

/-- A real resource instruction and, when supplied, its real external response.
    The instruction/argument/pair premises are INTERNAL checked-code obligations.
    Raw None/wrong-kind values are not validated until the later actual consumer. -/
theorem SourceResourceStep.response_run
    {request : SourceResourceRequest World}
    {response : SourceExternalRelation World ExternalFault}
    {external : ExternalRelation World ExternalFault}
    {ordinary : EffectOrdinaryPairs} {resources : EffectResourcePairs} {fields : EffectFieldPairs}
    {program : CallProgram} {caller : Int} {base : CallFrame} {saved : List SavedCall}
    (step : SourceResourceStep response request outcome after sourceEvents)
    (paired : (request.key,target) ∈ resources)
    (related : EffectExternalRelated resources response external)
    (atCall : program caller base.pc = some (.resource target))
    (collected : collectArguments true target.parameters.length base = some (request.arguments,stack)) :
    ∃ machineEvents final,
      CallRuns program external (.running ⟨caller,base,saved,request.before.toCall⟩) machineEvents final ∧
      EffectMachineTraceRelated ordinary resources fields sourceEvents machineEvents ∧
      EffectExpressionResult resources caller saved {base with stack := stack}
        (base.pc + 1) after outcome final := by
  let pending : WaitingCall World :=
    ⟨request.toCall target,caller,{base with pc := base.pc + 1,stack := stack},saved⟩
  have invoke : CallTransition program external
      (.running ⟨caller,base,saved,request.before.toCall⟩)
      [.externalInvoke (request.toCall target)] (.waiting pending) := by
    apply CallTransition.local
    simp only [callStep,atCall,collected]
    rfl
  cases step with
  | pending =>
    refine ⟨_,_,CallRuns.one invoke,.cons (.externalInvoke paired) .nil,?_⟩
    exact ⟨target,pending,paired,rfl,rfl,rfl⟩
  | returned responded =>
    have machine := (related request.key target paired request.arguments request.before (.returned _) _).mp responded
    refine ⟨_,_,CallRuns.step invoke (CallRuns.one (.resume machine rfl)),
      .cons (.externalInvoke paired) (.cons .externalReturn .nil),?_⟩
    rfl
  | fault responded =>
    have machine := (related request.key target paired request.arguments request.before (.fault _) _).mp responded
    refine ⟨_,_,CallRuns.step invoke (CallRuns.one (.resume machine rfl)),
      .cons (.externalInvoke paired) (.cons .externalFault .nil),?_⟩
    exact ⟨_,rfl,rfl⟩

end Aurora.SourceBinding
