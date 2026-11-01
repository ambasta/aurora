import SourceBinding.CallMachine
namespace Aurora.SourceBinding

theorem CallRuns.trans (first : CallRuns program external initial events middle)
    (later : CallRuns program external middle rest final) :
    CallRuns program external initial (events ++ rest) final := by
  induction first with
  | reflexive => exact later
  | step step tail ih => simpa only [List.append_assoc] using CallRuns.step step (ih later)

theorem CallRuns.one (step : CallTransition program external initial events final) :
    CallRuns program external initial events final := by
  simpa only [List.append_nil] using CallRuns.step step (.reflexive (phase := final))

def LocalSupported : EffectExecution → Prop
  | .trap (.scalar .unsupported) _ => False
  | _ => True

/-- A supported local effect step cannot be a call hidden by the local projection.
    This discharges the call-free bridge from behavior, not a frame assumption. -/
theorem supported_local_step (program : CallProgram) (active : ActiveCall World)
    (supported : LocalSupported (effectStep (localProgram program active.callable)
      (active.frame.inject active.shared)).execution) :
    callStep (ExternalFault := ExternalFault) program active = localCallStep program active := by
  cases atPC : program active.callable active.frame.pc with
  | none => simp only [callStep,atPC]
  | some operation =>
    cases operation with
    | «local» op => simp only [callStep,atPC]
    | ordinary target | resource target =>
      simp only [effectStep,localProgram,CallFrame.inject,atPC,pureView,step,retainState,LocalSupported] at supported

def activeAt (callable : Int) (saved : List SavedCall) (world : World) (machine : Machine) : ActiveCall World :=
  ⟨callable,CallFrame.ofMachine machine,saved,⟨machine.receiver,world⟩⟩

@[simp] theorem activeAt_inject (callable : Int) (saved : List SavedCall) (world : World) (machine : Machine) :
    (activeAt callable saved world machine).frame.inject (activeAt callable saved world machine).shared = machine := by
  cases machine; rfl

def finishEffect (callable : Int) (saved : List SavedCall) (world : World) : EffectExecution →
    CallPhase World ExternalFault × List (CallEvent World ExternalFault)
  | .next machine => (.running (activeAt callable saved world machine),[])
  | .trap fault machine => (.trapped (.local fault) (activeAt callable saved world machine),[])
  | .returned value machine => returnToCaller (activeAt callable saved world machine) value

theorem lifted_local_step (program : CallProgram) (callable : Int) (saved : List SavedCall) (world : World)
    (machine : Machine) (result : EffectExecution) (stores : List StoreEvent)
    (step : effectStep (localProgram program callable) machine = ⟨result,stores⟩)
    (supported : LocalSupported result) :
    callStep program (activeAt callable saved world machine) =
      ((finishEffect (ExternalFault := ExternalFault) callable saved world result).1,
        stores.map CallEvent.store ++ (finishEffect callable saved world result).2) := by
  have supported' : LocalSupported (effectStep (localProgram program callable)
      ((activeAt callable saved world machine).frame.inject (activeAt callable saved world machine).shared)).execution := by
    simpa only [activeAt_inject,step] using supported
  rw [supported_local_step program _ supported']
  simp only [localCallStep,activeAt_inject]
  cases result <;> simp only [activeAt,CallShared.commit,step,EffectExecution.state,finishEffect,List.append_nil]

theorem EffectRuns.call_lift {program : CallProgram} {callable : Int}
    (run : EffectRuns (localProgram program callable) initial stores result)
    (supported : LocalSupported result) (saved : List SavedCall) (world : World)
    (external : ExternalRelation World ExternalFault) :
    CallRuns program external (.running (activeAt callable saved world initial))
      (stores.map CallEvent.store ++ (finishEffect callable saved world result).2)
      (finishEffect callable saved world result).1 := by
  induction run with
  | reflexive => exact .reflexive
  | next step rest ih =>
    have first := lifted_local_step (ExternalFault := ExternalFault) program callable saved world _ _ _ step (by trivial)
    have prior := CallRuns.one (external := external) (CallTransition.local first)
    have tail := ih supported
    simpa only [finishEffect,List.append_nil,List.map_append,List.append_assoc] using prior.trans tail
  | returned step =>
    exact CallRuns.one (.local (lifted_local_step program callable saved world _ _ _ step supported))
  | trap step =>
    exact CallRuns.one (.local (lifted_local_step program callable saved world _ _ _ step supported))

end Aurora.SourceBinding
