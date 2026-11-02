import SourceBinding.RuntimeArgumentCollection
namespace Aurora.SourceBinding

theorem RuntimeCallRun.value_run
    (run : RuntimeCallRun program external base caller saved world start stop accumulator stack (.value value) events) :
    CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base stop (some value) stack))) := by
  obtain ⟨final,actual,same⟩ := run
  exact same ▸ actual

theorem RuntimeCallRun.fault_stop
    (run : RuntimeCallRun program external base caller saved world start stop accumulator stack (.trap fault) events) :
    RuntimeCallRun program external base caller saved world start other accumulator stack (.trap fault) events := run

/-- An actual local suffix is lifted without changing any earlier invocation
    events. Its fault retains the precise instruction frame. -/
theorem runtime_call_apply
    (prior : CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base pc input inputStack))))
    (step : effectStep (localProgram program caller) (frameState base pc input inputStack) =
      ⟨retainState (frameState base pc input inputStack) (finish base stop stack outcome),[]⟩)
    (supported : SupportedOutcome outcome) :
    RuntimeCallRun program external base caller saved world start stop accumulator stack outcome events := by
  cases outcome with
  | value value =>
    have suffix : EffectRuns (localProgram program caller) (frameState base pc input inputStack) []
        (.next (frameState base stop (some value) stack)) := .next step .reflexive
    refine ⟨_,?_,rfl⟩
    simpa only [finishEffect,List.map_nil,List.append_nil] using prior.trans (suffix.call_lift (by trivial) saved world external)
  | trap fault =>
    have suffix : EffectRuns (localProgram program caller) (frameState base pc input inputStack) []
        (.trap (.scalar fault) (frameState base pc input inputStack)) := .trap step
    have support : LocalSupported (.trap (.scalar fault) (frameState base pc input inputStack)) := by
      cases fault <;> first | trivial | exact False.elim (supported rfl)
    refine ⟨_,?_,activeAt caller saved world (frameState base pc input inputStack),rfl,rfl⟩
    simpa only [finishEffect,List.map_nil,List.append_nil] using prior.trans (suffix.call_lift support saved world external)

theorem RuntimeCallRun.negate
    (run : RuntimeCallRun program external base caller saved world start middle accumulator stack outcome events)
    (code : localProgram program caller middle = some (.pure .negate)) :
    RuntimeCallRun program external base caller saved world start (middle+1) accumulator stack
      (outcome.then notValue) events := by
  cases outcome with
  | trap fault => exact run
  | value value =>
    apply runtime_call_apply run.value_run _ (not_supported value)
    simp only [effectStep,frameState,code,pureView,step]
    cases value <;> rfl

theorem runtime_call_push
    (run : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value value) events)
    (code : localProgram program caller middle = some (.pure .push)) :
    CallRuns program external
      (.running (activeAt caller saved world (frameState base start accumulator stack))) events
      (.running (activeAt caller saved world (frameState base (middle+1) (some value) (value::stack)))) := by
  have pushed : EffectRuns (localProgram program caller) (frameState base middle (some value) stack) []
      (.next (frameState base (middle+1) (some value) (value::stack))) := .next (runtime_push_step code) .reflexive
  simpa only [finishEffect,List.map_nil,List.append_nil] using run.value_run.trans (pushed.call_lift (by trivial) saved world external)

theorem runtime_call_binary
    (leftRun : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value left) leftEvents)
    (push : localProgram program caller middle = some (.pure .push))
    (rightRun : RuntimeCallRun program external base caller saved world (middle+1) endPC (some left) (left::stack) rightOutcome rightEvents)
    (operation : localProgram program caller endPC = some (.pure (.binary primitive))) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack
      (rightOutcome.then (binaryValue primitive left)) (leftEvents++rightEvents) := by
  have pushed := runtime_call_push leftRun push
  cases rightOutcome with
  | trap fault => exact runtime_call_prefix_fault pushed rightRun
  | value value =>
    apply runtime_call_apply (pushed.trans rightRun.value_run) _ (binary_supported _ _ _)
    simp only [effectStep,frameState,operation,pureView,step]
    cases binaryValue primitive left value <;> rfl

theorem runtime_call_enum_compare
    (leftRun : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value left) leftEvents)
    (push : localProgram program caller middle = some (.pure .push))
    (rightRun : RuntimeCallRun program external base caller saved world (middle+1) endPC (some left) (left::stack) rightOutcome rightEvents)
    (operation : localProgram program caller endPC = some (.enumCompare identity equal)) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack
      (rightOutcome.then (compareNominal identity equal left)) (leftEvents++rightEvents) := by
  have pushed := runtime_call_push leftRun push
  cases rightOutcome with
  | trap fault => exact runtime_call_prefix_fault pushed rightRun
  | value value =>
    apply runtime_call_apply (pushed.trans rightRun.value_run) _ (runtime_nominal_compare_supported _ _ _ _)
    simp only [effectStep,frameState,operation]
    cases compareNominal identity equal left value <;> rfl

end Aurora.SourceBinding
