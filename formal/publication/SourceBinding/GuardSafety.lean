import SourceBinding.GuardSemantics
import SourceBinding.MethodSyntax
import SourceBinding.EntryBinding
namespace Aurora.SourceBinding

deriving instance DecidableEq for GuardExpr

/-- Runtime type/range readiness of one declared scalar value. -/
def ScalarReady : GuardType → Value → Prop
  | .word, .word n => n < wordLimit
  | .boolean, .boolean _ => True
  | _, _ => False

def ReadReady (kind : GuardType) (value : Option Value) : Prop :=
  ∃ scalar, value = some scalar ∧ ScalarReady kind scalar

/-- Only leaf values are assumed ready. This relation contains no evaluation
    result for compound expressions and no assumed subtraction bound. -/
def LeavesReady (state : SourceState) : {kind : GuardType} → GuardExpr kind → Prop
  | _, .wordLit _ | _, .boolLit _ => True
  | _, .parameter kind _ index => ReadReady kind (state.parameters index)
  | _, .field kind _ ordinal => ReadReady kind (state.fields ordinal)
  | _, .not expression | _, .shift12 expression => LeavesReady state expression
  | _, .sub left right | _, .bitAnd left right | _, .bitOr left right | _, .compare _ left right => LeavesReady state left ∧ LeavesReady state right
  | _, .and left right | _, .or left right => LeavesReady state left ∧ LeavesReady state right

/-- Independent total scalar fragment. Subtraction intentionally has no rule. -/
inductive SimpleGuard : {kind : GuardType} → GuardExpr kind → Prop
  | word : n < wordLimit → SimpleGuard (.wordLit n)
  | boolean : SimpleGuard (.boolLit b)
  | parameter : SimpleGuard (.parameter kind name index)
  | field : SimpleGuard (.field kind name ordinal)
  | not : SimpleGuard child → SimpleGuard (.not child)
  | compare : SimpleGuard left → SimpleGuard right → SimpleGuard (.compare operation left right)
  | and : SimpleGuard left → SimpleGuard right → SimpleGuard (.and left right)
  | or : SimpleGuard left → SimpleGuard right → SimpleGuard (.or left right)

structure CheckedSimple {kind : GuardType} (expression : GuardExpr kind) : Type where
  simple : SimpleGuard expression

def checkSimple : {kind : GuardType} → (expression : GuardExpr kind) → Option (CheckedSimple expression)
  | _, .wordLit n => if bound : n < wordLimit then some ⟨.word bound⟩ else none
  | _, .boolLit _ => some ⟨.boolean⟩
  | _, .parameter _ _ _ => some ⟨.parameter⟩
  | _, .field _ _ _ => some ⟨.field⟩
  | _, .not child => do return ⟨.not (← checkSimple child).simple⟩
  | _, .compare _ left right => do return ⟨.compare (← checkSimple left).simple (← checkSimple right).simple⟩
  | _, .and left right => do return ⟨.and (← checkSimple left).simple (← checkSimple right).simple⟩
  | _, .or left right => do return ⟨.or (← checkSimple left).simple (← checkSimple right).simple⟩
  | _, .sub _ _ | _, .bitAnd _ _ | _, .bitOr _ _ | _, .shift12 _ => none

theorem read_ready (kind : GuardType) (value : Value) (ready : ScalarReady kind value) :
    readScalar kind (some value) = .value value := by
  cases kind <;> cases value <;> simp_all [ScalarReady,readScalar]

theorem simple_total {kind : GuardType} {expression : GuardExpr kind}
    (simple : SimpleGuard expression) (state : SourceState) (ready : LeavesReady state expression) :
    ∃ value, ScalarReady kind value ∧ evalGuard state expression = .value value := by
  induction simple with
  | word bound => exact ⟨.word _,bound,by simp [evalGuard,readScalar,bound]⟩
  | boolean => exact ⟨.boolean _,True.intro,rfl⟩
  | parameter =>
    obtain ⟨value,eq,bound⟩ := ready
    exact ⟨value,bound,by simp [evalGuard,eq,read_ready _ _ bound]⟩
  | field =>
    obtain ⟨value,eq,bound⟩ := ready
    exact ⟨value,bound,by simp [evalGuard,eq,read_ready _ _ bound]⟩
  | not child ih =>
    obtain ⟨value,bound,eq⟩ := ih ready
    cases value with
    | word _ | signedCount12 => contradiction
    | boolean b => exact ⟨.boolean (!b),True.intro,by simp [evalGuard,eq,Outcome.then,notValue]⟩
  | @compare leftExpr rightExpr op left right leftIH rightIH =>
    obtain ⟨a,ha,ea⟩ := leftIH ready.1
    obtain ⟨b,hb,eb⟩ := rightIH ready.2
    cases a with
    | boolean _ | signedCount12 => contradiction
    | word a =>
      cases b with
      | boolean _ | signedCount12 => contradiction
      | word b => exact ⟨.boolean (compareWords op a b),True.intro,by simp only [ScalarReady] at ha hb; simp [evalGuard,ea,eb,Outcome.then,binaryValue,ha,hb]⟩
  | and left right leftIH rightIH =>
    obtain ⟨a,ha,ea⟩ := leftIH ready.1
    obtain ⟨b,hb,eb⟩ := rightIH ready.2
    cases a with
    | word _ | signedCount12 => contradiction
    | boolean a =>
      cases b with
      | word _ | signedCount12 => contradiction
      | boolean b => exact ⟨.boolean (a && b),True.intro,by cases a <;> simp [evalGuard,ea,eb,Outcome.then]⟩
  | or left right leftIH rightIH =>
    obtain ⟨a,ha,ea⟩ := leftIH ready.1
    obtain ⟨b,hb,eb⟩ := rightIH ready.2
    cases a with
    | word _ | signedCount12 => contradiction
    | boolean a =>
      cases b with
      | word _ | signedCount12 => contradiction
      | boolean b => exact ⟨.boolean (a || b),True.intro,by cases a <;> simp [evalGuard,ea,eb,Outcome.then]⟩

