import SourceBinding.EffectCallableBinding
import SourceBinding.EffectMachineTrace
import SourceBinding.RuntimeCallSourceFacts
namespace Aurora.SourceBinding

/-- INTERNAL induction property for the actual checked node body. It consumes
    an actual source derivation, never an assumed result or supplied run summary.
    Source response/initial shared state and the entire source observation are
    fixed before machine traces and arbitrary saved continuations. Resource pairs
    are the INTERNAL all-syntactic-used closure derived by the full code checker,
    not every available declaration or a public caller-supplied interface. -/
def EffectCalleeSimulates (program : CallProgram)
    (nodes : List (EffectCallable t files root)) (resources : EffectResourcePairs)
    (node : EffectCallable t files root)
    (World ExternalFault : Type) : Prop :=
  ∀ (response : SourceExternalRelation World ExternalFault)
    (shared : SourceShared World) (values : List Value),
    RuntimeReadyArguments node.source.parameters values →
    ∀ after outcome sourceEvents,
    EffectStatements (nodes.map (·.source)) response node.source.context node.source.result
      node.source.initialCursor
      ⟨formalSourceLocals node.source.parameters (fun index => values[index]?),shared⟩
      node.source.parsed.statements after outcome sourceEvents →
    ∃ machineEvents,
      EffectMachineTraceRelated (EffectCallable.ordinaryPairs nodes)
        resources (nodes.flatMap (·.fieldPairs))
        sourceEvents machineEvents ∧
      ∀ (saved : List SavedCall) (external : ExternalRelation World ExternalFault),
      EffectExternalRelated resources response external →
      ∃ final, CallRuns program external
        (.running ⟨node.target.id,freshCallFrame values,saved,shared.toCall⟩) machineEvents final ∧
        EffectBodyResult resources program node.target.id saved
          (freshCallFrame values) (Aurora.Publication.functionCode t node.target.id).size outcome final

end Aurora.SourceBinding
