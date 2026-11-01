import SourceBinding.CallLeafBinding
import SourceBinding.CallArgumentValues
namespace Aurora.SourceBinding

/-- Sole authoritative receiver and abstract environmental state. Saved frames
    deliberately cannot contain a receiver snapshot. -/
structure CallShared (World : Type) where
  receiver : Nat → Option Value
  world : World

structure CallFrame where
  pc : Nat
  accumulator : Option Value
  stack : List Value
  locals : Nat → Option Value
  arguments : Nat → Option Value

def CallFrame.inject (frame : CallFrame) (shared : CallShared World) : Machine :=
  ⟨frame.pc,frame.accumulator,frame.stack,frame.locals,shared.receiver,frame.arguments⟩
def CallFrame.ofMachine (machine : Machine) : CallFrame :=
  ⟨machine.pc,machine.accumulator,machine.stack,machine.locals,machine.arguments⟩
def CallShared.commit (shared : CallShared World) (machine : Machine) : CallShared World :=
  ⟨machine.receiver,shared.world⟩
def CallShared.source (shared : CallShared World) (arguments : Nat → Option Value) : SourceState :=
  ⟨shared.receiver,arguments⟩

@[simp] theorem inject_ofMachine (shared : CallShared World) (machine : Machine) :
    (CallFrame.ofMachine machine).inject (shared.commit machine) = machine := by cases machine; rfl
@[simp] theorem ofMachine_inject (frame : CallFrame) (shared : CallShared World) :
    CallFrame.ofMachine (frame.inject shared) = frame := by cases frame; rfl
@[simp] theorem commit_inject (frame : CallFrame) (shared : CallShared World) :
    shared.commit (frame.inject shared) = shared := by cases shared; rfl

/-- The assertion rule is shared as a scalar operation, not defined by executing
    an IR instruction. Missing and wrong-kind results are explicit type faults. -/
def assertResult : Option Value → Option EffectFault
  | some (.boolean true) => none
  | some (.boolean false) => some .assertion
  | _ => some (.scalar .type)

def assertMachine (machine : Machine) : EffectExecution :=
  match assertResult machine.accumulator with
  | none => .next {machine with pc := machine.pc + 1, accumulator := none}
  | some fault => .trap fault machine

def assertSource (state : SourceState) (value : Option Value) : SourceExecution :=
  match assertResult value with
  | none => .next state
  | some fault => .trap fault state

theorem require_assertMachine (program : EffectProgram) (machine : Machine)
    (atRequire : program machine.pc = some .require) :
    effectStep program machine = ⟨assertMachine machine,[]⟩ := by
  simp only [effectStep,atRequire,assertMachine]
  cases machine.accumulator with
  | none => rfl
  | some value => cases value with
    | word _ => rfl
    | boolean b => cases b <;> rfl

theorem require_assertSource (state : SourceState) (condition : GuardExpr .boolean) :
    evalBody (.require condition) state =
      sourceExpression state (evalGuard state condition) (fun value => ⟨assertSource state (some value),[]⟩) := by
  simp only [evalBody,sourceExpression]
  cases evalGuard state condition with
  | trap fault => rfl
  | value value => cases value with
    | word _ => rfl
    | boolean b => cases b <;> rfl

theorem assertion_related (frame : CallFrame) (shared : CallShared World) (source : SourceState)
    (context : ContextRelated source (frame.inject shared) slots) :
    BodyResultRelated slots frame.stack (frame.pc + 1)
      (assertSource source frame.accumulator) (assertMachine (frame.inject shared)) := by
  cases frame with
  | mk pc accumulator stack locals arguments =>
    cases accumulator with
    | none => exact ⟨rfl,funext context.fields⟩
    | some value => cases value with
      | word _ => exact ⟨rfl,funext context.fields⟩
      | boolean b => cases b with
        | false => exact ⟨rfl,funext context.fields⟩
        | true => exact ⟨rfl,rfl,context.fields,context.parameters⟩
end Aurora.SourceBinding