/-- A generic checked range-guard idiom. Operands are actual typed expressions;
    no source names, ordinals, constants or method identity are hard-coded. -/
inductive RangeGuard : GuardExpr .boolean → Prop
  | range : SimpleGuard prior → SimpleGuard offset → SimpleGuard bytes → SimpleGuard count →
      RangeGuard (.or (.or prior (.compare .gt offset bytes))
        (.compare .gt count (.sub bytes offset)))

structure CheckedRange (expression : GuardExpr .boolean) : Type where
  range : RangeGuard expression

def checkRange (expression : GuardExpr .boolean) : Option (CheckedRange expression) := do
  match expression with
  | .or (.or prior (.compare .gt offset bytes)) (.compare .gt count (.sub againBytes againOffset)) =>
    if bytesEq : againBytes = bytes then
      if offsetEq : againOffset = offset then
        let p ← checkSimple prior
        let o ← checkSimple offset
        let b ← checkSimple bytes
        let c ← checkSimple count
        have range : RangeGuard (.or (.or prior (.compare .gt offset bytes))
            (.compare .gt count (.sub againBytes againOffset))) := by
          rw [bytesEq,offsetEq]
          exact .range p.simple o.simple b.simple c.simple
        return ⟨range⟩
      else none
    else none
  | _ => none

theorem simple_word {expression : GuardExpr .word} (simple : SimpleGuard expression)
    (state : SourceState) (ready : LeavesReady state expression) :
    ∃ n, n < wordLimit ∧ evalGuard state expression = .value (.word n) := by
  obtain ⟨value,bound,eq⟩ := simple_total simple state ready
  cases value with
  | boolean _ | signedCount12 => contradiction
  | word n => exact ⟨n,bound,eq⟩

theorem simple_boolean {expression : GuardExpr .boolean} (simple : SimpleGuard expression)
    (state : SourceState) (ready : LeavesReady state expression) :
    ∃ b, evalGuard state expression = .value (.boolean b) := by
  obtain ⟨value,bound,eq⟩ := simple_total simple state ready
  cases value with
  | word _ | signedCount12 => contradiction
  | boolean b => exact ⟨b,eq⟩

/-- The ordinary subtraction is used only in the final branch. Its safety is
    DERIVED from the preceding false offset>bytes test, not assumed initially. -/
theorem range_evaluation (state : SourceState) (prior : GuardExpr .boolean)
    (offset bytes count : GuardExpr .word) (p : Bool) (o b c : Nat)
    (ep : evalGuard state prior = .value (.boolean p))
    (eo : evalGuard state offset = .value (.word o))
    (eb : evalGuard state bytes = .value (.word b))
    (ec : evalGuard state count = .value (.word c))
    (ho : o < wordLimit) (hb : b < wordLimit) (hc : c < wordLimit) :
    evalGuard state (.or (.or prior (.compare .gt offset bytes))
      (.compare .gt count (.sub bytes offset))) =
      .value (.boolean (p || (o > b) || (c > b - o))) := by
  cases p with
  | true => simp [evalGuard,ep,Outcome.then]
  | false =>
    by_cases outside : b < o
    · simp [evalGuard,ep,eo,eb,Outcome.then,binaryValue,ho,hb,compareWords,outside]
    · have safe : o ≤ b := by omega
      have remaining : b - o < wordLimit := by omega
      simp [evalGuard,ep,eo,eb,ec,Outcome.then,binaryValue,ho,hb,hc,compareWords,outside,safe,remaining]

/-- Universal trap-freedom for this checked guard idiom under bounded leaf
    values, including initial states with offset>bytes (which short-circuit). -/
