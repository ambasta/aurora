import SourceBinding.CallRelation
import SourceBinding.CallTraceProof
namespace Aurora.SourceBinding
open Aurora.Publication

def assertActive (active : ActiveCall World) : CallPhase World ExternalFault :=
  match assertResult active.frame.accumulator with
  | none => .running {active with frame := {active.frame with pc := active.frame.pc + 1,accumulator := none}}
  | some fault => .trapped (.local fault) active

theorem callStep_require (program : CallProgram) (active : ActiveCall World)
    (atRequire : program active.callable active.frame.pc = some (.local .require)) :
    callStep program active = (assertActive (ExternalFault := ExternalFault) active,[]) := by
  cases active with
  | mk callable frame saved shared =>
    cases frame with
    | mk pc accumulator stack locals arguments =>
      cases shared with
      | mk receiver world =>
        cases accumulator with
        | none => simp only [callStep,atRequire,localCallStep,effectStep,localProgram,CallFrame.inject,
            CallFrame.ofMachine,CallShared.commit,assertActive,assertResult,EffectExecution.state,List.map_nil]
        | some value =>
          cases value with
          | word _ | signedCount12 => simp only [callStep,atRequire,localCallStep,effectStep,localProgram,CallFrame.inject,
              CallFrame.ofMachine,CallShared.commit,assertActive,assertResult,EffectExecution.state,List.map_nil]
          | boolean b => cases b <;> simp only [callStep,atRequire,localCallStep,effectStep,localProgram,CallFrame.inject,
              CallFrame.ofMachine,CallShared.commit,assertActive,assertResult,EffectExecution.state,List.map_nil]

theorem WaitingContext.resume_local
    {family : CallFamilyBinding files root module path member bytes}
    {source : SourceWaiting World} {machine : WaitingCall World}
    (related : WaitingContext family source machine)
    (outcome : ExternalOutcome ExternalFault) (after : CallShared World) :
    ∃ final, LocalCallRuns
        (canonicalCalls (tables family.shape.ir.publication.artifact.document.reversed.reverse)
          (pieceTargets family.shape.source.pieces)) (resumeCall machine outcome after).1 [] final ∧
      ExecutionRelated family (sourceResume source outcome after).1 final ∧
      (resumeCall machine outcome after).2 = (sourceResume source outcome after).2 := by
  let program := canonicalCalls (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces)
  cases outcome with
  | fault reason => exact ⟨_,.reflexive,.trapped rfl,rfl⟩
  | returned value =>
    let active : ActiveCall World :=
      ⟨machine.callable,{machine.continuation with accumulator := value},machine.saved,after⟩
    have atRequire : program active.callable active.frame.pc = some (.local .require) := by
      simp only [program,active,canonicalCalls,related.callable,related.require]
    have run : LocalCallRuns program (.running active) [] (assertActive (ExternalFault := ExternalFault) active) := by
      simpa only [List.nil_append] using LocalCallRuns.step (callStep_require program active atRequire) .reflexive
    have context : ContextRelated (after.source source.arguments) (machine.continuation.inject after)
        (parameterSlot family.shape.bindings) :=
      ContextRelated.change_shared _ machine.request.before _ _
        (by simpa only [related.request] using related.context)
    cases value with
    | none => exact ⟨_,run,.trapped rfl,rfl⟩
    | some value =>
      cases value with
      | word _ | signedCount12 => exact ⟨_,run,.trapped rfl,rfl⟩
      | boolean b =>
        cases b with
        | false => exact ⟨_,run,.trapped rfl,rfl⟩
        | true =>
          refine ⟨_,run,.running ?_,rfl⟩
          exact ⟨related.callable,related.saved,rfl,related.stack,
            ⟨context.fields,context.parameters⟩,related.returns,related.remaining,related.code⟩
theorem WaitingContext.resume
    {family : CallFamilyBinding files root module path member bytes}
    {source : SourceWaiting World} {machine : WaitingCall World}
    (related : WaitingContext family source machine)
    (external : ExternalRelation World ExternalFault) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) (response : external source.request outcome after) :
    ∃ final, CallRuns family.program external (.waiting machine)
        (sourceResume source outcome after).2 final ∧
      ExecutionRelated family (sourceResume source outcome after).1 final := by
  have sameResponse : external machine.request outcome after := related.request ▸ response
  have first := CallRuns.one (CallTransition.resume (program := family.program) sameResponse (rfl :
    resumeCall machine outcome after = ((resumeCall machine outcome after).1,(resumeCall machine outcome after).2)))
  obtain ⟨final,localRun,result,events⟩ := related.resume_local outcome after
  have complete := first.trans (localRun.embed external)
  change CallRuns family.program external (.waiting machine) ((resumeCall machine outcome after).2 ++ []) final at complete
  rw [List.append_nil,events] at complete
  exact ⟨final,complete,result⟩
end Aurora.SourceBinding
