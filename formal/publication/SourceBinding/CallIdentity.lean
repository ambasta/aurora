import SourceBinding.BodySyntax
import SourceBinding.IRIdentity
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Interface data, not a native implementation or ownership guarantee. -/
structure OrdinaryDescriptor where
  member : ByteArray
  id : Int
  parameters : List GuardType
  result : GuardType
  deriving BEq, DecidableEq
structure ResourceDescriptor where
  fieldName : ByteArray
  fieldOrdinal : Nat
  resource : Int
  sourceType : Name
  resourceCatalog : Int
  method : Int
  sourceMethod : ByteArray
  parameters : List GuardType
  result : GuardType
  resultCatalog : Int
  parameterCatalog : Int
  effect : Int
  native : ByteArray
  deriving BEq, DecidableEq

/-- Unqualified self calls resolve in the SAME full source class. -/
structure OrdinaryCallIdentity (t : Tables) (module path : Name) (members : List Declaration)
    (target : OrdinaryDescriptor) where
  found : FoundFunction members target.member
  visible : Bool
  visibility : VisibilityAt false members target.member visible
  identity : SourceIRIdentity t target.id module path target.member members found.function visible
  parameters : found.function.formals.map (·.type) = target.parameters.map guardSourceType
  result : found.function.result = guardSourceType target.result

def sourceScalarKind (type : SourceType) : Option GuardType :=
  if type == guardSourceType .word then some .word
  else if type == guardSourceType .boolean then some .boolean else none
structure BoundOrdinaryCall (t : Tables) (module path : Name) (members : List Declaration) (name : ByteArray) where
  target : OrdinaryDescriptor
  named : target.member = name
  identity : OrdinaryCallIdentity t module path members target

def bindOrdinaryCall (t : Tables) (module path : Name) (members : List Declaration) (name : ByteArray) :
    Option (BoundOrdinaryCall t module path members name) := do
  let found ← findFunction members name
  let visibility ← visibilityAt name false members
  let parameters ← found.function.formals.mapM (fun formal => sourceScalarKind formal.type)
  let result ← sourceScalarKind found.function.result
  let row ← (namedCallables t (methodSymbol module path name))[0]?
  let id := row.integer 0
  if identity : SourceIRIdentity t id module path name members found.function visibility.val then
    if params : found.function.formals.map (·.type) = parameters.map guardSourceType then
      if resultType : found.function.result = guardSourceType result then
        return ⟨⟨name,id,parameters,result⟩,rfl,⟨found,visibility.val,visibility.property,identity,params,resultType⟩⟩
      else none
    else none
  else none

/-- Exact catalogue join. Effect 1 is only a profile restriction, not a frame or
    liveness fact. Changed native bytes may denote a different valid interface. -/
def ResourceDescriptorMatches (t : Tables) (caller : Int) (sourceType : Name)
    (target : ResourceDescriptor) : Prop :=
  Index (Int.ofNat target.fieldOrdinal) (functionFields t caller).size ∧
  ResourceTypeIdentity t sourceType ((fieldOf t caller (Int.ofNat target.fieldOrdinal)).integer 2) ∧
  Index target.resource t.resources.size ∧ target.sourceType = sourceType ∧
  (atRow t.resources target.resource).integer 1 = target.resourceCatalog ∧
  (atRow t.resources target.resource).blob 3 = sourceName sourceType ∧
  Index target.method (Aurora.Publication.group t.methods target.resource).size ∧
  let method := atRow (Aurora.Publication.group t.methods target.resource) target.method
  method.integer 0 = target.resource ∧ method.integer 1 = target.method ∧
  method.blob 9 = target.sourceMethod ∧
  ((Aurora.Publication.group t.methods target.resource).filter (fun row => row.blob 9 == target.sourceMethod)).size = 1 ∧
  method.integer 2 = target.resultCatalog ∧ method.integer 5 = target.parameterCatalog ∧
  method.integer 7 = target.effect ∧ target.effect = 1 ∧
  method.blob 8 = target.native ∧ 0 < target.native.size ∧
  catalogueScalar (method.integer 3) = some target.result ∧
  0 ≤ method.integer 4 ∧ method.integer 4 ≤ 64 ∧
  target.parameters.length = (method.integer 4).toNat ∧
  target.parameters.map some = List.replicate (method.integer 4).toNat (catalogueScalar (method.integer 6))
instance (t : Tables) (caller : Int) (sourceType : Name) (target : ResourceDescriptor) :
    Decidable (ResourceDescriptorMatches t caller sourceType target) := by
  unfold ResourceDescriptorMatches; infer_instance
structure ResourceCallIdentity (t : Tables) (caller : Int) (members : List Declaration)
    (target : ResourceDescriptor) where
  field : FieldAt members target.fieldName
  ordinal : field.ordinal = target.fieldOrdinal
  sourceType : Name
  fieldType : field.field.type = .named sourceType
  ordered : OrderedFieldsIdentity t caller (fields members)
  descriptor : ResourceDescriptorMatches t caller sourceType target
structure BoundResourceCall (t : Tables) (caller : Int) (members : List Declaration)
    (field method : ByteArray) where
  target : ResourceDescriptor
  fieldNamed : target.fieldName = field
  methodNamed : target.sourceMethod = method
  identity : ResourceCallIdentity t caller members target

def bindResourceCall (t : Tables) (caller : Int) (members : List Declaration) (field method : ByteArray) :
    Option (BoundResourceCall t caller members field method) := do
  let found ← fieldAt members field
  match typeEq : found.field.type with
  | .named sourceType =>
    let resource ← (t.resources.filter (fun row => row.blob 3 == sourceName sourceType))[0]?
    let row ← ((Aurora.Publication.group t.methods (resource.integer 0)).filter (fun row => row.blob 9 == method))[0]?
    if row.integer 4 < 0 || row.integer 4 > 64 then none else do
      let result ← catalogueScalar (row.integer 3)
      let parameters ← (List.replicate (row.integer 4).toNat (catalogueScalar (row.integer 6))).mapM id
      let target : ResourceDescriptor := ⟨field,found.ordinal,resource.integer 0,sourceType,resource.integer 1,row.integer 1,method,
        parameters,result,row.integer 2,row.integer 5,row.integer 7,row.blob 8⟩
      if ordered : OrderedFieldsIdentity t caller (fields members) then
        if descriptor : ResourceDescriptorMatches t caller sourceType target then
          return ⟨target,rfl,rfl,⟨found,rfl,sourceType,typeEq,ordered,descriptor⟩⟩
        else none
      else none
  | _ => none

theorem bound_ordinary_call_sound (checked : BoundOrdinaryCall t module path members name) :
    SourceIRIdentity t checked.target.id module path checked.target.member members
      checked.identity.found.function checked.identity.visible := checked.identity.identity

theorem bound_resource_call_sound (checked : BoundResourceCall t caller members field method) :
    ResourceDescriptorMatches t caller checked.identity.sourceType checked.target := checked.identity.descriptor
end Aurora.SourceBinding
