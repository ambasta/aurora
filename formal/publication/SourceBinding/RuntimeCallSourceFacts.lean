import SourceBinding.RuntimeEvaluationFacts
namespace Aurora.SourceBinding

/-- Adding source functions does not alter any already witnessed evaluation.
    In particular the old empty-environment fragment embeds with its entire
    outcome (including faults) and exactly the same empty trace. -/
theorem RuntimeEvaluation.weaken
    (evaluated : RuntimeEvaluation functions context state raw kind outcome events)
    (included : ∀ leaf, leaf ∈ functions → leaf ∈ larger) :
    RuntimeEvaluation larger context state raw kind outcome events := by
  apply PureRuntimeEvaluation.induct evaluated
  exact { pureRuntimeAlgebra larger with
    expression_callArgumentsFault := by
      intro leaf context name state sources fault events member resolves args
      exact .callArgumentsFault (included leaf member) resolves args
    expression_callValue := by
      intro leaf context name state sources values argumentEvents after value finished bodyEvents member resolves args body
      exact .callValue (included leaf member) resolves args body
    expression_callFault := by
      intro leaf context name state sources values argumentEvents after fault finished bodyEvents member resolves args body
      exact .callFault (included leaf member) resolves args body
  }

theorem RuntimeEvaluatesWith.weaken
    (evaluated : RuntimeEvaluatesWith functions context state raw kind outcome events)
    (included : ∀ leaf, leaf ∈ functions → leaf ∈ larger) :
    RuntimeEvaluatesWith larger context state raw kind outcome events := by
  apply RuntimeEvaluation.weaken evaluated
  intro source member
  obtain ⟨leaf,present,equal⟩ := List.mem_map.mp member
  exact List.mem_map.mpr ⟨leaf,included leaf present,equal⟩

theorem RuntimeEvaluation.in_environment
    (evaluated : RuntimeEvaluation [] context state raw kind outcome events) (functions : List RuntimeSourceFunction) :
    RuntimeEvaluation functions context state raw kind outcome events :=
  evaluated.weaken (fun _ impossible => False.elim (List.not_mem_nil impossible))

theorem RuntimeEvaluates.in_environment
    (evaluated : RuntimeEvaluates context state raw kind outcome) (functions : List RuntimeSourceLeaf) :
    RuntimeEvaluatesWith functions context state raw kind outcome [] :=
  evaluated.weaken (fun _ impossible => False.elim (List.not_mem_nil impossible))

inductive RuntimeReadyArguments : List RuntimeType → List Value → Prop
  | nil : RuntimeReadyArguments [] []
  | cons : readRuntime kind (some value) = .value value → RuntimeReadyArguments kinds values →
      RuntimeReadyArguments (kind :: kinds) (value :: values)

theorem RuntimeReadyArguments.length (ready : RuntimeReadyArguments kinds values) : kinds.length = values.length := by
  induction ready with
  | nil => rfl
  | cons _ _ ih => exact congrArg Nat.succ ih

theorem RuntimeReadyArguments.lookup {index : Nat} (ready : RuntimeReadyArguments kinds values)
    (found : kinds[index]? = some kind) :
    ∃ value, values[index]? = some value ∧ readRuntime kind (some value) = .value value := by
  induction ready generalizing index with
  | nil => simp at found
  | cons typed rest ih =>
    cases index with
    | zero => simp only [List.getElem?_cons_zero,Option.some.injEq] at found; subst kind; exact ⟨_,rfl,typed⟩
    | succ index => exact ih found

def RuntimeArgumentsOutcomeTyped (kinds : List RuntimeType) : Outcome (List Value) → Prop
  | .trap _ => True
  | .value values => RuntimeReadyArguments kinds values

/-- Argument readiness is a consequence of actual ordered source evaluation,
    not a successful-callee or entry-readiness assumption. -/
theorem RuntimeArgumentEvaluation.outcome_typed
    (evaluated : RuntimeArgumentEvaluation functions context state raws kinds outcome events) :
    RuntimeArgumentsOutcomeTyped kinds outcome := by
  have checked := (evaluated PUnit PUnit (fun _ _ _ => False)
    (⟨fun _ => none, PUnit.unit⟩ : SourceShared PUnit)).checked
  cases outcome with
  | trap fault => trivial
  | value values =>
    change checkSourceArguments kinds values = .value () at checked
    change RuntimeReadyArguments kinds values
    clear evaluated
    induction kinds generalizing values with
    | nil => cases values with
      | nil => exact .nil
      | cons value rest => cases checked
    | cons kind kinds ih => cases values with
      | nil => cases checked
      | cons value rest =>
        cases read : readRuntime kind (some value) with
        | trap fault => simp only [checkSourceArguments, read] at checked; cases checked
        | value actual =>
          have same := readRuntime_preserves kind (some value) actual read
          cases Option.some.inj same
          exact .cons read (ih rest (by simpa only [checkSourceArguments, read] using checked))

theorem RuntimeArgumentsEvaluateWith.outcome_typed
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds outcome events) :
    RuntimeArgumentsOutcomeTyped kinds outcome := RuntimeArgumentEvaluation.outcome_typed evaluated

theorem RuntimeArgumentsEvaluateWith.ready
    (evaluated : RuntimeArgumentsEvaluateWith functions context state raws kinds (.value values) events) :
    RuntimeReadyArguments kinds values := evaluated.outcome_typed

end Aurora.SourceBinding
