import SourceBinding.CallSource
namespace Aurora.SourceBinding

theorem source_ordinary_running_tail (bodies : SourceCallProgram) (source : SourceCallActive World)
    (rest : List CallPiece) (target : OrdinaryDescriptor) (arguments : List Value)
    (step : sourceOrdinary (ExternalFault := ExternalFault) bodies source rest target arguments = (.running next,events)) :
    next.pieces = rest := by
  unfold sourceOrdinary at step
  cases body : bodies target with
  | none => simp only [body] at step; cases step
  | some body =>
    simp only [body] at step
    split at step <;> cases step
    rfl

theorem source_step_running_tail (bodies : SourceCallProgram) (source : SourceCallActive World)
    (step : sourceCallStep (ExternalFault := ExternalFault) bodies source = (.running next,events)) :
    ∃ piece, source.pieces = piece :: next.pieces := by
  unfold sourceCallStep at step
  cases pieces : source.pieces with
  | nil => simp only [pieces] at step; cases step
  | cons piece rest =>
    refine ⟨piece,?_⟩
    have tail : next.pieces = rest := by
      cases piece with
      | localBody body =>
        simp only [pieces,sourceBodyResult] at step
        split at step <;> cases step
        rfl
      | invoke call =>
        cases call with
        | ordinary target arguments =>
          simp only [pieces] at step
          split at step
          · cases step
          · exact source_ordinary_running_tail _ _ _ _ _ step
        | resourceAssert target arguments =>
          simp only [pieces] at step
          split at step <;> cases step
    rw [tail]

theorem source_step_decreases (bodies : SourceCallProgram) (source : SourceCallActive World)
    (step : sourceCallStep (ExternalFault := ExternalFault) bodies source = (.running next,events)) :
    next.pieces.length < source.pieces.length := by
  obtain ⟨piece,same⟩ := source_step_running_tail bodies source step
  rw [same]
  exact Nat.lt_succ_self _

theorem SourceCallRuns.trans (first : SourceCallRuns bodies external initial events middle)
    (later : SourceCallRuns bodies external middle rest final) :
    SourceCallRuns bodies external initial (events ++ rest) final := by
  induction first with
  | reflexive => exact later
  | step step tail ih => simpa only [List.append_assoc] using SourceCallRuns.step step (ih later)

theorem SourceCallRuns.one (step : SourceCallTransition bodies external initial events final) :
    SourceCallRuns bodies external initial events final := by
  simpa only [List.append_nil] using SourceCallRuns.step step (.reflexive (phase := final))
def sourceRank : SourceCallPhase World ExternalFault → Nat
  | .running active => 2 * active.pieces.length + 1
  | .waiting pending => 2 * pending.remaining.length + 2
  | _ => 0

theorem source_step_rank (bodies : SourceCallProgram) (source : SourceCallActive World) :
    sourceRank (sourceCallStep (ExternalFault := ExternalFault) bodies source).1 < sourceRank (ExternalFault := ExternalFault) (.running source) := by
  cases pieces : source.pieces with
  | nil => simp only [sourceCallStep,pieces,sourceRank,List.length_nil]; omega
  | cons piece rest =>
    cases piece with
    | localBody body =>
      simp only [sourceCallStep,pieces,sourceBodyResult]
      split <;> simp only [sourceRank,pieces,List.length_cons] <;> omega
    | invoke call =>
      cases call with
      | ordinary target arguments =>
        simp only [sourceCallStep,pieces]
        split
        · simp only [sourceRank,pieces,List.length_cons]; omega
        · unfold sourceOrdinary
          split
          · simp only [sourceRank,pieces,List.length_cons]; omega
          · dsimp only
            split <;> simp only [sourceRank,pieces,List.length_cons] <;> omega
      | resourceAssert target arguments =>
        simp only [sourceCallStep,pieces]
        split <;> simp only [sourceRank,pieces,List.length_cons] <;> omega

theorem source_resume_rank (pending : SourceWaiting World) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) : sourceRank (sourceResume pending outcome after).1 < sourceRank (ExternalFault := ExternalFault) (.waiting pending) := by
  cases outcome with
  | fault reason => simp only [sourceResume,sourceRank]; omega
  | returned value =>
    simp only [sourceResume]
    split <;> simp only [sourceRank] <;> omega
end Aurora.SourceBinding
