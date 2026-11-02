import SourceBinding.RuntimeStatementCode
import SourceBinding.RuntimeExecution
import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

theorem RuntimeLabelRun.monotone (labels : RuntimeLabelRun program caller start stop) : start ≤ stop := by
  induction labels with
  | nil => exact Nat.le_refl _
  | cons label rest ih => exact Nat.le_trans (Nat.le_succ _) ih

/-- A checked jump into an administrative label interval cannot bypass an
    unexamined operation. The suffix consists of the same consecutive labels. -/
theorem RuntimeLabelRun.suffix (labels : RuntimeLabelRun program caller start stop)
    (lower : start ≤ joinPC) (upper : joinPC ≤ stop) : RuntimeLabelRun program caller joinPC stop := by
  induction labels with
  | nil => have same : joinPC = _ := Nat.le_antisymm upper lower; subst joinPC; exact .nil
  | @cons pc stop label rest ih =>
    by_cases same : joinPC = pc
    · subst joinPC; exact .cons label rest
    · exact ih (by omega) upper

theorem RuntimeLabelRun.effect_runs (labels : RuntimeLabelRun program caller start stop)
    (base : Machine) (accumulator : Option Value) (stack : List Value) :
    EffectRuns (localProgram program caller) (frameState base start accumulator stack) []
      (.next (frameState base stop accumulator stack)) := by
  induction labels with
  | nil => exact .reflexive
  | cons label rest ih =>
    apply EffectRuns.next (events := []) (later := []) _ ih
    simp only [effectStep,frameState,label,pureView,step,retainState]

theorem RuntimeLabelRun.call_runs (labels : RuntimeLabelRun program caller start stop)
    (base : Machine) (accumulator : Option Value) (stack : List Value)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    CallRuns program external (.running (activeAt caller saved world (frameState base start accumulator stack))) []
      (.running (activeAt caller saved world (frameState base stop accumulator stack))) := by
  simpa only [List.map_nil,List.nil_append,finishEffect] using
    (labels.effect_runs base accumulator stack).call_lift (by trivial) saved world external

end Aurora.SourceBinding
