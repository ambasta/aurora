import SourceBinding.MemoryManagerReleaseFacts

namespace Aurora.SourceBinding.MemoryManagerRelease

private theorem owner_count_positive (bank : Bank extent) (index : Fin extent)
    (allocated : FramePolicy.stateOf (bank index) = 2)
    (owned : FramePolicy.wordOf (bank index) = owner) : 0 < ownerCount bank owner := by
  rw [ownerCount,← List.countP_eq_length_filter]
  apply List.countP_pos_iff.mpr
  refine ⟨index,List.mem_ofFn.mpr ⟨index,rfl⟩,?_⟩
  change (decide (FramePolicy.stateOf (bank index) = 2) && decide (FramePolicy.wordOf (bank index) = owner)) = true
  rw [decide_eq_true allocated,decide_eq_true owned]
  rfl

private theorem count_zero_of_false (items : List α) (predicate : α → Bool)
    (empty : ∀ item ∈ items, predicate item = false) : items.countP predicate = 0 := by
  induction items with
  | nil => rfl
  | cons item rest ih =>
    rw [List.countP_cons,empty item List.mem_cons_self]
    exact ih (fun other member => empty other (List.mem_cons_of_mem _ member))

private theorem owner_count_zero (bank : Bank extent)
    (valid : ∀ index, FramePolicy.RecordValid (bank index)) : ownerCount bank 0 = 0 := by
  rw [ownerCount,← List.countP_eq_length_filter]
  apply count_zero_of_false
  intro index _
  apply Bool.eq_false_iff.mpr
  intro both
  change (decide (FramePolicy.stateOf (bank index) = 2) && decide (FramePolicy.wordOf (bank index) = 0)) = true at both
  simp only [Bool.and_eq_true,decide_eq_true_eq] at both
  have allocated := both.1
  have zero := both.2
  have nonzero : FramePolicy.wordOf (bank index) ≠ 0 := by
    rcases valid index with free | allocated | kernel | retired
    · omega
    · exact allocated.2.1
    · omega
    · omega
  exact nonzero zero

private theorem release_output_fields
    (specified : FramePolicy.ResultSpec .release record owner generation link next)
    (kind : FramePolicy.stateOf next = 1 ∨ FramePolicy.stateOf next = 4) :
    FramePolicy.RecordValid next ∧
      (FramePolicy.stateOf next = 1 → FramePolicy.wordOf next = link) := by
  have inputs := release_result_inputs specified kind
  have matching := FramePolicy.matching_release inputs.2.1 inputs.2.2.1 inputs.1 inputs.2.2.2.1 inputs.2.2.2.2
  change next = FramePolicy.encode (FramePolicy.transition .release record owner generation link) at specified
  rw [matching] at specified
  by_cases full : FramePolicy.generationOf record = FramePolicy.generationMax
  · rw [if_pos full] at specified
    change next = FramePolicy.retiredRecord at specified
    subst next
    exact ⟨by decide,by intro impossible; cases impossible⟩
  · rw [if_neg full] at specified
    change next = FramePolicy.pack 1 (FramePolicy.generationOf record + 1) link at specified
    have room : FramePolicy.generationOf record + 1 ≤ FramePolicy.generationMax := by
      have bound := FramePolicy.generation_bound record
      omega
    have fields := FramePolicy.pack_fields 1 _ link (by decide) room
    subst next
    exact ⟨Or.inl fields.1,fun _ => fields.2.2⟩

