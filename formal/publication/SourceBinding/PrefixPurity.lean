import SourceBinding.IRSemantics
import SourceBinding.PrefixRuns
namespace Aurora.SourceBinding
open Aurora.Publication
variable {t : Tables} {id : Int}

/-- The admitted raw forms contain no calls or receiver stores. Parameter binding
    (45) may initialize locals; receiver loads (32) are read-only. -/
def PurePrefixForm (form : Int) : Prop :=
  form ∈ ([5,7,9,11,12,14,32,40,41,42,43,45] : List Int)
instance (form : Int) : Decidable (PurePrefixForm form) := by
  unfold PurePrefixForm; infer_instance

/-- Complete static coverage of EVERY normalized position below the cutpoint,
    including unreachable rows. Exact optional indexing forbids default rows.
    This is not itself a reachability, source correspondence, or tail property. -/
def NoCallStore (t : Tables) (id : Int) (cut : Nat) : Prop :=
  cut ≤ (functionCode t id).size ∧
  ∀ pc ∈ List.range cut,
    ∃ row ∈ (functionCode t id)[pc]?.toList,
      row.integer 1 = Int.ofNat pc ∧ PurePrefixForm (row.integer 6)
instance (t : Tables) (id : Int) (cut : Nat) : Decidable (NoCallStore t id cut) := by
  unfold NoCallStore; infer_instance

structure CheckedPurePrefix (t : Tables) (id : Int) (cut : Nat) : Type where
  pure : NoCallStore t id cut

def checkPurePrefix (t : Tables) (id : Int) (cut : Nat) :
    Option (CheckedPurePrefix t id cut) :=
  if proof : NoCallStore t id cut then some ⟨proof⟩ else none

theorem checked_pure_prefix_sound (result : CheckedPurePrefix t id cut)
    (_accepted : checkPurePrefix t id cut = some result) : NoCallStore t id cut := result.pure

theorem NoCallStore.lookup (pure : NoCallStore t id cut) (before : pc < cut) :
    ∃ row, (functionCode t id)[pc]? = some row ∧
      row.integer 1 = Int.ofNat pc ∧ PurePrefixForm (row.integer 6) := by
  obtain ⟨row, member, facts⟩ := pure.2 pc (List.mem_range.mpr before)
  cases eq : (functionCode t id)[pc]? with
  | none => simp [eq] at member
  | some actual =>
    simp only [eq, Option.toList_some, List.mem_singleton] at member
    subst row
    exact ⟨actual,rfl,facts⟩

/-- An operation's independent canonical meaning excludes every call/store raw
    form, regardless of how its candidate was projected. -/
theorem OperationMeaning.pure_form (meaning : OperationMeaning t id row operation) :
    PurePrefixForm (row.integer 6) := by
  rcases meaning with ⟨_,_,_,meaning⟩
  cases operation
  all_goals first
    | (split at meaning <;> simp_all [PurePrefixForm, Aurora.Publication.SignedCount12])
    | simp_all [PurePrefixForm, Aurora.Publication.SignedCount12]

/-- Decoder-present canonical positions carry both exact-row provenance and the
    independent no-call/store form fact. No missing/default instruction is read. -/
theorem canonical_pure_form (accepted : canonicalProgram t id pc = some operation) :
    ∃ row, (functionCode t id)[pc]? = some row ∧
      row.integer 1 = Int.ofNat pc ∧ PurePrefixForm (row.integer 6) := by
  obtain ⟨row, index, position, meaning⟩ := canonical_program_sound t id pc operation accepted
  exact ⟨row,index,position,meaning.pure_form⟩

/-- All modeled normal steps preserve receiver and argument mappings. Binding
    may change locals; no claim is made about a machine after return or trap. -/
theorem step_preserves_receiver_arguments
    (normal : step program initial = .next final) :
    final.receiver = initial.receiver ∧ final.arguments = initial.arguments := by
  unfold step at normal
  split at normal
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals cases normal
  all_goals exact ⟨rfl,rfl⟩

/-- Every finite observed normal state preserves receiver/arguments, even if an
    eventual return/trap erases its final machine. This does not model concurrent
    environment mutation, native execution, or resource effects in the tail. -/
