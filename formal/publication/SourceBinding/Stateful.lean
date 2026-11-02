import SourceBinding.IRSemantics
namespace Aurora.SourceBinding

/-- A failed assertion is distinct from malformed scalar input. -/
inductive EffectFault where
  | scalar (fault : Fault)
  | assertion
  deriving BEq, DecidableEq, Repr

/-- Only completed receiver stores are observable events in this local profile. -/
structure StoreEvent where
  ordinal : Nat
  value : Value
  deriving BEq, DecidableEq, Repr

inductive EffectOp where
  | pure (operation : Op)
  | store (kind : GuardType) (ordinal : Nat)
  | require
  deriving BEq, DecidableEq, Repr
abbrev EffectProgram := Nat → Option EffectOp

/-- Terminal states are the actual state at the failing/returning instruction,
    not a reconstructed entry state. No unwinding or rollback is modeled. -/
inductive EffectExecution where
  | next (state : Machine)
  | returned (value : Value) (state : Machine)
  | trap (fault : EffectFault) (state : Machine)

def EffectExecution.state : EffectExecution → Machine
  | .next state | .returned _ state | .trap _ state => state

structure EffectStep where
  execution : EffectExecution
  stores : List StoreEvent := []

/-- Existing pure instructions retain their exact scalar semantics. -/
def retainState (state : Machine) : Execution → EffectExecution
  | .next next => .next next
  | .returned value => .returned value state
  | .trap fault => .trap (.scalar fault) state

def pureView (program : EffectProgram) : Program := fun pc =>
  match program pc with | some (.pure operation) => some operation | _ => none

def effectStep (program : EffectProgram) (state : Machine) : EffectStep :=
  match program state.pc with
  | some (.store kind ordinal) =>
    match readScalar kind state.accumulator with
    | .trap fault => ⟨.trap (.scalar fault) state,[]⟩
    | .value value => ⟨.next { state with
        pc := state.pc + 1
        receiver := fun index => if index = ordinal then some value else state.receiver index },[⟨ordinal,value⟩]⟩
  | some .require =>
    match state.accumulator with
    | some (.boolean true) => ⟨.next { state with pc := state.pc + 1, accumulator := none },[]⟩
    | some (.boolean false) => ⟨.trap .assertion state,[]⟩
    | _ => ⟨.trap (.scalar .type) state,[]⟩
  | _ => ⟨retainState state (step (pureView program) state),[]⟩

/-- Erasure applies to pure executions only; assertion failure has no old counterpart. -/
def eraseEffect : EffectExecution → Option Execution
  | .next state => some (.next state)
  | .returned value _ => some (.returned value)
  | .trap (.scalar fault) _ => some (.trap fault)
  | .trap .assertion _ => none

@[simp] theorem erase_retain (state : Machine) (execution : Execution) :
    eraseEffect (retainState state execution) = some execution := by cases execution <;> rfl

def embedProgram (program : Program) : EffectProgram := fun pc => (program pc).map EffectOp.pure

@[simp] theorem pureView_embed (program : Program) : pureView (embedProgram program) = program := by
  funext pc; unfold pureView embedProgram; cases program pc <;> rfl

theorem embedded_step (program : Program) (state : Machine) :
    effectStep (embedProgram program) state = ⟨retainState state (step program state),[]⟩ := by
  simp only [effectStep,pureView_embed]
  cases eq : program state.pc <;> simp only [embedProgram,eq,Option.map_none,Option.map_some]

theorem embedded_step_erases (program : Program) (state : Machine) :
    eraseEffect (effectStep (embedProgram program) state).execution = some (step program state) ∧
    (effectStep (embedProgram program) state).stores = [] := by rw [embedded_step]; exact ⟨erase_retain _ _,rfl⟩

/-- Stores accumulate in execution order and survive every terminal outcome. -/
inductive EffectRuns (program : EffectProgram) : Machine → List StoreEvent → EffectExecution → Prop
  | reflexive : EffectRuns program state [] (.next state)
  | next : effectStep program initial = ⟨.next middle,events⟩ →
      EffectRuns program middle later result → EffectRuns program initial (events ++ later) result
  | returned : effectStep program initial = ⟨.returned value state,events⟩ →
      EffectRuns program initial events (.returned value state)
  | trap : effectStep program initial = ⟨.trap fault state,events⟩ →
      EffectRuns program initial events (.trap fault state)

theorem EffectRuns.one {program : EffectProgram} {state : Machine} :
    EffectRuns program state (effectStep program state).stores (effectStep program state).execution := by
  cases eq : effectStep program state with
  | mk execution events =>
    cases execution with
    | next middle => simpa only [List.append_nil] using EffectRuns.next eq (.reflexive (state := middle))
    | returned value final => exact .returned eq
    | trap fault final => exact .trap eq

theorem EffectRuns.trans {program : EffectProgram} {initial middle : Machine}
    {first later : List StoreEvent} {result : EffectExecution}
    (prior : EffectRuns program initial first (.next middle))
    (tail : EffectRuns program middle later result) : EffectRuns program initial (first ++ later) result := by
  generalize ending : EffectExecution.next middle = last at prior
  induction prior generalizing middle with
  | reflexive => cases ending; exact tail
  | next step rest ih => simpa only [List.append_assoc] using EffectRuns.next step (ih tail ending)
  | returned step => cases ending
  | trap step => cases ending