private theorem owner_census_update (chosen : Prop) [Decidable chosen]
    (old : OwnerCensus before oldOwner oldCount)
    (replacement : OneCellReplacement before after index next)
    (allocated : FramePolicy.stateOf (before index) = 2)
    (notAllocated : FramePolicy.stateOf next ≠ 2)
    (owned : FramePolicy.wordOf (before index) = releasedOwner)
    (selected : chosen → oldOwner = releasedOwner)
    (other : ¬ chosen → oldOwner ≠ releasedOwner)
    (valid : ∀ index, FramePolicy.RecordValid (after index))
    (count : newCount = if chosen then oldCount - 1 else oldCount)
    (owner : newOwner = if chosen ∧ oldCount = 1 then 0 else oldOwner) :
    OwnerCensus after newOwner newCount := by
  have balance := replacement.owner_count_balance oldOwner
  have noNew : ¬ (FramePolicy.stateOf next = 2 ∧ FramePolicy.wordOf next = oldOwner) :=
    fun both => notAllocated both.1
  rw [if_neg noNew] at balance
  clear noNew
  by_cases selectedCase : chosen
  · have matched : FramePolicy.wordOf (before index) = oldOwner := owned.trans (selected selectedCase).symm
    rw [if_pos ⟨allocated,matched⟩] at balance
    rw [if_pos selectedCase] at count
    have positive : 0 < oldCount := by rw [old.exactCount]; omega
    by_cases last : oldCount = 1
    · rw [if_pos ⟨selectedCase,last⟩] at owner
      have emptyCount : newCount = 0 := by omega
      rw [owner,emptyCount]
      exact ⟨Iff.rfl,fun impossible => False.elim (impossible rfl),(owner_count_zero after valid).symm⟩
    · rw [if_neg (fun both => last both.2)] at owner
      have countPositive : 0 < newCount := by omega
      have ownerPositive : oldOwner ≠ 0 := by
        intro zero
        have empty := old.empty.mpr zero
        omega
      rw [owner]
      refine ⟨?_,old.activeOwner,?_⟩
      · constructor
        · intro zero; omega
        · intro zero; exact False.elim (ownerPositive zero)
      · rw [old.exactCount] at count
        omega
  · have unmatched : FramePolicy.wordOf (before index) ≠ oldOwner := by
      intro same
      exact other selectedCase (same.symm.trans owned)
    rw [if_neg (fun both => unmatched both.2)] at balance
    rw [if_neg selectedCase] at count
    rw [if_neg (fun both => selectedCase both.1)] at owner
    rw [count,owner]
    refine ⟨old.empty,old.activeOwner,?_⟩
    rw [old.exactCount]
    omega

private theorem represented_owner_survives (chosen : Prop) [Decidable chosen]
    (old : OwnerCensus before oldOwner oldCount)
    (replacement : OneCellReplacement before after index next)
    (allocated : FramePolicy.stateOf (before index) = 2)
    (notAllocated : FramePolicy.stateOf next ≠ 2)
    (owned : FramePolicy.wordOf (before index) = releasedOwner)
    (selected : chosen → oldOwner = releasedOwner)
    (owner : newOwner = if chosen ∧ oldCount = 1 then 0 else oldOwner)
    (remaining : FramePolicy.stateOf (after other) = 2)
    (remainingOwner : FramePolicy.wordOf (after other) = oldOwner) : newOwner = oldOwner := by
  by_cases clear : chosen ∧ oldCount = 1
  · have matched : FramePolicy.wordOf (before index) = oldOwner := owned.trans (selected clear.1).symm
    have balance := replacement.owner_count_balance oldOwner
    rw [if_pos ⟨allocated,matched⟩,if_neg (fun both => notAllocated both.1)] at balance
    have countPositive := owner_count_positive after other remaining remainingOwner
    have exactOld := old.exactCount
    omega
  · rw [if_neg clear] at owner
    exact owner

