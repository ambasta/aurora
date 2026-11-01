import SourceBinding.CallBinding
import SourceBinding.CallFootprint
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Optional checked policy shape: rejecting guard, actual ordinary callee, then
    asserted resource invocation. No names, ordinals or instruction PCs are fixed. -/
structure GuardedCallPrefix (checked : CallBinding files root module path member bytes) where
  guard : GuardExpr .boolean
  target : OrdinaryDescriptor
  arguments : CallArguments target.parameters
  resource : ResourceDescriptor
  resourceArguments : CallArguments resource.parameters
  rest : List CallPiece
  order : checked.family.shape.source.pieces =
    .localBody (.branch guard (.seq (.returnValue .boolean (.boolLit false)) .skip)) ::
    .invoke (.ordinary target arguments) :: .invoke (.resourceAssert resource resourceArguments) :: rest
  leaf : CheckedCallLeaf checked.family.shape target
  selected : checked.family.leaves.lookup target = some leaf
  disjoint : ∀ index ∈ guardReads guard, index ∉ bodyWrites leaf.source.body

def checkGuardedCallPrefix (checked : CallBinding files root module path member bytes) :
    Option (GuardedCallPrefix checked) :=
  match order : checked.family.shape.source.pieces with
  | .localBody (.branch guard (.seq (.returnValue .boolean (.boolLit false)) .skip)) ::
      .invoke (.ordinary target arguments) :: .invoke (.resourceAssert resource resourceArguments) :: rest => do
    match selected : checked.family.leaves.lookup target with
    | none => none
    | some leaf =>
      if disjoint : ∀ index ∈ guardReads guard, index ∉ bodyWrites leaf.source.body then
        return ⟨guard,target,arguments,resource,resourceArguments,rest,order,leaf,selected,disjoint⟩
      else none
  | _ => none

/-- The saved ROOT parameter map is fixed while the actual callee runs with its
    separately evaluated arguments. Guard preservation follows from actual
    stores, including fault prefixes; neither successful enter nor external
    preservation is assumed. The result stops BEFORE resource behavior. -/
theorem GuardedCallPrefix.preserves_guard
    (guarded : GuardedCallPrefix checked) (caller : SourceState) (values : List Value)
    (evaluated : evalCallArguments caller guarded.arguments = .value values) :
    ∃ result,
      EffectRuns (canonicalEffects (tables checked.family.shape.ir.publication.artifact.document.reversed.reverse)
        guarded.target.id)
        ((freshCallFrame values).inject (⟨caller.fields,()⟩ : CallShared Unit))
        (evalBody guarded.leaf.source.body ⟨caller.fields,fun index => values[index]?⟩).stores result ∧
      EffectTerminal result ∧
      evalGuard ⟨result.state.receiver,caller.parameters⟩ guarded.guard = evalGuard caller guarded.guard := by
  let base := (freshCallFrame values).inject (⟨caller.fields,()⟩ : CallShared Unit)
  have ready := eval_call_arguments_ready caller guarded.arguments evaluated
  have entry : EntryArguments guarded.leaf.body.bindings base.arguments :=
    ready.entry guarded.leaf.body.entry guarded.leaf.identity.parameters
  obtain ⟨result,run,related,terminal⟩ := guarded.leaf.body.executes base entry
  have sizes := congrArg List.length guarded.leaf.identity.parameters
  simp only [List.length_map] at sizes
  have length : guarded.leaf.body.bindings.length = values.length := by
    have entryLength := guarded.leaf.body.entry.1
    have valueLength := ready.length
    omega
  have sourceEq := entrySource_values (⟨caller.fields,()⟩ : CallShared Unit) values guarded.leaf.body.bindings length
  change entrySource base guarded.leaf.body.bindings.length = _ at sourceEq
  rw [sourceEq] at run
  have start : preparedEntry base (parameterSlot guarded.leaf.body.bindings) 0 = base := rfl
  rw [start] at run
  refine ⟨result,run,terminal,?_⟩
  exact run.guard_footprint_frame guarded.leaf.source.body _ guarded.guard caller.parameters guarded.disjoint
end Aurora.SourceBinding
