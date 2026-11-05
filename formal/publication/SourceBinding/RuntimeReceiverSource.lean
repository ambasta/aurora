import SourceBinding.RuntimeSourceFunction
import SourceBinding.ScopeProfile
namespace Aurora.SourceBinding

/-- Source identity only: an actual class path, never a fabricated class for a
    free function. Selection and canonical linkage are separate certificates. -/
structure RuntimeReceiverKey where
  module : Name
  path : Name
  deriving BEq, DecidableEq

structure RuntimeReceiverScope where
  key : RuntimeReceiverKey
  members : List Declaration

structure RuntimeReceiverContext where
  scope : RuntimeReceiverScope
  mode : ReceiverMode

/-- The two retained non-consuming source interfaces in this bounded profile.
    These labels are not resource frame, authorization, or success promises. -/
inductive RuntimeResourceMode where
  | readonly
  | mutable
  deriving BEq, DecidableEq

def RuntimeResourceMode.catalogueEffect : RuntimeResourceMode → Int
  | .readonly => 0
  | .mutable => 1

/-- Source-side request identity. No canonical ID, native symbol, outcome,
    physical backing, or resource implementation is hidden in this data. -/
structure RuntimeSourceResource where
  receiver : RuntimeReceiverScope
  field : ByteArray
  sourceType : Name
  method : ByteArray
  parameters : List GuardType
  result : GuardType
  mode : RuntimeResourceMode

/-- The requested source field is the actual declared retained resource field.
    Catalogue method/signature matching remains a separate canonical join. -/
structure RuntimeSourceResourceBinding (resource : RuntimeSourceResource) where
  found : FieldAt resource.receiver.members resource.field
  retainedType : found.field.type = .named resource.sourceType

/-- Namespace data for lexical/import lookup. A checked source context must tie
    these to the same graph's namespace declaration and direct exported import;
    merely populating this record is not import accessibility evidence. -/
structure RuntimeNamespaceScope where
  module : Name
  path : Name
  members : List Declaration

/-- Source lookup context for the single generic effect judgment. The old free
    specialization has receiver=none and empty enclosing/imported inventories.
    Exact graph provenance and shadow-safe resolution are checked separately. -/
structure EffectContext where
  lexical : RuntimeExprContext
  receiver : Option RuntimeReceiverContext
  enclosing : List RuntimeNamespaceScope
  imported : List RuntimeNamespaceScope
  profile : ScopeProfile
  resources : List RuntimeSourceResource

def EffectContext.pure (context : RuntimeExprContext) : EffectContext :=
  ⟨context,none,[],[],.legacy,[]⟩

end Aurora.SourceBinding
