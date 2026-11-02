import SourceBinding.RuntimeStatementEvaluation
import SourceBinding.RuntimeScopeReservation
import SourceBinding.RuntimeCallExecution
namespace Aurora.SourceBinding

def runtimeBodyFrame (base : Machine) (source : RuntimeLocals) (pc : Nat) (accumulator : Option Value) : Machine :=
  {base with pc := pc,accumulator := accumulator,locals := source.values}

/-- Returning is internally a pending checked ret instruction, not a fabricated
    terminal state. The complete-body endpoint executes that instruction. This
    keeps source internal traces separate from the enclosing caller's return. -/
def RuntimeBodyResult (program : CallProgram) (caller : Int) (saved : List SavedCall)
    (world : World) (base : Machine) (stop : Nat) : RuntimeBodyOutcome → CallPhase World ExternalFault → Prop
  | .continued source,final => ∃ accumulator,
      final = .running (activeAt caller saved world (runtimeBodyFrame base source stop accumulator))
  | .returned value source,final => ∃ pc,
      localProgram program caller pc = some (.pure .ret) ∧
      final = .running (activeAt caller saved world (runtimeBodyFrame base source pc (some value)))
  | .trapped fault _,final => ∃ active,
      final = .trapped (.local (.scalar fault)) active ∧ active.shared = ⟨base.receiver,world⟩

def RuntimeBodyRun (program : CallProgram) (external : ExternalRelation World ExternalFault)
    (caller : Int) (saved : List SavedCall) (world : World) (base : Machine)
    (source : RuntimeLocals) (start stop : Nat) (accumulator : Option Value)
    (outcome : RuntimeBodyOutcome) (events : List (CallEvent World ExternalFault)) : Prop :=
  ∃ final, CallRuns program external
    (.running (activeAt caller saved world (runtimeBodyFrame base source start accumulator))) events final ∧
    RuntimeBodyResult program caller saved world base stop outcome final

def RuntimeContinuationAt (members : List Declaration) (module path : Name) (formals : List Formal)
    (after : LocalContext) (ancestors : List Nat) : RuntimeBodyOutcome → Prop
  | .continued next => RuntimeStateAt members module path formals after ancestors next
  | .returned _ _ | .trapped _ _ => True

theorem RuntimeBodyRun.then_run
    (first : RuntimeBodyRun program external caller saved world base source start middle accumulator (.continued next) events)
    (rest : ∀ a, RuntimeBodyRun program external caller saved world base next middle stop a outcome later) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator outcome (events++later) := by
  obtain ⟨middleState,firstRun,a,same⟩ := first
  subst middleState
  obtain ⟨final,restRun,result⟩ := rest a
  exact ⟨final,firstRun.trans restRun,result⟩

theorem RuntimeBodyRun.return_stop
    (first : RuntimeBodyRun program external caller saved world base source start middle accumulator (.returned value next) events) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.returned value next) events := first

theorem RuntimeBodyRun.fault_stop
    (first : RuntimeBodyRun program external caller saved world base source start middle accumulator (.trapped fault next) events) :
    RuntimeBodyRun program external caller saved world base source start stop accumulator (.trapped fault next) events := first

end Aurora.SourceBinding
