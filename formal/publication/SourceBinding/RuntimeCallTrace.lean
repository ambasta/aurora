import SourceBinding.RuntimeCallIdentity
namespace Aurora.SourceBinding

/-- A source key is related to a machine descriptor only through membership of
    the SAME checked source/IR leaf. Argument and result values are unchanged. -/
inductive RuntimeCallEventRelated (leaves : List (RuntimeCallLeaf t files root module path)) :
    RuntimeSourceEvent → CallEvent World ExternalFault → Prop
  | invoke : leaf ∈ leaves → RuntimeCallEventRelated leaves
      (.invoke leaf.source.key values) (.ordinaryInvoke leaf.target values)
  | returned : leaf ∈ leaves → RuntimeCallEventRelated leaves
      (.returned leaf.source.key value) (.ordinaryReturn leaf.target value)

inductive RuntimeCallTraceRelated (leaves : List (RuntimeCallLeaf t files root module path)) :
    List RuntimeSourceEvent → List (CallEvent World ExternalFault) → Prop
  | nil : RuntimeCallTraceRelated leaves [] []
  | cons : RuntimeCallEventRelated leaves source target → RuntimeCallTraceRelated leaves sources targets →
      RuntimeCallTraceRelated leaves (source :: sources) (target :: targets)

theorem RuntimeCallTraceRelated.append
    (first : RuntimeCallTraceRelated leaves sources targets)
    (second : RuntimeCallTraceRelated leaves moreSources moreTargets) :
    RuntimeCallTraceRelated leaves (sources ++ moreSources) (targets ++ moreTargets) := by
  induction first with
  | nil => exact second
  | cons event _ ih => exact .cons event (ih second)

theorem RuntimeCallTraceRelated.length (related : RuntimeCallTraceRelated leaves sources targets) :
    sources.length = targets.length := by
  induction related with
  | nil => rfl
  | cons _ _ ih => simp only [List.length_cons,ih]

/-- Relative unmatched invocation stacks. A return removes exactly its own
    source key AND full machine descriptor. This is trace algebra, not an
    assumption that a fault unwinds a real saved frame. A machine simulation
    must separately connect these stacks to its actual ActiveCall.saved. -/
inductive RuntimeCallStackTrace (leaves : List (RuntimeCallLeaf t files root module path)) :
    List RuntimeSourceKey → List OrdinaryDescriptor →
    List RuntimeSourceEvent → List (CallEvent World ExternalFault) →
    List RuntimeSourceKey → List OrdinaryDescriptor → Prop
  | nil : RuntimeCallStackTrace leaves sources targets [] [] sources targets
  | invoke : leaf ∈ leaves →
      RuntimeCallStackTrace leaves (leaf.source.key :: sources) (leaf.target :: targets)
        sourceEvents targetEvents finalSources finalTargets →
      RuntimeCallStackTrace leaves sources targets
        (.invoke leaf.source.key values :: sourceEvents) (.ordinaryInvoke leaf.target values :: targetEvents)
        finalSources finalTargets
  | returned : leaf ∈ leaves →
      RuntimeCallStackTrace leaves sources targets sourceEvents targetEvents finalSources finalTargets →
      RuntimeCallStackTrace leaves (leaf.source.key :: sources) (leaf.target :: targets)
        (.returned leaf.source.key value :: sourceEvents) (.ordinaryReturn leaf.target value :: targetEvents)
        finalSources finalTargets

theorem RuntimeCallStackTrace.events
    (stack : RuntimeCallStackTrace leaves initialSources initialTargets sourceEvents targetEvents finalSources finalTargets) :
    RuntimeCallTraceRelated leaves sourceEvents targetEvents := by
  induction stack with
  | nil => exact .nil
  | invoke member _ ih => exact .cons (.invoke member) ih
  | returned member _ ih => exact .cons (.returned member) ih

theorem RuntimeCallStackTrace.append
    (first : RuntimeCallStackTrace leaves initialSources initialTargets sourceEvents targetEvents middleSources middleTargets)
    (second : RuntimeCallStackTrace leaves middleSources middleTargets moreSources moreTargets finalSources finalTargets) :
    RuntimeCallStackTrace leaves initialSources initialTargets
      (sourceEvents ++ moreSources) (targetEvents ++ moreTargets) finalSources finalTargets := by
  induction first with
  | nil => exact second
  | invoke member _ ih => exact .invoke member (ih second)
  | returned member _ ih => exact .returned member (ih second)

/-- A failed call may leave its invoke unmatched. No return or rollback event
    can be manufactured by this relation. -/
theorem runtime_unmatched_invoke {leaf : RuntimeCallLeaf t files root module path}
    (member : leaf ∈ leaves) :
    RuntimeCallStackTrace leaves sourceStack targetStack
      [RuntimeSourceEvent.invoke leaf.source.key values]
      [(CallEvent.ordinaryInvoke leaf.target values : CallEvent World ExternalFault)]
      (leaf.source.key :: sourceStack) (leaf.target :: targetStack) := .invoke member .nil

end Aurora.SourceBinding
