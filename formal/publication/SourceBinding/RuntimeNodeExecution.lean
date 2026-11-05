import SourceBinding.RuntimeDAGFacts
import SourceBinding.RuntimeCallSourceFacts
import SourceBinding.RuntimeCallLeafProof
import SourceBinding.RuntimeUniformBody
import SourceBinding.RuntimeBodyContext
import SourceBinding.RuntimeInitialState
import SourceBinding.RuntimeBodyNoFallthrough
namespace Aurora.SourceBinding

/-- Structural terminal coverage excludes only normal fallthrough. It does not
    exclude source faults, require a chosen return value, or describe native
    execution outside the checked body. -/
theorem RuntimeNoFallthrough.not_continued_general (terminal : RuntimeNoFallthrough statements) :
    ¬ RuntimeStatementsEvaluation functions members module path formals result
      before initial statements after (.continued final) events := by
  intro evaluated
  exact terminal.effect_not_continued
    (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])

theorem RuntimeNoFallthrough.outcome_general {outcome : RuntimeBodyOutcome}
    (terminal : RuntimeNoFallthrough statements)
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before initial statements after outcome events) :
    ∀ final, outcome ≠ .continued final := by
  intro final equal
  subst outcome
  exact terminal.not_continued_general evaluated



/-- Actual complete-node execution, with an internal direct-callee hypothesis
    which the checked DAG rank discharges. -/
theorem RuntimeNodeBodyCertificate.callee_executes
    {nodes : List (RuntimeCallable t files root module path)}
    {node : RuntimeCallable t files root module path}
    (checked : RuntimeNodeBodyCertificate nodes node)
    (callees : ∀ (direct : List (RuntimeCallable t files root module path)),
      runtimeStatementsNames 4096 node.source.parsed.statements = some (direct.map RuntimeCallable.name) →
      (∀ callee ∈ direct, callee ∈ nodes) →
      ∀ callee ∈ direct, RuntimeCalleeExecutes (canonicalRuntimeCalls t (nodes.map (·.target)))
        nodes callee World ExternalFault) :
    RuntimeCalleeExecutes (canonicalRuntimeCalls t (nodes.map (·.target))) nodes node World ExternalFault := by
  obtain ⟨direct,names,included,code⟩ := checked.code
  intro values ready
  let seed : Machine := ⟨0,none,[],fun _ => none,fun _ => none,fun index => values[index]?⟩
  let source := formalRuntimeLocals node.parameters.kinds seed
  have valid := code.initial_context checked.noFallthrough
  have initial := runtime_initial_state (base := seed) valid node.parameters.grammar ready.entry
  obtain ⟨outcome,se,me,evaluated,trace,stateAt,run⟩ :=
    code.simulates_uniform included (callees direct names included) source [] initial
  refine ⟨outcome,se,me,evaluated,trace,checked.noFallthrough.outcome_general evaluated,?_⟩
  intro shared saved external
  let base := (freshCallFrame values).inject shared
  let prepared := preparedEntry base runtimeParameterSlot node.parameters.kinds.length
  obtain ⟨final,bodyRun,related⟩ := run prepared saved shared.world external none
  have sourceEq : source = formalRuntimeLocals node.parameters.kinds base := rfl
  have seedEq : runtimeBodyFrame prepared source node.parameters.kinds.length none = prepared := by
    rw [sourceEq]
    have valuesEq := (funext (formal_prepared_values node.parameters.kinds base)).symm
    change (formalRuntimeLocals node.parameters.kinds base).values = prepared.locals at valuesEq
    rw [runtimeBodyFrame,valuesEq,← prepared_pc base runtimeParameterSlot node.parameters.kinds.length,
      ← prepared_accumulator base runtimeParameterSlot node.parameters.kinds.length]
  rw [seedEq] at bodyRun
  have entry := runtime_entry_runs checked.entry base ready.entry
  rw [← canonical_runtime_calls_local t (nodes.map (·.target)) node.target.id] at entry
  have lifted := entry.call_lift (by trivial) saved shared.world external
  refine ⟨final,?_,?_⟩
  · simpa only [List.map_nil,List.nil_append,finishEffect] using lifted.trans bodyRun
  · cases outcome with
    | continued next => exact False.elim (checked.noFallthrough.not_continued_general evaluated)
    | returned value next =>
      obtain ⟨pc,atReturn,same⟩ := related
      refine ⟨pc,atReturn,?_⟩
      simpa only [runtimeBodyFrame,prepared,prepared_stack,prepared_receiver,prepared_arguments] using same
    | trapped fault next =>
      simpa only [RuntimeBodyResult,prepared,prepared_receiver] using related

end Aurora.SourceBinding
