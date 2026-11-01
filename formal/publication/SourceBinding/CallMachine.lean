import SourceBinding.CallState
namespace Aurora.SourceBinding

inductive CallOp where
  | local (operation : EffectOp)
  | ordinary (target : OrdinaryDescriptor)
  | resource (target : ResourceDescriptor)
abbrev CallProgram := Int → Nat → Option CallOp

def localProgram (program : CallProgram) (callable : Int) : EffectProgram := fun pc =>
  match program callable pc with | some (.local operation) => some operation | _ => none

/-- Protected abstract caller state. No receiver or world can be restored here. -/
structure SavedCall where
  target : OrdinaryDescriptor
  caller : Int
  continuation : CallFrame
structure ActiveCall (World : Type) where
  callable : Int
  frame : CallFrame
  saved : List SavedCall
  shared : CallShared World

structure ExternalRequest (World : Type) where
  target : ResourceDescriptor
  arguments : List Value
  before : CallShared World

/-- One pending occurrence owns exactly one frozen request and continuation.
    There is no second mutable copy of its pre-state. -/
structure WaitingCall (World : Type) where
  request : ExternalRequest World
  callable : Int
  continuation : CallFrame
  saved : List SavedCall

inductive ExternalOutcome (ExternalFault : Type) where
  | returned (value : Option Value)
  | fault (reason : ExternalFault)

inductive CallFault (ExternalFault : Type) where
  | local (reason : EffectFault)
  | external (reason : ExternalFault)

inductive CallEvent (World ExternalFault : Type) where
  | store (event : StoreEvent)
  | ordinaryInvoke (target : OrdinaryDescriptor) (arguments : List Value)
  | ordinaryReturn (target : OrdinaryDescriptor) (value : Value)
  | externalInvoke (request : ExternalRequest World)
  | externalReturn (value : Option Value) (after : CallShared World)
  | externalFault (reason : ExternalFault) (after : CallShared World)

inductive CallPhase (World ExternalFault : Type) where
  | running (active : ActiveCall World)
  | waiting (pending : WaitingCall World)
  | returned (value : Value) (active : ActiveCall World)
  | trapped (fault : CallFault ExternalFault) (active : ActiveCall World)

/-- Matching the published argument convention, not assuming successful typed
    entry. Type/range checks remain in the actual callee entry instructions. -/
def collectArguments (resource : Bool) (count : Nat) (frame : CallFrame) :
    Option (List Value × List Value) :=
  if resource && count == 1 then
    frame.accumulator.map fun value => ([value],frame.stack)
  else if count ≤ frame.stack.length then
    some ((frame.stack.take count).reverse,frame.stack.drop count)
  else none

def freshCallFrame (arguments : List Value) : CallFrame :=
  ⟨0,none,[],fun _ => none,fun index => arguments[index]?⟩

def returnToCaller (active : ActiveCall World) (value : Value) :
    CallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match active.saved with
  | [] => (.returned value active,[])
  | saved :: rest =>
    (.running ⟨saved.caller,{saved.continuation with accumulator := some value},rest,active.shared⟩,
      [.ordinaryReturn saved.target value])

def localCallStep (program : CallProgram) (active : ActiveCall World) :
    CallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  let result := effectStep (localProgram program active.callable) (active.frame.inject active.shared)
  let next : ActiveCall World := ⟨active.callable,CallFrame.ofMachine result.execution.state,
    active.saved,active.shared.commit result.execution.state⟩
  let stores := result.stores.map CallEvent.store
  match result.execution with
  | .next _ => (.running next,stores)
  | .trap fault _ => (.trapped (.local fault) next,stores)
  | .returned value _ =>
    let returned := returnToCaller next value
    (returned.1,stores ++ returned.2)

def callStep (program : CallProgram) (active : ActiveCall World) :
    CallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match program active.callable active.frame.pc with
  | some (.ordinary target) =>
    match collectArguments false target.parameters.length active.frame with
    | none => (.trapped (.local (.scalar .type)) active,[])
    | some (arguments,stack) =>
      let continuation := {active.frame with pc := active.frame.pc + 1,stack := stack}
      (.running ⟨target.id,freshCallFrame arguments,
        ⟨target,active.callable,continuation⟩ :: active.saved,active.shared⟩,
        [.ordinaryInvoke target arguments])
  | some (.resource target) =>
    match collectArguments true target.parameters.length active.frame with
    | none => (.trapped (.local (.scalar .type)) active,[])
    | some (arguments,stack) =>
      let request : ExternalRequest World := ⟨target,arguments,active.shared⟩
      let continuation := {active.frame with pc := active.frame.pc + 1,stack := stack}
      (.waiting ⟨request,active.callable,continuation,active.saved⟩,[.externalInvoke request])
  | _ => localCallStep program active

