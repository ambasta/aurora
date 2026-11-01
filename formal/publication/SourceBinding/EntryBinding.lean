import SourceBinding.ExprCode
import SourceBinding.MethodSyntax
namespace Aurora.SourceBinding

structure ParameterBinding where
  kind : GuardType
  slot : Nat
  deriving BEq, DecidableEq

def parameterSlot (bindings : List ParameterBinding) (index : Nat) : Nat :=
  ((bindings[index]?).map (·.slot)).getD 0

def parameterKind (bindings : List ParameterBinding) (index : Nat) : GuardType :=
  ((bindings[index]?).map (·.kind)).getD .word

/-- Independent declaration/entry relation, not a predicate on checker success.
    Positive distinct slots reserve zero as the absent-parameter sentinel. -/
def EntryCode (program : Program) (formals : List Formal) (bindings : List ParameterBinding) : Prop :=
  bindings.length = formals.length ∧
  (bindings.map (·.slot)).Nodup ∧
  ∀ index, index < bindings.length →
    0 < parameterSlot bindings index ∧
    (formals[index]?).map (·.type) = some (guardSourceType (parameterKind bindings index)) ∧
    program index = some (.bind (parameterKind bindings index) index (parameterSlot bindings index))

instance (program : Program) (formals : List Formal) (bindings : List ParameterBinding) :
    Decidable (EntryCode program formals bindings) := by
  unfold EntryCode
  exact inferInstance

structure CheckedEntry (program : Program) (formals : List Formal) where
  bindings : List ParameterBinding
  code : EntryCode program formals bindings

def checkEntry (program : Program) (formals : List Formal) : Option (CheckedEntry program formals) := do
  let bindings ← (List.range formals.length).mapM fun index => do
    match program index with
    | some (.bind kind _ slot) => pure (⟨kind,slot⟩ : ParameterBinding)
    | _ => none
  if code : EntryCode program formals bindings then return ⟨bindings,code⟩ else none

/-- Pure mathematical state after the first n bindings; no machine effects other
    than the explicitly initialized local slots are hidden in this definition. -/
def preparedEntry (base : Machine) (slots : Nat → Nat) : Nat → Machine
  | 0 => { base with pc := 0, accumulator := none, stack := [], locals := fun _ => none }
  | n + 1 => { (preparedEntry base slots n) with
      pc := n + 1
      locals := fun slot => if slot = slots n then base.arguments n else (preparedEntry base slots n).locals slot }

@[simp] theorem prepared_receiver (base : Machine) (slots : Nat → Nat) (n : Nat) :
    (preparedEntry base slots n).receiver = base.receiver := by induction n <;> simp_all [preparedEntry]
@[simp] theorem prepared_arguments (base : Machine) (slots : Nat → Nat) (n : Nat) :
    (preparedEntry base slots n).arguments = base.arguments := by induction n <;> simp_all [preparedEntry]
@[simp] theorem prepared_pc (base : Machine) (slots : Nat → Nat) (n : Nat) :
    (preparedEntry base slots n).pc = n := by cases n <;> rfl
@[simp] theorem prepared_accumulator (base : Machine) (slots : Nat → Nat) (n : Nat) :
    (preparedEntry base slots n).accumulator = none := by induction n <;> simp_all [preparedEntry]
@[simp] theorem prepared_stack (base : Machine) (slots : Nat → Nat) (n : Nat) :
    (preparedEntry base slots n).stack = [] := by induction n <;> simp_all [preparedEntry]

/-- All supplied arguments used by this prefix are represented values of the
    declared scalar kind, including u64 range. No guard outcome is assumed. -/
def EntryArguments (bindings : List ParameterBinding) (arguments : Nat → Option Value) : Prop :=
  ∀ index, index < bindings.length → ∃ value, arguments index = some value ∧
    readScalar (parameterKind bindings index) (some value) = .value value

theorem entry_runs {program : Program} {formals : List Formal} {bindings : List ParameterBinding}
    (code : EntryCode program formals bindings) (base : Machine)
    (arguments : EntryArguments bindings base.arguments) :
    Runs program (preparedEntry base (parameterSlot bindings) 0)
      (.next (preparedEntry base (parameterSlot bindings) bindings.length)) := by
  have go : ∀ n, n ≤ bindings.length →
      Runs program (preparedEntry base (parameterSlot bindings) 0)
        (.next (preparedEntry base (parameterSlot bindings) n)) := by
    intro n bound
    induction n with
    | zero => exact .reflexive
    | succ n ih =>
      have less : n < bindings.length := by omega
      obtain ⟨value,valueEq,typed⟩ := arguments n less
      have first := (code.2.2 n less).2.2
      apply (ih (by omega)).trans
      apply Runs.one
      simp only [step,prepared_pc,first,prepared_arguments,valueEq,typed]
      simp only [preparedEntry,valueEq,prepared_arguments]
  exact go bindings.length (Nat.le_refl _)

