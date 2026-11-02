import SourceBinding.RuntimeCallable
import SourceBinding.SourceStatementEquality
import SourceBinding.RuntimeBodyBinding
namespace Aurora.SourceBinding

/-- Full source/target compatibility is separate from unconstrained source
    evaluation. Duplicate entries are harmless only when all retained data agree. -/
def RuntimeCallablesCompatible (nodes : List (RuntimeCallable t files root module path)) : Prop :=
  ∀ first ∈ nodes, ∀ second ∈ nodes,
    (first.source.key = second.source.key →
      first.source.input = second.source.input ∧ first.source.function = second.source.function ∧
      first.source.context.members = second.source.context.members ∧
      first.source.parsed.statements = second.source.parsed.statements ∧ first.target = second.target) ∧
    (first.target.id = second.target.id → first.source.key = second.source.key)

instance (nodes : List (RuntimeCallable t files root module path)) :
    Decidable (RuntimeCallablesCompatible nodes) := by unfold RuntimeCallablesCompatible; infer_instance

/-- Edges are the complete syntactic call inventory, not a chosen execution's
    calls. Both short-circuit operands, branches and dead suffixes contribute. -/
def RuntimeSourceEdge (nodes : List (RuntimeCallable t files root module path))
    (sourceNode targetNode : RuntimeCallable t files root module path) : Prop :=
  sourceNode ∈ nodes ∧ targetNode ∈ nodes ∧ ∃ names,
    runtimeStatementsNames 4096 sourceNode.source.parsed.statements = some names ∧ targetNode.name ∈ names

inductive RuntimeSourceReachable (nodes : List (RuntimeCallable t files root module path))
    (rootKey : RuntimeSourceKey) : RuntimeSourceKey → Prop
  | root : RuntimeSourceReachable nodes rootKey rootKey
  | step : RuntimeSourceReachable nodes rootKey before.source.key → RuntimeSourceEdge nodes before after →
      RuntimeSourceReachable nodes rootKey after.source.key

/-- Identity/closure/rank shape ONLY. Complete node body-code fields are added
    after the single existing statement grammar is generalized to RuntimeCallable;
    this shape alone does not certify execution or any callee result. -/
structure RuntimeDAGShape (t : Aurora.Publication.Tables) (files : List SourceFile)
    (root module path : Name) (rootName : ByteArray) where
  nodes : List (RuntimeCallable t files root module path)
  rootNode : RuntimeCallable t files root module path
  rootNameEq : rootNode.name = rootName
  rootMember : rootNode ∈ nodes
  compatible : RuntimeCallablesCompatible nodes
  inventory : ∀ node ∈ nodes, ∃ names, runtimeStatementsNames 4096 node.source.parsed.statements = some names
  closed : ∀ node ∈ nodes, ∀ names,
    runtimeStatementsNames 4096 node.source.parsed.statements = some names →
    ∀ name ∈ names, ∃ callee ∈ nodes, callee.name = name
  exactClosure : ∀ node ∈ nodes, RuntimeSourceReachable nodes rootNode.source.key node.source.key
  rank : RuntimeSourceKey → Nat
  decreases : ∀ before after, RuntimeSourceEdge nodes before after → rank after.source.key < rank before.source.key

end Aurora.SourceBinding
