import SourceBinding.MemoryManagerReleaseFacts

namespace Aurora.SourceBinding.MemoryManagerRelease

/-- Source-facing mathematical facts, not source evaluation or assumed helper
results. SlotMatches preserves the real owner_slot first/second priority. -/
structure ReleaseGuardFacts (ledger : Ledger extent) (position : Fin extent)
    (owner next : Nat) (slot : OwnerSlot) : Prop where
  selected : SlotMatches ledger.fields owner slot
  heldPositive : 0 < heldCount ledger.fields slot
  allocatedPositive : 0 < ledger.fields.allocatedCount
  heldLeAllocated : heldCount ledger.fields slot ≤ ledger.fields.allocatedCount
  nextKind : FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4
  freeLink : FramePolicy.stateOf next = 1 → FramePolicy.wordOf next = ledger.fields.head
  retiredLink : FramePolicy.stateOf next = 4 → FramePolicy.wordOf next = 0
  freeRoom : FramePolicy.stateOf next = 1 → ledger.fields.freeCount < extent
  nextBound : next < FramePolicy.u64Modulus
  allocatedDecrementBound : ledger.fields.allocatedCount - 1 < FramePolicy.u64Modulus
  heldDecrementBound : heldCount ledger.fields slot - 1 < FramePolicy.u64Modulus
  freeIncrementBound : FramePolicy.stateOf next = 1 → ledger.fields.freeCount + 1 < FramePolicy.u64Modulus
  indexIncrementWordBound : position.val + 1 ≤ FramePolicy.wordMax
  indexIncrementBound : position.val + 1 < FramePolicy.u64Modulus

private theorem release_accepted_kind
    (accepted : FramePolicy.transition .release record owner generation link = .accept state gen word) :
    state = 1 ∨ state = 4 := by
  simp only [FramePolicy.transition,reduceCtorEq,if_false] at accepted
  split at accepted
  · cases accepted
  next =>
    split at accepted
    · cases accepted
    next =>
      split at accepted
      · cases accepted
      next =>
        split at accepted
        · cases accepted
        next =>
          split at accepted
          · cases accepted
          next =>
            split at accepted
            · cases accepted
            next =>
              split at accepted
              · cases accepted
              next =>
                split at accepted
                · cases accepted
                next =>
                  split at accepted
                  · cases accepted; exact Or.inr rfl
                  · cases accepted; exact Or.inl rfl

private theorem nonzero_release_kind
    (specified : FramePolicy.ResultSpec .release record owner generation link next)
    (nonzero : FramePolicy.stateOf next ≠ 0) :
    FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4 := by
  cases decision : FramePolicy.transition .release record owner generation link with
  | reject reason =>
    have encoded := specified.trans (congrArg FramePolicy.encode decision)
    have zero : FramePolicy.stateOf next = 0 := by rw [encoded]; cases reason <;> decide
    exact False.elim (nonzero zero)
  | accept state gen word =>
    have encoded := specified.trans (congrArg FramePolicy.encode decision)
    have canonical := FramePolicy.accepted_canonical decision
    have fields := FramePolicy.pack_fields state gen word (FramePolicy.canonical_state_bound canonical) canonical.1
    change next = FramePolicy.pack state gen word at encoded
    rw [encoded,fields.1]
    exact release_accepted_kind decision

private theorem release_result_links
    (specified : FramePolicy.ResultSpec .release record owner generation link next)
    (kind : FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4) :
    (FramePolicy.stateOf next = 1 → FramePolicy.wordOf next = link) ∧
      (FramePolicy.stateOf next = 4 → FramePolicy.wordOf next = 0) := by
  have inputs := release_result_inputs specified kind
  have matching := FramePolicy.matching_release inputs.2.1 inputs.2.2.1 inputs.1 inputs.2.2.2.1 inputs.2.2.2.2
  change next = FramePolicy.encode (FramePolicy.transition .release record owner generation link) at specified
  rw [matching] at specified
  by_cases full : FramePolicy.generationOf record = FramePolicy.generationMax
  · rw [if_pos full] at specified
    change next = FramePolicy.retiredRecord at specified
    subst next
    constructor
    · intro impossible; cases impossible
    · intro _; exact FramePolicy.retired_fields.2.2
  · rw [if_neg full] at specified
    change next = FramePolicy.pack 1 (FramePolicy.generationOf record + 1) link at specified
    have room : FramePolicy.generationOf record + 1 ≤ FramePolicy.generationMax := by
      have bound := FramePolicy.generation_bound record
      omega
    have fields := FramePolicy.pack_fields 1 _ link (by decide) room
    subst next
    refine ⟨fun _ => fields.2.2,?_⟩
    intro impossible
    rw [fields.1] at impossible
    cases impossible

