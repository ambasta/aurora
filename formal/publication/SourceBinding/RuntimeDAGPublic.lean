import SourceBinding.RuntimeDAGExecution
import SourceBinding.RuntimeBodyTerminal
namespace Aurora.SourceBinding

/-- Complete actual root execution for the checked whole source/IR DAG. The
    only input premise is typed ordered arguments. The source outcome and both
    traces precede all receiver/world/external contexts. Root ret is executed;
    a fault retains its actual active frame, including nested callee frames. -/
theorem RuntimeDAGCertificate.executes
    (checked : RuntimeDAGCertificate t files root module path name)
    (values : List Value)
    (ready : RuntimeReadyArguments checked.shape.rootNode.source.parameters values) :
    ∃ outcome sourceEvents machineEvents,
      RuntimeStatementsEvaluation (checked.shape.nodes.map (·.source))
        checked.shape.rootNode.source.context.members module path
        checked.shape.rootNode.source.context.formals checked.shape.rootNode.source.result
        ⟨[],0,1,checked.shape.rootNode.source.context.formals.length⟩
        (formalSourceLocals checked.shape.rootNode.source.parameters (fun index => values[index]?))
        checked.shape.rootNode.source.parsed.statements
        checked.shape.rootNode.identified.details.lexical.lexical.after outcome sourceEvents ∧
      RuntimeCallTraceRelated checked.shape.nodes sourceEvents machineEvents ∧
      ∀ (shared : CallShared World) (external : ExternalRelation World ExternalFault),
      ∃ final, CallRuns (canonicalRuntimeCalls t (checked.shape.nodes.map (·.target))) external
        (.running (activeAt checked.shape.rootNode.target.id [] shared.world ((freshCallFrame values).inject shared)))
        machineEvents final ∧
      RuntimeBodyTerminal ((freshCallFrame values).inject shared) shared.world outcome final := by
  obtain ⟨outcome,se,me,evaluated,trace,terminal,run⟩ := checked.root_executes values ready
  refine ⟨outcome,se,me,evaluated,trace,?_⟩
  intro shared external
  obtain ⟨final,actual,related⟩ := run shared [] external
  cases outcome with
  | continued next => exact False.elim (terminal next rfl)
  | trapped fault next =>
    obtain ⟨active,equal,sharedEq⟩ := related
    subst final
    exact ⟨_,actual,rfl,sharedEq⟩
  | returned value next =>
    obtain ⟨pc,code,equal⟩ := related
    subst final
    let base := (freshCallFrame values).inject shared
    have last : EffectRuns
        (localProgram (canonicalRuntimeCalls t (checked.shape.nodes.map (·.target))) checked.shape.rootNode.target.id)
        (runtimeBodyFrame base next pc (some value)) []
        (.returned value (runtimeBodyFrame base next pc (some value))) := by
      apply EffectRuns.returned
      simp only [effectStep,runtimeBodyFrame,code,pureView,step,retainState]
    have lastCall := last.call_lift (by trivial) [] shared.world external
    refine ⟨.returned value (activeAt checked.shape.rootNode.target.id [] shared.world
      (runtimeBodyFrame base next pc (some value))),?_,rfl,rfl,rfl,rfl⟩
    simpa only [List.map_nil,List.nil_append,finishEffect,returnToCaller,activeAt,List.append_nil]
      using actual.trans lastCall

end Aurora.SourceBinding
