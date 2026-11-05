import SourceBinding.EffectSourceNames
import SourceBinding.CallCode
import SourceBinding.NominalFreeIdentity
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Same source receiver field and full retained catalogue descriptor. Expected
    effect is the declared source mode, never inferred from a response law. -/
structure CanonicalEffectResource (t : Tables) (caller : Int)
    (receiver : RuntimeReceiverContext) where
  source : RuntimeSourceResource
  target : ResourceDescriptor
  scope : source.receiver = receiver.scope
  declared : RuntimeSourceResourceBinding source
  permitted : ReceiverAllowsResource receiver source.mode
  fieldName : target.fieldName = source.field
  fieldOrdinal : target.fieldOrdinal = declared.found.ordinal
  sourceType : target.sourceType = source.sourceType
  methodName : target.sourceMethod = source.method
  parameters : target.parameters = source.parameters
  result : target.result = source.result
  fields : OrderedFieldsIdentity t caller (fields receiver.scope.members)
  catalogue : ResourceCatalogueMatches t caller source.sourceType target source.mode.catalogueEffect

def CanonicalEffectResource.pair {receiver : RuntimeReceiverContext} (item : CanonicalEffectResource t caller receiver) :
    RuntimeSourceResource × ResourceDescriptor := ⟨item.source,item.target⟩

/-- All duplicates of a field/method pair agree on the complete source and
    machine descriptors; uniqueness is not guessed from an ID or arity. -/
def CanonicalEffectResourcesCompatible {receiver : RuntimeReceiverContext} (items : List (CanonicalEffectResource t caller receiver)) : Prop :=
  ∀ left ∈ items, ∀ right ∈ items,
    left.source.field = right.source.field → left.source.method = right.source.method →
      left.source = right.source ∧ left.target = right.target

/-- Exact receiver header, source mode and visibility; full slots are below.
    Neither a public flag nor a readonly flag is an authority/frame theorem. -/
def EffectReceiverHeader (t : Tables) (id : Int) (module path : Name)
    (function : Function) (visible : Bool) : Prop :=
  let c := atRow t.callables id
  module ≠ [] ∧ path ≠ [] ∧ Index id t.callables.size ∧
  (function.mode = .ordinary ∨ function.mode = .readonly) ∧
  nameBytes t c 1 = methodSymbol module path function.name ∧
  (namedCallables t (methodSymbol module path function.name)).size = 1 ∧
  nameBytes t c 6 = classSymbol module path ∧
  (namedClasses t (classSymbol module path)).size = 1 ∧
  c.integer 8 = (if function.mode = .ordinary then 1 else 0) + (if visible then 4 else 0) ∧
  c.integer 9 = 0 ∧ c.integer 10 = 0 ∧ c.integer 11 = 1 ∧ c.integer 12 = 0 ∧
  c.integer 5 = Int.ofNat (function.formals.length + 1) ∧
  (Aurora.Publication.group t.bodies id).size = 1 ∧
  (atRow (Aurora.Publication.group t.bodies id) 0).integer 2 = 0 ∧
  0 < (functionCode t id).size ∧ (functionCode t id).size ≤ 4096

/-- No separate field/local table: source declaration order exactly covers the
    canonical receiver fields and all actual formal/local frame slots. -/
def EffectReceiverFrame (t : Tables) (id : Int) (members : List Declaration)
    (parameters : List RuntimeType) (locals : List SourceLocal) : Prop :=
  let c := atRow t.callables id
  let kinds := parameters ++ locals.map (·.kind)
  OrderedFieldsIdentity t id (fields members) ∧
  c.integer 15 = Int.ofNat kinds.length ∧
  (∀ entry ∈ kinds.zipIdx, RuntimeFrameSlot t c entry) ∧
  (∀ entry ∈ locals.zipIdx, entry.1.slot = 8 * (parameters.length + entry.2 + 1))

/-- Minimal same-graph method certificate. Resource inventory and scope uses are
    derived fields here, never free public context parameters. Complete resource
    occurrence coverage, imported call resolution and body code remain the next
    checker layer; this record alone asserts no execution correspondence. -/
structure CanonicalEffectMethod (t : Tables) (files : List SourceFile)
    (root module namespacePath : Name) (className member : ByteArray) where
  source : CheckedEffectReceiver files root module namespacePath className member
  id : Int
  visible : Bool
  visibility : VisibilityAt false source.selected.classDecl.members member visible
  header : EffectReceiverHeader t id module (namespacePath ++ [className]) source.selected.method.function visible
  types : CheckedRuntimeSignature t source.selected.classDecl.members module (namespacePath ++ [className])
    ((atRow t.callables id).integer 4)
    (source.selected.method.function.result :: source.selected.method.function.formals.map (·.type))
  resources : List (CanonicalEffectResource t id source.receiver)
  compatible : CanonicalEffectResourcesCompatible resources
  parsed : ParsedMethod source.selected.file.file.bytes source.selected.method.function
  formalNames : FormalNames source.selected.method.function.formals
  typeNames : ∀ formal ∈ source.selected.method.function.formals,
    TypeUnshadowed source.selected.method.function.formals [] formal.type
  lexical : ScopedResultWith .receiverEffects
    (source.context ⟨[],0,1,source.selected.method.function.formals.length⟩ (resources.map (·.source))).uses
    (source.context ⟨[],0,1,source.selected.method.function.formals.length⟩ (resources.map (·.source))).writes
    source.selected.classDecl.members module (namespacePath ++ [className])
    source.selected.method.function.formals ⟨[],0,1,source.selected.method.function.formals.length⟩ parsed.statements
  frame : EffectReceiverFrame t id source.selected.classDecl.members types.kinds.tail lexical.declaredItems

def CanonicalEffectMethod.resourcePairs
    (checked : CanonicalEffectMethod t files root module namespacePath className member) :
    List (RuntimeSourceResource × ResourceDescriptor) := checked.resources.map (·.pair)

/-- The actual raw retained call89 convention. Zero arguments are empty, one is
    accumulator, and multiarguments are the existing reverse stack convention;
    no alternate ABI is introduced by the catalogue effect generalization. -/
def EffectResourceMeaning (t : Tables) (caller : Int) (row : Record)
    (mode : RuntimeResourceMode) (target : ResourceDescriptor) : Prop :=
  InstructionBinding t caller row ∧ CodeEdges t caller row ∧ row.integer 0 = caller ∧ row.integer 6 = 89 ∧
  operandValue t row 1 = Int.ofNat target.fieldOrdinal ∧ operandValue t row 2 = target.method ∧
  operandValue t row 4 = target.resource ∧
  ResourceCatalogueMatches t caller target.sourceType target mode.catalogueEffect ∧
  argumentTypes t row = target.parameters.map some ∧ callResult t row = some target.result

theorem EffectResourceMeaning.mutable_iff :
    EffectResourceMeaning t caller row .mutable target ↔ CallMeaning t caller row (.resource target) := Iff.rfl

end Aurora.SourceBinding
