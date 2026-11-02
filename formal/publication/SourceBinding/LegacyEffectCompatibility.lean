import SourceBinding.LegacyEffectTyping
import SourceBinding.EffectEvaluationTyping
import SourceBinding.EffectLegacyContext
import SourceBinding.EffectPureEmbedding
namespace Aurora.SourceBinding

/-- Forward preservation includes every old source environment and fault.
    Shared state and response relation are arbitrary and are never consulted. -/
theorem LegacyEffectEvaluation.forward
    (evaluated : LegacyEffectEvaluation functions context state raw kind outcome events)
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) :
    EffectEvaluation (functions.map RuntimeSourceFunction.toEffect) response (.pure context) ⟨state,shared⟩
      raw kind (sourceLift outcome) shared (events.map RuntimeSourceEvent.toEffect) := by
  induction evaluated using LegacyEffectEvaluation.rec
      (motive_2 := fun context state raws kinds outcome events _ =>
        EffectArguments (functions.map RuntimeSourceFunction.toEffect) response (.pure context) ⟨state,shared⟩
          raws kinds (legacyEffectArguments outcome) shared (events.map RuntimeSourceEvent.toEffect))
      (motive_3 := fun members module path formals result before state raw after outcome events _ =>
        ∀ visible, EffectStatement (functions.map RuntimeSourceFunction.toEffect) response
          (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raw after
          (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect))
      (motive_4 := fun members module path formals result before state raws after outcome events _ =>
        ∀ visible, EffectStatements (functions.map RuntimeSourceFunction.toEffect) response
          (.pure ⟨members,module,path,formals,visible⟩) result before ⟨state,shared⟩ raws after
          (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect)) with
  | word => exact .word
  | boolean => exact .boolean
  | readVariable binding => exact .readVariable binding
  | enumValue binding => exact .enumValue (.localValue binding)
  | not _ ih => simpa only [sourceThen_sourceLift] using EffectEvaluation.not ih
  | wordBinaryFault operator _ ih => exact .wordBinaryStop operator ih
  | wordBinary operator _ _ left right =>
      simpa only [sourceThen_sourceLift,List.map_append] using EffectEvaluation.wordBinary operator left right
  | enumCompareFault _ ih => exact .enumCompareStop ih
  | enumCompare _ _ left right =>
      simpa only [sourceThen_sourceLift,List.map_append] using EffectEvaluation.enumCompare left right
  | shiftLeft _ count ih => simpa only [sourceThen_sourceLift] using EffectEvaluation.shiftLeft ih count
  | shiftRight _ count ih => simpa only [sourceThen_sourceLift] using EffectEvaluation.shiftRight ih count
  | andFault _ ih => exact .andStopped ih
  | andStop _ ih => exact .andStop ih
  | andContinue _ _ left right => simpa only [List.map_append] using EffectEvaluation.andContinue left right
  | orFault _ ih => exact .orStopped ih
  | orStop _ ih => exact .orStop ih
  | orContinue _ _ left right => simpa only [List.map_append] using EffectEvaluation.orContinue left right
  | callArgumentsFault member resolves _ ih =>
      exact .callArgumentsStop (List.mem_map.mpr ⟨_,member,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr resolves) ih
  | callValue member resolves arguments body args bodyIH =>
      simpa only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect]
        using EffectEvaluation.callValue (List.mem_map.mpr ⟨_,member,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr resolves)
          args arguments.checked (bodyIH _)
  | callFault member resolves arguments body args bodyIH =>
      simpa only [List.map_append,List.map_cons,List.map_nil,RuntimeSourceEvent.toEffect]
        using EffectEvaluation.callStop (List.mem_map.mpr ⟨_,member,rfl⟩) ((RuntimeSourceFunction.toEffect_resolves _ _ _).mpr resolves)
          args arguments.checked (bodyIH _)
  | nil => exact .nil
  | fault _ ih => exact .stopped ih
  | cons _ _ first rest => simpa only [effect_prepend_legacy,List.map_append] using EffectArguments.cons first rest
  | declarationFault scope _ ih => rename_i visible; exact .declarationStop scope ih
  | declarationValue scope expression installed ih =>
      rename_i visible; exact .declarationValue scope ih expression.outcome_typed installed
  | assignmentFault member named mutable _ ih => rename_i visible; exact .assignmentStop member named mutable ih
  | assignmentValue member named mutable expression assigned ih =>
      rename_i visible; exact .assignmentValue member named mutable ih expression.outcome_typed assigned
  | returnFault _ ih => rename_i visible; exact .returnStop ih
  | returnValue _ ih => rename_i visible; exact .returnValue ih
  | branchFault scope _ ih => rename_i visible; exact .branchStop scope ih
  | branchFalse scope _ reserved ih => rename_i visible; exact .branchFalse scope ih reserved
  | branchTrueContinue scope _ entered _ reserved test body =>
      rename_i visible
      simpa only [List.map_append] using EffectStatement.branchTrueContinue scope test entered (body visible) reserved
  | branchTrueReturn scope _ entered _ test body =>
      rename_i visible
      simpa only [List.map_append] using EffectStatement.branchTrueReturn scope test entered (body visible)
  | branchTrueFault scope _ entered _ test body =>
      rename_i visible
      simpa only [List.map_append] using EffectStatement.branchTrueStop scope test entered (body visible)
  | next _ _ first rest => rename_i visible; simpa only [List.map_append] using EffectStatements.next (first visible) (rest visible)
  | returned _ scope ih => rename_i visible; exact .returned (ih visible) scope
  | trapped _ scope ih => rename_i visible; exact .stopped (ih visible) scope
  | _ => intros; exact .nil

