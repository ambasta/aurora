import SourceBinding.EffectExpressions
namespace Aurora.SourceBinding

/-- Successful pure evaluation already supplies a correctly represented scalar.
    This derives call-entry readiness, rather than asking callers to assume it. -/
def TypedOutcome (kind : GuardType) : Outcome Value → Prop
  | .value value => readScalar kind (some value) = .value value
  | .trap _ => True

theorem read_typed (kind : GuardType) (input : Option Value) :
    TypedOutcome kind (readScalar kind input) := by
  cases input with
  | none => trivial
  | some value =>
    cases value with
    | boolean b => cases kind <;> simp [TypedOutcome,readScalar]
    | word n =>
      cases kind with
      | boolean => simp [TypedOutcome,readScalar]
      | word =>
        by_cases bound : n < wordLimit
        · simp [readScalar,bound,TypedOutcome]
        · simp [readScalar,bound,TypedOutcome]

theorem not_typed (value : Value) : TypedOutcome .boolean (notValue value) := by
  cases value <;> simp [TypedOutcome,notValue,readScalar]

def Binary.resultKind : Binary → GuardType
  | .sub => .word
  | .compare _ => .boolean

theorem binary_typed (operation : Binary) (left right : Value) :
    TypedOutcome operation.resultKind (binaryValue operation left right) := by
  cases left with
  | boolean _ => cases right <;> trivial
  | word a =>
    cases right with
    | boolean _ => trivial
    | word b =>
      simp only [binaryValue]
      split
      next bounds =>
        cases operation with
        | compare op => simp [TypedOutcome,Binary.resultKind,readScalar]
        | sub =>
          simp only [Binary.resultKind]
          split
          next order =>
            have bound : a - b < wordLimit := Nat.lt_of_le_of_lt (Nat.sub_le a b) bounds.1
            simp only [TypedOutcome,readScalar,if_pos bound,if_true]
          next => trivial
      next => trivial

theorem then_typed (result : Outcome Value) (next : Value → Outcome Value)
    (rest : ∀ value, TypedOutcome kind (next value)) :
    TypedOutcome kind (result.then next) := by
  cases result with
  | trap _ => trivial
  | value value => exact rest value

theorem eval_typed (state : SourceState) (expression : GuardExpr kind) :
    TypedOutcome kind (evalGuard state expression) := by
  induction expression with
  | wordLit _ | parameter _ _ _ | field _ _ _ => exact read_typed _ _
  | boolLit _ => simp [evalGuard,TypedOutcome,readScalar]
  | not child ih => exact then_typed _ _ not_typed
  | sub left right leftIH rightIH =>
    exact then_typed _ _ (fun a => then_typed _ _ (fun b => binary_typed .sub a b))
  | compare op left right leftIH rightIH =>
    exact then_typed _ _ (fun a => then_typed _ _ (fun b => binary_typed (.compare op) a b))
  | and left right leftIH rightIH =>
    apply then_typed
    intro value
    cases value with
    | word _ => trivial
    | boolean b => cases b <;> first | exact rightIH | simp [TypedOutcome,readScalar]
  | or left right leftIH rightIH =>
    apply then_typed
    intro value
    cases value with
    | word _ => trivial
    | boolean b => cases b <;> first | exact rightIH | simp [TypedOutcome,readScalar]

theorem eval_value_typed (state : SourceState) (expression : GuardExpr kind)
    (value : Value) (evaluated : evalGuard state expression = .value value) :
    readScalar kind (some value) = .value value := by
  have typed := eval_typed state expression
  rw [evaluated] at typed
  exact typed

end Aurora.SourceBinding
