import SourceBinding.RuntimeCallFormalBinding
import SourceBinding.RuntimeCallExpressionProof
namespace Aurora.SourceBinding

/-- Contextual execution at the checked interval, with formal metadata and
    slots derived from the SAME parsed caller/signature. No caller-PC reachability
    or successful callee evaluation is assumed. Arbitrary values may fault.
    The scalar source/machine store is seeded identically, not postulated related. -/
theorem FormalRuntimeCallInterval.executes
    {identified : IdentifiedRuntimeFree t files root module path name}
    (checked : FormalRuntimeCallInterval identified) (base : Machine)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    ∃ outcome sourceEvents machineEvents,
      RuntimeEvaluatesWith (checked.interval.leaves.map RuntimeCallLeaf.source)
        checked.interval.occurrence.context (formalRuntimeLocals checked.parameters base)
        checked.interval.occurrence.selected.raw checked.interval.code.kind outcome sourceEvents ∧
      RuntimeCallTraceRelated checked.interval.leaves sourceEvents machineEvents ∧
      ∀ accumulator stack,
        RuntimeCallRun (canonicalRuntimeCalls t (checked.interval.leaves.map (·.target))) external
          (preparedEntry base runtimeParameterSlot checked.parameters.length) identified.id saved world
          checked.interval.start checked.interval.code.stop accumulator stack outcome machineEvents := by
  apply checked.interval.code.grammar.evaluates_and_runs
  · intro leaf member
    exact canonical_runtime_calls_local _ _ _
  · exact runtime_formal_bindings checked.interval.occurrence.valid checked.signature checked.emptyVisible
  · exact formal_prepared_values checked.parameters base

end Aurora.SourceBinding