/-- INTERNAL mathematical preservation. The complete source/canonical theorem
must derive ReleaseSuccess from the real bank request and ordered stores; this
lemma supplies neither execution nor a successful-store premise to that theorem. -/
theorem ReleaseSuccess.preserves {before after : Ledger extent}
    (healthy : LedgerInv before)
    (released : ReleaseSuccess before after index generation owner code) :
    LedgerInv after ∧ RetiredPreserved before after ∧
      (CanonicalRetired before → CanonicalRetired after) := by
  have retiredPreserved := released.retired_preserved
  have canonicalPreserved := released.canonical_retired
  obtain ⟨position,slot,next,positionEq,selected,specified,kind,delta,returned⟩ := released
  have inputs := release_result_inputs specified kind
  have output := release_output_fields specified kind
  have nextBound := FramePolicy.result_bounded specified
  have allocated := inputs.2.1
  have owned := inputs.2.2.1
  have notAllocated : FramePolicy.stateOf next ≠ 2 := by rcases kind with h | h <;> omega
  have notKernel : FramePolicy.stateOf next ≠ 3 := by rcases kind with h | h <;> omega
  have ownerNonzero : owner ≠ 0 := by
    have user := inputs.1
    change 16 ≤ owner ∧ owner ≤ FramePolicy.wordMax at user
    omega
  have afterCells : ∀ other, after.bank other < FramePolicy.u64Modulus ∧ FramePolicy.RecordValid (after.bank other) := by
    intro other
    by_cases same : other = position
    · subst other
      rw [delta.bankWrite.1]
      exact ⟨nextBound,output.1⟩
    · rw [delta.bankWrite.2 other same]
      exact healthy.cells other
  have selected0 : slot = .first → before.fields.owner0 = owner := by
    intro first
    subst slot
    exact selected
  have selected1 : slot = .second → before.fields.owner1 = owner := by
    intro second
    subst slot
    exact selected.2
  have other0 : slot ≠ .first → before.fields.owner0 ≠ owner := by
    intro different
    cases slot with
    | first => exact False.elim (different rfl)
    | second => exact selected.1
  have other1 : slot ≠ .second → before.fields.owner1 ≠ owner := by
    intro different
    cases slot with
    | second => exact False.elim (different rfl)
    | first =>
      intro same
      have firstNonzero : before.fields.owner0 ≠ 0 := by rw [selected]; exact ownerNonzero
      have secondNonzero : before.fields.owner1 ≠ 0 := by rw [same]; exact ownerNonzero
      exact healthy.distinctOwners firstNonzero secondNonzero (selected.trans same.symm)
  have firstCensus := owner_census_update (slot = .first) healthy.firstOwner delta.bankWrite
    allocated notAllocated owned selected0 other0 (fun other => (afterCells other).2) delta.firstCount delta.firstOwner
  have secondCensus := owner_census_update (slot = .second) healthy.secondOwner delta.bankWrite
    allocated notAllocated owned selected1 other1 (fun other => (afterCells other).2) delta.secondCount delta.secondOwner
  have noOrphans : ∀ other, FramePolicy.stateOf (after.bank other) = 2 →
      (after.fields.owner0 ≠ 0 ∧ FramePolicy.wordOf (after.bank other) = after.fields.owner0) ∨
      (after.fields.owner1 ≠ 0 ∧ FramePolicy.wordOf (after.bank other) = after.fields.owner1) := by
    intro other isAllocated
    have different : other ≠ position := by
      intro same
      subst other
      rw [delta.bankWrite.1] at isAllocated
      exact notAllocated isAllocated
    have cellEq := delta.bankWrite.2 other different
    have oldAllocated : FramePolicy.stateOf (before.bank other) = 2 := by rw [← cellEq]; exact isAllocated
    rcases healthy.noOrphanAllocated other oldAllocated with first | second
    · have remainingOwner : FramePolicy.wordOf (after.bank other) = before.fields.owner0 := by rw [cellEq]; exact first.2
      have kept := represented_owner_survives (slot = .first) healthy.firstOwner delta.bankWrite
        allocated notAllocated owned selected0 delta.firstOwner isAllocated remainingOwner
      exact Or.inl ⟨by rw [kept]; exact first.1,remainingOwner.trans kept.symm⟩
    · have remainingOwner : FramePolicy.wordOf (after.bank other) = before.fields.owner1 := by rw [cellEq]; exact second.2
      have kept := represented_owner_survives (slot = .second) healthy.secondOwner delta.bankWrite
        allocated notAllocated owned selected1 delta.secondOwner isAllocated remainingOwner
      exact Or.inr ⟨by rw [kept]; exact second.1,remainingOwner.trans kept.symm⟩
  have distinct : after.fields.owner0 ≠ 0 → after.fields.owner1 ≠ 0 → after.fields.owner0 ≠ after.fields.owner1 := by
    intro first second
    have kept0 : after.fields.owner0 = before.fields.owner0 := by
      by_cases clear : slot = .first ∧ before.fields.count0 = 1
      · rw [delta.firstOwner,if_pos clear] at first
        exact False.elim (first rfl)
      · simpa only [if_neg clear] using delta.firstOwner
    have kept1 : after.fields.owner1 = before.fields.owner1 := by
      by_cases clear : slot = .second ∧ before.fields.count1 = 1
      · rw [delta.secondOwner,if_pos clear] at second
        exact False.elim (second rfl)
      · simpa only [if_neg clear] using delta.secondOwner
    rw [kept0] at first
    rw [kept1] at second
    rw [kept0,kept1]
    exact healthy.distinctOwners first second
  have allocatedSum : after.fields.allocatedCount = after.fields.count0 + after.fields.count1 := by
    have first := delta.firstCount
    have second := delta.secondCount
    have total := delta.allocated
    have positive := delta.heldPositive
    rw [healthy.allocatedOwners] at total
    cases slot <;> simp only [heldCount,reduceCtorEq,if_false,if_true] at first second positive <;> omega
  have reservePrefix : ∀ other, FramePolicy.stateOf (after.bank other) = 3 ↔ other.val < after.fields.reservedCount := by
    intro other
    rw [delta.reserved]
    by_cases same : other = position
    · subst other
      rw [delta.bankWrite.1]
      constructor
      · intro impossible; exact False.elim (notKernel impossible)
      · intro inside
        have kernel := (healthy.reservedPrefix position).mpr inside
        omega
    · rw [delta.bankWrite.2 other same]
      exact healthy.reservedPrefix other
  have b1 := delta.bankWrite.state_count_balance 1
  have b2 := delta.bankWrite.state_count_balance 2
  have b3 := delta.bankWrite.state_count_balance 3
  have b4 := delta.bankWrite.state_count_balance 4
  have allocatedExact : after.fields.allocatedCount = stateCount after.bank 2 := by
    simp only [allocated,if_true,if_neg notAllocated,Nat.add_zero] at b2
    have old := healthy.allocatedExact
    have updated := delta.allocated
    omega
  have reservedExact : after.fields.reservedCount = stateCount after.bank 3 := by
    simp only [allocated,Nat.reduceEqDiff,if_false,if_neg notKernel,Nat.add_zero] at b3
    rw [delta.reserved,healthy.reservedExact]
    exact b3.symm
  have freeExact : after.fields.freeCount = stateCount after.bank 1 := by
    have old := healthy.freeExact
    have updated := delta.free
    rcases kind with free | retired
    · simp only [allocated,free,Nat.reduceEqDiff,if_false,if_true,Nat.add_zero] at b1
      simp only [free,show ((1 : Nat) == 1) = true from rfl,if_true] at updated
      omega
    · simp only [allocated,retired,Nat.reduceEqDiff,if_false,Nat.add_zero] at b1
      simp only [retired,Nat.reduceBEq,Bool.false_eq_true,if_false] at updated
      omega
  have partition : after.fields.reservedCount + after.fields.freeCount + after.fields.allocatedCount + stateCount after.bank 4 = extent := by
    have old := healthy.partition
    rw [healthy.reservedExact,healthy.freeExact,healthy.allocatedExact] at old
    rw [reservedExact,freeExact,allocatedExact]
    rcases kind with h | h <;>
      simp only [allocated,h,Nat.reduceEqDiff,if_false,if_true,Nat.add_zero] at b1 b2 b3 b4 <;> omega
  have chain : ∃ chain, CompleteFreeChain after chain := by
    obtain ⟨chain,old⟩ := healthy.freeChain
    rcases kind with free | retired
    · refine ⟨position :: chain,old.prepend allocated delta.bankWrite free (output.2 free) ?_ ?_⟩
      · simpa only [free,show ((1 : Nat) == 1) = true from rfl,if_true] using delta.head
      · simpa only [free,show ((1 : Nat) == 1) = true from rfl,if_true] using delta.free
    · refine ⟨chain,old.retain allocated delta.bankWrite retired ?_ ?_⟩
      · simpa only [retired,Nat.reduceBEq,Bool.false_eq_true,if_false] using delta.head
      · simpa only [retired,Nat.reduceBEq,Bool.false_eq_true,if_false] using delta.free
  have scalarBounds : ∀ value ∈ [after.fields.head,after.fields.freeCount,after.fields.allocatedCount,
      after.fields.reservedCount,after.fields.owner0,after.fields.count0,after.fields.owner1,after.fields.count1],
      value < FramePolicy.u64Modulus := by
    have oldHead := healthy.scalarBounds before.fields.head (by simp)
    have oldFree := healthy.scalarBounds before.fields.freeCount (by simp)
    have oldAllocated := healthy.scalarBounds before.fields.allocatedCount (by simp)
    have oldReserved := healthy.scalarBounds before.fields.reservedCount (by simp)
    have oldOwner0 := healthy.scalarBounds before.fields.owner0 (by simp)
    have oldCount0 := healthy.scalarBounds before.fields.count0 (by simp)
    have oldOwner1 := healthy.scalarBounds before.fields.owner1 (by simp)
    have oldCount1 := healthy.scalarBounds before.fields.count1 (by simp)
    have extentSmall : extent < FramePolicy.u64Modulus := by
      have extentBound := healthy.extentBound
      exact Nat.lt_of_le_of_lt extentBound (by decide)
    intro value member
    simp only [List.mem_cons,List.mem_singleton,List.not_mem_nil,or_false] at member
    rcases member with rfl | rfl | rfl | rfl | rfl | rfl | rfl | rfl
    · rw [delta.head]
      split
      · have inside := position.isLt; omega
      · exact oldHead
    · rw [delta.free]
      split
      next reusable => have room := delta.reusableRoom reusable; omega
      next => exact oldFree
    · rw [delta.allocated]
      exact Nat.lt_of_le_of_lt (Nat.sub_le _ _) oldAllocated
    · rw [delta.reserved]; exact oldReserved
    · rw [delta.firstOwner]; split
      · decide
      · exact oldOwner0
    · rw [delta.firstCount]; split
      · exact Nat.lt_of_le_of_lt (Nat.sub_le _ _) oldCount0
      · exact oldCount0
    · rw [delta.secondOwner]; split
      · decide
      · exact oldOwner1
    · rw [delta.secondCount]; split
      · exact Nat.lt_of_le_of_lt (Nat.sub_le _ _) oldCount1
      · exact oldCount1
  refine ⟨?_,retiredPreserved,canonicalPreserved⟩
  exact {
    nonempty := healthy.nonempty
    extentBound := healthy.extentBound
    initialized := delta.initialized.trans healthy.initialized
    unpoisoned := delta.poison.trans healthy.unpoisoned
    scalarBounds := scalarBounds
    cells := afterCells
    reservedBound := by rw [delta.reserved]; exact healthy.reservedBound
    reservedPrefix := reservePrefix
    reservedExact := reservedExact
    freeExact := freeExact
    allocatedExact := allocatedExact
    partition := partition
    freeChain := chain
    firstOwner := firstCensus
    secondOwner := secondCensus
    distinctOwners := distinct
    noOrphanAllocated := noOrphans
    allocatedOwners := allocatedSum }

end Aurora.SourceBinding.MemoryManagerRelease
