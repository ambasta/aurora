import SourceBinding.GuardSemantics
namespace Aurora.SourceBinding

/-- Independent instruction/use relation. No checker result appears in its definition.
    Every instruction between entry and exit belongs to one of these compositional rules. -/
inductive ExprCode (program : Program) (slots : Nat → Nat) :
    {kind : GuardType} → GuardExpr kind → Nat → Nat → Prop
  | word : program start = some (.constant .word (.word n)) → ExprCode program slots (.wordLit n) start (start + 1)
  | boolean : program start = some (.constant .boolean (.boolean b)) → ExprCode program slots (.boolLit b) start (start + 1)
  | parameter : program start = some (.load kind (slots index)) →
      ExprCode program slots (.parameter kind name index) start (start + 1)
  | field : program start = some (.receiver kind ordinal) →
      ExprCode program slots (.field kind name ordinal) start (start + 1)
  | not : ExprCode program slots child start middle → program middle = some .negate →
      ExprCode program slots (.not child) start (middle + 1)
  | sub : ExprCode program slots left start leftEnd → program leftEnd = some .push →
      ExprCode program slots right (leftEnd + 1) rightEnd → program rightEnd = some (.binary .sub) →
      ExprCode program slots (.sub left right) start (rightEnd + 1)
  | bitAnd : ExprCode program slots left start leftEnd → program leftEnd = some .push →
      ExprCode program slots right (leftEnd + 1) rightEnd → program rightEnd = some (.binary .bitAnd) →
      ExprCode program slots (.bitAnd left right) start (rightEnd + 1)
  | bitOr : ExprCode program slots left start leftEnd → program leftEnd = some .push →
      ExprCode program slots right (leftEnd + 1) rightEnd → program rightEnd = some (.binary .bitOr) →
      ExprCode program slots (.bitOr left right) start (rightEnd + 1)
  | shift12 : ExprCode program slots child start middle → program middle = some .push →
      program (middle + 1) = some .count12 → program (middle + 2) = some (.binary .leftShift) →
      ExprCode program slots (.shift12 child) start (middle + 3)
  | compare : ExprCode program slots left start leftEnd → program leftEnd = some .push →
      ExprCode program slots right (leftEnd + 1) rightEnd → program rightEnd = some (.binary (.compare operation)) →
      ExprCode program slots (.compare operation left right) start (rightEnd + 1)

  | and : ExprCode program slots left start leftEnd →
      program leftEnd = some (.branchFalse rightEnd) →
      ExprCode program slots right (leftEnd + 1) rightEnd → program rightEnd = some .label →
      ExprCode program slots (.and left right) start (rightEnd + 1)
  | or : ExprCode program slots left start leftEnd →
      program leftEnd = some (.branchFalse (leftEnd + 2)) →
      program (leftEnd + 1) = some (.jump rightEnd) → program (leftEnd + 2) = some .label →
      ExprCode program slots right (leftEnd + 3) rightEnd → program rightEnd = some .label →
      ExprCode program slots (.or left right) start (rightEnd + 1)

structure ParsedExprCode (program : Program) (slots : Nat → Nat) {kind : GuardType}
    (expression : GuardExpr kind) (start : Nat) where
  stop : Nat
  grammar : ExprCode program slots expression start stop

