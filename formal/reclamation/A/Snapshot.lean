import A.Completion
import A.Witnesses
namespace Aurora.A.Snapshot

/-- Exact receipt return credits only its immutable reservation. Whole-snapshot
publication additionally requires coverage by that reservation and already free
cells; a broad old grant ceiling alone never supplies missing permission. -/
def returnedState (s : State Agent) (i : Nat) (p : Payload Agent) :=
  markReturned (move s p.grant.generation (.use i) (.gate p.origin) p.grant.footprint) i
def sealFromReceipt (s : State Agent) (i : Nat) (p : Payload Agent) (allocation : Footprint) :=
  readEnable (move (returnedState s i p) p.grant.generation (.gate p.origin) .frozen allocation)
    p.origin allocation

variable {s : State Agent}

theorem seal_receipt_bridge
    (reachable : Reachable issuer initialSubject allocation s)
    (registered : s.protocol.registrations r = some i)
    (payload : s.payloads r = some p) (writer : p.grant.writable = true)
    (found : s.protocol.entries i = some e) (use : e.kind = .use p.grant.subject)
    (bound : e.generation = p.grant.generation) (receipt : e.receipt = true)
    (fresh : s.returned i = false) (current : p.grant.generation = s.protocol.generation)
    (cover : allocation.Within (s.holdings p.grant.generation (.gate p.origin) ++ p.grant.footprint)) :
    Reachable issuer initialSubject allocation (sealFromReceipt s i p allocation) ∧
    allocation.Within ((sealFromReceipt s i p allocation).readable p.origin) ∧
    Frozen (sealFromReceipt s i p allocation) s.protocol.generation allocation ∧
    (∀ ticket cell, ¬Enabled (sealFromReceipt s i p allocation) ticket cell true) := by
  have h := reachable_invariant reachable
  obtain ⟨q,parent,hq,hg,origin,derived⟩ := h.payloadBound r p payload
  have parentAt : s.grants p.origin = some parent := by simpa [origin] using hg
  have parentGen : parent.generation = p.grant.generation := derived.2.2.1.symm
  obtain ⟨parentEntry,a,parentFound,parentKind⟩ := h.protocol.2.requestSource r q hq
  have sourceFound : s.protocol.entries p.origin = some parentEntry := by simpa [origin] using parentFound
  have parentSubject := (grant_entry h parentAt sourceFound).2.1
  have sourceKind : parentEntry.kind = .gate parent.subject := by
    simpa [parentKind,subject] using congrArg Q.Kind.gate parentSubject
  have ceiling : allocation.Within parent.footprint := by
    intro cell hc
    rcases List.mem_append.mp (cover hc) with free | reserved
    · obtain ⟨g,ge,hg',_,_,_,hcell⟩ := h.gateInventory _ _ _ free
      have same : g = parent := Option.some.inj (hg'.symm.trans parentAt)
      simpa [same] using hcell
    · exact derived.2.2.2.1 reserved
  have returned : Step issuer initialSubject allocation s .internal (returnedState s i p) :=
    .returnUse s r i e p registered payload writer origin found use bound receipt fresh
  have available : allocation.Within ((returnedState s i p).holdings parent.generation (.gate p.origin)) := by
    simpa [returnedState,markReturned,move,Inventory.move,parentGen] using cover
  have frozenStep : Step issuer initialSubject allocation (returnedState s i p) .internal
      (sealFromReceipt s i p allocation) := by
    simpa [sealFromReceipt,parentGen] using
      (Step.freeze (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
        (returnedState s i p) p.origin parentEntry parent allocation sourceFound sourceKind parentAt ceiling available)
  have reached : Reachable issuer initialSubject allocation (sealFromReceipt s i p allocation) :=
    Reaches.trans reachable ((Reaches.single returned).trans (Reaches.single frozenStep))
  have frozen : Frozen (sealFromReceipt s i p allocation) s.protocol.generation allocation := by
    intro cell hc
    simp [sealFromReceipt,readEnable,move,Inventory.move,←current,hc]
  refine ⟨reached,?_,frozen,?_⟩
  · intro cell hc
    simp [sealFromReceipt,readEnable,hc]
  · intro ticket cell enabled
    have finalInvariant := reachable_invariant reached
    have inside := enabled_within_allocation finalInvariant enabled
    have stable : (sealFromReceipt s i p allocation).protocol.generation = s.protocol.generation := rfl
    exact frozen_cell_excludes_enabled_write finalInvariant (by simpa [stable] using frozen inside) enabled

/-- Native fill checks building phase, epoch and bounds. This is still an
abstract backing-footprint contract, not verified memcpy or address decoding. -/
theorem fill_cell_is_authorized
    (reachable : Reachable issuer initialSubject allocation s)
    (fill : Enabled s ticket cell true) : allocation.Contains cell ∧
      cell ∉ s.holdings s.protocol.generation .frozen := by
  refine ⟨reachable_effect_bounds reachable fill,?_⟩
  intro frozen
  exact frozen_cell_excludes_enabled_write (reachable_invariant reachable) frozen fill

/-- The existing sequential fill/seal policy is also a constructive specialization
of the generalized authority model: a full-allocation writer drains before seal. -/
def serialFilled := Witness.admit Witness.s2 0 Witness.rootEntry Witness.defaultGrant Witness.allocation true
def serialDone := Witness.finishUse serialFilled 1 Witness.busyUse
def serialPayload : Payload Witness.CPU := ⟨child Witness.defaultGrant none Witness.allocation true false,0⟩
theorem serial_done_reachable : Witness.Reached serialDone := by
  apply Reaches.trans Witness.reaches2
  apply (Witness.admit_reaches Witness.s2 0 Witness.rootEntry Witness.defaultGrant Witness.allocation true
    rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)).trans
  apply (Reaches.single (.effect serialFilled 1 Witness.busyUse serialPayload.grant 11
    rfl rfl rfl (by decide) (by decide))).trans
  exact Witness.finishUse_reaches (s := serialFilled) (i := 1) (e := Witness.busyUse) rfl rfl rfl rfl

theorem serial_snapshot_receipt_contract :
    Witness.Reached (sealFromReceipt serialDone 1 serialPayload Witness.allocation) ∧
    Frozen (sealFromReceipt serialDone 1 serialPayload Witness.allocation) 0 Witness.allocation ∧
    (∀ ticket cell, ¬Enabled (sealFromReceipt serialDone 1 serialPayload Witness.allocation) ticket cell true) := by
  have bridge := seal_receipt_bridge (r := (0,0)) (i := 1) (p := serialPayload) (e := Witness.doneUse)
    serial_done_reachable rfl rfl rfl rfl rfl rfl rfl rfl rfl (by decide)
  exact ⟨bridge.1,bridge.2.2⟩

/-- Actual admitted effects demonstrate partial freezing and same-backing read
sharing alongside disjoint writable work; whole coverage is achieved later.
Current native parser pins remain single/synchronous, not this concurrency API. -/
theorem checked_fill_seal_shared_read_contract :
    Witness.Reached Witness.s4 ∧ Witness.Reached Witness.s12 ∧ Witness.Reached Witness.s23 ∧
    Frozen Witness.s12 0 Witness.left ∧ Frozen Witness.s23 0 Witness.allocation ∧
    Step 0 1 Witness.allocation Witness.s12 (.access 0 4 11 false) Witness.s12 ∧
    Step 0 1 Witness.allocation Witness.s12 (.access 0 5 11 false) Witness.s12 ∧
    Step 0 1 Witness.allocation Witness.s12 (.access 0 2 9 true) Witness.s12 := by
  exact ⟨Witness.reaches4,Witness.reaches12,Witness.successful_reuse.1,
    Witness.overlapping_readers.2.2.1,Witness.successful_reuse.2.2.2,
    Witness.overlapping_readers.2.2.2⟩
end Aurora.A.Snapshot
