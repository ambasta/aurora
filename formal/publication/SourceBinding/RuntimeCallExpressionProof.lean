import SourceBinding.RuntimeUniformExpression
import SourceBinding.RuntimeLeafExecution
namespace Aurora.SourceBinding

/-- Exact old call-free-leaf profile, specialized from uniform full-body
    composition. Its formerly supplied local projection is retained unchanged;
    actual leaf certificates discharge the generic internal callee hypothesis. -/
theorem RuntimeCallExpressionCode.evaluates_and_runs
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeCallExpressionCode program caller (leaves.map (·.toCallable)) context raw kind start stop)
    (projection : ∀ leaf ∈ leaves, localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (source : RuntimeLocals) (base : Machine)
    (bindings : RuntimeBindingsPresent context source)
    (locals : ∀ slot, base.locals slot = source.values slot)
    (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    ∃ outcome sourceEvents machineEvents,
      RuntimeEvaluatesWith (leaves.map RuntimeCallLeaf.source) context source raw kind outcome sourceEvents ∧
      RuntimeLeafCallTraceRelated leaves sourceEvents machineEvents ∧
      ∀ accumulator stack, RuntimeCallRun program external base caller saved world start stop accumulator stack outcome machineEvents := by
  have callees : ∀ callable ∈ leaves.map (·.toCallable),
      RuntimeCalleeExecutes program (leaves.map (·.toCallable)) callable World ExternalFault := by
    intro callable member
    obtain ⟨leaf,present,equal⟩ := List.mem_map.mp member
    subst callable
    exact leaf.callee_executes program (projection leaf present) _
  obtain ⟨outcome,se,me,evaluated,trace,run⟩ := code.evaluates_uniform (fun _ member => member) callees source bindings
  refine ⟨outcome,se,me,?_,trace,run base locals saved world external⟩
  simpa only [RuntimeEvaluatesWith,List.map_map,RuntimeCallLeaf.toCallable_source] using evaluated

end Aurora.SourceBinding
