import SourceBinding.EffectSourceFunction
import SourceBinding.EffectSourceBinding
namespace Aurora.SourceBinding

/-- Updating the lexical cursor never changes source receiver/import interfaces. -/
def EffectContext.atCursor (context : EffectContext) (cursor : LocalContext) : EffectContext :=
  { context with lexical := { context.lexical with visible := cursor.visible } }

structure EffectField where
  name : ByteArray
  kind : GuardType
  ordinal : Nat

structure EffectFieldResolved (context : EffectContext) (name : ByteArray) (field : EffectField) where
  enabled : context.profile = .receiverEffects
  receiver : RuntimeReceiverContext
  current : context.receiver = some receiver
  members : context.lexical.members = receiver.scope.members
  declared : FieldAt receiver.scope.members name
  named : field.name = name
  ordinal : field.ordinal = declared.ordinal
  scalar : declared.field.type = guardSourceType field.kind
  clear : context.UnshadowedName name

structure EffectFieldWritable (context : EffectContext) (name : ByteArray) (field : EffectField)
    extends EffectFieldResolved context name field where
  mutableReceiver : receiver.mode = .ordinary

/-- Declaration lookup only; imports are authenticated by the checked context.
    No global same-spelling lookup or implicit namespace concatenation. -/
inductive EffectEnumValue (context : EffectContext) : Name → NominalIdentity → Nat → Prop
  | localValue : RuntimeEnumValue context.lexical name identity ordinal →
      EffectEnumValue context name identity ordinal
  | enclosing : context.profile = .receiverEffects → scope ∈ context.enclosing →
      RuntimeEnumValue ⟨scope.members,scope.module,scope.path,context.lexical.formals,context.lexical.visible⟩
        name identity ordinal →
      (∀ first ∈ name.head?.toList, first ∉ context.lexical.members.filterMap declarationName) →
      EffectEnumValue context name identity ordinal
  | imported : context.profile = .receiverEffects → scope ∈ context.imported →
      RuntimeEnumValue ⟨scope.members,scope.module,scope.path,context.lexical.formals,context.lexical.visible⟩
        name identity ordinal →
      (∀ first ∈ name.head?.toList, first ∉ context.lexical.members.filterMap declarationName) →
      (∀ enclosing ∈ context.enclosing, ∀ first ∈ name.head?.toList,
        first ∉ enclosing.members.filterMap declarationName) →
      EffectEnumValue context name identity ordinal

/-- Source name admission is weaker than typed code correspondence. In
    particular this does not establish a call result or callee body summary. -/
inductive EffectNamedCall (context : EffectContext) : Name → Prop
  | localCall : name ∈ localCallNames context.lexical.members context.lexical.path →
      Unshadowed context.lexical.formals context.lexical.visible name → EffectNamedCall context name
  | enclosing : scope ∈ context.enclosing → Declaration.functionDecl function ∈ scope.members →
      function.mode = .ordinary → name = [function.name] → context.UnshadowedName function.name →
      function.name ∉ context.lexical.members.filterMap declarationName → EffectNamedCall context name
  | imported : scope ∈ context.imported → Declaration.functionDecl function ∈ scope.members →
      function.mode = .ordinary → name = [function.name] → context.UnshadowedName function.name →
      function.name ∉ context.lexical.members.filterMap declarationName →
      (∀ enclosing ∈ context.enclosing, function.name ∉ enclosing.members.filterMap declarationName) →
      EffectNamedCall context name

/-- Recursive pure-expression name admission; retained resource operations
    deliberately have no constructor here. -/
inductive EffectPureNames (context : EffectContext) : SourceExpr → Prop
  | word : EffectPureNames context (.word value)
  | boolean : EffectPureNames context (.boolean value)
  | count12 : EffectPureNames context .signed12
  | count : (value = 4 ∨ value = 32) → EffectPureNames context (.signedCount value)
  | variable : name ∈ visibleNames context.lexical.formals context.lexical.visible →
      EffectPureNames context (.name [name])
  | field : EffectFieldResolved context name field → EffectPureNames context (.name [name])
  | nominal : EffectEnumValue context name identity ordinal → EffectPureNames context (.name name)
  | not : EffectPureNames context inner → EffectPureNames context (.not inner)
  | binary : EffectPureNames context left → EffectPureNames context right →
      EffectPureNames context (.binary operator left right)
  | call : EffectNamedCall context name → (∀ argument ∈ arguments, EffectPureNames context argument) →
      EffectPureNames context (.call (.named name) arguments)

/-- Only the statement boundary admits a direct resource call or require of a
    direct resource call; its arguments retain pure expression syntax. -/
inductive EffectStatementNames (context : EffectContext) : SourceExpr → Prop
  | pure : EffectPureNames context raw → EffectStatementNames context raw
  | resource : EffectResourceResolved context resource →
      (∀ argument ∈ arguments, EffectPureNames context argument) →
      EffectStatementNames context (.call (.receiver resource.field resource.method) arguments)
  | requireResource : EffectResourceResolved context resource →
      (∀ argument ∈ arguments, EffectPureNames context argument) →
      EffectStatementNames context (.call (.named ["builtin".toUTF8,"require".toUTF8])
        [.call (.receiver resource.field resource.method) arguments])

def EffectContext.uses (context : EffectContext) (cursor : LocalContext) (raw : SourceExpr) : Prop :=
  match context.profile with
  | .legacy => ExpressionNames context.lexical.members context.lexical.path context.lexical.formals cursor.visible raw
  | .receiverEffects => EffectStatementNames (context.atCursor cursor) raw

def EffectContext.writes (context : EffectContext) (cursor : LocalContext) (name : ByteArray) : Prop :=
  match context.profile with
  | .legacy => False
  | .receiverEffects => ∃ field, Nonempty (EffectFieldWritable (context.atCursor cursor) name field)

end Aurora.SourceBinding
