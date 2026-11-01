import SourceBinding.CallMachineProof
namespace Aurora.SourceBinding

/-- A local segment stops before any external response, or at termination. -/
def CallBoundary : CallPhase World ExternalFault → Prop
  | .running _ => False
  | _ => True

/-- Only deterministic running-source steps. Waiting and terminal phases have
    no successor in this relation; external responses are deliberately absent.
    A segment may also stop early at a running phase for compositional use. -/
inductive LocalCallRuns (program : CallProgram) :
    CallPhase World ExternalFault → List (CallEvent World ExternalFault) → CallPhase World ExternalFault → Prop
  | reflexive : LocalCallRuns program phase [] phase
  | step : callStep program active = (middle,events) →
      LocalCallRuns program middle later final →
      LocalCallRuns program (.running active) (events ++ later) final

variable {World ExternalFault : Type} {program : CallProgram}
  {initial middle final boundary otherFinal : CallPhase World ExternalFault}
  {events later otherEvents prefixEvents : List (CallEvent World ExternalFault)}
  {external : ExternalRelation World ExternalFault}

theorem LocalCallRuns.embed (run : LocalCallRuns program initial events final)
    (external : ExternalRelation World ExternalFault) :
    CallRuns program external initial events final := by
  induction run with
  | reflexive => exact .reflexive
  | step first rest ih => exact .step (.local first) (ih external)

/-- A finite run under the empty response relation contains only local steps.
    This does not classify an unanswered wait as blocked or divergent. -/
theorem CallRuns.false_local
    (run : CallRuns program (fun _ _ _ => False) initial events final) :
    LocalCallRuns program initial events final := by
  induction run with
  | reflexive => exact .reflexive
  | step first rest ih =>
    cases first with
    | «local» first => exact .step first ih
    | resume impossible resumed => exact False.elim impossible

theorem LocalCallRuns.trans (first : LocalCallRuns program initial events middle)
    (rest : LocalCallRuns program middle later final) :
    LocalCallRuns program initial (events ++ later) final := by
  induction first with
  | reflexive => exact rest
  | step first tail ih => simpa only [List.append_assoc] using LocalCallRuns.step first (ih rest)

theorem running_transition_unique
    (first : CallTransition program external (.running active) events next)
    (second : CallTransition program external (.running active) otherEvents otherNext) :
    next = otherNext ∧ events = otherEvents := by
  cases first with
  | «local» first => cases second with
    | «local» second => exact Prod.mk.inj (first.symm.trans second)

/-- An arbitrary finite run reaching any boundary contains the whole constructed
    deterministic local prefix. Its remaining responses retain their original
    witnesses; no equality of distinct external outcomes is assumed. -/
theorem LocalCallRuns.decompose
    (segment : LocalCallRuns program initial prefixEvents boundary)
    (run : CallRuns program external initial events final)
    (finished : CallBoundary final) :
    ∃ rest, events = prefixEvents ++ rest ∧ CallRuns program external boundary rest final := by
  induction segment with
  | reflexive => exact ⟨events,rfl,run⟩
  | step first tail ih =>
    cases run with
    | reflexive => cases finished
    | step actual rest =>
      cases actual with
      | «local» actual =>
        obtain ⟨sameMiddle,sameEvents⟩ := Prod.mk.inj (first.symm.trans actual)
        cases sameMiddle
        cases sameEvents
        obtain ⟨remaining,equal,after⟩ := ih rest finished
        exact ⟨remaining,by rw [equal,List.append_assoc],after⟩

/-- A local segment starting at a boundary is necessarily empty. -/
theorem LocalCallRuns.from_boundary (run : LocalCallRuns program initial events final)
    (boundary : CallBoundary initial) : events = [] ∧ final = initial := by
  cases run with
  | reflexive => exact ⟨rfl,rfl⟩
  | step first rest => cases boundary

/-- Two locally constructed first exits agree, including their complete event
    lists, even though the ambient external relation may be nondeterministic. -/
