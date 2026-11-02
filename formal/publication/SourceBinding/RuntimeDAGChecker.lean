import SourceBinding.RuntimeDAGShape
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Discovery is source-driven; repeated names are visited once. Fuel is only a
    fail-closed work bound, never evidence of termination of source execution. -/
def discoverRuntimeCallables (t : Tables) (files : List SourceFile) (root module path : Name) :
    Nat → List ByteArray → List (RuntimeCallable t files root module path) →
    Option (List (RuntimeCallable t files root module path))
  | 0, _, _ => none
  | _+1, [], visited => some visited
  | fuel+1, name::pending, visited =>
    if visited.any (fun node => node.name == name) then
      discoverRuntimeCallables t files root module path fuel pending visited
    else do
      let node ← checkRuntimeCallable t files root module path name
      let names ← runtimeStatementsNames 4096 node.source.parsed.statements
      discoverRuntimeCallables t files root module path fuel (names ++ pending) (visited ++ [node])

def RuntimeNodeCallsClosed (nodes : List (RuntimeCallable t files root module path))
    (node : RuntimeCallable t files root module path) : Prop :=
  match runtimeStatementsNames 4096 node.source.parsed.statements with
  | none => False
  | some names => ∀ name ∈ names, ∃ callee ∈ nodes, callee.name = name
instance (nodes : List (RuntimeCallable t files root module path)) (node : RuntimeCallable t files root module path) :
    Decidable (RuntimeNodeCallsClosed nodes node) := by
  unfold RuntimeNodeCallsClosed; split <;> infer_instance

def RuntimeCallsClosed (nodes : List (RuntimeCallable t files root module path)) : Prop :=
  ∀ node ∈ nodes, RuntimeNodeCallsClosed nodes node
instance (nodes : List (RuntimeCallable t files root module path)) : Decidable (RuntimeCallsClosed nodes) := by
  unfold RuntimeCallsClosed; infer_instance

def RuntimeNodeCallsRanked (nodes : List (RuntimeCallable t files root module path))
    (rank : RuntimeSourceKey → Nat) (node : RuntimeCallable t files root module path) : Prop :=
  match runtimeStatementsNames 4096 node.source.parsed.statements with
  | none => False
  | some names => ∀ callee ∈ nodes, callee.name ∈ names → rank callee.source.key < rank node.source.key
instance (nodes : List (RuntimeCallable t files root module path)) (rank : RuntimeSourceKey → Nat)
    (node : RuntimeCallable t files root module path) : Decidable (RuntimeNodeCallsRanked nodes rank node) := by
  unfold RuntimeNodeCallsRanked; split <;> infer_instance

def RuntimeCallsRanked (nodes : List (RuntimeCallable t files root module path))
    (rank : RuntimeSourceKey → Nat) : Prop := ∀ node ∈ nodes, RuntimeNodeCallsRanked nodes rank node
instance (nodes : List (RuntimeCallable t files root module path)) (rank : RuntimeSourceKey → Nat) :
    Decidable (RuntimeCallsRanked nodes rank) := by unfold RuntimeCallsRanked; infer_instance

private def knownRank (ranks : List (RuntimeSourceKey × Nat)) (key : RuntimeSourceKey) : Option Nat :=
  ((ranks.find? (fun pair => pair.1 == key)).map (·.2))

/-- Bottom-up finite ranking; the resulting candidate is independently checked
    against every actual syntactic edge before being admitted. -/
def runtimeRankPass (nodes : List (RuntimeCallable t files root module path))
    (ranks : List (RuntimeSourceKey × Nat)) : List (RuntimeSourceKey × Nat) :=
  nodes.foldl (fun known node =>
    if (knownRank known node.source.key).isSome then known else
      match runtimeStatementsNames 4096 node.source.parsed.statements with
      | none => known
      | some names =>
        let values := names.mapM fun name => do
          let callee ← nodes.find? (fun item => item.name == name)
          knownRank known callee.source.key
        match values with
        | none => known
        | some values => (node.source.key,1 + values.foldl max 0) :: known) ranks

def runtimeRankRounds (nodes : List (RuntimeCallable t files root module path)) :
    Nat → List (RuntimeSourceKey × Nat) → List (RuntimeSourceKey × Nat)
  | 0, known => known
  | fuel+1, known => runtimeRankRounds nodes fuel (runtimeRankPass nodes known)

/-- Search constructs a source-edge path certificate. Equality is by source key,
    never by proof-bearing selection-package identity. -/
def checkRuntimeReachable (nodes : List (RuntimeCallable t files root module path))
    (rootKey target : RuntimeSourceKey) :
    Nat → (current : RuntimeCallable t files root module path) → current ∈ nodes →
    RuntimeSourceReachable nodes rootKey current.source.key →
    Option { _witness : Unit // RuntimeSourceReachable nodes rootKey target }
  | 0, _, _, _ => none
  | fuel+1, current, member, reached =>
    if same : current.source.key = target then some ⟨(),same ▸ reached⟩ else
      match found : runtimeStatementsNames 4096 current.source.parsed.statements with
      | none => none
      | some names => nodes.attach.findSome? fun next =>
        if called : next.val.name ∈ names then
          checkRuntimeReachable nodes rootKey target fuel next.val next.property
            (.step reached ⟨member,next.property,names,found,called⟩)
        else none

def checkRuntimeDAGShape (t : Tables) (files : List SourceFile) (root module path : Name)
    (rootName : ByteArray) : Option (RuntimeDAGShape t files root module path rootName) := do
  let nodes ← discoverRuntimeCallables t files root module path 4096 [rootName] []
  match found : nodes.find? (fun node => node.name == rootName) with
  | none => none
  | some rootNode =>
    if named : rootNode.name = rootName then
      if compatible : RuntimeCallablesCompatible nodes then
        if closed : RuntimeCallsClosed nodes then
          let known := runtimeRankRounds nodes nodes.length []
          let rank := fun key => (knownRank known key).getD 0
          if ranked : RuntimeCallsRanked nodes rank then
            let reach ← certifyEach (fun node => RuntimeSourceReachable nodes rootNode.source.key node.source.key)
              (fun node => checkRuntimeReachable nodes rootNode.source.key node.source.key (nodes.length + 1)
                rootNode (List.mem_of_find?_eq_some found) .root) nodes
            return {
              nodes := nodes, rootNode := rootNode, rootNameEq := named
              rootMember := List.mem_of_find?_eq_some found, compatible := compatible
              inventory := by
                intro node member
                have actual := closed node member
                cases names : runtimeStatementsNames 4096 node.source.parsed.statements with
                | none => simp only [RuntimeNodeCallsClosed,names] at actual
                | some values => exact ⟨values,rfl⟩
              closed := by
                intro node member names equal
                have actual := closed node member
                simpa only [RuntimeNodeCallsClosed,equal] using actual
              exactClosure := reach.property
              rank := rank
              decreases := by
                intro before after edge
                obtain ⟨first,second,names,equal,called⟩ := edge
                have actual := ranked before first
                simp only [RuntimeNodeCallsRanked,equal] at actual
                exact actual after second called }
          else none
        else none
      else none
    else none

end Aurora.SourceBinding