/-- Candidate structural lowering is validated against the independent use relation. -/
def checkExprCode (program : Program) (slots : Nat → Nat) : {kind : GuardType} →
    (expression : GuardExpr kind) → (start : Nat) → Option (ParsedExprCode program slots expression start)
  | _, .wordLit n, start =>
    if code : program start = some (.constant .word (.word n)) then some ⟨start + 1,.word code⟩ else none
  | _, .boolLit b, start =>
    if code : program start = some (.constant .boolean (.boolean b)) then some ⟨start + 1,.boolean code⟩ else none
  | _, .parameter kind _ index, start =>
    if code : program start = some (.load kind (slots index)) then some ⟨start + 1,.parameter code⟩ else none
  | _, .field kind _ ordinal, start =>
    if code : program start = some (.receiver kind ordinal) then some ⟨start + 1,.field code⟩ else none
  | _, .not child, start => do
    let inner ← checkExprCode program slots child start
    if code : program inner.stop = some .negate then return ⟨inner.stop + 1,.not inner.grammar code⟩ else none
  | _, .sub left right, start => do
    let l ← checkExprCode program slots left start
    if push : program l.stop = some .push then
      let r ← checkExprCode program slots right (l.stop + 1)
      if binary : program r.stop = some (.binary .sub) then
        return ⟨r.stop + 1,.sub l.grammar push r.grammar binary⟩
      else none
    else none
  | _, .bitAnd left right, start => do
    let l ← checkExprCode program slots left start
    if push : program l.stop = some .push then
      let r ← checkExprCode program slots right (l.stop + 1)
      if binary : program r.stop = some (.binary .bitAnd) then
        return ⟨r.stop + 1,.bitAnd l.grammar push r.grammar binary⟩
      else none
    else none
  | _, .bitOr left right, start => do
    let l ← checkExprCode program slots left start
    if push : program l.stop = some .push then
      let r ← checkExprCode program slots right (l.stop + 1)
      if binary : program r.stop = some (.binary .bitOr) then
        return ⟨r.stop + 1,.bitOr l.grammar push r.grammar binary⟩
      else none
    else none
  | _, .shift12 child, start => do
    let c ← checkExprCode program slots child start
    if push : program c.stop = some .push then
      if count : program (c.stop + 1) = some .count12 then
        if binary : program (c.stop + 2) = some (.binary .leftShift) then
          return ⟨c.stop + 3,.shift12 c.grammar push count binary⟩
        else none
      else none
    else none
  | _, .compare operation left right, start => do
    let l ← checkExprCode program slots left start
    if push : program l.stop = some .push then
      let r ← checkExprCode program slots right (l.stop + 1)
      if binary : program r.stop = some (.binary (.compare operation)) then
        return ⟨r.stop + 1,.compare l.grammar push r.grammar binary⟩
      else none
    else none
  | _, .and left right, start => do
    let l ← checkExprCode program slots left start
    let r ← checkExprCode program slots right (l.stop + 1)
    if branch : program l.stop = some (.branchFalse r.stop) then
      if label : program r.stop = some .label then
        return ⟨r.stop + 1,.and l.grammar branch r.grammar label⟩
      else none
    else none
  | _, .or left right, start => do
    let l ← checkExprCode program slots left start
    let r ← checkExprCode program slots right (l.stop + 3)
    if branch : program l.stop = some (.branchFalse (l.stop + 2)) then
      if jump : program (l.stop + 1) = some (.jump r.stop) then
        if enter : program (l.stop + 2) = some .label then
          if done : program r.stop = some .label then
            return ⟨r.stop + 1,.or l.grammar branch jump enter r.grammar done⟩
          else none
        else none
      else none
    else none

/-- Parameter slots are explicit. This relation equates values, never guard outcomes. -/
structure ContextRelated (source : SourceState) (machine : Machine) (slots : Nat → Nat) : Prop where
  fields : ∀ index, machine.receiver index = source.fields index
  parameters : ∀ index, machine.locals (slots index) = source.parameters index

@[simp] theorem frame_frame (base : Machine) (p q : Nat) (a b : Option Value) (s t : List Value) :
    frameState (frameState base p a s) q b t = frameState base q b t := rfl

@[simp] theorem finish_frame (base : Machine) (p q : Nat) (a : Option Value) (s t : List Value) (out : Outcome Value) :
    finish (frameState base p a s) q t out = finish base q t out := by cases out <;> rfl

theorem Runs.one {program : Program} {state : Machine} {result : Execution}
    (equation : step program state = result) : Runs program state result := by
  rw [← equation]; exact Runs.single

/-- Compositional stack argument: left is evaluated, pushed, then right; operand
    order is left-minus-right, not accumulator-minus-stack. Traps stop immediately. -/
