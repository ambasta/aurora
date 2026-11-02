import SourceBinding.EffectSourceChecks
namespace Aurora.SourceBinding
open Aurora.Publication

private def declarationMember (item : Declaration) : (members : List Declaration) → Decidable (item ∈ members)
  | [] => .isFalse (by intro member; cases member)
  | head :: tail =>
    if same : item = head then .isTrue (List.mem_cons.mpr (.inl same))
    else match declarationMember item tail with
      | .isTrue member => .isTrue (List.mem_cons.mpr (.inr member))
      | .isFalse absent => .isFalse (by
          intro member
          rcases List.mem_cons.mp member with equal | member
          · exact same equal
          · exact absent member)

def checkEffectReceiver (files : List SourceFile) (root module namespacePath : Name)
    (className member : ByteArray) :
    Option (CheckedEffectReceiver files root module namespacePath className member) := do
  let graph ← checkGraph files root
  let selected ← selectMember files module (namespacePath ++ [className]) member
  let enclosing ← findNamespace 4096 selected.file.file.checked.source.shell.declarations namespacePath
  let _ := declarationMember (Declaration.classDecl className selected.classDecl.members) enclosing.members
  if nested : Declaration.classDecl className selected.classDecl.members ∈ enclosing.members then
    if mode : selected.method.function.mode = .ordinary ∨ selected.method.function.mode = .readonly then
      let imports ← (importedNames selected.file.file).attach.mapM fun imported => do
        let file ← findFile files imported.val
        let scope ← findNamespace 4096 file.file.checked.source.shell.declarations namespacePath
        if exportedModule : file.file.checked.source.header.declarations.module.exported = true then
          if exportedNamespace : scope.exported = true then
            return (⟨imported.val,namespacePath,file,scope,imported.property,exportedModule,exportedNamespace⟩ :
              EffectImportedScope files selected.file.file)
          else none
        else none
      if order : imports.map (·.module) = importedNames selected.file.file then
        if paths : ∀ item ∈ imports, item.path = namespacePath then
          return ⟨graph.property,selected,enclosing,nested,mode,imports,order,paths⟩
        else none
      else none
    else none
  else none

def checkCanonicalEffectResource (t : Tables) (caller : Int) (receiver : RuntimeReceiverContext)
    (field method : ByteArray) : Option (CanonicalEffectResource t caller receiver) := do
  let found ← fieldAt receiver.scope.members field
  match typeEq : found.field.type with
  | .named sourceType =>
    let resource ← (t.resources.filter (fun row => row.blob 3 == sourceName sourceType))[0]?
    let row ← ((Aurora.Publication.group t.methods (resource.integer 0)).filter (fun row => row.blob 9 == method))[0]?
    let mode ← if row.integer 7 == 0 then some RuntimeResourceMode.readonly
      else if row.integer 7 == 1 then some RuntimeResourceMode.mutable else none
    if permitted : ReceiverAllowsResource receiver mode then
      if row.integer 4 < 0 || row.integer 4 > 64 then none else do
        let result ← catalogueScalar (row.integer 3)
        let parameters ← (List.replicate (row.integer 4).toNat (catalogueScalar (row.integer 6))).mapM id
        let source : RuntimeSourceResource := ⟨receiver.scope,field,sourceType,method,parameters,result,mode⟩
        let target : ResourceDescriptor := ⟨field,found.ordinal,resource.integer 0,sourceType,resource.integer 1,
          row.integer 1,method,parameters,result,row.integer 2,row.integer 5,row.integer 7,row.blob 8⟩
        if ordered : OrderedFieldsIdentity t caller (fields receiver.scope.members) then
          if catalogue : ResourceCatalogueMatches t caller sourceType target mode.catalogueEffect then
            return ⟨source,target,rfl,⟨found,typeEq⟩,permitted,rfl,rfl,rfl,rfl,rfl,rfl,ordered,catalogue⟩
          else none
        else none
    else none
  | _ => none

/-- Candidate enumeration is not admission: every returned item carries the
    full source/catalogue proof. Unsupported unused interfaces need not enter
    this bounded profile; every actual use is checked against the inventory. -/
