import SourceBinding.RuntimeExecution
import SourceBinding.RuntimeCallSupport
import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

/-- A successful expression restores the complete caller frame. A fault keeps
    the actual active frame from the call machine: it may be a callee, so no
    caller-locals/argument equality is asserted. Shared state is unchanged in
    this private-local expression profile. -/
def RuntimeCallResult (base : Machine) (caller : Int) (saved : List SavedCall)
    (world : World) (stop : Nat) (stack : List Value) :
    Outcome Value → CallPhase World ExternalFault → Prop
  | .value value, final => final = .running (activeAt caller saved world (frameState base stop (some value) stack))
  | .trap fault, final => ∃ active,
      final = .trapped (.local (.scalar fault)) active ∧
      active.shared = ⟨base.receiver,world⟩

def RuntimeCallRun (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (base : Machine) (caller : Int) (saved : List SavedCall) (world : World)
    (start stop : Nat) (accumulator : Option Value) (stack : List Value)
    (outcome : Outcome Value) (events : List (CallEvent World ExternalFault)) : Prop :=
  ∃ final, CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events final ∧
    RuntimeCallResult base caller saved world stop stack outcome final

theorem RuntimeRun.call_run
    (run : RuntimeRun (localProgram program caller) base start stop accumulator stack outcome)
    (supported : SupportedOutcome outcome) (saved : List SavedCall) (world : World)
    (external : ExternalRelation World ExternalFault) :
    RuntimeCallRun program external base caller saved world start stop accumulator stack outcome [] := by
  cases outcome with
  | value value => exact ⟨_,run.call_lift (by trivial) saved world external,rfl⟩
  | trap fault =>
    obtain ⟨final,actual,locals,receiver,arguments⟩ := run
    have support : LocalSupported (.trap (.scalar fault) final) := by
      cases fault <;> first | trivial | exact False.elim (supported rfl)
    refine ⟨_,actual.call_lift support saved world external,_,rfl,?_⟩
    change CallShared.mk final.receiver world = _
    rw [receiver]

theorem RuntimeCallRun.prior
    (prior : CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base middle nextAccumulator nextStack))))
    (later : RuntimeCallRun program external base caller saved world middle stop nextAccumulator nextStack outcome rest)
    (restored : nextStack = stack) :
    RuntimeCallRun program external base caller saved world start stop accumulator stack outcome (events ++ rest) := by
  subst nextStack
  obtain ⟨final,run,result⟩ := later
  exact ⟨final,prior.trans run,result⟩

theorem runtime_call_prefix_fault
    (prior : CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base middle nextAccumulator nextStack))))
    (later : RuntimeCallRun program external base caller saved world middle stop nextAccumulator nextStack (.trap fault) rest) :
    RuntimeCallRun program external base caller saved world start finalStop accumulator stack (.trap fault) (events ++ rest) := by
  obtain ⟨final,run,result⟩ := later
  exact ⟨final,prior.trans run,result⟩

end Aurora.SourceBinding
