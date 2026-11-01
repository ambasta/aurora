import Q.Witnesses

namespace Aurora.Q
namespace Mutants

/- These are intentionally WRONG protocol rules, not axioms or changes to Step.
   Their concrete counterexamples use the SAME physical access/admission rules. -/
inductive Fault : State Cpu → State Cpu → Prop where
  | uncoveredPublication (s : State Cpu) (c : Cpu) :
      Fault s (put (issue s s.generation (.gate c)) s.next
        ⟨s.generation, .gate c, false, true, false⟩)
  | prematureAck (s : State Cpu) (i : Nat) (e : Entry Cpu)
      (found : s.entries i = some e) : Fault s (put s i (acknowledged e))
  | lostTransfer (s : State Cpu) (i : Nat) (e : Entry Cpu) (c : Cpu)
      (found : s.entries i = some e) (transfer : e.kind = .transfer c) :
      Fault s (put s i (retired e))
  /- Abstracts a duplicate aggregate decrement wrongly consuming another ticket.
     This is NOT a claim that the identity-keyed Step implementation has a counter. -/
  | duplicateSubtract (s : State Cpu) (ackID victim : Nat) (a e : Entry Cpu)
      (ackFound : s.entries ackID = some a) (receipt : a.receipt = true)
      (victimFound : s.entries victim = some e) : Fault s (put s victim (retired e))
  | replayActivation (s : State Cpu) (i : Nat) (e : Entry Cpu) (c : Cpu)
      (found : s.entries i = some e) (transfer : e.kind = .transfer c) :
      Fault s (issue s e.generation (.gate c))
  | epochOnlyReuse (s : State Cpu) :
      Fault s { s with generation := s.generation + 1, phase := .active }

variable {Cpu : Type} {s : State Cpu} {e : Entry Cpu}

theorem uncovered_violates (found : s.entries i = some e)
    (possible : e.possible = true) (uncovered : e.live = false) : ¬ Invariant s := by
  intro h
  have live := (h.entriesOK i e found).covered possible
  simp [uncovered] at live

theorem premature_receipt_violates (found : s.entries i = some e)
    (possible : e.possible = true) (receipt : e.receipt = true) : ¬ Invariant s := by
  intro h
  have stopped := (h.entriesOK i e found).receiptSound receipt
  simp [possible] at stopped

open Witness

theorem reachable2 : Reachable s2 := by
  apply Reaches.trans (Reaches.single (.root s0 a rfl))
  exact Reaches.single (.admit s1 0 gateA a rfl rfl rfl)

theorem reachable3 : Reachable s3 :=
  Reaches.trans reachable2 (Reaches.single (.send s2 0 gateA a b rfl rfl rfl))

theorem uncovered_publication_counterexample :
    ∃ t : State CPU, Reachable s0 ∧ Fault s0 t ∧ ¬ Invariant t := by
  refine ⟨_, ⟨[], .nil s0⟩, .uncoveredPublication s0 a, ?_⟩
  exact uncovered_violates (i := 0) (by rfl) rfl rfl

theorem premature_fence_ack_counterexample :
    Reachable s2 ∧ Fault s2 (put s2 0 (acknowledged gateA)) ∧
      ¬ Invariant (put s2 0 (acknowledged gateA)) := by
  exact ⟨reachable2, .prematureAck s2 0 gateA rfl,
    premature_receipt_violates (e := acknowledged gateA) (i := 0) (by simp [put]) rfl rfl⟩

theorem premature_drain_ack_counterexample :
    Reachable s2 ∧ Fault s2 (put s2 1 (acknowledged useA)) ∧
      ¬ Invariant (put s2 1 (acknowledged useA)) := by
  exact ⟨reachable2, .prematureAck s2 1 useA rfl,
    premature_receipt_violates (e := acknowledged useA) (i := 1) (by simp [put]) rfl rfl⟩

theorem lost_transfer_counterexample :
    Reachable s3 ∧ Fault s3 (put s3 2 (retired transferB)) ∧
      ¬ Invariant (put s3 2 (retired transferB)) := by
  exact ⟨reachable3, .lostTransfer s3 2 transferB b rfl rfl,
    uncovered_violates (e := retired transferB) (i := 2) (by simp [put]) rfl rfl⟩

