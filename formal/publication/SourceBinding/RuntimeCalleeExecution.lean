import SourceBinding.RuntimeCallable
import SourceBinding.RuntimeBodyExecution
import SourceBinding.RuntimeCallTrace
namespace Aurora.SourceBinding

/-- An INTERNAL constructive induction hypothesis for one checked callable.
    A source outcome and both traces are chosen before every receiver/world,
    external relation and saved caller frame. The run executes actual fresh
    entry and body; returned outcomes retain a checked pending ret, which the
    caller bridge must execute. Public DAG theorems derive this from the actual
    lower-rank node certificate; users never supply an outcome summary. -/
def RuntimeCalleeExecutes (program : CallProgram)
    (nodes : List (RuntimeCallable t files root module path))
    (callable : RuntimeCallable t files root module path)
    (World ExternalFault : Type) : Prop :=
  ∀ values, RuntimeReadyArguments callable.source.parameters values →
  ∃ outcome sourceEvents machineEvents,
    RuntimeStatementsEvaluation (nodes.map (·.source))
      callable.source.context.members callable.source.context.module callable.source.context.path
      callable.source.context.formals callable.source.result
      ⟨[],0,1,callable.source.context.formals.length⟩
      (formalSourceLocals callable.source.parameters (fun index => values[index]?))
      callable.source.parsed.statements callable.identified.details.lexical.lexical.after outcome sourceEvents ∧
    RuntimeCallTraceRelated nodes sourceEvents machineEvents ∧
    (∀ state, outcome ≠ .continued state) ∧
    ∀ (shared : CallShared World) (saved : List SavedCall) (external : ExternalRelation World ExternalFault),
    ∃ final, CallRuns program external
      (.running (activeAt callable.target.id saved shared.world ((freshCallFrame values).inject shared)))
      machineEvents final ∧
    RuntimeBodyResult program callable.target.id saved shared.world ((freshCallFrame values).inject shared)
      (Publication.functionCode t callable.target.id).size outcome final

end Aurora.SourceBinding
