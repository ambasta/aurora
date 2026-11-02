import SourceBinding.FramePolicyHelpers
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}

/-- Exact positional source formal read for either scalar or nominal input.
    The declared type comes from the SAME selected runtime signature. -/
theorem ExactProfile.formal_result {declaration : Formal} {values : List Value} {index : Nat} (profile : ExactProfile bound)
    (node : RuntimeCallable (tables bound.artifact.document.reversed.reverse) files root frameModule framePath)
    (member : node ∈ bound.checked.shape.nodes)
    (formalAt : node.source.context.formals[index]? = some declaration)
    (kindAt : node.source.parameters[index]? = some kind)
    (valueAt : values[index]? = some value)
    (typed : readRuntime kind (some value) = .value value) :
    RuntimeExpressionResult (bound.checked.shape.nodes.map (·.source)) node.source.context
      (formalSourceLocals node.source.parameters (fun index => values[index]?))
      (.name [declaration.name]) kind (.value value) := by
  have sourceAt := congrArg (Option.map (·.type)) formalAt
  rw [← List.getElem?_map] at sourceAt
  obtain ⟨actual,found,declared⟩ := node.parameters.grammar.lookup sourceAt
  have same := Option.some.inj (found.symm.trans kindAt)
  subst actual
  have binding : RuntimeVariableBinding node.source.context declaration.name
      ⟨declaration.name,kind,false,0,runtimeParameterSlot index⟩ := by
    apply RuntimeVariableBinding.formal formalAt rfl declared
    simp only [RuntimeCallable.source,runtimeReturnContext,List.map_nil,List.not_mem_nil,not_false_eq_true]
  have expression := RuntimeExpressionResult.readVariable
    (functions := bound.checked.shape.nodes.map (·.source))
    (state := formalSourceLocals node.source.parameters (fun index => values[index]?))
    (profile.initial_context node member) binding
  have reading := formal_read (name := declaration.name) (arguments := fun index => values[index]?) kindAt
  dsimp only at reading
  rw [valueAt,typed] at reading
  rw [reading] at expression
  exact expression

end Aurora.SourceBinding.FramePolicyAttachment
