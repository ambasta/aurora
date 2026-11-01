import A.Completion
import A.Witnesses
namespace Aurora.A.Mutants
open Witness

/-- Faulty permission recovery: re-create gate authority before its actual use
has drained. This is NOT an A transition. The following continuation uses only
ordinary A transitions and produces two conflicting enabled writable streams. -/
def duplicateOwner : State CPU := move s7 0 (.gate 0)
def d1 := request duplicateOwner 1 allocation true
def d2 := register d1 1
def d3 := grant d2 1 2
def d4 := pub d3 2
def d5 := submit d4 2

theorem duplicate_owner_continuation : Goes duplicateOwner d5 := by
  apply Reaches.trans (Reaches.single (.request _ 0 1 (entry duplicateOwner 0) (cap duplicateOwner 0)
    none allocation true false rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide)))
  apply Reaches.trans (Reaches.single (.register _ (0,1) none (entry d1 0) 1 (payload d1 (0,1))
    (by decide) rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.passive _ _ (.grant _ (0,1) 2 ⟨none,false⟩ (by decide) rfl)))
  apply Reaches.trans (Reaches.single (.passive _ _ (.publish _ 2 (entry d3 2) (by decide) rfl (by trivial) rfl)))
  exact Reaches.single (.submit _ 2 (entry d4 2) (cap d4 2) rfl rfl rfl rfl rfl (by intro _; rfl))

theorem duplicate_owner_actual_conflict : Reached s7 ∧ Goes duplicateOwner d5 ∧
    Enabled d5 1 5 true ∧ Enabled d5 2 5 true := by
  refine ⟨reaches7, duplicate_owner_continuation, ?_, ?_⟩
  · exact ⟨entry d5 1, cap d5 1, rfl, rfl, rfl, by decide, by decide, rfl⟩
  · exact ⟨entry d5 2, cap d5 2, rfl, rfl, rfl, by decide, by decide, rfl⟩

/-- Incorrect freeze publishes local reader admission while writable work is
still live. Existing effects do not consult a global freeze flag. -/
def prematureFreeze : State CPU := readEnable (move s7 0 (.frozen 0)) 0
def f1 := request prematureFreeze 1 ⟨4,12⟩ false
def f2 := register f1 1
def f3 := grant f2 1 2
def f4 := pub f3 2
def f5 := submit f4 2

theorem premature_freeze_continuation : Goes prematureFreeze f5 := by
  apply Reaches.trans (Reaches.single (.request _ 0 1 (entry prematureFreeze 0) (cap prematureFreeze 0)
    none ⟨4,12⟩ false false rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide)))
  apply Reaches.trans (Reaches.single (.register _ (0,1) none (entry f1 0) 1 (payload f1 (0,1))
    (by decide) rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.passive _ _ (.grant _ (0,1) 2 ⟨none,false⟩ (by decide) rfl)))
  apply Reaches.trans (Reaches.single (.passive _ _ (.publish _ 2 (entry f3 2) (by decide) rfl (by trivial) rfl)))
  exact Reaches.single (.submit _ 2 (entry f4 2) (cap f4 2) rfl rfl rfl rfl rfl (by decide))

theorem premature_freeze_actual_conflict : Reached s7 ∧ Goes prematureFreeze f5 ∧
    Enabled f5 1 5 true ∧ Enabled f5 2 5 false := by
  refine ⟨reaches7, premature_freeze_continuation, ?_, ?_⟩
  · exact ⟨entry f5 1, cap f5 1, rfl, rfl, rfl, by decide, by decide, rfl⟩
  · exact ⟨entry f5 2, cap f5 2, rfl, rfl, rfl, by decide, by decide, rfl⟩

/-- Loss/timeout is not a permission return: a request in flight remains sole
owner even before registration. This mutant breaks conserved escrow coverage. -/
def timeoutRestore : State CPU := move s3 0 (.gate 0)
theorem timeout_loses_escrow : Reached s3 ∧ ¬Invariant allocation timeoutRestore := by
  refine ⟨step1.trans (step2.trans step3), ?_⟩
  intro h
  have pending := h.pendingWriter (0,0) (payload s3 (0,0)) rfl rfl rfl
  change Location.gate 0 = .request (0,0) at pending
  contradiction

/-- A changed generation in an admitted immutable descriptor no longer matches
its registered backing-version ticket. It is an identity failure, not claimed
as a complete physical stale-use execution. -/
def staleRebind : State CPU := putGrant s7 1 { cap s7 1 with generation := 1 }
theorem stale_descriptor_rebinding_breaks_identity : Reached s7 ∧ ¬Invariant allocation staleRebind := by
  refine ⟨reaches7, ?_⟩
  intro h
  have bound := grant_entry h (i := 1) (g := { cap s7 1 with generation := 1 })
    (e := entry s7 1) (by simp [staleRebind, putGrant]) rfl
  have impossible : (0 : Nat) = 1 := bound.1
  contradiction

theorem checked_attenuation_refusals :
    ¬(⟨0,17⟩ : Extent).Within allocation ∧
    ¬(cap s22 2).writable = true ∧
    ¬s7.tokens 0 = .gate 0 ∧ ¬s3.tokens 0 = .gate 0 ∧
    ¬(cap Witness.d8 2).delegates = true ∧
    ¬(entry Witness.d8 2).kind = .gate 1 ∧
    ¬(⟨0,16⟩ : Extent).Within (cap Witness.d8 2).extent := by decide

end Aurora.A.Mutants