theorem binary_simulation (program : Program) (base : Machine) (start middle stop : Nat)
    (accumulator : Option Value) (stack : List Value) (operation : Binary)
    (left right : Outcome Value)
    (leftRun : Runs program (frameState base start accumulator stack) (finish base middle stack left))
    (push : program middle = some .push)
    (rightRun : ∀ value, Runs program (frameState base (middle + 1) (some value) (value :: stack))
      (finish base stop (value :: stack) right))
    (binary : program stop = some (.binary operation)) :
    Runs program (frameState base start accumulator stack)
      (finish base (stop + 1) stack (left.then fun a => right.then fun b => binaryValue operation a b)) := by
  cases left with
  | trap fault => simpa [Outcome.then,finish] using leftRun
  | value a =>
    have pushed : Runs program (frameState base middle (some a) stack)
        (.next (frameState base (middle + 1) (some a) (a :: stack))) :=
      Runs.one (by simp [step,frameState,push])
    have untilRight := (Runs.trans leftRun pushed).trans (rightRun a)
    cases right with
    | trap fault => simpa [Outcome.then,finish] using untilRight
    | value b =>
      have operated : Runs program (frameState base stop (some b) (a :: stack))
          (finish base (stop + 1) stack (binaryValue operation a b)) :=
        Runs.one (by simp [step,frameState,binary,finish])
      simpa [Outcome.then] using untilRight.trans operated

theorem label_simulation (program : Program) (base : Machine) (pc : Nat)
    (stack : List Value) (outcome : Outcome Value) (label : program pc = some .label)
    {initial : Machine} (priorRun : Runs program initial (finish base pc stack outcome)) :
    Runs program initial (finish base (pc + 1) stack outcome) := by
  cases outcome with
  | trap fault => exact priorRun
  | value value =>
    exact priorRun.trans (Runs.one (by simp [step,frameState,finish,label]))

theorem and_simulation (program : Program) (base : Machine) (start middle stop : Nat)
    (accumulator : Option Value) (stack : List Value) (left right : Outcome Value)
    (leftRun : Runs program (frameState base start accumulator stack) (finish base middle stack left))
    (branch : program middle = some (.branchFalse stop))
    (rightRun : Runs program (frameState base (middle + 1) (some (.boolean true)) stack)
      (finish base stop stack right)) (label : program stop = some .label) :
    Runs program (frameState base start accumulator stack)
      (finish base (stop + 1) stack (left.then fun value => match value with
        | .boolean false => .value (.boolean false)
        | .boolean true => right
        | _ => .trap .type)) := by
  cases left with
  | trap fault => exact leftRun
  | value value =>
    cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ =>
      exact leftRun.trans (Runs.one (by simp [step,frameState,branch,finish,Outcome.then]))
    | boolean b =>
      cases b with
      | false =>
        apply label_simulation program base stop stack (.value (.boolean false)) label
        exact leftRun.trans (Runs.one (by simp [step,frameState,branch,finish]))
      | true =>
        apply label_simulation program base stop stack right label
        exact (leftRun.trans (Runs.one (by simp [step,frameState,branch]))).trans rightRun

theorem or_simulation (program : Program) (base : Machine) (start middle stop : Nat)
    (accumulator : Option Value) (stack : List Value) (left right : Outcome Value)
    (leftRun : Runs program (frameState base start accumulator stack) (finish base middle stack left))
    (branch : program middle = some (.branchFalse (middle + 2)))
    (jump : program (middle + 1) = some (.jump stop))
    (enter : program (middle + 2) = some .label)
    (rightRun : Runs program (frameState base (middle + 3) (some (.boolean false)) stack)
      (finish base stop stack right)) (label : program stop = some .label) :
    Runs program (frameState base start accumulator stack)
      (finish base (stop + 1) stack (left.then fun value => match value with
        | .boolean true => .value (.boolean true)
        | .boolean false => right
        | _ => .trap .type)) := by
  cases left with
  | trap fault => exact leftRun
  | value value =>
    cases value with
    | word _ | signedCount12 | signedCount4 | signedCount32 | nominal _ _ =>
      exact leftRun.trans (Runs.one (by simp [step,frameState,branch,finish,Outcome.then]))
    | boolean b =>
      cases b with
      | false =>
        apply label_simulation program base stop stack right label
        have branched : Runs program (frameState base middle (some (.boolean false)) stack)
            (.next (frameState base (middle + 2) (some (.boolean false)) stack)) :=
          Runs.one (by simp [step,frameState,branch])
        have entered : Runs program (frameState base (middle + 2) (some (.boolean false)) stack)
            (.next (frameState base (middle + 3) (some (.boolean false)) stack)) :=
          Runs.one (by simp [step,frameState,enter,Nat.add_assoc])
        exact ((leftRun.trans branched).trans entered).trans rightRun
      | true =>
        apply label_simulation program base stop stack (.value (.boolean true)) label
        have branched : Runs program (frameState base middle (some (.boolean true)) stack)
            (.next (frameState base (middle + 1) (some (.boolean true)) stack)) :=
          Runs.one (by simp [step,frameState,branch])
        exact (leftRun.trans branched).trans (Runs.one (by simp [step,frameState,jump,finish]))

