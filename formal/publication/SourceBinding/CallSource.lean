import SourceBinding.CallMachine
namespace Aurora.SourceBinding

/-- Call-free source bodies, later coupled to SAME-table leaf certificates.
    Evaluation executes the body; this interface supplies no result summary. -/
abbrev SourceCallProgram := OrdinaryDescriptor → Option EffectBody

structure SourceCallActive (World : Type) where
  pieces : List CallPiece
  arguments : Nat → Option Value
  shared : CallShared World
structure SourceWaiting (World : Type) where
  request : ExternalRequest World
  remaining : List CallPiece
  arguments : Nat → Option Value

inductive SourceCallPhase (World ExternalFault : Type) where
  | running (active : SourceCallActive World)
  | waiting (pending : SourceWaiting World)
  | returned (value : Value) (shared : CallShared World)
  | trapped (fault : CallFault ExternalFault) (shared : CallShared World)
  | exhausted (shared : CallShared World)

/-- Exhaustion is explicit, not silently equated with return. Checked CallReturns
    must rule it out in the complete-root endpoint theorem. -/
def sourceBodyResult (active : SourceCallActive World) (rest : List CallPiece)
    (result : BodyEvaluation) : SourceCallPhase World ExternalFault :=
  let shared : CallShared World := ⟨result.execution.state.fields,active.shared.world⟩
  match result.execution with
  | .next _ => .running ⟨rest,active.arguments,shared⟩
  | .returned value _ => .returned value shared
  | .trap fault _ => .trapped (.local fault) shared

def sourceOrdinary (bodies : SourceCallProgram) (active : SourceCallActive World) (rest : List CallPiece)
    (target : OrdinaryDescriptor) (arguments : List Value) :
    SourceCallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match bodies target with
  | none => (.trapped (.local (.scalar .unsupported)) active.shared,[])
  | some body =>
    let result := evalBody body (active.shared.source (fun index => arguments[index]?))
    let shared : CallShared World := ⟨result.execution.state.fields,active.shared.world⟩
    let events := .ordinaryInvoke target arguments :: result.stores.map CallEvent.store
    match result.execution with
    | .next _ => (.exhausted shared,events)
    | .trap fault _ => (.trapped (.local fault) shared,events)
    | .returned value _ =>
      (.running ⟨rest,active.arguments,shared⟩,events ++ [.ordinaryReturn target value])

def sourceCallStep (bodies : SourceCallProgram) (active : SourceCallActive World) :
    SourceCallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match active.pieces with
  | [] => (.exhausted active.shared,[])
  | .localBody body :: rest =>
    let result := evalBody body (active.shared.source active.arguments)
    (sourceBodyResult active rest result,result.stores.map CallEvent.store)
  | .invoke (.ordinary target expressions) :: rest =>
    match evalCallArguments (active.shared.source active.arguments) expressions with
    | .trap fault => (.trapped (.local (.scalar fault)) active.shared,[])
    | .value arguments => sourceOrdinary bodies active rest target arguments
  | .invoke (.resourceAssert target expressions) :: rest =>
    match evalCallArguments (active.shared.source active.arguments) expressions with
    | .trap fault => (.trapped (.local (.scalar fault)) active.shared,[])
    | .value arguments =>
      let request : ExternalRequest World := ⟨target,arguments,active.shared⟩
      (.waiting ⟨request,rest,active.arguments⟩,[.externalInvoke request])

/-- The accepted source syntax is require(resource-call). Returned raw values
    therefore undergo the SAME independent scalar assertion, with post-state
    installed first. No leave or rollback is implicit in a failure. -/
def sourceResume (pending : SourceWaiting World) (outcome : ExternalOutcome ExternalFault)
    (after : CallShared World) : SourceCallPhase World ExternalFault × List (CallEvent World ExternalFault) :=
  match outcome with
  | .fault fault => (.trapped (.external fault) after,[.externalFault fault after])
  | .returned value =>
    let events := [CallEvent.externalReturn value after]
    match assertResult value with
    | none => (.running ⟨pending.remaining,pending.arguments,after⟩,events)
    | some fault => (.trapped (.local fault) after,events)

inductive SourceCallTransition (bodies : SourceCallProgram) (external : ExternalRelation World ExternalFault) :
    SourceCallPhase World ExternalFault → List (CallEvent World ExternalFault) →
      SourceCallPhase World ExternalFault → Prop
  | local : sourceCallStep bodies active = (next,events) →
      SourceCallTransition bodies external (.running active) events next
  | resume : external pending.request outcome after → sourceResume pending outcome after = (next,events) →
      SourceCallTransition bodies external (.waiting pending) events next

inductive SourceCallRuns (bodies : SourceCallProgram) (external : ExternalRelation World ExternalFault) :
    SourceCallPhase World ExternalFault → List (CallEvent World ExternalFault) →
      SourceCallPhase World ExternalFault → Prop
  | reflexive : SourceCallRuns bodies external phase [] phase
  | step : SourceCallTransition bodies external first events middle →
      SourceCallRuns bodies external middle later last → SourceCallRuns bodies external first (events ++ later) last

/-- Only completed root outcomes and suspended requests are boundary observations.
    No source PC/temporary stack or external divergence execution is invented. -/
inductive BoundaryObservation (World ExternalFault : Type) where
  | returned (value : Value) (shared : CallShared World)
  | trapped (fault : CallFault ExternalFault) (shared : CallShared World)
  | waiting (request : ExternalRequest World)

def sourceBoundary : SourceCallPhase World ExternalFault → Option (BoundaryObservation World ExternalFault)
  | .returned value shared => some (.returned value shared)
  | .trapped fault shared => some (.trapped fault shared)
  | .waiting pending => some (.waiting pending.request)
  | _ => none

def machineBoundary : CallPhase World ExternalFault → Option (BoundaryObservation World ExternalFault)
  | .returned value active => some (.returned value active.shared)
  | .trapped fault active => some (.trapped fault active.shared)
  | .waiting pending => some (.waiting pending.request)
  | _ => none

def BoundaryRelated (source : SourceCallPhase World ExternalFault) (machine : CallPhase World ExternalFault) : Prop :=
  ∃ observation, sourceBoundary source = some observation ∧ machineBoundary machine = some observation

def SourcePendingClassified (classification : ExternalRequest World → Prop) : SourceCallPhase World ExternalFault → Prop
  | .waiting pending => classification pending.request
  | _ => False

end Aurora.SourceBinding
