import SourceBinding.FramePolicyProfile
import SourceBinding.RuntimeEvaluationResults
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication

/-- Proof-only characterization of ordered argument evaluation. -/
def ArgumentsResult (functions : List RuntimeSourceFunction) (context : RuntimeExprContext)
    (state : RuntimeLocals) (raw : List SourceExpr) (kinds : List RuntimeType) (values : List Value) : Prop :=
  ∀ outcome events, RuntimeArgumentEvaluation functions context state raw kinds outcome events →
    outcome = .value values

private theorem ArgumentsResult.effect
    (result : ArgumentsResult functions context state raws kinds values)
    (evaluated : EffectArguments (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
      ⟨state,shared⟩ raws kinds outcome after events) :
    outcome = legacyEffectArguments (.value values) := by
  rcases evaluated.pure_induction (pureRuntimeAlgebra functions) context rfl with
    ⟨oldOutcome,oldEvents,old,same,_,_⟩
  exact same.trans (congrArg legacyEffectArguments (result _ _ old))

theorem ArgumentsResult.nil : ArgumentsResult functions context state [] [] [] := by
  intro outcome events evaluated
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩
  generalize same : legacyEffectArguments outcome = actualOutcome at actual
  generalize List.map RuntimeSourceEvent.toEffect events = actualEvents at actual
  cases actual
  exact legacyEffectArguments_injective same

theorem ArgumentsResult.cons
    (first : RuntimeExpressionResult functions context state raw kind (.value value))
    (rest : ArgumentsResult functions context state raws kinds values) :
    ArgumentsResult functions context state (raw::raws) (kind::kinds) (value::values) := by
  intro outcome events evaluated
  have actual := evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩
  generalize same : legacyEffectArguments outcome = actualOutcome at actual
  generalize List.map RuntimeSourceEvent.toEffect events = actualEvents at actual
  cases actual with
  | stopped expression => have impossible := (first.effect expression).2; cases impossible
  | missing expression => exact False.elim expression.outcome_typed
  | cons expression tail =>
    have valueEq := (first.effect expression).2
    cases valueEq
    have tailEq := rest.effect tail
    rw [tailEq] at same
    exact legacyEffectArguments_injective same

variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- Internal modular consequence, not a public assumed-summary endpoint. The
    actual chosen source callee is recovered from global DAG membership and the
    bare-name resolution proof. Clients instantiate `body` with proved contracts. -/
theorem ExactProfile.call_result (profile : ExactProfile bound) (role : Role)
    (args : ArgumentsResult (bound.checked.shape.nodes.map (·.source)) context state raw
      (role.parameterKinds profile.operations.nominal profile.rejections.nominal) values)
    (body : ∀ node ∈ bound.checked.shape.nodes, node.name = role.name →
      ∀ after outcome events, FunctionEvaluation profile node values after outcome events →
        ∃ final, outcome = .returned value final) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) context state
      (.call (.named [role.name]) raw) role.resultKind (.value value) := by
  intro kind outcome events evaluated
  obtain ⟨callee,member,resolves,resultKind,casesCall⟩ := evaluated.call_cases
  obtain ⟨node,nodeMember,sourceEq⟩ := List.mem_map.mp member
  subst callee
  have named : node.name = role.name := by
    have same := resolves.2.2.2.1
    have singleton := List.cons.inj same
    exact node.identified.selected.function.named.symm.trans singleton.1.symm
  have parameters := profile.node_parameters node nodeMember named
  have result := profile.node_result node nodeMember named
  refine ⟨resultKind.trans result,?_⟩
  rcases casesCall with failed | succeeded | trapped
  · obtain ⟨fault,same,evaluatedArgs⟩ := failed
    rw [parameters] at evaluatedArgs
    have impossible := args _ _ evaluatedArgs
    cases impossible
  · obtain ⟨actualValues,argEvents,after,finished,bodyEvents,returned,evaluatedArgs,evaluatedBody,same,eventsEq⟩ := succeeded
    rw [parameters] at evaluatedArgs
    have sameValues := args _ _ evaluatedArgs
    cases sameValues
    obtain ⟨final,bodyEq⟩ := body node nodeMember named after _ _ evaluatedBody
    cases bodyEq
    exact same
  · obtain ⟨actualValues,argEvents,after,finished,bodyEvents,fault,evaluatedArgs,evaluatedBody,same,eventsEq⟩ := trapped
    rw [parameters] at evaluatedArgs
    have sameValues := args _ _ evaluatedArgs
    cases sameValues
    obtain ⟨final,impossible⟩ := body node nodeMember named after _ _ evaluatedBody
    cases impossible

end Aurora.SourceBinding.FramePolicyAttachment
