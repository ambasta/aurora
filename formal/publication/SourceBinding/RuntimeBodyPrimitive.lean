import SourceBinding.RuntimeBodyExecution
import SourceBinding.RuntimeCallComposition
namespace Aurora.SourceBinding

def runtimeExpressionBase (base : Machine) (source : RuntimeLocals) : Machine :=
  runtimeBodyFrame base source 0 none

theorem runtime_body_expression_fault
    (run : RuntimeCallRun program external (runtimeExpressionBase base source) caller saved world start middle
      accumulator base.stack (.trap fault) events) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.trapped fault source) events := by
  obtain ⟨final,actual,active,same,shared⟩ := run
  exact ⟨final,actual,active,same,shared⟩

theorem runtime_body_return
    (run : RuntimeCallRun program external (runtimeExpressionBase base source) caller saved world start middle
      accumulator base.stack (.value value) events)
    (atReturn : localProgram program caller middle = some (.pure .ret)) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.returned value source) events :=
  ⟨_,run.value_run,middle,atReturn,rfl⟩

theorem runtime_body_store
    (run : RuntimeCallRun program external (runtimeExpressionBase base source) caller saved world start middle
      accumulator base.stack (.value value) events)
    (atStore : localProgram program caller middle = some (.localStore kind slot))
    (typed : readRuntime kind (some value) = .value value)
    (values : next.values = (fun i => if i=slot then some value else source.values i)) :
    RuntimeBodyRun program external caller saved world base source start (middle+1) accumulator (.continued next) events := by
  have step : effectStep (localProgram program caller)
      (runtimeBodyFrame base source middle (some value)) =
      ⟨.next (runtimeBodyFrame base next (middle+1) (some value)),[]⟩ := by
    simp only [effectStep,runtimeBodyFrame,atStore,typed,values]
  have stored : EffectRuns (localProgram program caller) (runtimeBodyFrame base source middle (some value)) []
      (.next (runtimeBodyFrame base next (middle+1) (some value))) := .next step .reflexive
  refine ⟨_,?_,some value,rfl⟩
  simpa only [List.map_nil,finishEffect,List.append_nil] using
    run.value_run.trans (stored.call_lift (by trivial) saved world external)

end Aurora.SourceBinding
