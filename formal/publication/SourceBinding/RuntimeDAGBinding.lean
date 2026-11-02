import SourceBinding.RuntimeDAGChecker
namespace Aurora.SourceBinding
open Aurora.Publication

/-- A node contains the actual whole source/code certificate. No callee value,
    successful guard, or assumed poststate appears in this interface. -/
structure RuntimeNodeBodyCertificate (nodes : List (RuntimeCallable t files root module path))
    (node : RuntimeCallable t files root module path) : Prop where
  entry : RuntimeEntryCode (canonicalEffects t node.target.id) node.parameters.kinds
  code : ∃ direct : List (RuntimeCallable t files root module path),
    runtimeStatementsNames 4096 node.source.parsed.statements = some (direct.map (·.name)) ∧
    (∀ callee ∈ direct, callee ∈ nodes) ∧
    RuntimeStatementsCode (canonicalRuntimeCalls t (nodes.map (·.target))) node.target.id direct
      node.identified.selected.scope.members node.identified.selected.function.function.formals node.resultKind
      ⟨[],0,1,node.identified.selected.function.function.formals.length⟩
      node.identified.details.lexical.parsed.statements
      node.identified.details.lexical.lexical.after node.identified.details.lexical.lexical.declaredItems
      node.parameters.kinds.length (functionCode t node.target.id).size
  noFallthrough : RuntimeNoFallthrough node.source.parsed.statements

structure RuntimeDirectCalls (nodes : List (RuntimeCallable t files root module path)) (names : List ByteArray) where
  targets : List (RuntimeCallable t files root module path)
  named : targets.map (·.name) = names
  included : ∀ callee ∈ targets, callee ∈ nodes

def checkRuntimeDirectCalls (nodes : List (RuntimeCallable t files root module path)) :
    (names : List ByteArray) → Option (RuntimeDirectCalls nodes names)
  | [] => some ⟨[],rfl,by intro callee member; cases member⟩
  | name::rest => do
    match found : nodes.find? (fun node => node.name == name) with
    | none => none
    | some node =>
      if named : node.name = name then
        let tail ← checkRuntimeDirectCalls nodes rest
        return ⟨node::tail.targets,by simp only [List.map_cons,named,tail.named],by
          intro callee member
          rcases List.mem_cons.mp member with same | later
          · subst callee; exact List.mem_of_find?_eq_some found
          · exact tail.included callee later⟩
      else none

def checkRuntimeNodeBody (nodes : List (RuntimeCallable t files root module path))
    (node : RuntimeCallable t files root module path) : Option { _witness : Unit // RuntimeNodeBodyCertificate nodes node } := do
  match namesEq : runtimeStatementsNames 4096 node.source.parsed.statements with
  | none => none
  | some names =>
    let direct ← checkRuntimeDirectCalls nodes names
    if entry : RuntimeEntryCode (canonicalEffects t node.target.id) node.parameters.kinds then
      let code ← checkRuntimeStatements (canonicalRuntimeCalls t (nodes.map (·.target))) node.target.id direct.targets
        node.identified.selected.scope.members node.identified.selected.function.function.formals node.resultKind 4096
        ⟨[],0,1,node.identified.selected.function.function.formals.length⟩
        node.identified.details.lexical.parsed.statements node.parameters.kinds.length
      if after : code.after = node.identified.details.lexical.lexical.after then
        if items : code.declaredItems = node.identified.details.lexical.lexical.declaredItems then
          if complete : code.stop = (functionCode t node.target.id).size then
            let terminal ← checkRuntimeNoFallthrough node.source.parsed.statements
            return ⟨(),⟨entry,⟨direct.targets,by simpa only [direct.named] using namesEq,direct.included,
              after ▸ items ▸ complete ▸ code.grammar⟩,terminal.property⟩⟩
          else none
        else none
      else none
    else none

/-- All nodes use the SAME canonical program and supplied publication tables.
    The shape's all-edge strict rank supports proof induction, not evaluation. -/
structure RuntimeDAGCertificate (t : Tables) (files : List SourceFile)
    (root module path : Name) (rootName : ByteArray) where
  shape : RuntimeDAGShape t files root module path rootName
  bodies : ∀ node ∈ shape.nodes, RuntimeNodeBodyCertificate shape.nodes node

def checkRuntimeDAG (t : Tables) (files : List SourceFile) (root module path : Name)
    (rootName : ByteArray) : Option (RuntimeDAGCertificate t files root module path rootName) := do
  let shape ← checkRuntimeDAGShape t files root module path rootName
  let bodies ← certifyEach (RuntimeNodeBodyCertificate shape.nodes)
    (checkRuntimeNodeBody shape.nodes) shape.nodes
  return ⟨shape,bodies.property⟩

structure RuntimeDAGBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  artifact : CheckedArtifact input
  checked : RuntimeDAGCertificate (tables artifact.document.reversed.reverse) files root module path name

def bindRuntimeDAG (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (input : ByteArray) : Option (RuntimeDAGBinding input files root module path name) := do
  let artifact ← decodeArtifact {} input
  let checked ← checkRuntimeDAG (tables artifact.document.reversed.reverse) files root module path name
  return ⟨artifact,checked⟩

end Aurora.SourceBinding
