import SourceBinding.EffectEvaluation
import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

/-- Exact shared-state association: no bank model or receiver rollback is hidden
    here. The concrete resource model and checked catalogue joins are separate. -/
def SourceShared.toCall (shared : SourceShared World) : CallShared World :=
  ⟨shared.receiver,shared.world⟩

def SourceExternalOutcome.toCall : SourceExternalOutcome ExternalFault → ExternalOutcome ExternalFault
  | .returned raw => .returned raw
  | .fault reason => .fault reason

/-- Internal interface inventory only. A public canonical certificate must derive
    these pairs from the SAME source declarations and full IR catalogue records. -/
abbrev EffectResourcePairs := List (RuntimeSourceResource × ResourceDescriptor)

def SourceResourceRequest.toCall (request : SourceResourceRequest World)
    (target : ResourceDescriptor) : ExternalRequest World :=
  ⟨target,request.arguments,request.before.toCall⟩

/-- Pointwise equivalence only on checked paired requests. Raw optional returns,
    arbitrary external faults, and the complete AFTER shared state are unchanged.
    No response existence, success, frame law, or native implementation is assumed.
    With an empty inventory this places no restriction on either relation. -/
def EffectExternalRelated (pairs : EffectResourcePairs)
    (source : SourceExternalRelation World ExternalFault)
    (machine : ExternalRelation World ExternalFault) : Prop :=
  ∀ key target, (key,target) ∈ pairs → ∀ arguments before outcome after,
    source ⟨key,arguments,before⟩ outcome after ↔
      machine ⟨target,arguments,before.toCall⟩ outcome.toCall after.toCall

/-- Terminal stops retain the actual machine active frame. In particular a fault
    in a nested callee does not restore caller locals, arguments, or saved frames.
    A finite wait retains the exact frozen request and a genuine machine-owned
    continuation; it does not assert that the response relation has no response. -/
def EffectStopResult (pairs : EffectResourcePairs) (after : SourceShared World) :
    SourceEffectStop World ExternalFault → CallPhase World ExternalFault → Prop
  | .localFault reason,final => ∃ active,
      final = .trapped (.local reason) active ∧ active.shared = after.toCall
  | .externalFault reason,final => ∃ active,
      final = .trapped (.external reason) active ∧ active.shared = after.toCall
  | .waiting request,final => ∃ target pending,
      (request.key,target) ∈ pairs ∧ final = .waiting pending ∧
      pending.request = request.toCall target ∧ after = request.before

/-- A completed expression restores its private caller frame at the checked cut,
    but uses the source AFTER receiver/world. There is no pre-call shared restore. -/
def EffectExpressionResult (pairs : EffectResourcePairs)
    (caller : Int) (saved : List SavedCall) (base : CallFrame) (stop : Nat)
    (after : SourceShared World) :
    SourceEffectOutcome World ExternalFault → CallPhase World ExternalFault → Prop
  | .value raw,final => final = .running
      ⟨caller,{base with pc := stop,accumulator := raw},saved,after.toCall⟩
  | .stopped reason,final => EffectStopResult pairs after reason final

/-- Internal body returns witness the real pending ret instruction. Only a
    complete-body/caller theorem executes that ret and claims a terminal return.
    Terminal source private locals are not equated to an active nested callee. -/
def EffectBodyResult (pairs : EffectResourcePairs) (program : CallProgram)
    (caller : Int) (saved : List SavedCall) (base : CallFrame) (stop : Nat) :
    SourceEffectBodyOutcome World ExternalFault → CallPhase World ExternalFault → Prop
  | .continued state,final => ∃ accumulator,
      final = .running ⟨caller,
        {base with pc := stop,accumulator := accumulator,locals := state.locals.values},
        saved,state.shared.toCall⟩
  | .returned value state,final => ∃ pc,
      localProgram program caller pc = some (.pure .ret) ∧
      final = .running ⟨caller,
        {base with pc := pc,accumulator := some value,locals := state.locals.values},
        saved,state.shared.toCall⟩
  | .stopped reason state,final => EffectStopResult pairs state.shared reason final

/-- Existing CallRuns, not a second machine or evaluator. Initial shared state
    and external behavior precede the chosen source result. Later uniformity is
    only over private continuations absent from source semantics; old pure APIs
    retain their stronger uniform shared/external quantifiers unchanged. -/
def EffectBodyRun (pairs : EffectResourcePairs) (program : CallProgram)
    (external : ExternalRelation World ExternalFault) (caller : Int)
    (saved : List SavedCall) (base : CallFrame) (initial : SourceEffectState World)
    (start stop : Nat) (accumulator : Option Value)
    (outcome : SourceEffectBodyOutcome World ExternalFault)
    (events : List (CallEvent World ExternalFault)) : Prop :=
  ∃ final, CallRuns program external
      (.running ⟨caller,{base with pc := start,accumulator := accumulator,locals := initial.locals.values},saved,initial.shared.toCall⟩) events final ∧
    EffectBodyResult pairs program caller saved base stop outcome final

end Aurora.SourceBinding