def effectResourceInventory (t : Tables) (caller : Int) (receiver : RuntimeReceiverContext) :
    List (CanonicalEffectResource t caller receiver) :=
  let methodNames := (t.methods.toList.map (·.blob 9)).eraseDups
  (fields receiver.scope.members).flatMap fun field =>
    methodNames.filterMap fun method => checkCanonicalEffectResource t caller receiver field.name method

instance (t : Tables) (id : Int) (module path : Name) (function : Function) (visible : Bool) :
    Decidable (EffectReceiverHeader t id module path function visible) := by
  unfold EffectReceiverHeader; infer_instance
instance (t : Tables) (id : Int) (members : List Declaration) (parameters : List RuntimeType)
    (locals : List SourceLocal) : Decidable (EffectReceiverFrame t id members parameters locals) := by
  unfold EffectReceiverFrame; infer_instance
instance {receiver : RuntimeReceiverContext} (items : List (CanonicalEffectResource t caller receiver)) :
    Decidable (CanonicalEffectResourcesCompatible items) := by
  unfold CanonicalEffectResourcesCompatible; infer_instance

def checkCanonicalEffectMethod (t : Tables) (files : List SourceFile)
    (root module namespacePath : Name) (className member : ByteArray) :
    Option (CanonicalEffectMethod t files root module namespacePath className member) := do
  let source ← checkEffectReceiver files root module namespacePath className member
  let row ← (namedCallables t (methodSymbol module (namespacePath ++ [className]) member))[0]?
  let id := row.integer 0
  let visible ← visibilityAt member false source.selected.classDecl.members
  if header : EffectReceiverHeader t id module (namespacePath ++ [className]) source.selected.method.function visible.val then
    let types ← checkRuntimeSignature t source.selected.classDecl.members module (namespacePath ++ [className])
      ((atRow t.callables id).integer 4)
      (source.selected.method.function.result :: source.selected.method.function.formals.map (·.type))
    let resources := effectResourceInventory t id source.receiver
    if compatible : CanonicalEffectResourcesCompatible resources then
      let parsed ← methodSyntax source.selected.file.file.bytes source.selected.method.function
      if formals : FormalNames source.selected.method.function.formals then
        if typeNames : ∀ formal ∈ source.selected.method.function.formals,
            TypeUnshadowed source.selected.method.function.formals [] formal.type then
          let context := source.context ⟨[],0,1,source.selected.method.function.formals.length⟩ (resources.map (·.source))
          let lexical ← scopeStatementsWith .receiverEffects context.uses context.writes
            (checkEffectUses context) (checkEffectWrites context) source.selected.classDecl.members module
            (namespacePath ++ [className]) source.selected.method.function.formals 4096
            ⟨[],0,1,source.selected.method.function.formals.length⟩ parsed.statements
          if frame : EffectReceiverFrame t id source.selected.classDecl.members types.kinds.tail lexical.declaredItems then
            return ⟨source,id,visible.val,visible.property,header,types,resources,compatible,parsed,formals,typeNames,lexical,frame⟩
          else none
        else none
      else none
    else none
  else none

def checkEffectMethodCallable (t : Tables) (files : List SourceFile)
    (root module namespacePath : Name) (className member : ByteArray) :
    Option (EffectMethodCallable t files root module namespacePath className member) := do
  let method ← checkCanonicalEffectMethod t files root module namespacePath className member
  let parameters ← checkRuntimeSignature t method.source.selected.classDecl.members module (namespacePath ++ [className])
    ((atRow t.callables method.id).integer 4 + 1) (method.source.selected.method.function.formals.map (·.type))
  let result ← resolveRuntimeType method.source.selected.classDecl.members module (namespacePath ++ [className])
    method.source.selected.method.function.result
  if identity : RuntimeTypeIdentity t ((atRow t.callables method.id).integer 4) result.kind then
    if signature : method.types.kinds = result.kind :: parameters.kinds then
      return ⟨method,parameters,result.kind,result.typing,identity,signature⟩
    else none
  else none

end Aurora.SourceBinding
