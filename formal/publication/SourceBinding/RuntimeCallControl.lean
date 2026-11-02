import SourceBinding.RuntimeCallComposition
namespace Aurora.SourceBinding

/-- A call-free suffix adds no call events. Existing primitive semantics and
    actual retained fault frames are reused rather than redefined. -/
theorem RuntimeCallRun.pure_suffix
    (prior : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value value) events)
    (suffix : RuntimeRun (localProgram program caller) base middle stop (some value) stack outcome)
    (supported : SupportedOutcome outcome) :
    RuntimeCallRun program external base caller saved world start stop accumulator stack outcome events := by
  simpa only [List.append_nil] using RuntimeCallRun.prior prior.value_run
    (suffix.call_run supported saved world external) rfl

theorem RuntimeCallRun.label
    (run : RuntimeCallRun program external base caller saved world start middle accumulator stack outcome events)
    (code : localProgram program caller middle = some (.pure .label)) :
    RuntimeCallRun program external base caller saved world start (middle+1) accumulator stack outcome events := by
  cases outcome with
  | trap fault => exact run
  | value value =>
    have suffix : RuntimeRun (localProgram program caller) base middle (middle+1)
        (some value) stack (.value value) := RuntimeRun.label EffectRuns.reflexive code
    exact run.pure_suffix suffix (by intro h; cases h)

theorem runtime_call_shift
    (run : RuntimeCallRun program external base caller saved world start middle accumulator stack outcome events)
    (push : localProgram program caller middle = some (.pure .push))
    (countCode : localProgram program caller (middle+1) = some (runtimeCount count))
    (operation : localProgram program caller (middle+2) = some (.pure (.binary primitive))) :
    RuntimeCallRun program external base caller saved world start (middle+3) accumulator stack
      (outcome.then fun value => binaryValue primitive value count.runtimeValue) events := by
  cases outcome with
  | trap fault => exact run
  | value value =>
    have suffix : RuntimeRun (localProgram program caller) base middle (middle+3)
        (some value) stack (binaryValue primitive value count.runtimeValue) :=
      runtime_shift_run (outcome := .value value) EffectRuns.reflexive push countCode operation
    exact run.pure_suffix suffix (binary_supported _ _ _)

theorem runtime_call_and_stop
    (left : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value (.boolean false)) events)
    (branch : localProgram program caller middle = some (.pure (.branchFalse endPC)))
    (label : localProgram program caller endPC = some (.pure .label)) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack (.value (.boolean false)) events := by
  have suffix : RuntimeRun (localProgram program caller) base middle (endPC+1)
      (some (.boolean false)) stack (.value (.boolean false)) :=
    runtime_and_stop EffectRuns.reflexive branch label
  exact left.pure_suffix suffix (by intro h; cases h)

theorem runtime_call_and_continue
    (left : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value (.boolean true)) leftEvents)
    (branch : localProgram program caller middle = some (.pure (.branchFalse endPC)))
    (right : RuntimeCallRun program external base caller saved world (middle+1) endPC
      (some (.boolean true)) stack outcome rightEvents)
    (label : localProgram program caller endPC = some (.pure .label)) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack outcome (leftEvents++rightEvents) := by
  have suffix : RuntimeRun (localProgram program caller) base middle (middle+1)
      (some (.boolean true)) stack (.value (.boolean true)) :=
    EffectRuns.next (runtime_branch_false branch) .reflexive
  have advanced := left.pure_suffix suffix (by intro h; cases h)
  exact (RuntimeCallRun.prior advanced.value_run right rfl).label label

theorem runtime_call_or_stop
    (left : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value (.boolean true)) events)
    (branch : localProgram program caller middle = some (.pure (.branchFalse (middle+2))))
    (jump : localProgram program caller (middle+1) = some (.pure (.jump endPC)))
    (label : localProgram program caller endPC = some (.pure .label)) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack (.value (.boolean true)) events := by
  have suffix : RuntimeRun (localProgram program caller) base middle (endPC+1)
      (some (.boolean true)) stack (.value (.boolean true)) :=
    runtime_or_stop EffectRuns.reflexive branch jump label
  exact left.pure_suffix suffix (by intro h; cases h)

theorem runtime_call_or_continue
    (left : RuntimeCallRun program external base caller saved world start middle accumulator stack (.value (.boolean false)) leftEvents)
    (branch : localProgram program caller middle = some (.pure (.branchFalse (middle+2))))
    (begin : localProgram program caller (middle+2) = some (.pure .label))
    (right : RuntimeCallRun program external base caller saved world (middle+3) endPC
      (some (.boolean false)) stack outcome rightEvents)
    (label : localProgram program caller endPC = some (.pure .label)) :
    RuntimeCallRun program external base caller saved world start (endPC+1) accumulator stack outcome (leftEvents++rightEvents) := by
  have jumped : RuntimeRun (localProgram program caller) base middle (middle+2)
      (some (.boolean false)) stack (.value (.boolean false)) :=
    EffectRuns.next (runtime_branch_false branch) .reflexive
  have advanced := left.pure_suffix (jumped.label begin) (by intro h; cases h)
  exact (RuntimeCallRun.prior advanced.value_run right rfl).label label

end Aurora.SourceBinding
