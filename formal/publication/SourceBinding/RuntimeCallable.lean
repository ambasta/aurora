import SourceBinding.RuntimeCallIdentity
import SourceBinding.RuntimeSourceFunction
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Same-graph/table selected callable identity, without a callee outcome or a
    singleton-body restriction. Complete local slots are already authenticated
    by identified.details.identity; body code is certified separately. -/
structure RuntimeCallable (t : Tables) (files : List SourceFile) (root module path : Name) where
  name : ByteArray
  identified : IdentifiedRuntimeFree t files root module path name
  parameters : CheckedRuntimeSignature t identified.selected.scope.members module path
    ((atRow t.callables identified.id).integer 4 + 1)
    (identified.selected.function.function.formals.map (·.type))
  resultKind : RuntimeType
  resultSource : RuntimeSourceType identified.selected.scope.members module path
    identified.selected.function.function.result resultKind
  resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) resultKind

def RuntimeCallable.source (callable : RuntimeCallable t files root module path) : RuntimeSourceFunction where
  input := callable.identified.selected.file.file.bytes
  function := callable.identified.selected.function.function
  parsed := callable.identified.details.lexical.parsed
  context := runtimeReturnContext callable.identified
  declared := callable.identified.selected.function.present
  formals := rfl
  visible := rfl
  ordinary := by
    have identity := callable.identified.details.identity
    unfold RuntimeFunctionIdentity at identity
    exact identity.1
  parameters := callable.parameters.kinds
  result := callable.resultKind
  parameterTypes := callable.parameters.grammar.source_signature
  resultType := callable.resultSource

def RuntimeCallable.target (callable : RuntimeCallable t files root module path) : OrdinaryDescriptor :=
  ⟨callable.name,callable.identified.id,callable.parameters.kinds,callable.resultKind⟩

def RuntimeCallLeaf.toCallable (leaf : RuntimeCallLeaf t files root module path) : RuntimeCallable t files root module path :=
  ⟨leaf.name,leaf.identified,leaf.body.parameters,leaf.body.resultKind,leaf.body.resultSource,leaf.body.resultIdentity⟩

@[simp] theorem RuntimeCallLeaf.toCallable_target (leaf : RuntimeCallLeaf t files root module path) :
    leaf.toCallable.target = leaf.target := rfl
@[simp] theorem RuntimeCallLeaf.toCallable_source (leaf : RuntimeCallLeaf t files root module path) :
    leaf.toCallable.source = leaf.source.toFunction := rfl

def checkRuntimeCallable (t : Tables) (files : List SourceFile) (root module path : Name)
    (name : ByteArray) : Option (RuntimeCallable t files root module path) := do
  let identified ← identifyRuntimeFree t files root module path name
  let parameters ← checkRuntimeSignature t identified.selected.scope.members module path
    ((atRow t.callables identified.id).integer 4 + 1)
    (identified.selected.function.function.formals.map (·.type))
  let result ← resolveRuntimeType identified.selected.scope.members module path
    identified.selected.function.function.result
  if resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) result.kind then
    return ⟨name,identified,parameters,result.kind,result.typing,resultIdentity⟩
  else none

@[simp] theorem RuntimeCallable.parameters_exact (callable : RuntimeCallable t files root module path) :
    callable.source.parameters = callable.target.parameters := rfl
@[simp] theorem RuntimeCallable.result_exact (callable : RuntimeCallable t files root module path) :
    callable.source.result = callable.target.result := rfl
@[simp] theorem RuntimeCallable.source_key (callable : RuntimeCallable t files root module path) :
    callable.source.key = ⟨module,path,callable.name⟩ := by
  change (⟨module,path,callable.identified.selected.function.function.name⟩ : RuntimeSourceKey) = _
  rw [callable.identified.selected.function.named]

end Aurora.SourceBinding
