import SourceBinding.RequestReach
import SourceBinding.RequestShape
namespace Aurora.SourceBinding

/-- Exact first-request values and range, in the receiver AFTER the checked
    ordinary callee. This says nothing about external authority or poststate. -/
def RequestAdmitted (shape : RequestShape checked) (parameters : Nat → Option Value)
    (request : ExternalRequest World) : Prop :=
  request.target = shape.guarded.resource ∧ ∃ epoch offset bytes count,
    request.arguments = [.word epoch,.word offset,.word 0,.word count] ∧
    evalGuard (request.before.source parameters) shape.epoch = .value (.word epoch) ∧
    evalGuard (request.before.source parameters) shape.offset = .value (.word offset) ∧
    evalGuard (request.before.source parameters) shape.bytes = .value (.word bytes) ∧
    evalGuard (request.before.source parameters) shape.count = .value (.word count) ∧
    0 < count ∧ offset ≤ bytes ∧ count ≤ bytes - offset ∧ offset + count ≤ bytes ∧
    bytes < wordLimit ∧ epoch < wordLimit ∧ offset < wordLimit ∧ count < wordLimit

theorem RequestShape.source_reached {World ExternalFault : Type} {pending : SourceWaiting World}
    (shape : RequestShape checked) (parameters : Nat → Option Value) (shared : CallShared World)
    (reached : ReachesRequest checked.family.sourceBodies
      (.running ⟨checked.family.shape.source.pieces,parameters,shared⟩ : SourceCallPhase World ExternalFault) pending) :
    RequestAdmitted shape parameters pending.request := by
  obtain ⟨_,target,evaluated,accepted⟩ := shape.guarded.reached_guard parameters shared reached
  rw [shape.guardEq] at accepted
  obtain ⟨offset,bytes,count,eo,eb,ec,positive,offsetBound,countBound,endBound,bb,ob,cb⟩ :=
    request_range_bounds _ shape.prior shape.offset shape.bytes shape.count accepted
  obtain ⟨epoch,actualOffset,actualCount,ordered,ee,actualO,actualC,epochBound,_,_⟩ :=
    shape.arguments.values _ _ evaluated
  have sameOffset : actualOffset = offset := Value.word.inj (Outcome.value.inj (actualO.symm.trans eo))
  have sameCount : actualCount = count := Value.word.inj (Outcome.value.inj (actualC.symm.trans ec))
  subst actualOffset
  subst actualCount
  exact ⟨target,epoch,offset,bytes,count,ordered,ee,eo,eb,ec,positive,offsetBound,countBound,endBound,bb,
    epochBound,ob,cb⟩

/-- Public reached-request corollary: the ONLY execution premise is an actual
    finite local path from fresh PC0 to Waiting. Guard acceptance, actual callee
    return, argument readiness and exact range are all derived. No prior external
    response occurs on this path; later requests after responses are not covered. -/
theorem RequestShape.first_request {World ExternalFault : Type}
    (shape : RequestShape checked) (world : World) (base : Machine)
    (arguments : EntryArguments checked.family.shape.bindings base.arguments)
    {events : List (CallEvent World ExternalFault)} {pending : WaitingCall World}
    (run : LocalCallRuns checked.family.program
      (.running (checked.machineInitial world base)) events (.waiting pending)) :
    RequestAdmitted shape (checked.sourceInitial world base).arguments pending.request := by
  obtain ⟨source,sourceRun,related⟩ := checked.reflect world base arguments
    (run.embed (fun _ _ _ => False)) (by trivial)
  cases related with
  | waiting context =>
    rw [context.request]
    exact shape.source_reached _ _ ⟨events,sourceRun⟩
end Aurora.SourceBinding
