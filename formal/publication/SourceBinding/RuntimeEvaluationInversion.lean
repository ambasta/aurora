import SourceBinding.RuntimeEvaluation
import SourceBinding.RuntimeExpressionNames
namespace Aurora.SourceBinding

/-- Invert any derivation of a known lexical variable. Missing/malformed runtime
    values remain the exact readBound outcome; readiness is not assumed. -/
theorem RuntimeEvaluation.variable_result
    (valid : RuntimeContextValid context)
    (known : RuntimeVariableBinding context name binding)
    (evaluated : RuntimeEvaluation functions context state (.name [name]) kind outcome events) :
    kind = binding.kind ∧ outcome = state.readBound binding ∧ events = [] := by
  cases evaluated with
  | readVariable actual =>
    have same := actual.unique valid known
    subst binding
    exact ⟨rfl,rfl,rfl⟩
  | enumValue impossible => exact False.elim impossible.not_singleton

/-- Nominal constants retain their exact source-selected identity and ordinal. -/
theorem RuntimeEvaluation.enum_result
    (valid : RuntimeContextValid context)
    (known : RuntimeEnumValue context name identity ordinal)
    (evaluated : RuntimeEvaluation functions context state (.name name) kind outcome events) :
    kind = .nominal identity ∧
    outcome = readRuntime (.nominal identity) (some (.nominal identity.name ordinal)) ∧ events = [] := by
  cases evaluated with
  | readVariable _ => exact False.elim known.not_singleton
  | enumValue actual =>
    obtain ⟨sameIdentity,sameOrdinal⟩ := actual.unique valid known
    subst identity; subst ordinal
    exact ⟨rfl,rfl,rfl⟩

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
          outcome = .trap fault ∧ events = argumentEvents ++ [.invoke callee.key values] ++ bodyEvents)) := by
  cases evaluated with
  | callArgumentsFault member resolves args => exact ⟨_,member,resolves,rfl,Or.inl ⟨_,rfl,args⟩⟩
  | callValue member resolves args body =>
    exact ⟨_,member,resolves,rfl,Or.inr (Or.inl ⟨_,_,_,_,_,_,args,body,rfl,rfl⟩)⟩
  | callFault member resolves args body =>
    exact ⟨_,member,resolves,rfl,Or.inr (Or.inr ⟨_,_,_,_,_,_,args,body,rfl,rfl⟩)⟩

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
      ScopedStatements members module path formals middle rest after items ∧ outcome = .trapped fault finished) := by
  cases evaluated with
  | next first tail => exact Or.inl ⟨_,_,_,_,first,tail,rfl⟩
  | returned first tail => exact Or.inr (Or.inl ⟨_,_,_,_,first,tail,rfl⟩)
  | trapped first tail => exact Or.inr (Or.inr ⟨_,_,_,_,first,tail,rfl⟩)

end Aurora.SourceBinding