/-- External behavior has access only to the exact frozen request/pre-state and
    may replace every shared field. Protected frames are outside this interface;
    this is an explicit abstract contract, not a native ABI or authority proof. -/
abbrev ExternalRelation (World ExternalFault : Type) :=
  ExternalRequest World → ExternalOutcome ExternalFault → CallShared World → Prop

/-- External faults retain the post-invocation suspended continuation (advanced
    PC and consumed argument prefix), not a native fault-site frame. -/
def resumeCall (pending : WaitingCall World) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) : CallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match outcome with
  | .returned value =>
    (.running ⟨pending.callable,{pending.continuation with accumulator := value},pending.saved,after⟩,
      [.externalReturn value after])
  | .fault reason =>
    (.trapped (.external reason) ⟨pending.callable,pending.continuation,pending.saved,after⟩,
      [.externalFault reason after])

inductive CallTransition (program : CallProgram) (external : ExternalRelation World ExternalFault) :
    CallPhase World ExternalFault → List (CallEvent World ExternalFault) → CallPhase World ExternalFault → Prop
  | local : callStep program active = (next,events) → CallTransition program external (.running active) events next
  | resume : external pending.request outcome after → resumeCall pending outcome after = (next,events) →
      CallTransition program external (.waiting pending) events next

/-- Finite traces only. Absence of a response is never classified as divergence. -/
inductive CallRuns (program : CallProgram) (external : ExternalRelation World ExternalFault) :
    CallPhase World ExternalFault → List (CallEvent World ExternalFault) → CallPhase World ExternalFault → Prop
  | reflexive : CallRuns program external phase [] phase
  | step : CallTransition program external first events middle → CallRuns program external middle later last →
      CallRuns program external first (events ++ later) last

def PendingClassified (classification : ExternalRequest World → Prop) : CallPhase World ExternalFault → Prop
  | .waiting pending => classification pending.request
  | _ => False

theorem resume_not_waiting (pending : WaitingCall World) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) : ∀ next, (resumeCall pending outcome after).1 ≠ .waiting next := by
  cases outcome <;> intro next impossible <;> cases impossible

def CallPhase.shared : CallPhase World ExternalFault → CallShared World
  | .running active | .returned _ active | .trapped _ active => active.shared
  | .waiting pending => pending.request.before

theorem resume_shared (pending : WaitingCall World) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) : (resumeCall pending outcome after).1.shared = after := by
  cases outcome <;> rfl

theorem return_shared (active : ActiveCall World) (value : Value) :
    (returnToCaller (ExternalFault := ExternalFault) active value).1.shared = active.shared := by
  cases stack : active.saved <;> simp only [returnToCaller,stack,CallPhase.shared]

theorem return_restores (active : ActiveCall World) (value : Value) (saved : SavedCall)
    (rest : List SavedCall) (stack : active.saved = saved :: rest) :
    returnToCaller (ExternalFault := ExternalFault) active value =
      (.running ⟨saved.caller,{saved.continuation with accumulator := some value},rest,active.shared⟩,
        [.ordinaryReturn saved.target value]) := by simp only [returnToCaller,stack]

theorem resume_return_protected (pending : WaitingCall World) (value : Option Value)
    (after : CallShared World) :
    resumeCall (ExternalFault := ExternalFault) pending (.returned value) after =
      (.running ⟨pending.callable,{pending.continuation with accumulator := value},pending.saved,after⟩,
        [.externalReturn value after]) := rfl

theorem no_transition_returned (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (value : Value) (active : ActiveCall World) :
    ¬ CallTransition program external (.returned value active) events next := by intro step; cases step

theorem no_transition_trapped (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (fault : CallFault ExternalFault) (active : ActiveCall World) :
    ¬ CallTransition program external (.trapped fault active) events next := by intro step; cases step

end Aurora.SourceBinding
