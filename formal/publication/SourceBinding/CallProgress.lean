import SourceBinding.CallReflection
namespace Aurora.SourceBinding

/-- Constructive local progress stops at a suspended external request or actual
    terminal state. It never supplies an external response or fairness premise. -/
theorem CallContext.first_boundary {World ExternalFault : Type}
    {family : CallFamilyBinding files root module path member bytes}
    (projection : CallProjectionBinding family)
    {source : SourceCallActive World} {machine : ActiveCall World}
    (context : CallContext family source machine) (external : ExternalRelation World ExternalFault) :
    ∃ sourceFinal machineFinal events,
      SourceCallRuns family.sourceBodies external (.running source) events sourceFinal ∧
      LocalCallRuns family.program (.running machine) events machineFinal ∧
      ExecutionRelated family sourceFinal machineFinal ∧ CallBoundary machineFinal := by
  generalize lengthEq : source.pieces.length = length
  induction length using Nat.strongRecOn generalizing source machine with
  | ind length ih =>
    obtain ⟨next,localRun,related⟩ := context.step (ExternalFault := ExternalFault) projection
    cases stepEq : sourceCallStep (ExternalFault := ExternalFault) family.sourceBodies source with
    | mk sourceNext emitted =>
      rw [stepEq] at localRun related
      have sourceStep : SourceCallTransition family.sourceBodies external (.running source) emitted sourceNext :=
        .local stepEq
      cases related with
      | @running _ _ nextSource nextMachine nextContext =>
        have smaller : nextSource.pieces.length < length := by
          rw [← lengthEq]
          exact source_step_decreases _ _ stepEq
        obtain ⟨sourceFinal,machineFinal,events,sourceRun,machineRun,finalRelated,boundary⟩ :=
          ih _ smaller nextContext rfl
        exact ⟨sourceFinal,machineFinal,emitted ++ events,.step sourceStep sourceRun,
          localRun.trans machineRun,finalRelated,boundary⟩
      | waiting waitingContext =>
        exact ⟨_,_,emitted,SourceCallRuns.one sourceStep,localRun,.waiting waitingContext,by trivial⟩
      | returned same =>
        exact ⟨_,_,emitted,SourceCallRuns.one sourceStep,localRun,.returned same,by trivial⟩
      | trapped same =>
        exact ⟨_,_,emitted,SourceCallRuns.one sourceStep,localRun,.trapped same,by trivial⟩

end Aurora.SourceBinding
