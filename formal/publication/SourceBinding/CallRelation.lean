import SourceBinding.CallLeafProof
namespace Aurora.SourceBinding
open Aurora.Publication

/-- A resumable relation retains code/continuation context, unlike the deliberately
    weaker final BoundaryRelated observation. -/
structure CallContext (family : CallFamilyBinding files root module path member bytes)
    (source : SourceCallActive World) (machine : ActiveCall World) : Prop where
  callable : machine.callable = family.shape.ir.id
  saved : machine.saved = []
  shared : machine.shared = source.shared
  stack : machine.frame.stack = []
  context : ContextRelated (source.shared.source source.arguments) (machine.frame.inject machine.shared)
    (parameterSlot family.shape.bindings)
  returns : CallReturns source.pieces
  remaining : ∀ piece ∈ source.pieces, piece ∈ family.shape.source.pieces
  code : CallPiecesCode (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id
    (parameterSlot family.shape.bindings) source.pieces machine.frame.pc family.shape.stop

structure WaitingContext (family : CallFamilyBinding files root module path member bytes)
    (source : SourceWaiting World) (machine : WaitingCall World) : Prop where
  request : machine.request = source.request
  callable : machine.callable = family.shape.ir.id
  saved : machine.saved = []
  stack : machine.continuation.stack = []
  context : ContextRelated (source.request.before.source source.arguments)
    (machine.continuation.inject machine.request.before) (parameterSlot family.shape.bindings)
  returns : CallReturns source.remaining
  remaining : ∀ piece ∈ source.remaining, piece ∈ family.shape.source.pieces
  require : canonicalEffects (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    family.shape.ir.id machine.continuation.pc = some .require
  code : CallPiecesCode (tables family.shape.ir.publication.artifact.document.reversed.reverse) family.shape.ir.id
    (parameterSlot family.shape.bindings) source.remaining (machine.continuation.pc + 1) family.shape.stop

inductive ExecutionRelated (family : CallFamilyBinding files root module path member bytes) :
    SourceCallPhase World ExternalFault → CallPhase World ExternalFault → Prop
  | running : CallContext family source machine → ExecutionRelated family (.running source) (.running machine)
  | waiting : WaitingContext family source machine → ExecutionRelated family (.waiting source) (.waiting machine)
  | returned : machine.shared = shared → ExecutionRelated family (.returned value shared) (.returned value machine)
  | trapped : machine.shared = shared → ExecutionRelated family (.trapped fault shared) (.trapped fault machine)

theorem ExecutionRelated.boundary (related : ExecutionRelated family source machine)
    (observed : sourceBoundary source = some observation) : machineBoundary machine = some observation := by
  cases related with
  | running context => cases observed
  | waiting context => simp only [sourceBoundary,Option.some.injEq] at observed; subst observation
                       simp only [machineBoundary,context.request]
  | returned shared | trapped shared =>
    simp only [sourceBoundary,Option.some.injEq] at observed
    subst observation
    simp only [machineBoundary,shared]

/-- Changing Shared installs the SAME current receiver in both contexts. Only
    protected parameter/local correspondence survives the external boundary. -/
theorem ContextRelated.change_shared (frame : CallFrame) (before after : CallShared World)
    (arguments : Nat → Option Value)
    (context : ContextRelated (before.source arguments) (frame.inject before) slots) :
    ContextRelated (after.source arguments) (frame.inject after) slots :=
  ⟨fun _ => rfl,context.parameters⟩
end Aurora.SourceBinding
