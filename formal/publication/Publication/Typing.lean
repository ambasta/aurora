import Publication.Instructions
namespace Aurora.Publication

structure ValueTypes where
  accumulator : Option Scalar := none
  stack : List Scalar := []
  deriving BEq, DecidableEq, Repr

def catalogueScalar (kind : Int) : Option Scalar :=
  if kind == 1 then some .boolean else if kind == 7 then some .word else none

def argumentTypes (t : Tables) (code : Record) : List (Option Scalar) :=
  if code.integer 6 == 38 then
    ((signature t (callee t code)).drop 1).map (scalarKind t)
  else List.replicate ((methodOf t code).integer 4).toNat (catalogueScalar ((methodOf t code).integer 6))

def callResult (t : Tables) (code : Record) : Option Scalar :=
  if code.integer 6 == 38 then scalarKind t ((callee t code).integer 4)
  else catalogueScalar ((methodOf t code).integer 3)

/-- Retained primitives with one scalar parameter use current; ordinary method
    calls and retained primitives with multiple parameters use the operand stack.
    This matches the supported verifier calling convention, not native ABI. -/
def CallTransfer (resource : Bool) (args : List (Option Scalar)) (result : Option Scalar)
    (before after : ValueTypes) : Prop :=
  if resource = true ∧ args.length = 1 then
    before.accumulator = args.head?.getD none ∧ after = ⟨result, before.stack⟩
  else args.length ≤ before.stack.length ∧
    (before.stack.take args.length).map some = args.reverse ∧
    after = ⟨result, before.stack.drop args.length⟩
instance (resource : Bool) (args : List (Option Scalar)) (result : Option Scalar)
    (before after : ValueTypes) : Decidable (CallTransfer resource args result before after) := by
  unfold CallTransfer; infer_instance

/-- Independent abstract type transfer, NOT value-level IR execution semantics.
    Require has a checked boolean normal continuation and may fail; external
    calls have supplied result/argument types but no frame/effect guarantee. -/
def TypeTransfer (t : Tables) (id : Int) (code : Record) (before after : ValueTypes) : Prop :=
  let f := code.integer 6
  let v := operandValue t code
  if f = 45 ∨ f = 40 ∨ f = 41 then after = before
  else if f = 5 ∨ f = 7 ∨ f = 32 then
    after = { before with accumulator := scalarKind t (v 1) }
  else if f = 9 then
    match before.accumulator with
    | none => False
    | some scalar => after = { before with stack := scalar :: before.stack }
  else if f = 11 then before.accumulator = some .boolean ∧ after = before
  else if f = 12 ∨ f = 14 then
    before.accumulator = some .word ∧ before.stack.head? = some .word ∧
    after = ⟨some (if f = 12 then .word else .boolean), before.stack.tail⟩
  else if f = 33 then before.accumulator = scalarKind t (v 1) ∧ after = before
  else if f = 38 ∨ f = 89 then
    CallTransfer (f == 89) (argumentTypes t code) (callResult t code) before after
  else if f = 42 then before.accumulator = some .boolean ∧ after = before
  else if f = 91 then before.accumulator = some .boolean ∧ after = { before with accumulator := none }
  else if f = 43 then
    before.accumulator = scalarKind t ((atRow t.callables id).integer 4) ∧ before.stack = [] ∧ after = before
  else False
instance (t : Tables) (id : Int) (code : Record) (before after : ValueTypes) :
    Decidable (TypeTransfer t id code before after) := by
  unfold TypeTransfer
  split <;> infer_instance

/-- Candidate construction is not evidence: the independent relation is checked
    below before the candidate can enter a typing certificate. -/
def candidateTypes (t : Tables) (code : Record) (before : ValueTypes) : ValueTypes :=
  let f := code.integer 6
  if f == 5 || f == 7 || f == 32 then { before with accumulator := scalarKind t (operandValue t code 1) }
  else if f == 9 then
    match before.accumulator with
    | none => before
    | some scalar => { before with stack := scalar :: before.stack }
  else if f == 12 || f == 14 then
    ⟨some (if f == 12 then .word else .boolean), before.stack.tail⟩
  else if f == 38 || f == 89 then
    let count := (argumentTypes t code).length
    ⟨callResult t code, if f == 89 && count == 1 then before.stack else before.stack.drop count⟩
  else if f == 91 then { before with accumulator := none }
  else before

/-- Incoming unknown accumulator information may forget a predecessor's type,
    but cannot be used as a typed value. Stack information is never forgotten. -/
def FlowsTo (outgoing incoming : ValueTypes) : Prop :=
  incoming.stack = outgoing.stack ∧
  (incoming.accumulator = none ∨ incoming.accumulator = outgoing.accumulator)
instance (outgoing incoming : ValueTypes) : Decidable (FlowsTo outgoing incoming) := by
  unfold FlowsTo; infer_instance