theorem prepared_empty_slot (base : Machine) (slots : Nat → Nat) (n slot : Nat)
    (unused : ∀ index, index < n → slots index ≠ slot) :
    (preparedEntry base slots n).locals slot = none := by
  induction n with
  | zero => rfl
  | succ n ih =>
    have different : slot ≠ slots n := Ne.symm (unused n (by omega))
    simp only [preparedEntry,if_neg different]
    exact ih (fun index bound => unused index (by omega))

theorem prepared_parameter (base : Machine) (slots : Nat → Nat) (count n index : Nat)
    (distinct : ∀ i, i < count → ∀ j, j < count → slots i = slots j → i = j)
    (bound : n ≤ count) (valid : index < n) :
    (preparedEntry base slots n).locals (slots index) = base.arguments index := by
  induction n with
  | zero => omega
  | succ n ih =>
    by_cases last : index = n
    · subst index; simp [preparedEntry]
    · have different : slots index ≠ slots n := by
        intro same; exact last (distinct index (by omega) n (by omega) same)
      simp only [preparedEntry,if_neg different]
      exact ih (by omega) (by omega)

/-- Source formals beyond the declared finite list do not denote parameters. -/
def entrySource (base : Machine) (count : Nat) : SourceState :=
  ⟨base.receiver,fun index => if index < count then base.arguments index else none⟩

theorem parameterSlot_injective {bindings : List ParameterBinding}
    (unique : (bindings.map (·.slot)).Nodup) {i j : Nat}
    (hi : i < bindings.length) (hj : j < bindings.length)
    (same : parameterSlot bindings i = parameterSlot bindings j) : i = j := by
  have first := List.getElem?_eq_getElem hi
  have second := List.getElem?_eq_getElem hj
  simp only [parameterSlot,first,second,Option.map_some,Option.getD_some] at same
  have mapped : (bindings.map (·.slot))[i]? = (bindings.map (·.slot))[j]? := by
    simp [List.getElem?_map,first,second,same]
  exact List.getElem?_inj (by simpa using hi) unique mapped

theorem entry_context {program : Program} {formals : List Formal} {bindings : List ParameterBinding}
    (code : EntryCode program formals bindings) (base : Machine) :
    ContextRelated (entrySource base bindings.length)
      (preparedEntry base (parameterSlot bindings) bindings.length) (parameterSlot bindings) := by
  constructor
  · intro index; simp [entrySource]
  · intro index
    by_cases valid : index < bindings.length
    · simpa [entrySource,valid] using prepared_parameter base (parameterSlot bindings)
        bindings.length bindings.length index
        (fun i hi j hj same => parameterSlot_injective code.2.1 hi hj same)
        (Nat.le_refl _) valid
    · have absent : parameterSlot bindings index = 0 := by
        simp [parameterSlot,List.getElem?_eq_none (by omega : bindings.length ≤ index)]
      simp only [entrySource,valid,if_false,absent]
      exact prepared_empty_slot base (parameterSlot bindings) bindings.length 0
        (fun i hi => Nat.ne_of_gt (code.2.2 i hi).1)

@[simp] theorem prepared_frame (base : Machine) (slots : Nat → Nat) (n : Nat) :
    frameState (preparedEntry base slots n) n none [] = preparedEntry base slots n := by
  cases n <;> simp [frameState,preparedEntry,prepared_accumulator,prepared_stack]

/-- Entry binding establishes the expression context. The source parameter map
    is exactly the declared arguments, and the source field map is the receiver. -/
theorem entry_expression_runs {program : Program} {formals : List Formal}
    {bindings : List ParameterBinding} {kind : GuardType} {expression : GuardExpr kind} {stop : Nat}
    (entry : EntryCode program formals bindings)
    (code : ExprCode program (parameterSlot bindings) expression formals.length stop)
    (base : Machine) (arguments : EntryArguments bindings base.arguments) :
    Runs program (preparedEntry base (parameterSlot bindings) 0)
      (finish (preparedEntry base (parameterSlot bindings) bindings.length) stop []
        (evalGuard (entrySource base bindings.length) expression)) := by
  have expressionRun := code.simulates (entrySource base bindings.length)
    (preparedEntry base (parameterSlot bindings) bindings.length) (entry_context entry base) none []
  rw [← entry.1,prepared_frame] at expressionRun
  exact (entry_runs entry base arguments).trans expressionRun

theorem check_entry_sound (program : Program) (formals : List Formal)
    (result : CheckedEntry program formals) (_accepted : checkEntry program formals = some result) :
    EntryCode program formals result.bindings := result.code

end Aurora.SourceBinding
