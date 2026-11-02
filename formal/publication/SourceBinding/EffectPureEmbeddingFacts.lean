import SourceBinding.EffectPureEmbedding
namespace Aurora.SourceBinding

theorem sourceLift_injective : Function.Injective (sourceLift (World := World) (ExternalFault := ExternalFault)) := by
  intro first second same
  cases first <;> cases second <;> cases same <;> rfl

theorem legacyEffectArguments_injective :
    Function.Injective (legacyEffectArguments (World := World) (ExternalFault := ExternalFault)) := by
  intro first second same
  cases first <;> cases second <;> cases same <;> rfl

theorem legacyEffectBody_injective (shared : SourceShared World) :
    Function.Injective (legacyEffectBody (ExternalFault := ExternalFault) shared) := by
  intro first second same
  cases first <;> cases second <;> cases same <;> rfl

theorem RuntimeSourceEvent.toEffect_injective :
    Function.Injective (RuntimeSourceEvent.toEffect (World := World) (ExternalFault := ExternalFault)) := by
  intro first second same
  cases first <;> cases second <;> cases same <;> rfl

theorem RuntimeSourceEvent.map_toEffect_injective :
    Function.Injective (List.map (RuntimeSourceEvent.toEffect (World := World) (ExternalFault := ExternalFault))) := by
  intro first
  induction first with
  | nil => intro second same; cases second <;> cases same; rfl
  | cons head tail ih =>
    intro second same
    cases second with
    | nil => cases same
    | cons next rest =>
      have parts := List.cons.inj same
      have heads := RuntimeSourceEvent.toEffect_injective parts.1
      have tails := ih parts.2
      cases heads
      cases tails
      rfl

end Aurora.SourceBinding