theorem finish_retains_frame (state : Machine) (pc : Nat) (stack : List Value) (out : Outcome Value) :
    (retainState state (finish state pc stack out)).state.receiver = state.receiver ∧
    (retainState state (finish state pc stack out)).state.arguments = state.arguments := by
  cases out <;> exact ⟨rfl,rfl⟩

/-- Every pure step preserves receiver and arguments even when it terminates. -/
theorem pure_step_frame (program : Program) (state : Machine) :
    (retainState state (step program state)).state.receiver = state.receiver ∧
    (retainState state (step program state)).state.arguments = state.arguments := by
  unfold step
  cases operation : program state.pc with
  | none => exact ⟨rfl,rfl⟩
  | some op =>
    cases op with
    | constant kind value => exact finish_retains_frame _ _ _ _
    | load kind slot => exact finish_retains_frame _ _ _ _
    | receiver kind ordinal => exact finish_retains_frame _ _ _ _
    | push => cases state.accumulator <;> exact ⟨rfl,rfl⟩
    | negate =>
      cases state.accumulator with
      | none => exact ⟨rfl,rfl⟩
      | some value => exact finish_retains_frame _ _ _ _
    | binary op =>
      cases state.stack with
      | nil => cases state.accumulator <;> exact ⟨rfl,rfl⟩
      | cons first rest =>
        cases state.accumulator with
        | none => exact ⟨rfl,rfl⟩
        | some value => exact finish_retains_frame _ _ _ _
    | bind kind argument slot =>
      simp only
      cases readScalar kind (state.arguments argument) <;> exact ⟨rfl,rfl⟩
    | label | jump _ => exact ⟨rfl,rfl⟩
    | branchFalse target =>
      cases state.accumulator with
      | none => exact ⟨rfl,rfl⟩
      | some value => cases value <;> exact ⟨rfl,rfl⟩
    | count12 => exact ⟨rfl,rfl⟩
    | ret => cases state.accumulator <;> exact ⟨rfl,rfl⟩

/-- A supported pure step in a mixed program has exactly its old meaning. -/
theorem supported_pure_step (program : EffectProgram) (state : Machine)
    (supported : step (pureView program) state ≠ .trap .unsupported) :
    effectStep program state = ⟨retainState state (step (pureView program) state),[]⟩ := by
  cases code : program state.pc with
  | none => simp only [effectStep,code]
  | some operation =>
    cases operation with
    | pure op => simp only [effectStep,code]
    | store kind ordinal => simp [step,pureView,code] at supported
    | require => simp [step,pureView,code] at supported

/-- Conservative lift retains a terminal frame existentially; old erased
    terminals do not determine its PC, accumulator or stack. -/
theorem pure_runs_lift {program : EffectProgram} {initial : Machine} {result : Execution}
    (run : Runs (pureView program) initial result) (supported : result ≠ .trap .unsupported) :
    ∃ final, EffectRuns program initial [] final ∧ eraseEffect final = some result ∧
      final.state.receiver = initial.receiver ∧ final.state.arguments = initial.arguments := by
  induction run with
  | reflexive => exact ⟨.next _,.reflexive,rfl,rfl,rfl⟩
  | @next initial middle result first rest ih =>
    have safe : step (pureView program) initial ≠ .trap .unsupported := by rw [first]; intro h; cases h
    have frame := pure_step_frame (pureView program) initial
    rw [first] at frame
    obtain ⟨final,later,erased,receiver,arguments⟩ := ih supported
    refine ⟨final,?_,erased,receiver.trans frame.1,arguments.trans frame.2⟩
    have actual := supported_pure_step program initial safe
    rw [first] at actual
    exact .next actual later
  | @returned initial value first =>
    have safe : step (pureView program) initial ≠ .trap .unsupported := by rw [first]; intro h; cases h
    have actual := supported_pure_step program initial safe
    rw [first] at actual
    exact ⟨.returned value initial,.returned actual,rfl,rfl,rfl⟩
  | @trap initial fault first =>
    have safe : step (pureView program) initial ≠ .trap .unsupported := by rw [first]; exact supported
    have actual := supported_pure_step program initial safe
    rw [first] at actual
    exact ⟨.trap (.scalar fault) initial,.trap actual,rfl,rfl,rfl⟩

theorem require_false_stops (program : EffectProgram) (state : Machine)
    (code : program state.pc = some .require) (value : state.accumulator = some (.boolean false)) :
    effectStep program state = ⟨.trap .assertion state,[]⟩ := by simp only [effectStep,code,value]

theorem require_true_clears (program : EffectProgram) (state : Machine)
    (code : program state.pc = some .require) (value : state.accumulator = some (.boolean true)) :
    effectStep program state = ⟨.next {state with pc := state.pc + 1, accumulator := none},[]⟩ := by
  simp only [effectStep,code,value]

theorem store_step (program : EffectProgram) (state : Machine) (kind : GuardType) (ordinal : Nat) (value : Value)
    (code : program state.pc = some (.store kind ordinal))
    (typed : readScalar kind state.accumulator = .value value) :
    effectStep program state = ⟨.next {state with
      pc := state.pc + 1
      receiver := fun index => if index = ordinal then some value else state.receiver index},[⟨ordinal,value⟩]⟩ := by
  simp only [effectStep,code,typed]

end Aurora.SourceBinding
