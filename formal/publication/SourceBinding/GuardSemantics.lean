import SourceBinding.GuardExpr
namespace Aurora.SourceBinding

/-- Mathematical values, not native registers; words are checked against this bound. -/
def wordLimit : Nat := 18446744073709551616

inductive Value where
  | word (value : Nat) | boolean (value : Bool) | signedCount12
  deriving BEq, DecidableEq, Repr

inductive Fault where
  | type | range | underflow | overflow | unsupported
  deriving BEq, DecidableEq, Repr

inductive Outcome (α : Type) where
  | value (result : α) | trap (fault : Fault)
  deriving BEq, DecidableEq, Repr

def Outcome.then (result : Outcome α) (next : α → Outcome β) : Outcome β :=
  match result with | .value val => next val | .trap fault => .trap fault

def readScalar (kind : GuardType) : Option Value → Outcome Value
  | some (.word value) =>
    if kind = .word then if value < wordLimit then .value (.word value) else .trap .range else .trap .type
  | some (.boolean value) => if kind = .boolean then .value (.boolean value) else .trap .type
  | _ => .trap .type

inductive Binary where
  | sub | bitAnd | bitOr | shift12 | compare (operation : CompareOp)
  deriving BEq, DecidableEq, Repr

def compareWords (operation : CompareOp) (left right : Nat) : Bool :=
  match operation with
  | .eq => left == right | .ne => left != right | .lt => left < right
  | .le => left ≤ right | .gt => left > right | .ge => left ≥ right

/-- Independent mathematical scalar operations; subtraction never wraps or truncates below zero. -/
def binaryValue (operation : Binary) (left right : Value) : Outcome Value :=
  match left, right with
  | .word a, .signedCount12 =>
    if operation = .shift12 then
      if a < wordLimit then
        if a * 4096 < wordLimit then .value (.word (a * 4096)) else .trap .overflow
      else .trap .range
    else .trap .type
  | .word a, .word b =>
    if a < wordLimit ∧ b < wordLimit then
      match operation with
      | .sub => if b ≤ a then .value (.word (a - b)) else .trap .underflow
      | .bitAnd => .value (.word (a &&& b))
      | .bitOr => .value (.word (a ||| b))
      | .shift12 => .trap .type
      | .compare op => .value (.boolean (compareWords op a b))
    else .trap .range
  | _, _ => .trap .type

def notValue : Value → Outcome Value
  | .boolean value => .value (.boolean (!value))
  | _ => .trap .type

structure SourceState where
  fields : Nat → Option Value
  parameters : Nat → Option Value

/-- Structural source operational semantics. This evaluator is independent of the
    IR matcher/certificate. Short-circuiting and left-to-right evaluation are explicit. -/
def evalGuard (state : SourceState) : {kind : GuardType} → GuardExpr kind → Outcome Value
  | _, .wordLit value => readScalar .word (some (.word value))
  | _, .boolLit value => .value (.boolean value)
  | _, .parameter kind _ index => readScalar kind (state.parameters index)
  | _, .field kind _ ordinal => readScalar kind (state.fields ordinal)
  | _, .not expression => (evalGuard state expression).then notValue
  | _, .sub left right => (evalGuard state left).then fun a =>
      (evalGuard state right).then fun b => binaryValue .sub a b
  | _, .bitAnd left right => (evalGuard state left).then fun a =>
      (evalGuard state right).then fun b => binaryValue .bitAnd a b
  | _, .bitOr left right => (evalGuard state left).then fun a =>
      (evalGuard state right).then fun b => binaryValue .bitOr a b
  | _, .shift12 expression => (evalGuard state expression).then fun a => binaryValue .shift12 a .signedCount12
  | _, .compare operation left right => (evalGuard state left).then fun a =>
      (evalGuard state right).then fun b => binaryValue (.compare operation) a b
  | _, .and left right => (evalGuard state left).then fun value =>
      match value with
      | .boolean false => .value (.boolean false)
      | .boolean true => evalGuard state right
      | _ => .trap .type
  | _, .or left right => (evalGuard state left).then fun value =>
      match value with
      | .boolean true => .value (.boolean true)
      | .boolean false => evalGuard state right
      | _ => .trap .type

/-- Formal IR scalar subset. Unknown/call/store forms are NOT silently no-ops. -/
inductive Op where
  | constant (kind : GuardType) (value : Value)
  | load (kind : GuardType) (slot : Nat)
  | receiver (kind : GuardType) (ordinal : Nat)
  | count12 | push | negate | binary (operation : Binary)
  | bind (kind : GuardType) (argument slot : Nat)
  | label | jump (target : Nat) | branchFalse (target : Nat) | ret
  deriving BEq, DecidableEq, Repr

abbrev Program := Nat → Option Op