/-- Semantic soundness, not merely successful structural decoding. The output
    preserves the base receiver/arguments/frame and caller stack on value completion.
    Traps expose only the same fault and stopping, not a final machine state. -/
theorem ExprCode.simulates {program : Program} {slots : Nat → Nat} {kind : GuardType}
    {expression : GuardExpr kind} {start stop : Nat}
    (code : ExprCode program slots expression start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    Runs program (frameState base start accumulator stack)
      (finish base stop stack (evalGuard source expression)) := by
  induction code generalizing accumulator stack with
  | word code => exact Runs.one (by simp [step,frameState,code,evalGuard,finish])
  | boolean code => exact Runs.one (by simp [step,frameState,code,evalGuard,finish,readScalar])
  | parameter code => exact Runs.one (by simp [step,frameState,code,evalGuard,finish,context.parameters])
  | field code => exact Runs.one (by simp [step,frameState,code,evalGuard,finish,context.fields])
  | @not childExpr begin middle child code ih =>
    have inner := ih accumulator stack
    cases outcome : evalGuard source childExpr with
    | trap fault => simpa [evalGuard,outcome,Outcome.then,finish] using inner
    | value value =>
      have innerValue := inner
      rw [outcome] at innerValue
      apply Runs.trans innerValue
      exact Runs.one (by simp [step,frameState,code,evalGuard,outcome,Outcome.then,finish])
  | sub left push right binary leftIH rightIH =>
    exact binary_simulation program base _ _ _ accumulator stack .sub _ _
      (leftIH accumulator stack) push (fun value => rightIH (some value) (value :: stack)) binary
  | bitAnd left push right binary leftIH rightIH =>
    exact binary_simulation program base _ _ _ accumulator stack .bitAnd _ _
      (leftIH accumulator stack) push (fun value => rightIH (some value) (value :: stack)) binary
  | bitOr left push right binary leftIH rightIH =>
    exact binary_simulation program base _ _ _ accumulator stack .bitOr _ _
      (leftIH accumulator stack) push (fun value => rightIH (some value) (value :: stack)) binary
  | @shift12 childExpr begin middle child push count binary ih =>
    have counted (value : Value) : Runs program
        (frameState base (middle + 1) (some value) (value :: stack))
        (finish base (middle + 2) (value :: stack) (.value .signedCount12)) :=
      Runs.one (by simp [step,frameState,count,finish])
    simpa only [evalGuard,Outcome.then,Nat.add_assoc] using
      binary_simulation program base begin middle (middle + 2) accumulator stack .leftShift
        (evalGuard source childExpr) (.value .signedCount12) (ih accumulator stack) push counted binary
  | compare left push right binary leftIH rightIH =>
    exact binary_simulation program base _ _ _ accumulator stack _ _ _
      (leftIH accumulator stack) push (fun value => rightIH (some value) (value :: stack)) binary
  | and left branch right label leftIH rightIH =>
    exact and_simulation program base _ _ _ accumulator stack _ _
      (leftIH accumulator stack) branch (rightIH (some (.boolean true)) stack) label
  | or left branch jump enter right label leftIH rightIH =>
    exact or_simulation program base _ _ _ accumulator stack _ _
      (leftIH accumulator stack) branch jump enter (rightIH (some (.boolean false)) stack) label

theorem check_expr_code_sound (program : Program) (slots : Nat → Nat) {kind : GuardType}
    (expression : GuardExpr kind) (start : Nat) (result : ParsedExprCode program slots expression start)
    (_accepted : checkExprCode program slots expression start = some result) :
    ExprCode program slots expression start result.stop := result.grammar

end Aurora.SourceBinding