theorem LegacyEffectArgumentEvaluation.forward
    (evaluated : LegacyEffectArgumentEvaluation functions context state raws kinds outcome events)
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) :
    EffectArguments (functions.map RuntimeSourceFunction.toEffect) response (.pure context) ⟨state,shared⟩
      raws kinds (legacyEffectArguments outcome) shared (events.map RuntimeSourceEvent.toEffect) := by
  induction evaluated using LegacyEffectArgumentEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True)
      (motive_4 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | fault first _ => exact .stopped (first.forward shared response)
  | cons first rest _ ih =>
      simpa only [effect_prepend_legacy,List.map_append] using EffectArguments.cons (first.forward shared response) ih
  | _ => intros; first | exact True.intro | exact EffectArguments.nil

theorem LegacyEffectStatementEvaluation.forward
    (evaluated : LegacyEffectStatementEvaluation functions members module path formals result before state raw after outcome events)
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) (visible : List SourceLocal) :
    EffectStatement (functions.map RuntimeSourceFunction.toEffect) response (.pure ⟨members,module,path,formals,visible⟩)
      result before ⟨state,shared⟩ raw after (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect) := by
  induction evaluated using LegacyEffectStatementEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_2 := fun _ _ _ _ _ _ _ => True)
      (motive_4 := fun members module path formals result before state raws after outcome events _ =>
        EffectStatements (functions.map RuntimeSourceFunction.toEffect) response (.pure ⟨members,module,path,formals,visible⟩)
          result before ⟨state,shared⟩ raws after (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect)) with
  | declarationFault scope expression _ => exact .declarationStop scope (expression.forward shared response)
  | declarationValue scope expression installed _ =>
      exact .declarationValue scope (expression.forward shared response) expression.outcome_typed installed
  | assignmentFault member named mutable expression _ => exact .assignmentStop member named mutable (expression.forward shared response)
  | assignmentValue member named mutable expression assigned _ =>
      exact .assignmentValue member named mutable (expression.forward shared response) expression.outcome_typed assigned
  | returnFault expression _ => exact .returnStop (expression.forward shared response)
  | returnValue expression _ => exact .returnValue (expression.forward shared response)
  | branchFault scope expression _ => exact .branchStop scope (expression.forward shared response)
  | branchFalse scope expression reserved _ => exact .branchFalse scope (expression.forward shared response) reserved
  | branchTrueContinue scope expression entered _ reserved _ body =>
      simpa only [List.map_append] using EffectStatement.branchTrueContinue scope (expression.forward shared response) entered body reserved
  | branchTrueReturn scope expression entered _ _ body =>
      simpa only [List.map_append] using EffectStatement.branchTrueReturn scope (expression.forward shared response) entered body
  | branchTrueFault scope expression entered _ _ body =>
      simpa only [List.map_append] using EffectStatement.branchTrueStop scope (expression.forward shared response) entered body
  | next _ _ first rest => simpa only [List.map_append] using EffectStatements.next first rest
  | returned _ scope ih => exact .returned ih scope
  | trapped _ scope ih => exact .stopped ih scope
  | _ => intros; first | exact True.intro | exact EffectStatements.nil

theorem LegacyEffectStatementsEvaluation.forward
    (evaluated : LegacyEffectStatementsEvaluation functions members module path formals result before state raws after outcome events)
    (shared : SourceShared World) (response : SourceExternalRelation World ExternalFault) (visible : List SourceLocal) :
    EffectStatements (functions.map RuntimeSourceFunction.toEffect) response (.pure ⟨members,module,path,formals,visible⟩)
      result before ⟨state,shared⟩ raws after (legacyEffectBody shared outcome) (events.map RuntimeSourceEvent.toEffect) := by
  induction evaluated using LegacyEffectStatementsEvaluation.rec
      (motive_1 := fun _ _ _ _ _ _ _ => True)
      (motive_2 := fun _ _ _ _ _ _ _ => True)
      (motive_3 := fun _ _ _ _ _ _ _ _ _ _ _ _ => True) with
  | next first rest _ ih => simpa only [List.map_append] using EffectStatements.next (first.forward shared response visible) ih
  | returned first scope _ => exact .returned (first.forward shared response visible) scope
  | trapped first scope _ => exact .stopped (first.forward shared response visible) scope
  | _ => intros; first | exact True.intro | exact EffectStatements.nil

end Aurora.SourceBinding