structure Machine where
  pc : Nat
  accumulator : Option Value
  stack : List Value
  locals : Nat → Option Value
  receiver : Nat → Option Value
  arguments : Nat → Option Value

inductive Execution where
  | next (state : Machine) | returned (value : Value) | trap (fault : Fault)

def frameState (base : Machine) (pc : Nat) (accumulator : Option Value) (stack : List Value) : Machine :=
  { base with pc, accumulator, stack }

def finish (base : Machine) (pc : Nat) (stack : List Value) : Outcome Value → Execution
  | .value value => .next (frameState base pc (some value) stack)
  | .trap fault => .trap fault

/-- Deterministic small-step operational rules, separate from source evaluation.
    Entry parameter binding alone initializes frame slots. Prefix expression steps
    never modify receiver, arguments or locals. Unsupported forms fail explicitly. -/
def step (program : Program) (state : Machine) : Execution :=
  match program state.pc with
  | none => .trap .unsupported
  | some (.constant kind value) => finish state (state.pc + 1) state.stack (readScalar kind (some value))
  | some .count12 => .next (frameState state (state.pc + 1) (some .signedCount12) state.stack)
  | some (.load kind slot) => finish state (state.pc + 1) state.stack (readScalar kind (state.locals slot))
  | some (.receiver kind ordinal) => finish state (state.pc + 1) state.stack (readScalar kind (state.receiver ordinal))
  | some .push => match state.accumulator with
    | some value => .next (frameState state (state.pc + 1) state.accumulator (value :: state.stack))
    | _ => .trap .type
  | some .negate => match state.accumulator with
    | some value => finish state (state.pc + 1) state.stack (notValue value)
    | _ => .trap .type
  | some (.binary operation) => match state.stack, state.accumulator with
    | left :: tail, some right => finish state (state.pc + 1) tail (binaryValue operation left right)
    | _, _ => .trap .type
  | some (.bind kind argument slot) => match readScalar kind (state.arguments argument) with
    | .value value => .next { state with
        pc := state.pc + 1
        locals := fun index => if index = slot then some value else state.locals index }
    | .trap fault => .trap fault
  | some .label => .next { state with pc := state.pc + 1 }
  | some (.jump target) => .next { state with pc := target }
  | some (.branchFalse target) => match state.accumulator with
    | some (.boolean value) => .next { state with pc := if value then state.pc + 1 else target }
    | _ => .trap .type
  | some .ret => match state.accumulator with
    | some value => .returned value
    | _ => .trap .type

/-- Finite execution is not assumed for arbitrary programs (jump cycles are expressible). -/
inductive Runs (program : Program) : Machine → Execution → Prop
  | reflexive : Runs program state (.next state)
  | next : step program initial = .next middle → Runs program middle result → Runs program initial result
  | returned : step program initial = .returned value → Runs program initial (.returned value)
  | trap : step program initial = .trap fault → Runs program initial (.trap fault)

def Diverges (program : Program) (initial : Machine) : Prop :=
  ∃ states : Nat → Machine, states 0 = initial ∧ ∀ n, step program (states n) = .next (states (n + 1))

theorem Runs.single {program : Program} {state : Machine} : Runs program state (step program state) := by
  cases eq : step program state with
  | next middle => exact .next eq .reflexive
  | returned value => exact .returned eq
  | trap fault => exact .trap eq

theorem Runs.trans {program : Program} {initial middle : Machine} {result : Execution}
    (priorRun : Runs program initial (.next middle)) (tail : Runs program middle result) :
    Runs program initial result := by
  generalize ending : Execution.next middle = last at priorRun
  induction priorRun generalizing middle with
  | reflexive => cases ending; exact tail
  | next first _ ih => exact .next first (ih tail ending)
  | returned _ => cases ending
  | trap _ => cases ending

/-- No assumed offset precondition: generic checked subtraction traps on underflow. -/
theorem subtraction_underflow (a b : Nat) (aBound : a < wordLimit) (bBound : b < wordLimit) (under : a < b) :
    binaryValue .sub (.word a) (.word b) = .trap .underflow := by
  simp [binaryValue, aBound, bBound, Nat.not_le.mpr under]

theorem subtraction_safe (a b : Nat) (aBound : a < wordLimit) (bBound : b < wordLimit) (safe : b ≤ a) :
    binaryValue .sub (.word a) (.word b) = .value (.word (a - b)) := by
  simp [binaryValue, aBound, bBound, safe]

theorem disjunction_short_circuits (state : SourceState) (left right : GuardExpr .boolean)
    (yes : evalGuard state left = .value (.boolean true)) :
    evalGuard state (.or left right) = .value (.boolean true) := by
  simp [evalGuard, yes, Outcome.then]

end Aurora.SourceBinding
