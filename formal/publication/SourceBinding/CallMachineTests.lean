import SourceBinding.CallMachine
open Aurora.SourceBinding
namespace CallMachineFixtures
-- Bounded synthetic machine controls, not source/IR binding or production policy proofs.
def ordinary : OrdinaryDescriptor := ⟨"callee".toUTF8,7,[.word,.boolean],.boolean⟩
def resource (kinds : List GuardType := [.word,.word]) : ResourceDescriptor :=
  ⟨"authority".toUTF8,3,0,["builtin".toUTF8,"Resource".toUTF8],0,0,"foreign".toUTF8,
    kinds,.boolean,1,2,1,"__foreign".toUTF8⟩
def shared : CallShared Nat := ⟨fun i => if i == 4 then some (.word 5) else none,9⟩
def frame : CallFrame := ⟨0,some (.word 42),[.boolean false,.word 11,.word 999],
  fun i => if i == 8 then some (.word 88) else none,fun i => if i == 0 then some (.word 77) else none⟩
def initial : ActiveCall Nat := ⟨0,frame,[],shared⟩
def localProgramFixture (fail : Bool) : CallProgram := fun callable pc =>
  if callable == 0 && pc == 0 then some (.ordinary ordinary)
  else if callable == 7 then
    ([.local (.pure (.bind .word 0 8)),.local (.pure (.bind .boolean 1 16)),
      .local (.pure (.constant .word (.word 99))),.local (.store .word 4),
      .local (.pure (.constant .boolean (.boolean (!fail)))),
      if fail then .local .require else .local (.pure .ret)] : List CallOp)[pc]?
  else none

def advance (program : CallProgram) : Nat → CallPhase Nat Nat → CallPhase Nat Nat × List (CallEvent Nat Nat)
  | 0, phase => (phase,[])
  | fuel + 1, .running active =>
    let first := callStep program active
    let rest := advance program fuel first.1
    (rest.1,first.2 ++ rest.2)
  | _ + 1, phase => (phase,[])

def externalProgram (kinds : List GuardType := [.word,.word]) : CallProgram := fun _ pc =>
  ([.resource (resource kinds),.local .require,.local (.store .word 8)] : List CallOp)[pc]?
def externalInitial : ActiveCall Nat :=
  { initial with frame := {frame with stack := [.word 22,.word 11,.word 999]} }
def after : CallShared Nat := ⟨fun i => if i == 4 then some (.word 700) else
  if i == 90 then some (.boolean true) else shared.receiver i,100⟩
def pending : WaitingCall Nat :=
  ⟨⟨resource,[.word 11,.word 22],shared⟩,0,{frame with pc := 1,stack := [.word 999]},[]⟩
def allow : ExternalRelation Nat Nat := fun _ _ _ => True
def emptyExternal : ExternalRelation Nat Nat := fun _ _ _ => False

-- Distinct responses from the SAME pending request are permitted, not conflated.
example : CallTransition (externalProgram) allow (.waiting pending)
    (resumeCall pending (.returned (some (.boolean true))) after).2
    (resumeCall pending (.returned (some (.boolean true))) after).1 := .resume (outcome := .returned (some (.boolean true))) (after := after) trivial rfl
example : CallTransition (externalProgram) allow (.waiting pending)
    (resumeCall pending (.fault 17) after).2 (resumeCall pending (.fault 17) after).1 := .resume (outcome := .fault 17) (after := after) trivial rfl
example : ∀ next, (resumeCall pending (.returned none : ExternalOutcome Nat) after).1 ≠ .waiting next :=
  resume_not_waiting pending _ after
example : ¬ ∃ events next, CallTransition (externalProgram) emptyExternal (.waiting pending) events next := by
  rintro ⟨events,next,transition⟩
  cases transition with | resume allowed _ => exact allowed
-- Classification is a supplied request predicate; empty R supplies neither one.
example : PendingClassified (fun _ => True) (.waiting pending : CallPhase Nat Nat) := trivial
example : ¬ PendingClassified (fun _ => False) (.waiting pending : CallPhase Nat Nat) := fun h => h

private def expect (condition : Bool) (label : String) : IO Unit :=
  unless condition do throw (IO.userError s!"call machine fixture failed: {label}")

