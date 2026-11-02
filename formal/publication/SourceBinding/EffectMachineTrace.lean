import SourceBinding.EffectMachineBoundary
namespace Aurora.SourceBinding

/-- These finite identities are internal projections of the selected checked
    callable/receiver/catalogue inventory, not user supplied authority claims. -/
abbrev EffectOrdinaryPairs := List (RuntimeSourceKey × OrdinaryDescriptor)
abbrev EffectFieldPairs := List (ByteArray × Nat)

/-- Same ordered effects, with source identities replaced only by paired full
    machine descriptors/field ordinals. Raw values and all shared states survive. -/
inductive EffectMachineEventRelated (ordinary : EffectOrdinaryPairs)
    (resources : EffectResourcePairs) (fields : EffectFieldPairs) :
    SourceEffectEvent World ExternalFault → CallEvent World ExternalFault → Prop
  | invoke : (key,target) ∈ ordinary → EffectMachineEventRelated ordinary resources fields
      (.invoke key values) (.ordinaryInvoke target values)
  | returned : (key,target) ∈ ordinary → EffectMachineEventRelated ordinary resources fields
      (.returned key value) (.ordinaryReturn target value)
  | fieldStore : (name,ordinal) ∈ fields → EffectMachineEventRelated ordinary resources fields
      (.fieldStore name value) (.store ⟨ordinal,value⟩)
  | externalInvoke : (request.key,target) ∈ resources → EffectMachineEventRelated ordinary resources fields
      (.externalInvoke request) (.externalInvoke (request.toCall target))
  | externalReturn : EffectMachineEventRelated ordinary resources fields
      (.externalReturn raw after) (.externalReturn raw after.toCall)
  | externalFault : EffectMachineEventRelated ordinary resources fields
      (.externalFault reason after) (.externalFault reason after.toCall)

inductive EffectMachineTraceRelated (ordinary : EffectOrdinaryPairs)
    (resources : EffectResourcePairs) (fields : EffectFieldPairs) :
    List (SourceEffectEvent World ExternalFault) → List (CallEvent World ExternalFault) → Prop
  | nil : EffectMachineTraceRelated ordinary resources fields [] []
  | cons : EffectMachineEventRelated ordinary resources fields source target →
      EffectMachineTraceRelated ordinary resources fields sources targets →
      EffectMachineTraceRelated ordinary resources fields (source :: sources) (target :: targets)

end Aurora.SourceBinding
