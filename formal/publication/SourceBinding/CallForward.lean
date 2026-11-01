import SourceBinding.CallInvocationProof
import SourceBinding.CallTraceProof
import SourceBinding.CallSourceProgress
namespace Aurora.SourceBinding
open Aurora.Publication

theorem CallContext.normalize
    {family : CallFamilyBinding files root module path member bytes}
    {source : SourceCallActive World} {machine : ActiveCall World}
    (context : CallContext family source machine) :
    activeAt family.shape.ir.id [] source.shared.world
      (frameState (machine.frame.inject machine.shared) machine.frame.pc machine.frame.accumulator []) = machine := by
  have callable := context.callable
  have saved := context.saved
  have shared := context.shared
  have stack := context.stack
  rw [← callable,← shared]
  cases machine with
  | mk id frame frames state =>
    cases frame with
    | mk pc accumulator values locals arguments =>
      cases state with
      | mk receiver world =>
        simp only [activeAt,frameState,CallFrame.inject,CallFrame.ofMachine] at *
        subst frames
        subst values
        rfl

/-- One complete source statement, including its checked administrative labels,
    reaches the same next source boundary without any external response choice. -/
theorem CallContext.step {ExternalFault : Type}
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family)
    {source : SourceCallActive World} {machine : ActiveCall World}
    (related : CallContext family source machine) :
    ∃ final : CallPhase World ExternalFault, LocalCallRuns family.program (.running machine)
        (sourceCallStep family.sourceBodies source).2 final ∧
      ExecutionRelated family (sourceCallStep family.sourceBodies source).1 final := by
  let external : ExternalRelation World ExternalFault := fun _ _ _ => False
  let base := machine.frame.inject machine.shared
  have code := related.code
  generalize piecesEq : source.pieces = pieces at code
  cases code with
  | nil labels =>
    have returns := related.returns
    rw [piecesEq] at returns
    cases returns
  | @cons start afterLabels piece middle rest stop labels first tail =>
    have labelRun := labels.effect_runs base base.accumulator []
    rw [← canonical_calls_local (tables family.shape.ir.publication.artifact.document.reversed.reverse)
      (pieceTargets family.shape.source.pieces) family.shape.ir.id] at labelRun
    have prefixRun := labelRun.call_lift (by trivial) [] source.shared.world external
    have remaining : ∀ item ∈ rest, item ∈ family.shape.source.pieces := by
      intro item member
      exact related.remaining item (piecesEq ▸ List.mem_cons_of_mem _ member)
    have pieceRun : ∃ final, CallRuns family.program external
        (.running (activeAt family.shape.ir.id [] source.shared.world (frameState base afterLabels base.accumulator [])))
        (sourceCallStep family.sourceBodies source).2 final ∧
        ExecutionRelated family (sourceCallStep family.sourceBodies source).1 final := by
      cases first with
      | localBody bodyCode =>
        exact bodyCode.root_piece tail source base piecesEq related.context related.returns remaining external
      | ordinary argumentCode meaning =>
        cases evaluated : evalCallArguments (source.shared.source source.arguments) _ with
        | trap fault =>
          obtain ⟨final,run,result⟩ := argumentCode.root_fault source base related.context external fault evaluated
          exact ⟨final,by simpa only [sourceCallStep,piecesEq,evaluated] using run,
            by simpa only [sourceCallStep,piecesEq,evaluated] using result⟩
        | value values =>
          exact ordinary_piece_value projection argumentCode meaning tail source base piecesEq
            related.context related.returns related.remaining external values evaluated
      | resourceAssert argumentCode meaning boolean require =>
        cases evaluated : evalCallArguments (source.shared.source source.arguments) _ with
        | trap fault =>
          obtain ⟨final,run,result⟩ := argumentCode.root_fault source base related.context external fault evaluated
          exact ⟨final,by simpa only [sourceCallStep,piecesEq,evaluated] using run,
            by simpa only [sourceCallStep,piecesEq,evaluated] using result⟩
        | value values =>
          exact resource_piece_value projection argumentCode meaning require tail source base piecesEq
            related.context related.returns related.remaining external values evaluated
    obtain ⟨final,run,result⟩ := pieceRun
    have complete := prefixRun.trans run
    have initial := related.normalize
    refine ⟨final,?_,result⟩
    apply CallRuns.false_local
    simp only [finishEffect,List.map_nil,List.nil_append] at complete
    change CallRuns family.program external (.running (activeAt family.shape.ir.id [] source.shared.world
      (frameState (machine.frame.inject machine.shared) machine.frame.pc machine.frame.accumulator [])))
      (sourceCallStep family.sourceBodies source).2 final at complete
    rw [initial] at complete
    exact complete
theorem ExecutionRelated.step
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family)
    (related : ExecutionRelated family source machine)
    (step : SourceCallTransition family.sourceBodies external source events next) :
    ∃ final, CallRuns family.program external machine events final ∧ ExecutionRelated family next final := by
  cases step with
  | «local» actual =>
    cases related with
    | running context =>
      obtain ⟨final,run,result⟩ := context.step projection
      rw [actual] at run result
      exact ⟨final,run.embed external,result⟩
  | resume response actual =>
    cases related with
    | waiting context =>
      obtain ⟨final,run,result⟩ := context.resume external _ _ response
      rw [actual] at run result
      exact ⟨final,run,result⟩

theorem SourceCallRuns.forward
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family)
    (run : SourceCallRuns family.sourceBodies external source events final)
    (related : ExecutionRelated family source machine) :
    ∃ result, CallRuns family.program external machine events result ∧ ExecutionRelated family final result := by
  induction run generalizing machine with
  | reflexive => exact ⟨machine,.reflexive,related⟩
  | step first rest ih =>
    obtain ⟨middle,prefixRun,middleRelated⟩ := related.step projection first
    obtain ⟨result,later,resultRelated⟩ := ih middleRelated
    exact ⟨result,prefixRun.trans later,resultRelated⟩
end Aurora.SourceBinding
