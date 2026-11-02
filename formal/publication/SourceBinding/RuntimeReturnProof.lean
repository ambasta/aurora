import SourceBinding.RuntimeEntry
import SourceBinding.EffectRuns
namespace Aurora.SourceBinding

/-- The expression's successful value is returned; faults retain the actual
    terminal frame. Neither branch changes locals, receiver or arguments. -/
def RuntimeTerminal (base : Machine) (outcome : Outcome Value) (result : EffectExecution) : Prop :=
  (match outcome,result with
    | .value value,.returned actual _ => actual = value
    | .trap fault,.trap (.scalar actual) _ => actual = fault
    | _,_ => False) ∧
  result.state.locals = base.locals ∧ result.state.receiver = base.receiver ∧
  result.state.arguments = base.arguments

theorem RuntimeRun.returned
    (run : RuntimeRun program base start stop accumulator stack outcome)
    (code : program stop = some (.pure .ret)) :
    ∃ result, EffectRuns program (frameState base start accumulator stack) [] result ∧
      RuntimeTerminal base outcome result := by
  cases outcome with
  | value value =>
    refine ⟨.returned value (frameState base stop (some value) stack),?_,rfl,rfl,rfl,rfl⟩
    apply run.trans
    apply EffectRuns.returned
    simp only [effectStep,frameState,code,pureView,step,retainState]
  | trap fault =>
    obtain ⟨final,actual,locals,receiver,arguments⟩ := run
    exact ⟨.trap (.scalar fault) final,actual,rfl,locals,receiver,arguments⟩

theorem RuntimeTerminal.terminal (related : RuntimeTerminal base outcome result) :
    ∀ state, result ≠ .next state := by
  intro state same
  subst result
  cases outcome <;> exact False.elim related.1

/-- Complete fresh-entry/expression/return execution, not a pre-assumed body
    success. The enclosing source-bound checker supplies the SAME signature and
    whole-body shape. Numeric overflow remains an explicit result. -/
theorem runtime_entry_expression_returned
    (valid : RuntimeContextValid context)
    (signature : RuntimeSignature t context.members context.module context.path first
      (context.formals.map (·.type)) kinds)
    (emptyVisible : context.visible = [])
    (entry : RuntimeEntryCode program kinds)
    (expression : RuntimeExpressionCode program context raw kind kinds.length stop)
    (returnCode : program stop = some (.pure .ret))
    (base : Machine) (arguments : RuntimeEntryArguments kinds base.arguments) :
    ∃ outcome result,
      RuntimeEvaluates context (formalRuntimeLocals kinds base) raw kind outcome ∧
      EffectRuns program (preparedEntry base runtimeParameterSlot 0) [] result ∧
      RuntimeTerminal (preparedEntry base runtimeParameterSlot kinds.length) outcome result := by
  have bound := runtime_formal_bindings (base := base) valid signature emptyVisible
  obtain ⟨outcome,evaluated,run⟩ := expression.evaluates_and_runs (formalRuntimeLocals kinds base)
    (preparedEntry base runtimeParameterSlot kinds.length) bound (fun _ => rfl)
  obtain ⟨result,actual,related⟩ := (run none []).returned returnCode
  have prepared := runtime_entry_runs entry base arguments
  rw [prepared_frame] at actual
  exact ⟨outcome,result,evaluated,prepared.trans actual,related⟩

end Aurora.SourceBinding
