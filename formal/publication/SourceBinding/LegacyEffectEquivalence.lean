import SourceBinding.LegacyEffectCompatibility
import SourceBinding.LegacyEffectBackward
import SourceBinding.EffectPureEmbeddingFacts
import SourceBinding.RuntimePureAliases
namespace Aurora.SourceBinding

/-- Literal predecessor equivalence, for arbitrary source environments, locals,
    shared state and response relations. No readiness or uniqueness premise. -/
theorem LegacyEffectEvaluation.effect_iff
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) :
    LegacyEffectEvaluation functions context state raw kind outcome events ↔
      EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
        ⟨state,shared⟩ raw kind (sourceLift outcome) shared
        (events.map RuntimeSourceEvent.toEffect) := by
  constructor
  · intro evaluated; exact evaluated.forward shared response
  · intro evaluated
    rcases evaluated.legacy_backward rfl with ⟨oldOutcome,oldEvents,old,sameOutcome,_,sameEvents⟩
    have outcomeEq := sourceLift_injective sameOutcome
    have eventsEq := RuntimeSourceEvent.map_toEffect_injective sameEvents
    cases outcomeEq
    cases eventsEq
    exact old

theorem LegacyEffectArgumentEvaluation.effect_iff
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) :
    LegacyEffectArgumentEvaluation functions context state raws kinds outcome events ↔
      EffectArguments (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
        ⟨state,shared⟩ raws kinds (legacyEffectArguments outcome) shared
        (events.map RuntimeSourceEvent.toEffect) := by
  constructor
  · intro evaluated; exact evaluated.forward shared response
  · intro evaluated
    rcases evaluated.legacy_backward rfl with ⟨oldOutcome,oldEvents,old,sameOutcome,_,sameEvents⟩
    have outcomeEq := legacyEffectArguments_injective sameOutcome
    have eventsEq := RuntimeSourceEvent.map_toEffect_injective sameEvents
    cases outcomeEq
    cases eventsEq
    exact old

/-- Dead suffixes and unexecuted arms use the original fixed legacy scope
    predicates on both sides; visible is not a well-formedness assumption. -/
theorem LegacyEffectStatementEvaluation.effect_iff
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault)
    (visible : List SourceLocal) :
    LegacyEffectStatementEvaluation functions members module path formals result before state raw after outcome events ↔
      EffectStatement (functions.map RuntimeSourceFunction.toEffect) response
        (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raw after
        (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect) := by
  constructor
  · intro evaluated; exact evaluated.forward shared response visible
  · intro evaluated
    rcases evaluated.legacy_backward rfl with ⟨oldOutcome,oldEvents,old,sameOutcome,sameEvents⟩
    have outcomeEq := legacyEffectBody_injective shared sameOutcome
    have eventsEq := RuntimeSourceEvent.map_toEffect_injective sameEvents
    cases outcomeEq
    cases eventsEq
    exact old

theorem LegacyEffectStatementsEvaluation.effect_iff
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault)
    (visible : List SourceLocal) :
    LegacyEffectStatementsEvaluation functions members module path formals result before state raws after outcome events ↔
      EffectStatements (functions.map RuntimeSourceFunction.toEffect) response
        (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raws after
        (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect) := by
  constructor
  · intro evaluated; exact evaluated.forward shared response visible
  · intro evaluated
    rcases evaluated.legacy_backward rfl with ⟨oldOutcome,oldEvents,old,sameOutcome,sameEvents⟩
    have outcomeEq := legacyEffectBody_injective shared sameOutcome
    have eventsEq := RuntimeSourceEvent.map_toEffect_injective sameEvents
    cases outcomeEq
    cases eventsEq
    exact old

/-- The universal production alias is exactly the predecessor, not a stronger
    input-validity or environment assumption. -/
theorem LegacyEffectEvaluation.uniform_iff :
    LegacyEffectEvaluation functions context state raw kind outcome events ↔
      PureRuntimeEvaluation functions context state raw kind outcome events := by
  constructor
  · intro evaluated World ExternalFault response shared
    exact evaluated.forward shared response
  · intro evaluated
    exact (LegacyEffectEvaluation.effect_iff
      (⟨fun _ => none,PUnit.unit⟩ : SourceShared PUnit)
      (fun _ _ _ => False : SourceExternalRelation PUnit PUnit)).mpr
        (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩)

theorem LegacyEffectArgumentEvaluation.uniform_iff :
    LegacyEffectArgumentEvaluation functions context state raws kinds outcome events ↔
      PureRuntimeArgumentEvaluation functions context state raws kinds outcome events := by
  constructor
  · intro evaluated World ExternalFault response shared
    exact evaluated.forward shared response
  · intro evaluated
    exact (LegacyEffectArgumentEvaluation.effect_iff
      (⟨fun _ => none,PUnit.unit⟩ : SourceShared PUnit)
      (fun _ _ _ => False : SourceExternalRelation PUnit PUnit)).mpr
        (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩)

theorem LegacyEffectStatementEvaluation.uniform_iff :
    LegacyEffectStatementEvaluation functions members module path formals result before state raw after outcome events ↔
      PureRuntimeStatementEvaluation functions members module path formals result before state raw after outcome events := by
  constructor
  · intro evaluated World ExternalFault response shared visible
    exact evaluated.forward shared response visible
  · intro evaluated
    exact (LegacyEffectStatementEvaluation.effect_iff
      (⟨fun _ => none,PUnit.unit⟩ : SourceShared PUnit)
      (fun _ _ _ => False : SourceExternalRelation PUnit PUnit) []).mpr
        (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])

theorem LegacyEffectStatementsEvaluation.uniform_iff :
    LegacyEffectStatementsEvaluation functions members module path formals result before state raws after outcome events ↔
      PureRuntimeStatementsEvaluation functions members module path formals result before state raws after outcome events := by
  constructor
  · intro evaluated World ExternalFault response shared visible
    exact evaluated.forward shared response visible
  · intro evaluated
    exact (LegacyEffectStatementsEvaluation.effect_iff
      (⟨fun _ => none,PUnit.unit⟩ : SourceShared PUnit)
      (fun _ _ _ => False : SourceExternalRelation PUnit PUnit) []).mpr
        (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩ [])

end Aurora.SourceBinding
