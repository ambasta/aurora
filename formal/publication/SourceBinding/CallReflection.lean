import SourceBinding.CallForward
namespace Aurora.SourceBinding

theorem returned_run_empty (run : CallRuns program external (.returned value active) events final) :
    events = [] ∧ final = .returned value active := by
  cases run with
  | reflexive => exact ⟨rfl,rfl⟩
  | step first rest => cases first

theorem trapped_run_empty (run : CallRuns program external (.trapped fault active) events final) :
    events = [] ∧ final = .trapped fault active := by
  cases run with
  | reflexive => exact ⟨rfl,rfl⟩
  | step first rest => cases first

/-- Every finite machine boundary trace reflects an actual source trace. Local
    prefix decomposition is deterministic; external outcomes are taken from the
    actual run's witness, never replaced by a favorable existential choice. -/
theorem CallRuns.reflect {World ExternalFault : Type} {external : ExternalRelation World ExternalFault}
    {source : SourceCallPhase World ExternalFault} {machine final : CallPhase World ExternalFault}
    {events : List (CallEvent World ExternalFault)}
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family)
    (related : ExecutionRelated family source machine)
    (run : CallRuns family.program external machine events final)
    (boundary : CallBoundary final) :
    ∃ result, SourceCallRuns family.sourceBodies external source events result ∧
      ExecutionRelated family result final := by
  generalize rankEq : sourceRank source = rank
  induction rank using Nat.strongRecOn generalizing source machine events with
  | ind rank ih =>
    cases related with
    | returned same =>
      obtain ⟨empty,finalEq⟩ := returned_run_empty run
      subst events
      subst final
      exact ⟨_,.reflexive,.returned same⟩
    | trapped same =>
      obtain ⟨empty,finalEq⟩ := trapped_run_empty run
      subst events
      subst final
      exact ⟨_,.reflexive,.trapped same⟩
    | @running _ _ source machine context =>
      obtain ⟨next,localRun,nextRelated⟩ := context.step projection
      obtain ⟨remaining,traceEq,rest⟩ := localRun.decompose run boundary
      have smaller : sourceRank (sourceCallStep (ExternalFault := ExternalFault) family.sourceBodies source).1 < rank := by
        rw [← rankEq]
        exact source_step_rank _ _
      obtain ⟨result,sourceRest,resultRelated⟩ := ih _ smaller nextRelated rest rfl
      have first : SourceCallTransition family.sourceBodies external (.running source)
          (sourceCallStep family.sourceBodies source).2 (sourceCallStep family.sourceBodies source).1 := .local rfl
      exact ⟨result,traceEq ▸ SourceCallRuns.step first sourceRest,resultRelated⟩
    | @waiting _ _ source machine context =>
      rcases waiting_run_cases run with ⟨empty,finalEq⟩ | ⟨outcome,after,next,emitted,remaining,response,resumed,traceEq,rest⟩
      · subst events
        subst final
        exact ⟨_,.reflexive,.waiting context⟩
      · obtain ⟨middle,localRun,middleRelated,sameEvents⟩ := context.resume_local outcome after
        have continued : CallRuns family.program external (resumeCall machine outcome after).1 remaining final := by
          simpa only [resumed] using rest
        obtain ⟨later,laterEq,tail⟩ := localRun.decompose continued boundary
        have smaller : sourceRank (sourceResume source outcome after).1 < rank := by
          rw [← rankEq]
          exact source_resume_rank _ _ _
        obtain ⟨result,sourceRest,resultRelated⟩ := ih _ smaller middleRelated tail rfl
        have sourceResponse : external source.request outcome after := context.request ▸ response
        have first : SourceCallTransition family.sourceBodies external (.waiting source)
            (sourceResume source outcome after).2 (sourceResume source outcome after).1 :=
          .resume sourceResponse rfl
        have emittedEq : emitted = (sourceResume source outcome after).2 := by
          simpa only [resumed] using sameEvents
        have total : events = (sourceResume source outcome after).2 ++ later := by
          rw [traceEq,emittedEq,laterEq,List.nil_append]
        exact ⟨result,total ▸ SourceCallRuns.step first sourceRest,resultRelated⟩
end Aurora.SourceBinding
