import SourceBinding.RuntimeBodyExecution
import SourceBinding.RuntimeLabelProof
namespace Aurora.SourceBinding

/-- Concatenation uses the actual intermediate frame. Ghost source states need
    not be identical when their retained value maps describe that same frame. -/
theorem RuntimeBodyRun.prepend
    (initialRun : CallRuns program external
      (.running (activeAt caller saved world (runtimeBodyFrame base source start accumulator))) firstEvents
      (.running (activeAt caller saved world (runtimeBodyFrame base middleSource middle input))))
    (rest : RuntimeBodyRun program external caller saved world base middleSource middle stop input outcome laterEvents) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator outcome (firstEvents ++ laterEvents) := by
  obtain ⟨final,run,result⟩ := rest
  exact ⟨final,initialRun.trans run,result⟩

theorem RuntimeBodyRun.source_values
    (run : RuntimeBodyRun program external caller saved world base source start stop accumulator outcome events)
    (same : other.values = source.values) :
    RuntimeBodyRun program external caller saved world base other start stop accumulator outcome events := by
  simpa only [RuntimeBodyRun,runtimeBodyFrame,same] using run

theorem runtime_body_branch
    (branch : localProgram program caller pc = some (.pure (.branchFalse target)))
    (base : Machine) (source : RuntimeLocals) (value : Bool)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    CallRuns program external
      (.running (activeAt caller saved world (runtimeBodyFrame base source pc (some (.boolean value))))) []
      (.running (activeAt caller saved world
        (runtimeBodyFrame base source (if value then pc + 1 else target) (some (.boolean value))))) := by
  have run : EffectRuns (localProgram program caller)
      (frameState {base with locals := source.values} pc (some (.boolean value)) base.stack) []
      (.next (frameState {base with locals := source.values}
        (if value then pc + 1 else target) (some (.boolean value)) base.stack)) :=
    .next (runtime_branch_false branch) .reflexive
  simpa only [frameState,runtimeBodyFrame,finishEffect,List.map_nil,List.nil_append] using
    run.call_lift (by trivial) saved world external

theorem runtime_body_jump
    (jump : localProgram program caller pc = some (.pure (.jump target)))
    (base : Machine) (source : RuntimeLocals) (accumulator : Option Value)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    CallRuns program external
      (.running (activeAt caller saved world (runtimeBodyFrame base source pc accumulator))) []
      (.running (activeAt caller saved world (runtimeBodyFrame base source target accumulator))) := by
  have run : EffectRuns (localProgram program caller)
      (frameState {base with locals := source.values} pc accumulator base.stack) []
      (.next (frameState {base with locals := source.values} target accumulator base.stack)) :=
    .next (runtime_jump jump) .reflexive
  simpa only [frameState,runtimeBodyFrame,finishEffect,List.map_nil,List.nil_append] using
    run.call_lift (by trivial) saved world external

theorem RuntimeBodyRun.labels
    (run : RuntimeBodyRun program external caller saved world base source start middle accumulator (.continued next) events)
    (labels : RuntimeLabelRun program caller middle stop) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.continued next) events := by
  obtain ⟨final,prior,value,same⟩ := run
  subst final
  have suffix := labels.call_runs {base with locals := next.values} value base.stack saved world external
  have actual : CallRuns program external
      (.running (activeAt caller saved world (runtimeBodyFrame base next middle value))) []
      (.running (activeAt caller saved world (runtimeBodyFrame base next stop value))) := by
    simpa only [frameState,runtimeBodyFrame] using suffix
  exact ⟨_,by simpa only [List.append_nil] using prior.trans actual,value,rfl⟩

theorem RuntimeBodyRun.jump_labels
    (run : RuntimeBodyRun program external caller saved world base source start middle accumulator (.continued next) events)
    (jump : localProgram program caller middle = some (.pure (.jump joinPC)))
    (labels : RuntimeLabelRun program caller joinPC stop) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.continued next) events := by
  obtain ⟨final,prior,value,same⟩ := run
  subst final
  have jumped := runtime_body_jump jump base next value saved world external
  have intermediate : RuntimeBodyRun program external caller saved world base source start joinPC accumulator (.continued next) events :=
    ⟨_,by simpa only [List.append_nil] using prior.trans jumped,value,rfl⟩
  exact intermediate.labels labels

end Aurora.SourceBinding