theorem LocalCallRuns.boundary_unique
    (first : LocalCallRuns program initial events final)
    (second : LocalCallRuns program initial otherEvents otherFinal)
    (boundary : CallBoundary final) (otherBoundary : CallBoundary otherFinal) :
    events = otherEvents ∧ final = otherFinal := by
  induction first with
  | reflexive =>
    obtain ⟨empty,same⟩ := second.from_boundary boundary
    exact ⟨empty.symm,same.symm⟩
  | step first rest ih =>
    cases second with
    | reflexive => cases otherBoundary
    | step second tail =>
      obtain ⟨sameMiddle,sameEvents⟩ := Prod.mk.inj (first.symm.trans second)
      cases sameMiddle
      cases sameEvents
      obtain ⟨sameTail,sameFinal⟩ := ih tail boundary otherBoundary
      exact ⟨by rw [sameTail],sameFinal⟩

/-- Inverting the actual residual run exposes the SAME response witness, not a
    newly selected response from the relation. An empty wait is allowed. -/
theorem waiting_run_cases
    (run : CallRuns program external (.waiting pending) events final) :
    (events = [] ∧ final = .waiting pending) ∨
    ∃ outcome after next emitted rest,
      external pending.request outcome after ∧
      resumeCall pending outcome after = (next,emitted) ∧
      events = emitted ++ rest ∧ CallRuns program external next rest final := by
  cases run with
  | reflexive => exact .inl ⟨rfl,rfl⟩
  | step first tail =>
    cases first with
    | resume allowed resumed => exact .inr ⟨_,_,_,_,_,allowed,resumed,rfl,tail⟩

/-- Strengthens the existing effect lift without assuming absence of response
    events: the construction uses only the already proved local step bridge. -/
theorem EffectRuns.local_call_lift {program : CallProgram} {callable : Int}
    {initial : Machine} {stores : List StoreEvent} {result : EffectExecution}
    (run : EffectRuns (localProgram program callable) initial stores result)
    (supported : LocalSupported result) (saved : List SavedCall) (world : World) :
    LocalCallRuns program (.running (activeAt callable saved world initial))
      (stores.map CallEvent.store ++ (finishEffect callable saved world result).2)
      (finishEffect (ExternalFault := ExternalFault) callable saved world result).1 := by
  induction run with
  | reflexive => exact .reflexive
  | next first rest ih =>
    have step := lifted_local_step (ExternalFault := ExternalFault) program callable saved world _ _ _ first (by trivial)
    simpa only [finishEffect,List.append_nil,List.map_append,List.append_assoc] using
      LocalCallRuns.step step (ih supported)
  | returned first =>
    have step := lifted_local_step (ExternalFault := ExternalFault) program callable saved world _ _ _ first supported
    simpa only [List.append_nil] using LocalCallRuns.step step .reflexive
  | trap first =>
    have step := lifted_local_step (ExternalFault := ExternalFault) program callable saved world _ _ _ first supported
    simpa only [List.append_nil] using LocalCallRuns.step step .reflexive

/-- Infinitely many running-source steps without any external response. This is
    local divergence only, not divergence of an arbitrary environment interaction. -/
def LocalCallDiverges (program : CallProgram) (initial : CallPhase World ExternalFault) : Prop :=
  ∃ states : Nat → ActiveCall World, initial = .running (states 0) ∧
    ∀ n, ∃ emitted : List (CallEvent World ExternalFault),
      callStep program (states n) = (.running (states (n + 1)),emitted)

/-- A constructed finite first exit excludes an infinite local running path.
    It does not exclude later external or resumed divergence. -/
theorem LocalCallRuns.not_diverges
    (run : LocalCallRuns program initial events final) (boundary : CallBoundary final) :
    ¬ LocalCallDiverges program initial := by
  induction run with
  | reflexive =>
    rintro ⟨states,first,steps⟩
    rw [first] at boundary
    exact boundary
  | step first rest ih =>
    rintro ⟨states,initial,steps⟩
    cases initial
    obtain ⟨emitted,next⟩ := steps 0
    obtain ⟨same,_⟩ := Prod.mk.inj (first.symm.trans next)
    apply ih boundary
    refine ⟨fun n => states (n + 1),same,?_⟩
    intro n
    exact steps (n + 1)

end Aurora.SourceBinding