def gateFinished := finish s2 0 gateA

theorem gateFinished_reachable : Reachable gateFinished :=
  Reaches.trans reachable2 (finish_reaches (s := s2) (i := 0) (e := gateA) rfl)

theorem duplicate_subtraction_counterexample :
    Reachable gateFinished ∧ Fault gateFinished (put gateFinished 1 (retired useA)) ∧
      ¬ Invariant (put gateFinished 1 (retired useA)) := by
  exact ⟨gateFinished_reachable,
    .duplicateSubtract gateFinished 0 1 (retired (acknowledged (stopped gateA))) useA
      rfl rfl rfl,
    uncovered_violates (e := retired useA) (i := 1) (by simp [put]) rfl rfl⟩

theorem replay_after_reuse_counterexample :
    Reachable s12 ∧ Fault s12 (issue s12 0 (.gate b)) ∧
      ¬ Invariant (issue s12 0 (.gate b)) := by
  refine ⟨reaches12, .replayActivation s12 2 (resolved transferB) b rfl rfl, ?_⟩
  intro h
  have wrong := (h.entriesOK 5 ⟨0, .gate b, true, true, false⟩ rfl).liveCurrent rfl
  contradiction

/-- A bad epoch-only reuse really permits an old access under unchanged hardware
    event semantics; no hypothetical post-state invariant is assumed. -/
theorem epoch_only_reuse_counterexample :
    ∃ t : State CPU, Reachable s2 ∧ Fault s2 t ∧
      t.generation = 1 ∧ Step t (.access 0 1) t := by
  refine ⟨{ s2 with generation := 1, phase := .active }, reachable2,
    .epochOnlyReuse s2, rfl, ?_⟩
  exact .access _ 1 useA a rfl rfl rfl

/-- A false drain receipt can drive the ORIGINAL retire/quiesce/reuse rules all
    the way to an old physical access. This is the unmap-before-effective-fence
    abstract analogue; no literal unmap instruction or IOMMU implementation is modeled. -/
def closingUse : State CPU := { gateFinished with phase := .closing }
def falseReceipt := put closingUse 1 (acknowledged useA)
def falseRetired := put falseReceipt 1 (retired (acknowledged useA))
def falseQuiet : State CPU := { falseRetired with phase := .quiescent }
def falseReused : State CPU := { falseQuiet with generation := 1, phase := .active }

theorem falseRetired_entries (i : Nat) : falseRetired.entries i =
    if i = 1 then some (retired (acknowledged useA)) else
    if i = 0 then some (retired (acknowledged (stopped gateA))) else none := by
  by_cases one : i = 1
  · simp [falseRetired, put, one]
  by_cases zero : i = 0
  · simp [falseRetired, falseReceipt, closingUse, gateFinished, finish,
      s2, s1, s0, issue, put, initial, zero]
  · simp [falseRetired, falseReceipt, closingUse, gateFinished, finish,
      s2, s1, s0, issue, put, initial, one, zero]

theorem falseRetired_empty : LedgerEmpty falseRetired := by
  intro i e found
  rw [falseRetired_entries] at found
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  · cases found

theorem falseRetired_gates : GatesAcknowledged falseRetired := by
  intro i e c found gate
  rw [falseRetired_entries] at found
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  · cases found

theorem false_receipt_reuse_counterexample :
    Reachable closingUse ∧ Fault closingUse falseReceipt ∧
    Step falseReceipt .internal falseRetired ∧
    Step falseRetired .internal falseQuiet ∧
    Step falseQuiet (.reuse 0) falseReused ∧
    Step falseReused (.access 0 1) falseReused := by
  refine ⟨Reaches.trans gateFinished_reachable
    (Reaches.single (.beginClose gateFinished rfl)),
    .prematureAck closingUse 1 useA rfl,
    .retire falseReceipt 1 (acknowledged useA) rfl rfl,
    .quiesce falseRetired rfl falseRetired_empty falseRetired_gates,
    .reuse falseQuiet rfl, ?_⟩
  exact .access falseReused 1 (retired (acknowledged useA)) a rfl rfl rfl

end Mutants
end Aurora.Q
