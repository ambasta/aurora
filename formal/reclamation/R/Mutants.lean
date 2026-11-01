import R.Witnesses
namespace Aurora.R
namespace Mutants
open Witness

/-- Sealing after local close but before the pending registration settles violates
our concrete barrier, even though Q's existing invariant alone cannot see it. -/
def prematureGate := edit s10 0 (fun e => { e with sealed := true })
theorem premature_gate_breaks_barrier : ¬ LocalInvariant prematureGate := by
  intro h
  have bad := h.gateBarrier 0 (entryAt prematureGate 0) a rfl rfl rfl
    (0, 1) ⟨some b, false⟩ rfl rfl
  contradiction

/-- Submission disabling is not work completion. -/
def prematureDrain := edit s20 4 (fun e => { e with closed := true, sealed := true })
theorem premature_drain_breaks_local_safety : ¬ LocalInvariant prematureDrain := by
  intro h
  have bad := (h.sealedSafe 4 (entryAt prematureDrain 4) rfl rfl).2 b rfl
  contradiction

/-- A late-publication implementation that reopens a tombstoned activation is
not the protocol's publication handler (which never changes `closed`). -/
def reopen := edit s15 0 (fun e => { e with published := true, closed := false })
theorem late_publication_reopen_breaks_seal : ¬ LocalInvariant reopen := by
  intro h
  have bad := (h.sealedSafe 0 (entryAt reopen 0) rfl rfl).1
  contradiction

/-- Reallocating for an already registered operation destroys retained reply
binding. This is a provenance failure, not itself a physical-unsafety theorem. -/
def duplicateRegistration := register s5 (0, 0) (.use a)
theorem duplicate_registration_breaks_binding : ¬ LocalInvariant duplicateRegistration := by
  intro h
  have packet : Packet.grant (0, 0) 1 ∈ duplicateRegistration.packets := by decide
  have bad := (h.packetsValid _ packet).2
  contradiction

/-- Applying a valid gate receipt to a different, still executable use is not
identity-checked reception; the abstract receipt-soundness invariant detects it. -/
def misboundReceipt := edit s20 4 (fun e => { e with receipt := true })
theorem misbound_receipt_breaks_Q : ¬ Q.Invariant (project misboundReceipt) := by
  intro h
  have bad := (h.entriesOK 4 (abstractEntry (entryAt misboundReceipt 4)) rfl).receiptSound rfl
  contradiction

/-- A bypass exposes work without a live registration liability. This extends
rather than uses the protocol's guarded publication transition. -/
def uncoveredPublication :=
  edit (issue s3 0 (.use a)) 1 (fun e => { e with live := false, published := true, work := 1 })
theorem uncovered_publication_breaks_Q : ¬ Q.Invariant (project uncoveredPublication) := by
  intro h
  have bad := (h.entriesOK 1 (abstractEntry (entryAt uncoveredPublication 1)) rfl).covered rfl
  contradiction


/-- The sole extra mutant rule emits a drain receipt on submission closure,
without waiting for the actual outstanding work to finish. -/
inductive PrematureReceipt : State CPU → State CPU → Prop where
  | emit (s : State CPU) (i : Nat) (e : Entry CPU) (agent : CPU)
      (found : s.entries i = some e) (use : e.kind = .use agent)
      (closed : e.closed = true) :
      PrematureReceipt s (enqueue s (.receipt e.generation i))

def forged := enqueue s26 (.receipt 0 4)
def badAccepted := edit forged 4 (fun e => { e with receipt := true })
def badRetired := edit badAccepted 4 (fun e => { e with live := false })
def badQuiet : State CPU := { badRetired with phase := .quiescent }
def badReused : State CPU := { badQuiet with generation := 1, phase := .active }

theorem false_drain_breaks_origin : ¬ LocalInvariant forged := by
  intro h
  have bad := receipt_sealed h (i := 4) (generation := 0) (by decide)
    (e := entryAt forged 4) rfl
  contradiction

private theorem bad_bound (found : badRetired.entries i = some e) : i < 5 := by
  by_cases same : i = 4
  · omega
  · have original : s26.entries i = some e := by
      change (if i = 4 then some _ else if i = 4 then some _ else s26.entries i) = some e at found
      simpa only [if_neg same] using found
    exact Q.registered_lt (reachable_invariant reaches26).1 (project_found original)

private theorem bad_entry_facts (i : Nat) (bound : i < 5) :
    (badRetired.entries i).map Entry.live = some false ∧
    (badRetired.entries i).map Entry.receipt = some true := by
  have cases : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 := by omega
  rcases cases with h | h | h | h | h <;> subst i <;> exact ⟨rfl, rfl⟩

private theorem bad_empty : LedgerEmpty badRetired := by
  intro i e found
  have live := (bad_entry_facts i (bad_bound found)).1
  rw [found] at live
  exact Option.some.inj live

private theorem bad_gates : GatesAcknowledged badRetired := by
  intro i e agent found kind
  have receipt := (bad_entry_facts i (bad_bound found)).2
  rw [found] at receipt
  exact Option.some.inj receipt

/-- All steps AFTER the one premature receipt are original protocol steps. -/
theorem false_drain_suffix :
    Trace forged [.internal, .internal, .internal, .reuse 0] badReused := by
  apply Trace.cons (.receiveReceipt forged 4 0 (entryAt forged 4) (by decide) rfl rfl)
  apply Trace.cons (.retire badAccepted 4 (entryAt badAccepted 4) rfl rfl)
  apply Trace.cons (.quiesce badRetired rfl bad_empty bad_gates)
  exact .cons (.reuse badQuiet rfl) (.nil badReused)

/-- Actual post-reuse old-generation access from an originally reachable state,
not just an invariant failure or a renamed abstract Q counterexample. -/
theorem false_drain_actual_old_access :
    Reachable s26 ∧ PrematureReceipt s26 forged ∧
    Trace forged [.internal, .internal, .internal, .reuse 0] badReused ∧
    badReused.generation = 1 ∧ Step badReused (.access 0 4) badReused := by
  exact ⟨reaches26, .emit s26 4 (entryAt s26 4) b rfl rfl rfl,
    false_drain_suffix, rfl, .effect badReused 4 (entryAt badReused 4) b rfl rfl (by decide)⟩

/-- Losing every packet does not erase the remaining live use. No fairness or
partition recovery is claimed; indefinitely taking stutters remains admitted. -/
def lostPackets : State CPU := { s26 with packets := [] }
theorem loss_preserves_liability : Reachable lostPackets ∧ ¬ LedgerEmpty lostPackets := by
  refine ⟨Reaches.trans reaches26 (Reaches.single (.lose s26 [] (by simp))), ?_⟩
  intro empty
  have bad := empty 4 (entryAt lostPackets 4) rfl
  contradiction

end Mutants
end Aurora.R
