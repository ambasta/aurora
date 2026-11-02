import SourceBinding.RuntimeBodyContext
import SourceBinding.RuntimeBodyTerminal
namespace Aurora.SourceBinding

/-- Complete selected source/body execution from the actual PC0 entry. Initial
    arguments are typed; expression and nested-call faults remain outcomes.
    No local map, body success, selected return, or reachable cutpoint is assumed. -/
theorem RuntimeBodyCertificate.executes
    {identified : IdentifiedRuntimeFree t files root module path name}
    (checked : RuntimeBodyCertificate identified) (base : Machine)
    (arguments : RuntimeEntryArguments checked.parameters.kinds base.arguments)
    (world : World) (external : ExternalRelation World ExternalFault) :
    ∃ outcome sourceEvents machineEvents final,
      RuntimeStatementsEvaluate (checked.leaves.map (·.source))
        identified.selected.scope.members module path identified.selected.function.function.formals checked.resultKind
        ⟨[],0,1,identified.selected.function.function.formals.length⟩
        (formalRuntimeLocals checked.parameters.kinds base)
        identified.details.lexical.parsed.statements identified.details.lexical.lexical.after outcome sourceEvents ∧
      RuntimeLeafCallTraceRelated checked.leaves sourceEvents machineEvents ∧
      CallRuns (canonicalRuntimeCalls t (checked.leaves.map (·.target))) external
        (.running (activeAt identified.id [] world (preparedEntry base runtimeParameterSlot 0))) machineEvents final ∧
      RuntimeBodyTerminal base world outcome final := by
  let prepared := preparedEntry base runtimeParameterSlot checked.parameters.kinds.length
  have initial := runtime_initial_state checked.initial_context checked.parameters.grammar arguments
  have projection : ∀ leaf ∈ checked.leaves,
      localProgram (canonicalRuntimeCalls t (checked.leaves.map (·.target))) leaf.target.id = canonicalEffects t leaf.identified.id := by
    intro leaf member
    exact canonical_runtime_calls_local t _ _
  obtain ⟨outcome,se,me,evaluated,trace,stateAt,run⟩ := checked.code.simulates projection prepared [] world external
    (formalRuntimeLocals checked.parameters.kinds base) [] initial
  obtain ⟨final,bodyRun,related⟩ := (run none).finish (checked.noFallthrough.outcome evaluated)
  have seed : runtimeBodyFrame prepared (formalRuntimeLocals checked.parameters.kinds base)
      checked.parameters.kinds.length none = prepared := by
    have values := (funext (formal_prepared_values checked.parameters.kinds base)).symm
    change (formalRuntimeLocals checked.parameters.kinds base).values = prepared.locals at values
    rw [runtimeBodyFrame,values,← prepared_pc base runtimeParameterSlot checked.parameters.kinds.length,
      ← prepared_accumulator base runtimeParameterSlot checked.parameters.kinds.length]
  rw [seed] at bodyRun
  have entry := runtime_entry_runs checked.entry base arguments
  rw [← canonical_runtime_calls_local t (checked.leaves.map (·.target)) identified.id] at entry
  have entryCall := entry.call_lift (by trivial) [] world external
  refine ⟨outcome,se,me,final,evaluated,trace,?_,?_⟩
  · simpa only [List.map_nil,List.nil_append,finishEffect] using entryCall.trans bodyRun
  · simpa only [RuntimeBodyTerminal,prepared,prepared_receiver] using related

end Aurora.SourceBinding
