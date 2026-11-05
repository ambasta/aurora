import SourceBinding.RuntimeReceiverSource
import SourceBinding.FreeSelection
namespace Aurora.SourceBinding

/-- A direct, exported namespace of the SAME complete source graph. This is
    declaration accessibility, not a proof of native call/ABI behavior. -/
structure EffectImportedScope (files : List SourceFile) (caller : SourceFile) where
  module : Name
  path : Name
  file : FoundFile files module
  scope : FoundNamespace file.file.checked.source.shell.declarations path
  direct : module ∈ importedNames caller
  exportedModule : file.file.checked.source.header.declarations.module.exported = true
  exportedNamespace : scope.exported = true

def EffectImportedScope.source (item : EffectImportedScope files caller) : RuntimeNamespaceScope :=
  ⟨item.module,item.path,item.scope.members⟩

/-- Selected source receiver with its real enclosing namespace and declaration
    mode. No free function receives a dummy receiver. Canonical signature,
    complete local slots, and whole-body code coverage are separate joins. -/
structure CheckedEffectReceiver (files : List SourceFile) (root module namespacePath : Name)
    (className member : ByteArray) where
  graph : GraphReady files root
  selected : SelectedMember files module (namespacePath ++ [className]) member
  enclosing : FoundNamespace selected.file.file.checked.source.shell.declarations namespacePath
  nested : Declaration.classDecl className selected.classDecl.members ∈ enclosing.members
  ordinaryOrReadonly : selected.method.function.mode = .ordinary ∨ selected.method.function.mode = .readonly
  imports : List (EffectImportedScope files selected.file.file)
  importOrder : imports.map (·.module) = importedNames selected.file.file
  importPaths : ∀ item ∈ imports, item.path = namespacePath

def CheckedEffectReceiver.receiver (checked : CheckedEffectReceiver files root module namespacePath className member) :
    RuntimeReceiverContext :=
  ⟨⟨⟨module,namespacePath ++ [className]⟩,checked.selected.classDecl.members⟩,
    checked.selected.method.function.mode⟩

def CheckedEffectReceiver.context (checked : CheckedEffectReceiver files root module namespacePath className member)
    (cursor : LocalContext) (resources : List RuntimeSourceResource := []) : EffectContext :=
  ⟨⟨checked.selected.classDecl.members,module,namespacePath ++ [className],
      checked.selected.method.function.formals,cursor.visible⟩,
    some checked.receiver,[⟨module,namespacePath,checked.enclosing.members⟩],checked.imports.map (·.source),.receiverEffects,resources⟩

/-- Actual receiver declaration mode gates the source operation. These are
    permission checks, not resource success or frame guarantees. -/
def ReceiverAllowsResource (receiver : RuntimeReceiverContext) (mode : RuntimeResourceMode) : Prop :=
  receiver.mode = .ordinary ∨ (receiver.mode = .readonly ∧ mode = .readonly)

/-- Source receiver and retained-field identity are exact. Actual catalogue
    kind/method/signature/flags and emitted operands are joined separately. -/
structure EffectResourceResolved (context : EffectContext) (resource : RuntimeSourceResource) where
  member : resource ∈ context.resources
  receiver : RuntimeReceiverContext
  current : context.receiver = some receiver
  sameScope : resource.receiver = receiver.scope
  permitted : ReceiverAllowsResource receiver resource.mode
  declared : RuntimeSourceResourceBinding resource
  unshadowed : resource.field ∉ context.lexical.formals.map (·.name) ∧
    resource.field ∉ context.lexical.visible.map (·.name)

end Aurora.SourceBinding
