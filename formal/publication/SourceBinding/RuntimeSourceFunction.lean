import SourceBinding.RuntimeSourceLeaf
namespace Aurora.SourceBinding

/-- The actual parsed source body, with no machine outcome, rank, or scoping
    certificate hidden in the payload. The selected checker supplies those
    additional provenance/typing obligations separately. This deliberately
    admits every former leaf payload, including arbitrary dead expression arms. -/
structure RuntimeSourceFunction where
  input : ByteArray
  function : Function
  parsed : ParsedMethod input function
  context : RuntimeExprContext
  declared : Declaration.functionDecl function ∈ context.members
  formals : context.formals = function.formals
  visible : context.visible = []
  ordinary : function.mode = .ordinary
  parameters : List RuntimeType
  result : RuntimeType
  parameterTypes : RuntimeSourceSignature context.members context.module context.path
    (function.formals.map (·.type)) parameters
  resultType : RuntimeSourceType context.members context.module context.path function.result result

def RuntimeSourceFunction.key (source : RuntimeSourceFunction) : RuntimeSourceKey :=
  ⟨source.context.module,source.context.path,source.function.name⟩

def RuntimeSourceFunction.Resolves (source : RuntimeSourceFunction) (caller : RuntimeExprContext) (name : Name) : Prop :=
  caller.module = source.context.module ∧ caller.path = source.context.path ∧
  caller.members = source.context.members ∧ name = [source.function.name] ∧
  source.function.name ∉ caller.formals.map (·.name) ∧
  source.function.name ∉ caller.visible.map (·.name)
instance (source : RuntimeSourceFunction) (caller : RuntimeExprContext) (name : Name) :
    Decidable (source.Resolves caller name) := by unfold RuntimeSourceFunction.Resolves; infer_instance

def RuntimeSourceLeaf.toFunction (leaf : RuntimeSourceLeaf) : RuntimeSourceFunction where
  input := leaf.input
  function := leaf.function
  parsed := leaf.parsed
  context := leaf.context
  declared := leaf.declared
  formals := leaf.formals
  visible := leaf.visible
  ordinary := leaf.ordinary
  parameters := leaf.parameters
  result := leaf.result
  parameterTypes := leaf.parameterTypes
  resultType := leaf.resultType

@[simp] theorem RuntimeSourceLeaf.toFunction_key (leaf : RuntimeSourceLeaf) : leaf.toFunction.key = leaf.key := rfl
@[simp] theorem RuntimeSourceLeaf.toFunction_resolves (leaf : RuntimeSourceLeaf) :
    leaf.toFunction.Resolves caller name ↔ leaf.Resolves caller name := Iff.rfl
@[simp] theorem RuntimeSourceLeaf.toFunction_body (leaf : RuntimeSourceLeaf) :
    leaf.toFunction.parsed.statements = [.returnValue leaf.raw] := leaf.singleton

end Aurora.SourceBinding
