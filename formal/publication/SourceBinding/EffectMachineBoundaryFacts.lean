import SourceBinding.EffectMachineBoundary
namespace Aurora.SourceBinding

theorem SourceShared.toCall_injective {first second : SourceShared World} (equal : first.toCall = second.toCall) :
    first = (second : SourceShared World) := by
  cases first
  cases second
  cases equal
  rfl

theorem SourceExternalOutcome.toCall_injective {first second : SourceExternalOutcome ExternalFault} (equal : first.toCall = second.toCall) :
    first = (second : SourceExternalOutcome ExternalFault) := by
  cases first <;> cases second <;> cases equal <;> rfl

/-- An empty checked resource inventory imposes no restriction on arbitrary
    source or machine external behavior, as required by the old pure profile. -/
theorem EffectExternalRelated.empty (source : SourceExternalRelation World ExternalFault)
    (machine : ExternalRelation World ExternalFault) : EffectExternalRelated [] source machine := by
  intro key target impossible
  cases impossible

theorem EffectStopResult.shared (result : EffectStopResult pairs after outcome final) :
    final.shared = after.toCall := by
  cases outcome with
  | localFault reason =>
    obtain ⟨active,rfl,same⟩ := result
    exact same
  | externalFault reason =>
    obtain ⟨active,rfl,same⟩ := result
    exact same
  | waiting request =>
    obtain ⟨target,pending,_,rfl,same,rfl⟩ := result
    change pending.request.before = request.before.toCall
    rw [same]
    rfl

theorem EffectExpressionResult.shared
    (result : EffectExpressionResult pairs caller saved base stop after outcome final) :
    final.shared = after.toCall := by
  cases outcome with
  | value raw => cases result; rfl
  | stopped reason => exact EffectStopResult.shared result

theorem EffectBodyResult.shared
    {outcome : SourceEffectBodyOutcome World ExternalFault} {final : CallPhase World ExternalFault}
    (result : EffectBodyResult pairs program caller saved base stop outcome final) :
    final.shared = (match outcome with
      | .continued state | .returned _ state | .stopped _ state => state.shared.toCall) := by
  cases outcome with
  | continued state => obtain ⟨accumulator,rfl⟩ := result; rfl
  | returned value state => obtain ⟨pc,_,rfl⟩ := result; rfl
  | stopped reason state => exact EffectStopResult.shared result

end Aurora.SourceBinding
