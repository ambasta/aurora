import SourceBinding.CallEnvironment
import SourceBinding.CallArgumentProof
namespace Aurora.SourceBinding
open Aurora.Publication

theorem ReadyArguments.entry {kinds : List GuardType} (ready : ReadyArguments kinds values)
    (entry : EntryCode program formals bindings)
    (declared : formals.map (·.type) = kinds.map guardSourceType) :
    EntryArguments bindings (fun index => values[index]?) := by
  intro index bound
  exact ready.lookup (EntryCode.argument_kinds entry declared bound)

theorem entrySource_values (shared : CallShared World) (values : List Value) (bindings : List ParameterBinding)
    (length : bindings.length = values.length) :
    entrySource ((freshCallFrame values).inject shared) bindings.length =
      shared.source (fun index => values[index]?) := by
  unfold entrySource CallShared.source
  apply congrArg (SourceState.mk shared.receiver)
  funext index
  simp only [freshCallFrame,CallFrame.inject]
  by_cases bound : index < bindings.length
  · simp only [bound,if_true]
  · have missing : values[index]? = none := List.getElem?_eq_none (by omega)
    simp only [bound,if_false,missing]

/-- Execute the selected actual callee, including its actual typed entry, then
    lift all stores/faults/returns into the caller machine. Readiness here is
    derived by the invocation argument theorem; it is not assertion truth. -/
theorem CheckedCallLeaf.call_executes
    {shape : CallShapeBinding files root module path member bytes}
    (leaf : CheckedCallLeaf shape target) (program : CallProgram)
    (projection : localProgram program target.id =
      canonicalEffects (tables shape.ir.publication.artifact.document.reversed.reverse) target.id)
    (shared : CallShared World) (values : List Value) (ready : ReadyArguments target.parameters values)
    (saved : List SavedCall) (external : ExternalRelation World ExternalFault) :
    ∃ result,
      CallRuns program external
        (.running (activeAt target.id saved shared.world ((freshCallFrame values).inject shared)))
        ((evalBody leaf.source.body (shared.source (fun index => values[index]?))).stores.map CallEvent.store ++
          (finishEffect target.id saved shared.world result).2)
        (finishEffect target.id saved shared.world result).1 ∧
      BodyResultRelated (parameterSlot leaf.body.bindings) [] leaf.body.stop
        (evalBody leaf.source.body (shared.source (fun index => values[index]?))).execution result ∧
      EffectTerminal result := by
  have sizes := congrArg List.length leaf.identity.parameters
  simp only [List.length_map] at sizes
  have count : leaf.body.bindings.length = values.length := by
    have entryLength := leaf.body.entry.1
    have valueLength := ready.length
    omega
  let base := (freshCallFrame values).inject shared
  have entryReady : EntryArguments leaf.body.bindings base.arguments :=
    ready.entry leaf.body.entry leaf.identity.parameters
  obtain ⟨result,run,related,terminal⟩ := leaf.body.executes base entryReady
  have sourceEq := entrySource_values shared values leaf.body.bindings count
  change entrySource base leaf.body.bindings.length = _ at sourceEq
  rw [sourceEq] at run related
  have initial : preparedEntry base (parameterSlot leaf.body.bindings) 0 = base := rfl
  rw [initial,← projection] at run
  have supported := related.supported (eval_body_supported _ _)
  exact ⟨result,run.call_lift supported saved shared.world external,related,terminal⟩
end Aurora.SourceBinding