theorem FlowsTo.known {outgoing incoming : ValueTypes} {scalar : Scalar}
    (edge : FlowsTo outgoing incoming) (known : incoming.accumulator = some scalar) :
    outgoing.accumulator = some scalar := by
  rcases edge.2 with forgotten | equal
  · rw [known] at forgotten; cases forgotten
  · exact equal.symm.trans known

inductive TypedRows (t : Tables) (id : Int) : List Record → List (ValueTypes × ValueTypes) → Prop
  | nil : TypedRows t id [] []
  | cons : TypeTransfer t id code before after → TypedRows t id remaining facts →
      TypedRows t id (code :: remaining) ((before, after) :: facts)

def checkRows (t : Tables) (id : Int) : (code : List Record) → (facts : List (ValueTypes × ValueTypes)) →
    Option { _witness : Unit // TypedRows t id code facts }
  | [], [] => some ⟨(), .nil⟩
  | code :: rest, (before, after) :: facts => do
    if transfer : TypeTransfer t id code before after then
      let tail ← checkRows t id rest facts
      return ⟨(), .cons transfer tail.property⟩
    else none
  | _, _ => none

/-- These candidate operations carry no trusted proof; checkRows and the edge
    relation below independently validate their entire result. -/
def mergeIncoming (states : Array (Option ValueTypes)) (index : Nat) (value : ValueTypes) :
    Option (Array (Option ValueTypes)) := do
  if index < states.size then
    match states[index]?.getD none with
    | none => return states.set! index (some value)
    | some old =>
      if old.stack = value.stack then
        let accumulator := if old.accumulator = value.accumulator then old.accumulator else none
        return states.set! index (some ⟨accumulator, old.stack⟩)
      else none
  else none

def inferTypes (t : Tables) (id : Int) : Option (Array (ValueTypes × ValueTypes)) := Id.run do
  let code := functionCode t id
  let mut incoming : Array (Option ValueTypes) := Array.replicate code.size none
  if code.size = 0 then return none
  incoming := incoming.set! 0 (some {})
  let mut facts := #[]
  for index in [0:code.size] do
    let some before := incoming[index]?.getD none | return none
    let row := code[index]?.getD ⟨"", [], false⟩
    let after := candidateTypes t row before
    facts := facts.push (before, after)
    if falls row then
      let some next := mergeIncoming incoming (index + 1) after | return none
      incoming := next
    if 0 ≤ row.integer 3 then
      let some next := mergeIncoming incoming (row.integer 3).toNat after | return none
      incoming := next
  return some facts

def factAt (facts : Array (ValueTypes × ValueTypes)) (index : Nat) : ValueTypes × ValueTypes :=
  facts[index]?.getD ({}, {})

def EdgeAgreement (t : Tables) (id : Int) (facts : Array (ValueTypes × ValueTypes)) : Prop :=
  facts.size = (functionCode t id).size ∧ (factAt facts 0).1 = {} ∧
  ∀ entry ∈ (functionCode t id).toList.zipIdx,
    (falls entry.1 = true → FlowsTo (factAt facts entry.2).2 (factAt facts (entry.2 + 1)).1) ∧
    (0 ≤ entry.1.integer 3 → FlowsTo (factAt facts entry.2).2 (factAt facts (entry.1.integer 3).toNat).1)
instance (t : Tables) (id : Int) (facts : Array (ValueTypes × ValueTypes)) :
    Decidable (EdgeAgreement t id facts) := by unfold EdgeAgreement; infer_instance

inductive FunctionTyped (t : Tables) (id : Int) : Prop
  | intro (facts : Array (ValueTypes × ValueTypes)) : FunctionBindings t id →
      TypedRows t id (functionCode t id).toList facts.toList →
      EdgeAgreement t id facts → FunctionTyped t id

def checkFunction (t : Tables) (id : Int) : Option { _witness : Unit // FunctionTyped t id } := do
  if bindings : FunctionBindings t id then
    let facts ← inferTypes t id
    let localTypes ← checkRows t id (functionCode t id).toList facts.toList
    if agreement : EdgeAgreement t id facts then
      return ⟨(), .intro facts bindings localTypes.property agreement⟩
    else none
  else none

theorem TypedRows.length {t : Tables} {id code facts} (typing : TypedRows t id code facts) :
    facts.length = code.length := by
  induction typing with
  | nil => rfl
  | cons _ _ ih => simpa using congrArg Nat.succ ih

theorem function_reachable {t : Tables} {id : Int} (typed : FunctionTyped t id)
    (position : Nat) (bound : position < (functionCode t id).size) : Reachable t id position := by
  cases typed with
  | intro facts bindings localTypes edges =>
    exact predecessors_reachable bindings.2.2.1 position bound

theorem function_sound (t : Tables) (id : Int) (result : { _witness : Unit // FunctionTyped t id })
    (_accepted : checkFunction t id = some result) : FunctionTyped t id := result.property

end Aurora.Publication
