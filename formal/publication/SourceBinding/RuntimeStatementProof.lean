import SourceBinding.RuntimeBranchProof
import SourceBinding.RuntimeUniformBody
namespace Aurora.SourceBinding

/-- Exact former fixed-context leaf profile, obtained by specializing the
    uniform generic proof with actual complete call-free leaf certificates. -/
theorem RuntimeStatementCode.simulates
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementCode program caller (leaves.map (·.toCallable)) members formals result before raw after declaredItems start stop)
    (projection : ∀ leaf ∈ leaves, localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    RuntimeStatementSimulates program caller leaves members formals result before raw after start stop base saved world external := by
  have callees : ∀ callable ∈ leaves.map (·.toCallable),
      RuntimeCalleeExecutes program (leaves.map (·.toCallable)) callable World ExternalFault := by
    intro callable member
    obtain ⟨leaf,present,equal⟩ := List.mem_map.mp member
    subst callable
    exact leaf.callee_executes program (projection leaf present) _
  intro source ancestors stateAt
  obtain ⟨outcome,se,me,evaluated,trace,continued,run⟩ :=
    code.simulates_uniform (fun _ member => member) callees source ancestors stateAt
  refine ⟨outcome,se,me,?_,trace,continued,run base saved world external⟩
  simpa only [RuntimeStatementEvaluates,List.map_map,RuntimeCallLeaf.toCallable_source] using evaluated

/-- Exact former fixed-context leaf profile, obtained by specializing the
    uniform generic proof with actual complete call-free leaf certificates. -/
theorem RuntimeStatementsCode.simulates
    {leaves : List (RuntimeCallLeaf t files root module path)}
    (code : RuntimeStatementsCode program caller (leaves.map (·.toCallable)) members formals result before raw after declaredItems start stop)
    (projection : ∀ leaf ∈ leaves, localProgram program leaf.target.id = canonicalEffects t leaf.identified.id)
    (base : Machine) (saved : List SavedCall) (world : World) (external : ExternalRelation World ExternalFault) :
    RuntimeStatementsSimulates program caller leaves members formals result before raw after start stop base saved world external := by
  have callees : ∀ callable ∈ leaves.map (·.toCallable),
      RuntimeCalleeExecutes program (leaves.map (·.toCallable)) callable World ExternalFault := by
    intro callable member
    obtain ⟨leaf,present,equal⟩ := List.mem_map.mp member
    subst callable
    exact leaf.callee_executes program (projection leaf present) _
  intro source ancestors stateAt
  obtain ⟨outcome,se,me,evaluated,trace,continued,run⟩ :=
    code.simulates_uniform (fun _ member => member) callees source ancestors stateAt
  refine ⟨outcome,se,me,?_,trace,continued,run base saved world external⟩
  simpa only [RuntimeStatementsEvaluate,List.map_map,RuntimeCallLeaf.toCallable_source] using evaluated

end Aurora.SourceBinding
