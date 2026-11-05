import SourceBinding.EffectEvaluation
namespace Aurora.SourceBinding

/-- Exact old resolution, including arbitrary old source records and contexts. -/
theorem RuntimeSourceFunction.toEffect_resolves
    (source : RuntimeSourceFunction) (context : RuntimeExprContext) (name : Name) :
    source.toEffect.Resolves (.pure context) name ↔ source.Resolves context name := by
  constructor
  · intro resolved
    cases resolved with
    | legacy old =>
      exact old.2.2.2.2
    | method enabled => cases enabled
    | enclosing enabled => cases enabled
    | imported enabled => cases enabled
  · intro old
    exact .legacy ⟨rfl,rfl,rfl,rfl,old⟩

@[simp] theorem RuntimeSourceFunction.toEffect_key (source : RuntimeSourceFunction) :
    source.toEffect.key = source.key := rfl

@[simp] theorem EffectContext.pure_atCursor (context : RuntimeExprContext) (cursor : LocalContext) :
    (EffectContext.pure context).atCursor cursor =
      .pure {context with visible := cursor.visible} := rfl

@[simp] theorem EffectContext.pure_uses (context : RuntimeExprContext)
    (cursor : LocalContext) (raw : SourceExpr) :
    (EffectContext.pure context).uses cursor raw ↔
      ExpressionNames context.members context.path context.formals cursor.visible raw := Iff.rfl

@[simp] theorem EffectContext.pure_writes (context : RuntimeExprContext)
    (cursor : LocalContext) (name : ByteArray) :
    ¬ (EffectContext.pure context).writes cursor name := fun impossible => impossible

/-- Dead arms and suffixes keep the original legacy scope admission exactly. -/
theorem EffectScopedStatement.pure_iff (context : RuntimeExprContext) :
    EffectScopedStatement (.pure context) before raw after items ↔
      ScopedStatement context.members context.module context.path context.formals
        before raw after items := Iff.rfl

theorem EffectScopedStatements.pure_iff (context : RuntimeExprContext) :
    EffectScopedStatements (.pure context) before raw after items ↔
      ScopedStatements context.members context.module context.path context.formals
        before raw after items := Iff.rfl

/-- Pure contexts cannot gain enclosing/imported enum resolutions. -/
theorem EffectEnumValue.pure_iff (context : RuntimeExprContext) :
    EffectEnumValue (.pure context) name identity ordinal ↔
      RuntimeEnumValue context name identity ordinal := by
  constructor
  · intro resolved
    cases resolved with
    | localValue old => exact old
    | enclosing enabled => cases enabled
    | imported enabled => cases enabled
  · intro binding
    exact .localValue binding

/-- No resource interface or receiver permission is invented by embedding. -/
theorem EffectResourceResolved.pure_impossible (context : RuntimeExprContext)
    (resolved : EffectResourceResolved (.pure context) resource) : False := by
  exact List.not_mem_nil resolved.member

end Aurora.SourceBinding
