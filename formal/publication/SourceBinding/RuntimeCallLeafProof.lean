import SourceBinding.RuntimeCallIdentity
import SourceBinding.RuntimeCallSupport
import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

theorem RuntimeReadyArguments.entry (ready : RuntimeReadyArguments kinds values) :
    RuntimeEntryArguments kinds (fun index => values[index]?) := by
  intro index kind found
  obtain ⟨value,present,typed⟩ := ready.lookup found
  exact ⟨value,present,typed⟩

theorem RuntimeTerminal.supported (related : RuntimeTerminal base outcome result)
    (supported : SupportedOutcome outcome) : LocalSupported result := by
  cases outcome with
  | value value => cases result <;> first | trivial | cases related.1
  | trap fault =>
    cases result with
    | next state | returned value state => cases related.1
    | trap actual state =>
      cases actual with
      | assertion => cases related.1
      | scalar actual =>
        have same : actual = fault := related.1
        subst actual
        cases fault <;> first | trivial | exact supported

/-- Execute the actual selected call-free leaf from its real fresh entry.
    Both ordinary return and scalar fault are lifted into the SAME call machine;
    the latter retains the active callee and every saved caller frame. -/
theorem RuntimeCallLeaf.call_executes
    (leaf : RuntimeCallLeaf t files root module path) (program : CallProgram)
    (projection : localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (shared : CallShared World) (values : List Value)
    (ready : RuntimeReadyArguments leaf.source.parameters values)
    (saved : List SavedCall) (external : ExternalRelation World ExternalFault)
    (functions : List RuntimeSourceLeaf) :
    ∃ outcome result,
      RuntimeEvaluatesWith functions leaf.source.context
        (formalSourceLocals leaf.source.parameters (fun index => values[index]?))
        leaf.source.raw leaf.source.result outcome [] ∧
      CallRuns program external
        (.running (activeAt leaf.target.id saved shared.world ((freshCallFrame values).inject shared)))
        (finishEffect leaf.target.id saved shared.world result).2
        (finishEffect leaf.target.id saved shared.world result).1 ∧
      RuntimeTerminal (preparedEntry ((freshCallFrame values).inject shared)
        runtimeParameterSlot leaf.source.parameters.length) outcome result := by
  let base := (freshCallFrame values).inject shared
  have entry : RuntimeEntryArguments leaf.body.parameters.kinds base.arguments := ready.entry
  obtain ⟨outcome,result,evaluated,run,related⟩ := leaf.body.executes base entry
  have supported := related.supported evaluated.supported
  have initial : preparedEntry base runtimeParameterSlot 0 = base := rfl
  rw [initial,← projection] at run
  refine ⟨outcome,result,RuntimeEvaluates.in_environment evaluated functions,?_,related⟩
  simpa only [List.map_nil,List.nil_append] using run.call_lift supported saved shared.world external

end Aurora.SourceBinding
