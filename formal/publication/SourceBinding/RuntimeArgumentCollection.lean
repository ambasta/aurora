import SourceBinding.RuntimeCallExecution
import SourceBinding.CallArgumentProof
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

def RuntimeCallArgumentsRun (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (base : Machine) (caller : Int) (saved : List SavedCall) (world : World)
    (start stop : Nat) (accumulator : Option Value) (stack : List Value) :
    Outcome (List Value) → List (CallEvent World ExternalFault) → Prop
  | .value values,events => CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base stop
        (argumentAccumulator values accumulator) (values.reverse++stack))))
  | .trap fault,events => RuntimeCallRun program external base caller saved world start stop accumulator stack (.trap fault) events

end Aurora.SourceBinding