theorem Runs.preserves_receiver_arguments (run : Runs program initial (.next final)) :
    final.receiver = initial.receiver ∧ final.arguments = initial.arguments := by
  generalize ending : Execution.next final = result at run
  induction run generalizing final with
  | reflexive => cases ending; exact ⟨rfl,rfl⟩
  | next first tail ih =>
    obtain ⟨receiver,arguments⟩ := step_preserves_receiver_arguments first
    obtain ⟨laterReceiver,laterArguments⟩ := ih ending
    exact ⟨laterReceiver.trans receiver,laterArguments.trans arguments⟩
  | returned _ => cases ending
  | trap _ => cases ending

/-- Every nonterminal successor remains inside or exactly at the cutpoint. -/
def OpBound (cut pc : Nat) : Op → Prop
  | .jump target => target ≤ cut
  | .branchFalse target => target ≤ cut ∧ pc + 1 ≤ cut
  | .ret => True
  | _ => pc + 1 ≤ cut
instance (cut pc : Nat) (operation : Op) : Decidable (OpBound cut pc operation) := by
  cases operation <;> dsimp [OpBound] <;> infer_instance

/-- All raw rows are pure AND decode to operations whose edges cannot escape the
    prefix. The canonical decoder checks exact normalized row positions. -/
def ClosedRawPrefix (t : Tables) (id : Int) (cut : Nat) : Prop :=
  NoCallStore t id cut ∧ ∀ pc ∈ List.range cut,
    ∃ operation ∈ (canonicalProgram t id pc).toList, OpBound cut pc operation
instance (t : Tables) (id : Int) (cut : Nat) : Decidable (ClosedRawPrefix t id cut) := by
  unfold ClosedRawPrefix; infer_instance

theorem ClosedRawPrefix.operation (closed : ClosedRawPrefix t id cut) (before : pc < cut) :
    ∃ operation, canonicalProgram t id pc = some operation ∧ OpBound cut pc operation := by
  obtain ⟨operation, member, bound⟩ := closed.2 pc (List.mem_range.mpr before)
  cases eq : canonicalProgram t id pc with
  | none => simp [eq] at member
  | some actual =>
    simp only [eq, Option.toList_some, List.mem_singleton] at member
    subst operation
    exact ⟨actual,rfl,bound⟩

theorem step_preserves_bound (decoded : program initial.pc = some operation)
    (bound : OpBound cut initial.pc operation) (normal : step program initial = .next final) :
    final.pc ≤ cut := by
  unfold step at normal
  rw [decoded] at normal
  cases operation <;> simp only [OpBound] at bound
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals try simp only [finish] at normal
  all_goals try split at normal
  all_goals cases normal
  all_goals first | exact bound | exact bound.1 | exact bound.2

/-- Every actual normal step below the cutpoint stays at/below it and preserves
    receiver/arguments. Combined with first-exit stopping at equality, this covers
    every executed prefix instruction, without making claims about the tail. -/
theorem ClosedRawPrefix.step_invariant (closed : ClosedRawPrefix t id cut)
    (before : initial.pc < cut) (normal : step (canonicalProgram t id) initial = .next final) :
    final.pc ≤ cut ∧ final.receiver = initial.receiver ∧ final.arguments = initial.arguments := by
  obtain ⟨operation, decoded, bound⟩ := closed.operation before
  exact ⟨step_preserves_bound decoded bound normal, step_preserves_receiver_arguments normal⟩

/-- Normal states along any finite stalled-prefix trace stay within the covered
    raw rows (or at the nonexecuted cutpoint), with the original receiver/arguments. -/
theorem ClosedRawPrefix.trace_invariant (closed : ClosedRawPrefix t id cut)
    (run : Runs (stallAt (canonicalProgram t id) cut) initial (.next final))
    (inside : initial.pc ≤ cut) :
    final.pc ≤ cut ∧ final.receiver = initial.receiver ∧ final.arguments = initial.arguments := by
  have preserved := run.preserves_receiver_arguments
  refine ⟨?_,preserved⟩
  clear preserved
  generalize ending : Execution.next final = result at run
  induction run generalizing final with
  | reflexive => cases ending; exact inside
  | @next initial middle result first tail ih =>
    by_cases hitCut : initial.pc = cut
    · rw [step_stall_at hitCut] at first
      cases first
      exact ih inside ending
    · rw [step_stall_away hitCut] at first
      have before : initial.pc < cut := Nat.lt_of_le_of_ne inside hitCut
      exact ih (closed.step_invariant before first).1 ending
  | returned _ => cases ending
  | trap _ => cases ending

end Aurora.SourceBinding
