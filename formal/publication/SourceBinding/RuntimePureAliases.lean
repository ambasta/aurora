import SourceBinding.EffectEvaluationTyping
import SourceBinding.EffectLegacyContext
import SourceBinding.PureEffectAlgebra
namespace Aurora.SourceBinding

/-- Uniform pure specialization of the one effectful source judgment. No frozen
    legacy relation is imported; arbitrary shared states and responses are framed. -/
abbrev PureRuntimeEvaluation (functions : List RuntimeSourceFunction)
    (context : RuntimeExprContext) (state : RuntimeLocals) (raw : SourceExpr)
    (kind : RuntimeType) (outcome : Outcome Value) (events : List RuntimeSourceEvent) : Prop :=
  ∀ (World ExternalFault : Type) (response : SourceExternalRelation World ExternalFault)
    (shared : SourceShared World),
    EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
      ⟨state,shared⟩ raw kind (sourceLift outcome) shared (events.map RuntimeSourceEvent.toEffect)
abbrev PureRuntimeArgumentEvaluation (functions : List RuntimeSourceFunction)
    (context : RuntimeExprContext) (state : RuntimeLocals) (raws : List SourceExpr)
    (kinds : List RuntimeType) (outcome : Outcome (List Value)) (events : List RuntimeSourceEvent) : Prop :=
  ∀ (World ExternalFault : Type) (response : SourceExternalRelation World ExternalFault)
    (shared : SourceShared World),
    EffectArguments (functions.map RuntimeSourceFunction.toEffect) response (.pure context)
      ⟨state,shared⟩ raws kinds (legacyEffectArguments outcome) shared (events.map RuntimeSourceEvent.toEffect)
abbrev PureRuntimeStatementEvaluation (functions : List RuntimeSourceFunction)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (state : RuntimeLocals) (raw : SourceStatement) (after : LocalContext)
    (outcome : RuntimeBodyOutcome) (events : List RuntimeSourceEvent) : Prop :=
  ∀ (World ExternalFault : Type) (response : SourceExternalRelation World ExternalFault)
    (shared : SourceShared World) (visible : List SourceLocal),
    EffectStatement (functions.map RuntimeSourceFunction.toEffect) response
      (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raw after
      (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect)
abbrev PureRuntimeStatementsEvaluation (functions : List RuntimeSourceFunction)
    (members : List Declaration) (module path : Name) (formals : List Formal) (result : RuntimeType)
    (before : LocalContext) (state : RuntimeLocals) (raws : List SourceStatement) (after : LocalContext)
    (outcome : RuntimeBodyOutcome) (events : List RuntimeSourceEvent) : Prop :=
  ∀ (World ExternalFault : Type) (response : SourceExternalRelation World ExternalFault)
    (shared : SourceShared World) (visible : List SourceLocal),
    EffectStatements (functions.map RuntimeSourceFunction.toEffect) response
      (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raws after
      (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect)

end Aurora.SourceBinding
