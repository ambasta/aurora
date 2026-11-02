import SourceBinding.EffectSourceOperations
namespace Aurora.SourceBinding

def RuntimeSourceEvent.toEffect (event : RuntimeSourceEvent) : SourceEffectEvent World ExternalFault :=
  match event with
  | .invoke key arguments => .invoke key arguments
  | .returned key value => .returned key value

def legacyEffectArguments (outcome : Outcome (List Value)) : EffectArgumentOutcome World ExternalFault :=
  match outcome with
  | .value values => .values values
  | .trap fault => .stopped (.localFault (.scalar fault))

def legacyEffectBody (shared : SourceShared World) (outcome : RuntimeBodyOutcome) :
    SourceEffectBodyOutcome World ExternalFault :=
  match outcome with
  | .continued locals => .continued ⟨locals,shared⟩
  | .returned value locals => .returned value ⟨locals,shared⟩
  | .trapped fault locals => .stopped (.localFault (.scalar fault)) ⟨locals,shared⟩

@[simp] theorem sourceThen_sourceLift (outcome : Outcome Value) (next : Value → Outcome Value) :
    sourceThen (World := World) (ExternalFault := ExternalFault) (sourceLift outcome) next =
      sourceLift (outcome.then next) := by cases outcome <;> rfl

@[simp] theorem effect_prepend_legacy (outcome : Outcome (List Value)) (value : Value) :
    (legacyEffectArguments (World := World) (ExternalFault := ExternalFault) outcome).prepend value =
      legacyEffectArguments (outcome.then (fun rest => .value (value :: rest))) := by cases outcome <;> rfl


end Aurora.SourceBinding
