import SourceBinding.EffectCanonicalBinding
import SourceBinding.RuntimeCallable
import SourceBinding.EffectSourceFunction
namespace Aurora.SourceBinding
open Aurora.Publication

/-- A typed source payload derived from the same selected receiver method.
    The separate parameter/result witnesses agree with the full signature;
    no missing head is replaced with a default scalar type. -/
structure EffectMethodCallable (t : Tables) (files : List SourceFile)
    (root module namespacePath : Name) (className member : ByteArray) where
  method : CanonicalEffectMethod t files root module namespacePath className member
  parameters : CheckedRuntimeSignature t method.source.selected.classDecl.members module
    (namespacePath ++ [className]) ((atRow t.callables method.id).integer 4 + 1)
    (method.source.selected.method.function.formals.map (·.type))
  result : RuntimeType
  resultSource : RuntimeSourceType method.source.selected.classDecl.members module
    (namespacePath ++ [className]) method.source.selected.method.function.result result
  resultIdentity : RuntimeTypeIdentity t ((atRow t.callables method.id).integer 4) result
  signature : method.types.kinds = result :: parameters.kinds

def EffectMethodCallable.source
    (callable : EffectMethodCallable t files root module namespacePath className member) : EffectSourceFunction where
  input := callable.method.source.selected.file.file.bytes
  function := callable.method.source.selected.method.function
  parsed := callable.method.parsed
  context := callable.method.source.context ⟨[],0,1,callable.method.source.selected.method.function.formals.length⟩
    (callable.method.resources.map (·.source))
  declared := callable.method.source.selected.method.present
  formals := rfl
  visible := rfl
  mode := rfl
  parameters := callable.parameters.kinds
  result := callable.result
  parameterTypes := callable.parameters.grammar.source_signature
  resultType := callable.resultSource

def EffectMethodCallable.target
    (callable : EffectMethodCallable t files root module namespacePath className member) : OrdinaryDescriptor :=
  ⟨member,callable.method.id,callable.parameters.kinds,callable.result⟩

/-- One checked inventory, allowing actual namespace free functions and actual
    receiver methods. This is identity data, not a second code grammar/evaluator. -/
inductive EffectCallable (t : Tables) (files : List SourceFile) (root : Name) where
  | free {module path : Name} (checked : RuntimeCallable t files root module path)
  | method {module namespacePath : Name} {className member : ByteArray}
      (checked : EffectMethodCallable t files root module namespacePath className member)

def EffectCallable.source : EffectCallable t files root → EffectSourceFunction
  | .free checked => checked.source.toEffect
  | .method checked => checked.source

def EffectCallable.target : EffectCallable t files root → OrdinaryDescriptor
  | .free checked => checked.target
  | .method checked => checked.target

def EffectCallable.resourcePairs : EffectCallable t files root → List (RuntimeSourceResource × ResourceDescriptor)
  | .free _ => []
  | .method checked => checked.method.resourcePairs

/-- Scalar field events use the declared ordered field index. Resource fields
    do not become scalar storage events. This list is computed, never supplied. -/
def EffectCallable.fieldPairs : EffectCallable t files root → List (ByteArray × Nat)
  | .free _ => []
  | .method checked =>
      (fields checked.method.source.selected.classDecl.members).zipIdx.filterMap fun (field,index) =>
        match sourceScalarKind field.type with
        | some _ => some (field.name,index)
        | none => none

def EffectCallable.ordinaryPairs (nodes : List (EffectCallable t files root)) :
    List (RuntimeSourceKey × OrdinaryDescriptor) := nodes.map fun node => (node.source.key,node.target)

/-- Duplicate identities agree completely, not merely by name or arity. The
    graph/body checker must construct this property, not expose it as a public
    execution premise. No rank or callee result occurs in the inventory. -/
def EffectCallablesCompatible (nodes : List (EffectCallable t files root)) : Prop :=
  ∀ left ∈ nodes, ∀ right ∈ nodes,
    (left.source.key = right.source.key ∨ left.target.id = right.target.id) →
      left.source = right.source ∧ left.target = right.target

/-- All same-spelling function declarations in an authenticated scope. This
    inventory is computed before looking at retained IR or chosen DAG nodes. -/
def effectScopeCandidates (module path : Name) (members : List Declaration)
    (name : ByteArray) : List (RuntimeSourceKey × Function) :=
  members.filterMap fun declaration => match declaration with
    | .functionDecl function =>
      if function.name = name then some (⟨module,path,name⟩,function) else none
    | _ => none

/-- Conservative bare-name candidate inventory with the same lexical shadow
    guards. All imported competitors are retained, even if omitted from IR or
    from a proposed closure. Unsupported candidates cause checked rejection. -/
def effectAccessibleCandidates (context : EffectContext) (name : ByteArray) :
    List (RuntimeSourceKey × Function) :=
  if name ∈ context.lexical.formals.map (·.name) ∨ name ∈ context.lexical.visible.map (·.name) then []
  else if name ∈ context.lexical.members.filterMap declarationName then
    effectScopeCandidates context.lexical.module context.lexical.path context.lexical.members name
  else if context.profile = .legacy then []
  else if context.enclosing.any (fun scope => decide (name ∈ scope.members.filterMap declarationName)) then
    context.enclosing.flatMap fun scope => effectScopeCandidates scope.module scope.path scope.members name
  else context.imported.flatMap fun scope => effectScopeCandidates scope.module scope.path scope.members name

/-- Actual source resolution includes receiver mode, lexical precedence and
    authenticated imported namespace data from the selected method context.
    An ambiguous imported spelling is rejected unless its complete identity
    agrees. Complete call-occurrence coverage is a separate whole-body check. -/
structure EffectResolvedCall (nodes : List (EffectCallable t files root))
    (context : EffectContext) (name : Name) where
  chosen : EffectCallable t files root
  member : chosen ∈ nodes
  resolved : chosen.source.Resolves context name
  bare : name = [chosen.source.function.name]
  sourcePresent : (chosen.source.key,chosen.source.function) ∈
    effectAccessibleCandidates context chosen.source.function.name
  sourceUnambiguous : ∀ candidate ∈ effectAccessibleCandidates context chosen.source.function.name,
    candidate.1 = chosen.source.key ∧ candidate.2 = chosen.source.function
  unique : ∀ other ∈ nodes, other.source.Resolves context name →
    other.source = chosen.source ∧ other.target = chosen.target

@[simp] theorem EffectCallable.parameters_exact (callable : EffectCallable t files root) :
    callable.source.parameters = callable.target.parameters := by cases callable <;> rfl
@[simp] theorem EffectCallable.result_exact (callable : EffectCallable t files root) :
    callable.source.result = callable.target.result := by cases callable <;> rfl

end Aurora.SourceBinding
