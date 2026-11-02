import SourceBinding.RuntimeNodeExecution
namespace Aurora.SourceBinding

/-- Checked strict rank discharges every actual direct-callee hypothesis.
    No body outcome, source summary, or execution premise is supplied publicly. -/
theorem RuntimeDAGCertificate.node_executes
    (checked : RuntimeDAGCertificate t files root module path name)
    (node : RuntimeCallable t files root module path) (member : node ∈ checked.shape.nodes) :
    RuntimeCalleeExecutes (canonicalRuntimeCalls t (checked.shape.nodes.map (·.target)))
      checked.shape.nodes node World ExternalFault := by
  have bounded : ∀ rank, ∀ current ∈ checked.shape.nodes,
      checked.shape.rank current.source.key = rank →
      RuntimeCalleeExecutes (canonicalRuntimeCalls t (checked.shape.nodes.map (·.target)))
        checked.shape.nodes current World ExternalFault := by
    intro rank
    induction rank using Nat.strongRecOn with
    | ind rank ih =>
      intro current present ranked
      apply (checked.bodies current present).callee_executes
      intro direct names included callee called
      have decrease := checked.shape.direct_decreases current present direct names included callee called
      rw [ranked] at decrease
      exact ih (checked.shape.rank callee.source.key) decrease callee (included callee called) rfl
  exact bounded _ node member rfl

theorem RuntimeDAGCertificate.root_executes
    (checked : RuntimeDAGCertificate t files root module path name) :
    RuntimeCalleeExecutes (canonicalRuntimeCalls t (checked.shape.nodes.map (·.target)))
      checked.shape.nodes checked.shape.rootNode World ExternalFault :=
  checked.node_executes checked.shape.rootNode checked.shape.rootMember

end Aurora.SourceBinding