theorem RangeGuard.total {expression : GuardExpr .boolean} (range : RangeGuard expression)
    (state : SourceState) (ready : LeavesReady state expression) :
    ∃ result, evalGuard state expression = .value (.boolean result) := by
  cases range with
  | @range prior offset bytes count hp ho hb hc =>
    obtain ⟨p,ep⟩ := simple_boolean hp state ready.1.1
    obtain ⟨o,ob,eo⟩ := simple_word ho state ready.1.2.1
    obtain ⟨b,bb,eb⟩ := simple_word hb state ready.1.2.2
    obtain ⟨c,cb,ec⟩ := simple_word hc state ready.2.1
    exact ⟨_,range_evaluation state prior offset bytes count p o b c ep eo eb ec ob bb cb⟩

theorem range_admission_bounds (state : SourceState) (prior : GuardExpr .boolean)
    (offset bytes count : GuardExpr .word) (p : Bool) (o b c : Nat)
    (ep : evalGuard state prior = .value (.boolean p))
    (eo : evalGuard state offset = .value (.word o))
    (eb : evalGuard state bytes = .value (.word b))
    (ec : evalGuard state count = .value (.word c))
    (ho : o < wordLimit) (hb : b < wordLimit) (hc : c < wordLimit)
    (admitted : evalGuard state (.or (.or prior (.compare .gt offset bytes))
      (.compare .gt count (.sub bytes offset))) = .value (.boolean false)) :
    o ≤ b ∧ c ≤ b - o := by
  rw [range_evaluation state prior offset bytes count p o b c ep eo eb ec ho hb hc] at admitted
  have equality := Value.boolean.inj (Outcome.value.inj admitted)
  have parts := Bool.or_eq_false_iff.mp equality
  have earlier := Bool.or_eq_false_iff.mp parts.1
  exact ⟨Nat.le_of_not_gt (of_decide_eq_false earlier.2),
    Nat.le_of_not_gt (of_decide_eq_false parts.2)⟩

/-- Finite declaration readiness. Resource/other fields are unconstrained here;
    only source declarations resolving to admitted scalar kinds need values. -/
def DeclarationsReady (decls : List Formal) (values : Nat → Option Value) : Prop :=
  ∀ index decl kind, decls[index]? = some decl → decl.type = guardSourceType kind →
    ReadReady kind (values index)

theorem typed_guard_leaves {fieldDecls formalDecls : List Formal} {source : SourceExpr}
    {kind : GuardType} {expression : GuardExpr kind}
    (typing : TypedGuard fieldDecls formalDecls source expression) (state : SourceState)
    (fields : DeclarationsReady fieldDecls state.fields)
    (parameters : DeclarationsReady formalDecls state.parameters) : LeavesReady state expression := by
  induction typing with
  | word _ => trivial
  | boolean => trivial
  | parameter declaration _ type => exact parameters _ _ _ declaration type
  | field declaration _ type => exact fields _ _ _ declaration type
  | not _ ih | shift12 _ ih => exact ih
  | subtract _ _ left right | bitAnd _ _ left right | bitOr _ _ left right => exact ⟨left,right⟩
  | compare _ _ left right => exact ⟨left,right⟩
  | and _ _ left right => exact ⟨left,right⟩
  | or _ _ left right => exact ⟨left,right⟩

theorem guardSourceType_injective : Function.Injective guardSourceType := by
  intro a b same
  cases a <;> cases b <;> first | rfl | (cases same)

theorem scalar_ready_of_read {kind : GuardType} {value : Value}
    (typed : readScalar kind (some value) = .value value) : ScalarReady kind value := by
  cases kind <;> cases value <;> simp_all [readScalar,ScalarReady]

/-- The same checked entry signature derives formal readiness from argument
    typing; callers need not assume a second, unrelated parameter valuation. -/
theorem EntryCode.arguments_ready {program : Program} {formals : List Formal}
    {bindings : List ParameterBinding} (entry : EntryCode program formals bindings)
    (base : Machine) (arguments : EntryArguments bindings base.arguments) :
    DeclarationsReady formals (entrySource base bindings.length).parameters := by
  intro index decl kind declaration type
  have formalBound := (List.getElem?_eq_some_iff.mp declaration).1
  have bound : index < bindings.length := by rw [entry.1]; exact formalBound
  have declaredType := (entry.2.2 index bound).2.1
  rw [declaration] at declaredType
  have identity : parameterKind bindings index = kind :=
    guardSourceType_injective ((Option.some.inj declaredType).symm.trans type)
  obtain ⟨value,valueEq,typed⟩ := arguments index bound
  refine ⟨value,?_,?_⟩
  · simp [entrySource,bound,valueEq]
  · rw [identity] at typed
    exact scalar_ready_of_read typed

theorem check_range_sound (expression : GuardExpr .boolean) (result : CheckedRange expression)
    (_accepted : checkRange expression = some result) : RangeGuard expression := result.range

end Aurora.SourceBinding
