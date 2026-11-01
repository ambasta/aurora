import A.Completion
import A.Witnesses
namespace Aurora.A.Snapshot

/-- The abstract counterpart of snapshot publication: completion evidence for
one admitted writable stream is consumed before read admission is enabled.
No byte heap, page-table downgrade or compiler/native refinement is asserted. -/
def sealFromReceipt (s : State Agent) (generation origin : Nat) : State Agent :=
  readEnable (move (move s generation (.gate origin)) generation (.frozen origin)) origin

variable {s : State Agent}

theorem seal_receipt_bridge
    (reachable : Reachable issuer initialSubject allocation s)
    (registered : s.protocol.registrations r = some i)
    (payload : s.payloads r = some p) (writer : p.grant.writable = true)
    (found : s.protocol.entries i = some e) (use : e.kind = .use p.grant.subject)
    (receipt : e.receipt = true) (held : s.tokens p.grant.generation = .use i)
    (current : p.grant.generation = s.protocol.generation) :
    Reachable issuer initialSubject allocation (sealFromReceipt s p.grant.generation p.origin) ∧
    (sealFromReceipt s p.grant.generation p.origin).readable p.origin = true ∧
    Frozen (sealFromReceipt s p.grant.generation p.origin) s.protocol.generation ∧
    (∀ ticket cell, ¬Enabled (sealFromReceipt s p.grant.generation p.origin) ticket cell true) := by
  have h := reachable_invariant reachable
  obtain ⟨q, parent, _, hg, origin, derived⟩ := h.payloadBound r p payload
  have parentGen : parent.generation = p.grant.generation := derived.2.2.1.symm
  have parentAt : s.grants p.origin = some parent := by simpa [origin] using hg
  have returned : Step issuer initialSubject allocation s .internal
      (move s p.grant.generation (.gate p.origin)) :=
    .returnUse s r i e p registered payload writer found use receipt held
  have sealedStep : Step issuer initialSubject allocation
      (move s p.grant.generation (.gate p.origin)) .internal
      (sealFromReceipt s p.grant.generation p.origin) := by
    simpa [sealFromReceipt, parentGen] using
      (Step.freeze (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
        (move s p.grant.generation (.gate p.origin)) p.origin parent parentAt
        (by simp [move, parentGen]))
  have reached : Reachable issuer initialSubject allocation (sealFromReceipt s p.grant.generation p.origin) :=
    Reaches.trans reachable ((Reaches.single returned).trans (Reaches.single sealedStep))
  have frozen : Frozen (sealFromReceipt s p.grant.generation p.origin) s.protocol.generation :=
    ⟨p.origin, by simp [sealFromReceipt, readEnable, move, current]⟩
  refine ⟨reached, by simp [sealFromReceipt, readEnable], frozen, ?_⟩
  intro ticket cell
  exact reachable_frozen_no_write reached frozen

/-- Native `fill_snapshot` tests building phase, epoch and bounds. The A0
counterpart guarantees the effect's backing bounds from admitted authority;
it does not claim the native memcpy or physical alias decoder is verified. -/
theorem fill_cell_is_authorized
    (reachable : Reachable issuer initialSubject allocation s)
    (fill : Enabled s ticket cell true) : allocation.Contains cell ∧
      ¬Frozen s s.protocol.generation := by
  refine ⟨reachable_effect_bounds reachable fill, ?_⟩
  intro frozen
  exact reachable_frozen_no_write reachable frozen fill

/-- Two aliasing read consumers are admitted by the target protocol, unlike the
current single lexical native parser pin. The fill and seal phases stay Active. -/
theorem checked_fill_seal_shared_read_contract :
    Witness.Reached Witness.s7 ∧ Witness.Reached Witness.s12 ∧ Witness.Reached Witness.s22 ∧
    Witness.s12.protocol.phase = .active ∧ Frozen Witness.s12 0 ∧
    Enabled Witness.s22 2 5 false ∧ Enabled Witness.s22 3 5 false := by
  exact ⟨Witness.reaches7, Witness.reaches12, Witness.reaches22, rfl, ⟨0,rfl⟩,
    Witness.overlapping_readers.2.2.1, Witness.overlapping_readers.2.2.2⟩

end Aurora.A.Snapshot
