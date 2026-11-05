import SourceBinding.ResourceStatementRules
namespace Aurora.SourceBinding

def SourceEffectBodyOutcome.state : SourceEffectBodyOutcome World ExternalFault → SourceEffectState World
  | .continued state | .returned _ state | .stopped _ state => state

theorem SourceResourceStep.waiting_before {pendingRequest : SourceResourceRequest World}
    (step : SourceResourceStep response request (.stopped (.waiting pendingRequest)) after events) :
    pendingRequest = request ∧ after = request.before ∧ events = [.externalInvoke request] := by
  cases step
  exact ⟨rfl,rfl,rfl⟩

theorem SourceResourceInitialize.retains_response
    (evaluated : SourceResourceInitialize response key arguments binding state outcome events) :
    ∃ result after, SourceResourceStep response ⟨key,arguments,state.shared⟩ result after events ∧
      outcome.state.shared = after := by
  cases evaluated with
  | stopped step => exact ⟨_,_,step,rfl⟩
  | malformed step checked => exact ⟨_,_,step,rfl⟩
  | initialized step checked installed => exact ⟨_,_,step,rfl⟩

theorem SourceResourceAssert.retains_response
    (evaluated : SourceResourceAssert response key arguments state outcome events) :
    ∃ result after, SourceResourceStep response ⟨key,arguments,state.shared⟩ result after events ∧
      outcome.state.shared = after := by
  cases evaluated with
  | stopped step => exact ⟨_,_,step,rfl⟩
  | failed step checked => exact ⟨_,_,step,rfl⟩
  | passed step checked => exact ⟨_,_,step,rfl⟩

theorem SourceResourceAssert.false_retains_poststate
    (responded : response ⟨key,arguments,state.shared⟩ (.returned (some (.boolean false))) after) :
    SourceResourceAssert response key arguments state
      (.stopped (.localFault .assertion) {state with shared := after})
      [.externalInvoke ⟨key,arguments,state.shared⟩,.externalReturn (some (.boolean false)) after] :=
  .failed (.returned responded) rfl

theorem SourceResourceAssert.missing_retains_poststate
    (responded : response ⟨key,arguments,state.shared⟩ (.returned none) after) :
    SourceResourceAssert response key arguments state
      (.stopped (.localFault (.scalar .type)) {state with shared := after})
      [.externalInvoke ⟨key,arguments,state.shared⟩,.externalReturn none after] :=
  .failed (.returned responded) rfl

end Aurora.SourceBinding
