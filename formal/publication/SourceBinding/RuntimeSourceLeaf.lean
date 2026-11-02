import SourceBinding.RuntimeExpressions
import SourceBinding.MethodSyntax
import SourceBinding.DeclarationEquality
namespace Aurora.SourceBinding


structure RuntimeSourceKey where
  module : Name
  path : Name
  name : ByteArray
  deriving BEq, DecidableEq

inductive RuntimeSourceSignature (members : List Declaration) (module path : Name) :
    List SourceType → List RuntimeType → Prop
  | nil : RuntimeSourceSignature members module path [] []
  | cons : RuntimeSourceType members module path source kind →
      RuntimeSourceSignature members module path sources kinds →
      RuntimeSourceSignature members module path (source :: sources) (kind :: kinds)

/-- Source-only leaf data. The body is the original parsed raw statement list,
    restricted to one return. No IR table, machine execution or result summary
    occurs in this interface. A selected-graph adapter establishes provenance. -/
structure RuntimeSourceLeaf where
  input : ByteArray
  function : Function
  parsed : ParsedMethod input function
  context : RuntimeExprContext
  raw : SourceExpr
  singleton : parsed.statements = [.returnValue raw]
  declared : Declaration.functionDecl function ∈ context.members
  formals : context.formals = function.formals
  visible : context.visible = []
  ordinary : function.mode = .ordinary
  parameters : List RuntimeType
  result : RuntimeType
  parameterTypes : RuntimeSourceSignature context.members context.module context.path
    (function.formals.map (·.type)) parameters
  resultType : RuntimeSourceType context.members context.module context.path function.result result

def RuntimeSourceLeaf.key (leaf : RuntimeSourceLeaf) : RuntimeSourceKey :=
  ⟨leaf.context.module,leaf.context.path,leaf.function.name⟩

/-- Bare same-namespace lookup only; importing or receiver dispatch is not
    guessed. The caller's formal/local names cannot shadow a callable prefix. -/
def RuntimeSourceLeaf.Resolves (leaf : RuntimeSourceLeaf) (caller : RuntimeExprContext) (name : Name) : Prop :=
  caller.module = leaf.context.module ∧ caller.path = leaf.context.path ∧
  caller.members = leaf.context.members ∧ name = [leaf.function.name] ∧
  leaf.function.name ∉ caller.formals.map (·.name) ∧
  leaf.function.name ∉ caller.visible.map (·.name)
instance (leaf : RuntimeSourceLeaf) (caller : RuntimeExprContext) (name : Name) :
    Decidable (leaf.Resolves caller name) := by unfold RuntimeSourceLeaf.Resolves; infer_instance

end Aurora.SourceBinding
