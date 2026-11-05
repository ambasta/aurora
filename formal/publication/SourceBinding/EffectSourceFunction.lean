import SourceBinding.RuntimeReceiverSource
namespace Aurora.SourceBinding

/-- Actual raw source payload for the ONE effect-aware judgment. No result,
    scoping certificate, readiness, rank, or machine execution is a field. -/
structure EffectSourceFunction where
  input : ByteArray
  function : Function
  parsed : ParsedMethod input function
  context : EffectContext
  declared : Declaration.functionDecl function ∈ context.lexical.members
  formals : context.lexical.formals = function.formals
  visible : context.lexical.visible = []
  mode : match context.receiver with
    | none => function.mode = .ordinary
    | some receiver => function.mode = receiver.mode
  parameters : List RuntimeType
  result : RuntimeType
  parameterTypes : RuntimeSourceSignature context.lexical.members context.lexical.module context.lexical.path
    (function.formals.map (·.type)) parameters
  resultType : RuntimeSourceType context.lexical.members context.lexical.module context.lexical.path function.result result

def EffectSourceFunction.key (source : EffectSourceFunction) : RuntimeSourceKey :=
  ⟨source.context.lexical.module,source.context.lexical.path,source.function.name⟩

/-- This embeds every previous source record, including duplicate or malformed
    environments and nested call syntax. No additional validity premise. -/
def RuntimeSourceFunction.toEffect (source : RuntimeSourceFunction) : EffectSourceFunction where
  input := source.input
  function := source.function
  parsed := source.parsed
  context := .pure source.context
  declared := source.declared
  formals := source.formals
  visible := source.visible
  mode := source.ordinary
  parameters := source.parameters
  result := source.result
  parameterTypes := source.parameterTypes
  resultType := source.resultType

/-- Exact old lexical resolution clause. Additional receiver/import clauses
    are separately named source lookup relations, not a global name search. -/
def EffectSourceFunction.LegacyResolves (source : EffectSourceFunction) (caller : EffectContext) (name : Name) : Prop :=
  source.context.profile = .legacy ∧ caller.profile = .legacy ∧
  source.context.receiver = none ∧ caller.receiver = none ∧
  caller.lexical.module = source.context.lexical.module ∧ caller.lexical.path = source.context.lexical.path ∧
  caller.lexical.members = source.context.lexical.members ∧ name = [source.function.name] ∧
  source.function.name ∉ caller.lexical.formals.map (·.name) ∧
  source.function.name ∉ caller.lexical.visible.map (·.name)


def EffectContext.UnshadowedName (context : EffectContext) (name : ByteArray) : Prop :=
  name ∉ context.lexical.formals.map (·.name) ∧
  name ∉ context.lexical.visible.map (·.name)

def EffectSourceFunction.InNamespace (source : EffectSourceFunction) (scope : RuntimeNamespaceScope) : Prop :=
  source.context.receiver = none ∧ source.context.lexical.module = scope.module ∧
  source.context.lexical.path = scope.path ∧ source.context.lexical.members = scope.members

/-- Raw source resolution remains independent of IR and outcomes. Checked
    inventories authenticate every namespace; canonical binding additionally
    checks unambiguous full source keys and signatures. -/
inductive EffectSourceFunction.Resolves (source : EffectSourceFunction) (caller : EffectContext) (name : Name) : Prop
  | legacy : source.LegacyResolves caller name → source.Resolves caller name
  | method : caller.profile = .receiverEffects → source.context.profile = .receiverEffects →
      caller.receiver = some receiver → source.context.receiver = some targetReceiver →
      receiver.scope = targetReceiver.scope →
      (targetReceiver.mode = .readonly ∨ (receiver.mode = .ordinary ∧ targetReceiver.mode = .ordinary)) →
      caller.lexical.module = source.context.lexical.module → caller.lexical.path = source.context.lexical.path →
      caller.lexical.members = source.context.lexical.members → name = [source.function.name] →
      caller.UnshadowedName source.function.name → source.Resolves caller name
  | enclosing : caller.profile = .receiverEffects → scope ∈ caller.enclosing → source.InNamespace scope →
      source.function.name ∉ caller.lexical.members.filterMap declarationName →
      name = [source.function.name] → caller.UnshadowedName source.function.name → source.Resolves caller name
  | imported : caller.profile = .receiverEffects → scope ∈ caller.imported → source.InNamespace scope →
      source.function.name ∉ caller.lexical.members.filterMap declarationName →
      (∀ enclosing ∈ caller.enclosing, source.function.name ∉ enclosing.members.filterMap declarationName) →
      name = [source.function.name] → caller.UnshadowedName source.function.name → source.Resolves caller name

end Aurora.SourceBinding
