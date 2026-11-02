import SourceBinding.Selection
namespace Aurora.SourceBinding

/-- Namespace-only traversal; class bodies and opaque source spans are never searched. -/
inductive NamespaceAt : List Declaration → Name → List Declaration → Bool → Prop
  | root : NamespaceAt decls [] decls true
  | nested : Declaration.namespaceDecl name exported children ∈ decls →
      NamespaceAt children path members visible →
      NamespaceAt decls (name :: path) members (exported && visible)

theorem NamespaceAt.bindings (found : NamespaceAt decls path members visible)
    (binding : ScopeBindings decls) : ScopeBindings members := by
  induction found with
  | root => exact binding
  | nested present nested ih =>
    have valid := binding.member present
    cases valid with
    | namespaceDecl nameOK childOK => exact ih childOK

structure FoundNamespace (decls : List Declaration) (path : Name) where
  members : List Declaration
  exported : Bool
  grammar : NamespaceAt decls path members exported

def findNamespace : (fuel : Nat) → (decls : List Declaration) → (path : Name) →
    Option (FoundNamespace decls path)
  | 0, _, _ => none
  | _ + 1, decls, [] => some ⟨decls,true,.root⟩
  | fuel + 1, decls, name :: rest =>
    match found : decls.find? (fun item => match item with
      | .namespaceDecl actual _ _ => actual == name
      | _ => false) with
    | none => none
    | some candidate => match candidate with
      | .namespaceDecl actual exported children => do
        if named : actual = name then
          let child ← findNamespace fuel children rest
          return ⟨child.members,exported && child.exported, by
            have present := List.mem_of_find?_eq_some found
            subst actual
            exact .nested present child.grammar⟩
        else none
      | _ => none

/-- Exact bytes, complete shell, graph and actual declaration are retained together. -/
structure CheckedFreeSelection (files : List SourceFile) (root module path : Name) (name : ByteArray) where
  graph : GraphReady files root
  file : FoundFile files module
  scope : FoundNamespace file.file.checked.source.shell.declarations path
  function : FoundFunction scope.members name

def checkFreeSelection (files : List SourceFile) (root module path : Name) (name : ByteArray) :
    Option (CheckedFreeSelection files root module path name) := do
  let graph ← checkGraph files root
  let file ← findFile files module
  let scope ← findNamespace 4096 file.file.checked.source.shell.declarations path
  let function ← findFunction scope.members name
  return ⟨graph.property,file,scope,function⟩

theorem checked_free_selection_sound (checked : CheckedFreeSelection files root module path name) :
    GraphReady files root ∧ checked.file.file ∈ files ∧ moduleName checked.file.file = module ∧
    Coverage checked.file.file.bytes checked.file.file.checked.source.header.lexical.reversed
      checked.file.file.bytes.size ∧
    NamespaceAt checked.file.file.checked.source.shell.declarations path checked.scope.members checked.scope.exported ∧
    ScopeBindings checked.scope.members ∧
    Declaration.functionDecl checked.function.function ∈ checked.scope.members ∧
    checked.function.function.name = name :=
  ⟨checked.graph,checked.file.present,checked.file.named,
    checked.file.file.checked.source.header.lexical.grammar,checked.scope.grammar,
    checked.scope.grammar.bindings checked.file.file.checked.bindings,
    checked.function.present,checked.function.named⟩

end Aurora.SourceBinding