private theorem owner_census_positive (bank : Bank extent) (index : Fin extent)
    (allocated : FramePolicy.stateOf (bank index) = 2)
    (owned : FramePolicy.wordOf (bank index) = owner) : 0 < ownerCount bank owner := by
  rw [ownerCount,← List.countP_eq_length_filter]
  apply List.countP_pos_iff.mpr
  refine ⟨index,List.mem_ofFn.mpr ⟨index,rfl⟩,?_⟩
  change (decide (FramePolicy.stateOf (bank index) = 2) && decide (FramePolicy.wordOf (bank index) = owner)) = true
  rw [decide_eq_true allocated,decide_eq_true owned]
  rfl

/-- The actual method's accepted-policy branch can discharge its consistency
and arithmetic guards from these facts. It must derive Fin admission, ResultSpec
and nonzero low state itself; there is no Delta, after-state, store-success or
callee-return premise here. The bounded argument premise preserves that actual
typed invocation domain, even where acceptance gives tighter bounds. -/
theorem release_consistency_guards {ledger : Ledger extent}
    (healthy : LedgerInv ledger) (position : Fin extent)
    (_bounded : FramePolicy.InputsBounded (ledger.bank position) owner generation ledger.fields.head)
    (specified : FramePolicy.ResultSpec .release (ledger.bank position) owner generation ledger.fields.head next)
    (acceptedBranch : FramePolicy.stateOf next ≠ 0) :
    ∃ slot, ReleaseGuardFacts ledger position owner next slot := by
  have kind := nonzero_release_kind specified acceptedBranch
  have inputs := release_result_inputs specified kind
  have links := release_result_links specified kind
  have positive := owner_census_positive ledger.bank position inputs.2.1 inputs.2.2.1
  have represented : ledger.fields.owner0 = owner ∨ ledger.fields.owner1 = owner := by
    rcases healthy.noOrphanAllocated position inputs.2.1 with first | second
    · exact Or.inl (first.2.symm.trans inputs.2.2.1)
    · exact Or.inr (second.2.symm.trans inputs.2.2.1)
  have found : ∃ slot, SlotMatches ledger.fields owner slot ∧
      0 < heldCount ledger.fields slot ∧ heldCount ledger.fields slot ≤ ledger.fields.allocatedCount := by
    by_cases first : ledger.fields.owner0 = owner
    · refine ⟨.first,first,?_,?_⟩
      · change 0 < ledger.fields.count0
        rw [healthy.firstOwner.exactCount,first]
        exact positive
      · change ledger.fields.count0 ≤ ledger.fields.allocatedCount
        rw [healthy.allocatedOwners]
        omega
    · have second : ledger.fields.owner1 = owner := by
        rcases represented with impossible | matched
        · exact False.elim (first impossible)
        · exact matched
      refine ⟨.second,⟨first,second⟩,?_,?_⟩
      · change 0 < ledger.fields.count1
        rw [healthy.secondOwner.exactCount,second]
        exact positive
      · change ledger.fields.count1 ≤ ledger.fields.allocatedCount
        rw [healthy.allocatedOwners]
        omega
  obtain ⟨slot,selected,heldPositive,heldLe⟩ := found
  have allocatedPositive : 0 < ledger.fields.allocatedCount := Nat.lt_of_lt_of_le heldPositive heldLe
  have room : ledger.fields.freeCount < extent := by
    have partition := healthy.partition
    omega
  have allocatedBound := healthy.scalarBounds ledger.fields.allocatedCount (by simp)
  have heldBound := Nat.lt_of_le_of_lt heldLe allocatedBound
  have indexBound : position.val + 1 ≤ FramePolicy.wordMax := Nat.le_trans position.isLt healthy.extentBound
  refine ⟨slot,{
    selected := selected
    heldPositive := heldPositive
    allocatedPositive := allocatedPositive
    heldLeAllocated := heldLe
    nextKind := kind
    freeLink := links.1
    retiredLink := links.2
    freeRoom := fun _ => room
    nextBound := FramePolicy.result_bounded specified
    allocatedDecrementBound := Nat.lt_of_le_of_lt (Nat.sub_le _ _) allocatedBound
    heldDecrementBound := Nat.lt_of_le_of_lt (Nat.sub_le _ _) heldBound
    freeIncrementBound := fun _ => Nat.lt_of_le_of_lt (Nat.le_trans room healthy.extentBound) (by decide)
    indexIncrementWordBound := indexBound
    indexIncrementBound := Nat.lt_of_le_of_lt indexBound (by decide) }⟩

end Aurora.SourceBinding.MemoryManagerRelease