#eval do
  let invoked := callStep (localProgramFixture false) initial (ExternalFault := Nat)
  match invoked with
  | (.running callee,[.ordinaryInvoke target args]) =>
    expect (target == ordinary && args == [Value.word 11,Value.boolean false]) "ordinary argument order"
    expect (callee.callable == 7 && callee.frame.pc == 0 && callee.frame.stack == [] &&
      callee.frame.accumulator == none && callee.frame.locals 8 == none &&
      callee.frame.arguments 0 == some (Value.word 11) && callee.frame.arguments 1 == some (Value.boolean false) &&
      callee.shared.receiver 4 == shared.receiver 4) "fresh callee/current shared receiver"
  | _ => throw (IO.userError "ordinary invocation shape")
  let returned := advance (localProgramFixture false) 7 (.running initial)
  match returned with
  | (.running caller,[.ordinaryInvoke _ _,.store store,.ordinaryReturn target (Value.boolean true)]) =>
    expect (store == (⟨4,Value.word 99⟩ : StoreEvent) && target == ordinary) "ordered invoke/store/return"
    expect (caller.callable == 0 && caller.frame.pc == 1 && caller.saved.isEmpty &&
      caller.frame.accumulator == some (Value.boolean true) && caller.frame.stack == [Value.word 999] &&
      caller.frame.locals 8 == some (Value.word 88) && caller.frame.locals 100 == none &&
      caller.frame.arguments 0 == some (Value.word 77) && caller.frame.arguments 2 == none) "protected caller restoration"
    expect (caller.shared.receiver 4 == some (Value.word 99) && caller.shared.world == 9) "callee update not rolled back"
  | _ => throw (IO.userError "callee return shape")
  match advance (localProgramFixture true) 7 (.running initial) with
  | (.trapped (.local .assertion) active,[.ordinaryInvoke _ _,.store store]) =>
    expect (store == (⟨4,Value.word 99⟩ : StoreEvent) && active.shared.receiver 4 == some (Value.word 99) &&
      active.saved.length == 1 && active.callable == 7 && active.frame.pc == 5) "callee store then fault retains frame/store"
  | _ => throw (IO.userError "callee failure incorrectly returned/unwound")
  let waited := callStep (externalProgram) externalInitial (ExternalFault := Nat)
  let (.waiting waiting,[.externalInvoke request]) := waited | throw (IO.userError "external did not suspend")
  expect (request.arguments == [Value.word 11,Value.word 22] && request.target == resource &&
    request.before.receiver 4 == some (Value.word 5) && request.before.world == 9 &&
    waiting.continuation.pc == 1 && waiting.continuation.stack == [Value.word 999]) "frozen request/order/continuation"
  match callStep (externalProgram [.word]) initial (ExternalFault := Nat) with
  | (.waiting one,[.externalInvoke request]) =>
    expect (request.arguments == [Value.word 42] && one.continuation.stack == frame.stack) "singleton resource accumulator"
  | _ => throw (IO.userError "singleton resource invocation")
  for raw in [some (Value.boolean true),some (Value.boolean false),none,some (Value.word 1)] do
    let resumed := resumeCall waiting (.returned raw : ExternalOutcome Nat) after
    let (.running active,[.externalReturn observed world]) := resumed | throw (IO.userError "returned response phase")
    expect (observed == raw && world.world == 100 && active.frame.pc == 1 &&
      active.frame.stack == [Value.word 999] && active.frame.locals 8 == some (Value.word 88) &&
      active.frame.arguments 0 == some (Value.word 77) && active.shared.receiver 90 == some (Value.boolean true)) "resume protects frame, keeps external mutation"
    let checked := callStep (externalProgram) active (ExternalFault := Nat)
    match raw, checked with
    | some (Value.boolean true), (.running next,[]) =>
      expect (next.frame.pc == 2 && next.frame.accumulator == none && next.shared.receiver 4 == some (Value.word 700)) "true executes actual require"
    | some (Value.boolean false), (.trapped (.local .assertion) next,[]) =>
      expect (next.frame.pc == 1 && next.shared.receiver 4 == some (Value.word 700) && next.shared.receiver 8 == none) "false no rollback/no tail store"
    | none, (.trapped (.local (.scalar .type)) next,[])
    | some (Value.word _), (.trapped (.local (.scalar .type)) next,[]) =>
      expect (next.shared.world == 100 && next.shared.receiver 4 == some (Value.word 700)) "malformed result type fault retains poststate"
    | _, _ => throw (IO.userError "require response mismatch")
  match resumeCall waiting (.fault 17) after with
  | (.trapped (.external 17) active,[.externalFault 17 world]) =>
    expect (active.frame.pc == 1 && active.frame.stack == [Value.word 999] &&
      active.shared.receiver 4 == some (Value.word 700) && active.shared.receiver 8 == none && world.world == 100)
      "external fault preserves post-invocation continuation/poststate, no tail"
  | _ => throw (IO.userError "external fault changed kind or executed tail")
  IO.println "NATIVE call-machine controls passed: invoke/pop, store/fault, pending/resume and raw require outcomes"
end CallMachineFixtures
