import SourceBinding.RuntimePureInversion
import SourceBinding.RuntimeExpressionNames
namespace Aurora.SourceBinding

private theorem effect_variable_result
    (valid : RuntimeContextValid context) (known : RuntimeVariableBinding context name binding)
    (evaluated : EffectEvaluation functions response (.pure context) state (.name [name]) kind outcome shared events) :
    kind = binding.kind ∧ outcome = sourceLift (state.locals.readBound binding) ∧ events = [] := by
  cases evaluated with
  | readVariable actual =>
    have same := actual.unique valid known
    subst binding
    exact ⟨rfl,rfl,rfl⟩
  | readField actual => cases actual.enabled
  | enumValue actual =>
    exact False.elim (((EffectEnumValue.pure_iff _).mp actual).not_singleton)

private theorem effect_enum_result
    (valid : RuntimeContextValid context) (known : RuntimeEnumValue context name identity ordinal)
    (evaluated : EffectEvaluation functions response (.pure context) state (.name name) kind outcome shared events) :
    kind = .nominal identity ∧
    outcome = sourceLift (readRuntime (.nominal identity) (some (.nominal identity.name ordinal))) ∧ events = [] := by
  cases evaluated with
  | readVariable _ => exact False.elim known.not_singleton
  | readField actual => cases actual.enabled
  | enumValue actual =>
    obtain ⟨sameIdentity,sameOrdinal⟩ := ((EffectEnumValue.pure_iff _).mp actual).unique valid known
    subst identity; subst ordinal
    exact ⟨rfl,rfl,rfl⟩

/-- Invert any derivation of a known lexical variable. Missing/malformed runtime
    values remain the exact readBound outcome; readiness is not assumed. -/
theorem RuntimeEvaluation.variable_result
    (valid : RuntimeContextValid context)
    (known : RuntimeVariableBinding context name binding)
    (evaluated : RuntimeEvaluation functions context state (.name [name]) kind outcome events) :
    kind = binding.kind ∧ outcome = state.readBound binding ∧ events = [] := by
  have facts := effect_variable_result valid known
    (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩)
  exact ⟨facts.1,sourceLift_injective facts.2.1,
    RuntimeSourceEvent.map_toEffect_injective facts.2.2⟩

/-- Nominal constants retain their exact source-selected identity and ordinal. -/
theorem RuntimeEvaluation.enum_result
    (valid : RuntimeContextValid context)
    (known : RuntimeEnumValue context name identity ordinal)
    (evaluated : RuntimeEvaluation functions context state (.name name) kind outcome events) :
    kind = .nominal identity ∧
    outcome = readRuntime (.nominal identity) (some (.nominal identity.name ordinal)) ∧ events = [] := by
  have facts := effect_enum_result valid known
    (evaluated PUnit PUnit (fun _ _ _ => False) ⟨fun _ => none,PUnit.unit⟩)
  exact ⟨facts.1,sourceLift_injective facts.2.1,
    RuntimeSourceEvent.map_toEffect_injective facts.2.2⟩

/-- A named call either fails while evaluating arguments, or executes the actual
    chosen source body. Its existential lexical endpoint and current state are
    retained, not replaced with a separately checked body's endpoint. -/
theorem RuntimeEvaluation.call_cases
    (evaluated : RuntimeEvaluation functions context state (.call (.named name) arguments) kind outcome events) :
    ∃ callee ∈ functions, callee.Resolves context name ∧ kind = callee.result ∧
      ((∃ fault, outcome = .trap fault ∧
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.trap fault) events) ∨
       (∃ values argumentEvents after finished bodyEvents value,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.returned value finished) bodyEvents ∧
          outcome = .value value ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents ++ [.returned callee.key value]) ∨
       (∃ values argumentEvents after finished bodyEvents fault,
          RuntimeArgumentEvaluation functions context state arguments callee.parameters (.value values) argumentEvents ∧
          RuntimeStatementsEvaluation functions callee.context.members callee.context.module callee.context.path
            callee.context.formals callee.result ⟨[],0,1,callee.context.formals.length⟩
            (formalSourceLocals callee.parameters (fun index => values[index]?))
            callee.parsed.statements after (.trapped fault finished) bodyEvents ∧
          outcome = .trap fault ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents)) := PureRuntimeEvaluation.call_cases evaluated

/-- Cons inversion preserves first-fault/early-return behavior. The skipped tail
    has only its original scoped syntax witness, never an evaluation witness. -/
theorem RuntimeStatementsEvaluation.cons_cases
    (evaluated : RuntimeStatementsEvaluation functions members module path formals result
      before state (first :: rest) after outcome events) :
    (∃ middle next firstEvents restEvents,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.continued next) firstEvents ∧
      RuntimeStatementsEvaluation functions members module path formals result middle next rest after outcome restEvents ∧
      events = firstEvents ++ restEvents) ∨
    (∃ middle value finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.returned value finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .returned value finished) ∨
    (∃ middle fault finished items,
      RuntimeStatementEvaluation functions members module path formals result before state first middle (.trapped fault finished) events ∧
      ScopedStatements members module path formals middle rest after items ∧ outcome = .trapped fault finished) := PureRuntimeStatementsEvaluation.cons_cases evaluated

end Aurora.SourceBinding
