import SourceBinding.MemoryManagerLedgerFacts

namespace Aurora.SourceBinding.MemoryManagerRelease

private theorem release_accepted_inputs
    (accepted : FramePolicy.transition .release record owner generation link =
      .accept state nextGeneration word) :
    FramePolicy.UserOwner owner ∧ FramePolicy.stateOf record = 2 ∧
      FramePolicy.wordOf record = owner ∧ generation = FramePolicy.generationOf record ∧
      link ≤ FramePolicy.wordMax := by
  simp only [FramePolicy.transition,reduceCtorEq,if_false] at accepted
  by_cases valid : FramePolicy.RecordValid record
  · rw [if_neg (not_not_intro valid)] at accepted
    by_cases user : FramePolicy.UserOwner owner
    · rw [if_neg (not_not_intro user)] at accepted
      by_cases kernel : FramePolicy.stateOf record = 3
      · rw [if_pos kernel] at accepted
        cases accepted
      · rw [if_neg kernel] at accepted
        by_cases retired : FramePolicy.stateOf record = 4
        · rw [if_pos retired] at accepted
          cases accepted
        · rw [if_neg retired] at accepted
          by_cases allocated : FramePolicy.stateOf record = 2
          · rw [if_neg (not_not_intro allocated)] at accepted
            by_cases owned : FramePolicy.wordOf record = owner
            · rw [if_neg (not_not_intro owned)] at accepted
              by_cases matching : generation = FramePolicy.generationOf record
              · rw [if_neg (not_not_intro matching)] at accepted
                by_cases linkBound : link ≤ FramePolicy.wordMax
                · exact ⟨user,allocated,owned,matching,linkBound⟩
                · rw [if_pos (Nat.lt_of_not_ge linkBound)] at accepted
                  cases accepted
              · rw [if_pos matching] at accepted
                cases accepted
            · rw [if_pos owned] at accepted
              cases accepted
          · rw [if_pos allocated] at accepted
            cases accepted
    · rw [if_pos user] at accepted
      cases accepted
  · rw [if_pos valid] at accepted
    cases accepted

/-- Acceptance-kind evidence is postcondition data. This lemma inverts the
existing independent policy; it does not assert a source call or bank write. -/
theorem release_result_inputs
    (specified : FramePolicy.ResultSpec .release record owner generation link next)
    (kind : FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4) :
    FramePolicy.UserOwner owner ∧ FramePolicy.stateOf record = 2 ∧
      FramePolicy.wordOf record = owner ∧ generation = FramePolicy.generationOf record ∧
      link ≤ FramePolicy.wordMax := by
  cases decision : FramePolicy.transition .release record owner generation link with
  | reject reason =>
    have encoded : next = FramePolicy.encode (.reject reason) := specified.trans (congrArg FramePolicy.encode decision)
    have zero : FramePolicy.stateOf next = 0 := by
      rw [encoded]
      cases reason <;> decide
    rcases kind with one | four <;> omega
  | accept state nextGeneration word => exact release_accepted_inputs decision

/-- INTERNAL postcondition consequence; the complete source theorem must
produce ReleaseSuccess rather than assuming the requested store succeeded. -/
theorem ReleaseSuccess.retired_preserved
    (released : ReleaseSuccess before after index generation owner code) :
    RetiredPreserved before after := by
  obtain ⟨position,slot,next,positionEq,selected,specified,kind,delta,returned⟩ := released
  have inputs := release_result_inputs specified kind
  intro other retired
  apply delta.bankWrite.2
  intro same
  subst other
  omega

theorem ReleaseSuccess.canonical_retired
    (released : ReleaseSuccess before after index generation owner code)
    (canonical : CanonicalRetired before) : CanonicalRetired after := by
  obtain ⟨position,slot,next,positionEq,selected,specified,kind,delta,returned⟩ := released
  have inputs := release_result_inputs specified kind
  have matching := FramePolicy.matching_release inputs.2.1 inputs.2.2.1 inputs.1 inputs.2.2.2.1 inputs.2.2.2.2
  intro other retired
  by_cases same : other = position
  · subst other
    rw [delta.bankWrite.1] at retired ⊢
    by_cases full : FramePolicy.generationOf (before.bank position) = FramePolicy.generationMax
    · have result : next = FramePolicy.retiredRecord := by
        change next = FramePolicy.encode (FramePolicy.transition .release (before.bank position) owner generation before.fields.head) at specified
        rw [matching,if_pos full] at specified
        exact specified
      exact result
    · have result : next = FramePolicy.pack 1 (FramePolicy.generationOf (before.bank position) + 1) before.fields.head := by
        change next = FramePolicy.encode (FramePolicy.transition .release (before.bank position) owner generation before.fields.head) at specified
        rw [matching,if_neg full] at specified
        exact specified
      have room : FramePolicy.generationOf (before.bank position) + 1 ≤ FramePolicy.generationMax := by
        have bound := FramePolicy.generation_bound (before.bank position)
        omega
      have free := (FramePolicy.pack_fields 1 _ before.fields.head (by decide) room).1
      rw [result] at retired
      omega
  · rw [delta.bankWrite.2 other same] at retired ⊢
    exact canonical other retired

end Aurora.SourceBinding.MemoryManagerRelease
