import SourceBinding.EffectSourceData
import SourceBinding.CallState
namespace Aurora.SourceBinding

/-- The resource boundary is not an expression evaluator. The bounded source
    profile installs it only in a direct local initializer or direct require.
    Argument evaluation and exact receiver/resource resolution are premises of
    the enclosing SAME source statement rule, not supplied operation summaries. -/
inductive SourceResourceStep (response : SourceExternalRelation World ExternalFault)
    (request : SourceResourceRequest World) :
    SourceEffectOutcome World ExternalFault → SourceShared World →
      List (SourceEffectEvent World ExternalFault) → Prop
  | pending : SourceResourceStep response request (.stopped (.waiting request))
      request.before [.externalInvoke request]
  | returned (responded : response request (.returned raw) after) :
      SourceResourceStep response request (.value raw) after
        [.externalInvoke request,.externalReturn raw after]
  | fault (responded : response request (.fault reason) after) :
      SourceResourceStep response request (.stopped (.externalFault reason)) after
        [.externalInvoke request,.externalFault reason after]

/-- Actual typed localStore boundary after a direct resource initializer.
    No eager external-result validation, no rollback of response shared state,
    and no invented machine fault for failed ghost declaration admission. -/
inductive SourceResourceInitialize (response : SourceExternalRelation World ExternalFault)
    (key : RuntimeSourceResource) (arguments : List Value)
    (binding : SourceLocal) (state : SourceEffectState World) :
    SourceEffectBodyOutcome World ExternalFault → List (SourceEffectEvent World ExternalFault) → Prop
  | stopped (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.stopped stop) after events) :
      SourceResourceInitialize response key arguments binding state
        (.stopped stop {state with shared := after}) events
  | malformed (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.value raw) after events)
      (checked : readRuntime binding.kind raw = .trap fault) :
      SourceResourceInitialize response key arguments binding state
        (.stopped (.localFault (.scalar fault)) {state with shared := after}) events
  | initialized (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.value raw) after events)
      (checked : readRuntime binding.kind raw = .value value)
      (installed : state.locals.initialize binding.slot binding.runtimeDeclaration value = some next) :
      SourceResourceInitialize response key arguments binding state
        (.continued ⟨next,after⟩) events

/-- Actual require boundary, sharing assertResult with the existing machine and
    old resourceAssert profile. A false/malformed response retains its poststate. -/
inductive SourceResourceAssert (response : SourceExternalRelation World ExternalFault)
    (key : RuntimeSourceResource) (arguments : List Value) (state : SourceEffectState World) :
    SourceEffectBodyOutcome World ExternalFault → List (SourceEffectEvent World ExternalFault) → Prop
  | stopped (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.stopped stop) after events) :
      SourceResourceAssert response key arguments state
        (.stopped stop {state with shared := after}) events
  | failed (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.value raw) after events) (checked : assertResult raw = some fault) :
      SourceResourceAssert response key arguments state
        (.stopped (.localFault fault) {state with shared := after}) events
  | passed (step : SourceResourceStep response ⟨key,arguments,state.shared⟩
      (.value raw) after events) (checked : assertResult raw = none) :
      SourceResourceAssert response key arguments state
        (.continued {state with shared := after}) events

end Aurora.SourceBinding
