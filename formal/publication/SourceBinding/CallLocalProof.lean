import SourceBinding.CallResume
namespace Aurora.SourceBinding
open Aurora.Publication

theorem CallReturns.local_tail (returns : CallReturns (.localBody body :: rest))
    (normal : (evalBody body state).execution = .next next) : CallReturns rest := by
  cases returns with
  | here definite => exact False.elim (definite.no_fallthrough state next normal)
  | later later => exact later

theorem CallReturns.invoke_tail (returns : CallReturns (.invoke call :: rest)) : CallReturns rest := by
  cases returns with | later later => exact later

/-- A call-free root piece is simulated using the old complete body semantics.
    Its current receiver and exact stores are installed in the shared state. -/
theorem BodyCode.root_piece
    {family : CallFamilyBinding files root module path member bytes}
    {body : EffectBody} {rest : List CallPiece} {start stop : Nat}
    (code : BodyCode (canonicalEffects (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id) (parameterSlot family.shape.bindings) body start stop)
    (tail : CallPiecesCode (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      family.shape.ir.id (parameterSlot family.shape.bindings) rest stop family.shape.stop)
    (source : SourceCallActive World) (base : Machine)
    (pieces : source.pieces = .localBody body :: rest)
    (context : ContextRelated (source.shared.source source.arguments) base (parameterSlot family.shape.bindings))
    (returns : CallReturns source.pieces)
    (remaining : ∀ piece ∈ rest, piece ∈ family.shape.source.pieces)
    (external : ExternalRelation World ExternalFault) :
    ∃ final, CallRuns
        (canonicalCalls (tables family.shape.ir.publication.artifact.document.reversed.reverse)
          (pieceTargets family.shape.source.pieces)) external
        (.running (activeAt family.shape.ir.id [] source.shared.world
          (frameState base start base.accumulator [])))
        (sourceCallStep family.sourceBodies source).2 final ∧
      ExecutionRelated family (sourceCallStep family.sourceBodies source).1 final := by
  let program := canonicalCalls (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces)
  obtain ⟨result,run,related⟩ := code.simulates (source.shared.source source.arguments) base context base.accumulator []
  have supported := related.supported (eval_body_supported _ _)
  rw [← canonical_calls_local (tables family.shape.ir.publication.artifact.document.reversed.reverse)
    (pieceTargets family.shape.source.pieces) family.shape.ir.id] at run
  have lifted := run.call_lift supported [] source.shared.world external
  cases evaluated : (evalBody body (source.shared.source source.arguments)).execution with
  | next next =>
    cases result with
    | returned _ _ | trap _ _ => simp only [evaluated,BodyResultRelated] at related
    | next machine =>
      have relation : machine.pc = stop ∧ machine.stack = [] ∧
          ContextRelated next machine (parameterSlot family.shape.bindings) := by
        simpa only [evaluated,BodyResultRelated] using related
      have normal : (evalBody body (source.shared.source source.arguments)).execution = .next next := evaluated
      have tailReturns := CallReturns.local_tail (pieces ▸ returns) normal
      simp only [sourceCallStep,pieces,sourceBodyResult,evaluated]
      refine ⟨.running (activeAt family.shape.ir.id [] source.shared.world machine),?_,.running ?_⟩
      · simpa only [sourceCallStep,pieces,sourceBodyResult,evaluated,finishEffect,List.append_nil] using lifted
      · refine ⟨rfl,rfl,?_,relation.2.1,?_,tailReturns,remaining,?_⟩
        · change CallShared.mk machine.receiver source.shared.world = CallShared.mk next.fields source.shared.world
          exact congrArg (fun fields => CallShared.mk fields source.shared.world) (funext relation.2.2.fields)
        · refine ⟨relation.2.2.fields,?_⟩
          have parameters := eval_body_parameters body (source.shared.source source.arguments)
          rw [evaluated] at parameters
          change next.parameters = source.arguments at parameters
          intro index
          exact (relation.2.2.parameters index).trans (congrFun parameters index)
        · simpa only [activeAt,CallFrame.ofMachine,relation.1] using tail
  | returned value state =>
    cases result with
    | next _ | trap _ _ => simp only [evaluated,BodyResultRelated] at related
    | returned actual machine =>
      have relation : value = actual ∧ machine.receiver = state.fields ∧ machine.stack = [] := by
        simpa only [evaluated,BodyResultRelated] using related
      have same := relation.1
      subst actual
      simp only [sourceCallStep,pieces,sourceBodyResult,evaluated]
      refine ⟨.returned value (activeAt family.shape.ir.id [] source.shared.world machine),?_,.returned ?_⟩
      · simpa only [sourceCallStep,pieces,sourceBodyResult,evaluated,finishEffect,returnToCaller,
          activeAt,List.append_nil] using lifted
      · exact congrArg (fun fields => CallShared.mk fields source.shared.world) relation.2.1
  | trap fault state =>
    cases result with
    | next _ | returned _ _ => simp only [evaluated,BodyResultRelated] at related
    | trap actual machine =>
      have relation : fault = actual ∧ machine.receiver = state.fields := by
        simpa only [evaluated,BodyResultRelated] using related
      have same := relation.1
      subst actual
      simp only [sourceCallStep,pieces,sourceBodyResult,evaluated]
      refine ⟨.trapped (.local fault) (activeAt family.shape.ir.id [] source.shared.world machine),?_,.trapped ?_⟩
      · simpa only [sourceCallStep,pieces,sourceBodyResult,evaluated,finishEffect,List.append_nil] using lifted
      · exact congrArg (fun fields => CallShared.mk fields source.shared.world) relation.2
end Aurora.SourceBinding
