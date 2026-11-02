import SourceBinding.RuntimeDAGBinding
namespace Aurora.SourceBinding

/-- Even a call in unreachable syntax is an edge and must decrease rank. -/
theorem RuntimeDAGShape.no_self_edge (shape : RuntimeDAGShape t files root module path name)
    (node : RuntimeCallable t files root module path) : ¬ RuntimeSourceEdge shape.nodes node node := by
  intro edge
  exact Nat.lt_irrefl _ (shape.decreases node node edge)

theorem RuntimeDAGShape.reachable_rank (shape : RuntimeDAGShape t files root module path name)
    (reached : RuntimeSourceReachable shape.nodes first last) : shape.rank last ≤ shape.rank first := by
  induction reached with
  | root => exact Nat.le_refl _
  | step prior edge ih => exact Nat.le_trans (Nat.le_of_lt (shape.decreases _ _ edge)) ih

theorem RuntimeDAGShape.no_cycle (shape : RuntimeDAGShape t files root module path name)
    (edge : RuntimeSourceEdge shape.nodes before after)
    (back : RuntimeSourceReachable shape.nodes after.source.key before.source.key) : False :=
  Nat.not_lt_of_ge (shape.reachable_rank back) (shape.decreases before after edge)

/-- Exact direct inventories inherit the checked whole-graph rank. This is
    derived from source syntax and actual member nodes, not a supplied IH. -/
theorem RuntimeDAGShape.direct_decreases (shape : RuntimeDAGShape t files root module path name)
    (node : RuntimeCallable t files root module path) (member : node ∈ shape.nodes)
    (direct : List (RuntimeCallable t files root module path))
    (names : runtimeStatementsNames 4096 node.source.parsed.statements = some (direct.map (·.name)))
    (included : ∀ callee ∈ direct, callee ∈ shape.nodes)
    (callee : RuntimeCallable t files root module path) (called : callee ∈ direct) :
    shape.rank callee.source.key < shape.rank node.source.key :=
  shape.decreases node callee ⟨member,included callee called,direct.map (·.name),names,List.mem_map_of_mem called⟩

end Aurora.SourceBinding
