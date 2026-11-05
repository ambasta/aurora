import SourceBinding.MemoryManagerLedger

namespace Aurora.SourceBinding.MemoryManagerRelease

/-! Constructive finite-bank facts only. A cell replacement is a mathematical
relation, not evidence that the production source performed its bank store. -/

private theorem finite_indices_simple (extent : Nat) : (List.finRange extent).Nodup := by
  apply List.pairwise_iff_getElem.mpr
  intro i j hi hj less same
  have equal := congrArg Fin.val same
  simp only [List.getElem_finRange] at equal
  change i = j at equal
  omega

private theorem finite_index_present (index : Fin extent) : index ∈ List.finRange extent := by
  apply List.mem_ofFn.mpr
  exact ⟨index,rfl⟩

private theorem list_count_balance [DecidableEq α] (items : List α)
    (simple : items.Nodup) (index : α) (present : index ∈ items)
    (old new : α → Bool)
    (unchanged : ∀ other ∈ items, other ≠ index → new other = old other) :
    items.countP new + (if old index then 1 else 0) =
      items.countP old + (if new index then 1 else 0) := by
  induction items with
  | nil => cases present
  | cons item rest ih =>
    obtain ⟨absent,simpleRest⟩ := List.nodup_cons.mp simple
    by_cases selected : item = index
    · subst item
      have equal : rest.countP new = rest.countP old := by
        apply List.countP_congr
        intro other member
        have different : other ≠ index := by
          intro same
          subst other
          exact absent member
        rw [unchanged other (List.mem_cons_of_mem _ member) different]
      simp only [List.countP_cons,equal]
      omega
    · have presentRest : index ∈ rest := by
        rcases List.mem_cons.mp present with same | member
        · exact False.elim (selected same.symm)
        · exact member
      have tail := ih simpleRest presentRest
        (fun other member different => unchanged other (List.mem_cons_of_mem _ member) different)
      have head := unchanged item (List.mem_cons_self) selected
      simp only [List.countP_cons,head]
      omega

theorem OneCellReplacement.state_count_balance
    (replacement : OneCellReplacement before after index next) (kind : Nat) :
    stateCount after kind + (if FramePolicy.stateOf (before index) = kind then 1 else 0) =
      stateCount before kind + (if FramePolicy.stateOf next = kind then 1 else 0) := by
  have balance := list_count_balance (List.finRange _) (finite_indices_simple _) index
    (finite_index_present index)
    (fun i => FramePolicy.stateOf (before i) == kind)
    (fun i => FramePolicy.stateOf (after i) == kind)
    (fun other _ different => by dsimp only; rw [replacement.2 other different])
  simpa only [stateCount,← List.countP_eq_length_filter,replacement.1,
    Bool.beq_eq_decide_eq,decide_eq_true_eq] using balance

theorem OneCellReplacement.owner_count_balance
    (replacement : OneCellReplacement before after index next) (owner : Nat) :
    ownerCount after owner +
      (if FramePolicy.stateOf (before index) = 2 ∧ FramePolicy.wordOf (before index) = owner then 1 else 0) =
    ownerCount before owner +
      (if FramePolicy.stateOf next = 2 ∧ FramePolicy.wordOf next = owner then 1 else 0) := by
  have balance := list_count_balance (List.finRange _) (finite_indices_simple _) index
    (finite_index_present index)
    (fun i => FramePolicy.stateOf (before i) == 2 && FramePolicy.wordOf (before i) == owner)
    (fun i => FramePolicy.stateOf (after i) == 2 && FramePolicy.wordOf (after i) == owner)
    (fun other _ different => by dsimp only; rw [replacement.2 other different])
  simpa only [ownerCount,← List.countP_eq_length_filter,replacement.1,
    Bool.beq_eq_decide_eq,← Bool.decide_and,decide_eq_true_eq] using balance

theorem stateCount_le (bank : Bank extent) (kind : Nat) : stateCount bank kind ≤ extent := by
  have bounded := List.countP_le_length (p := fun i => FramePolicy.stateOf (bank i) == kind)
    (l := List.finRange extent)
  simpa only [stateCount,← List.countP_eq_length_filter,List.length_finRange] using bounded

theorem ownerCount_le (bank : Bank extent) (owner : Nat) : ownerCount bank owner ≤ extent := by
  have bounded := List.countP_le_length
    (p := fun i => FramePolicy.stateOf (bank i) == 2 && FramePolicy.wordOf (bank i) == owner)
    (l := List.finRange extent)
  simpa only [ownerCount,← List.countP_eq_length_filter,List.length_finRange] using bounded

theorem LedgerInv.head_bound {ledger : Ledger extent} (healthy : LedgerInv ledger) : ledger.fields.head ≤ extent := by
  obtain ⟨chain,complete⟩ := healthy.freeChain
  rw [complete.head]
  cases chain with
  | nil => exact Nat.zero_le _
  | cons index rest => exact index.isLt

private theorem chain_links_transport
    (links : ChainLinks before chain)
    (equal : ∀ index ∈ chain, after index = before index) : ChainLinks after chain := by
  induction chain with
  | nil => trivial
  | cons index rest ih =>
    refine ⟨?_,?_⟩
    · rw [equal index (List.mem_cons_self)]
      exact links.1
    · exact ih links.2 (fun other member => equal other (List.mem_cons_of_mem _ member))

private theorem allocated_not_free_chain (old : CompleteFreeChain before chain)
    (allocated : FramePolicy.stateOf (before.bank index) = 2) : index ∉ chain := by
  intro member
  have free := (old.complete index).mp member
  omega

theorem CompleteFreeChain.prepend
    (old : CompleteFreeChain before chain)
    (allocated : FramePolicy.stateOf (before.bank index) = 2)
    (replacement : OneCellReplacement before.bank after.bank index next)
    (free : FramePolicy.stateOf next = 1)
    (link : FramePolicy.wordOf next = before.fields.head)
    (head : after.fields.head = index.val + 1)
    (count : after.fields.freeCount = before.fields.freeCount + 1) :
    CompleteFreeChain after (index :: chain) := by
  have absent := allocated_not_free_chain old allocated
  have unchanged : ∀ other ∈ chain, after.bank other = before.bank other := by
    intro other member
    apply replacement.2
    intro same
    subst other
    exact absent member
  refine ⟨List.nodup_cons.mpr ⟨absent,old.simple⟩,head,?_,?_,?_⟩
  · exact ⟨by rw [replacement.1,link,old.head],chain_links_transport old.links unchanged⟩
  · intro other
    constructor
    · intro member
      rcases List.mem_cons.mp member with same | member
      · subst other
        rw [replacement.1]
        exact free
      · rw [unchanged other member]
        exact (old.complete other).mp member
    · intro isFree
      by_cases same : other = index
      · subst other
        exact List.mem_cons_self
      · rw [replacement.2 other same] at isFree
        exact List.mem_cons_of_mem _ ((old.complete other).mpr isFree)
  · rw [count,old.count]
    rfl

theorem CompleteFreeChain.retain
    (old : CompleteFreeChain before chain)
    (allocated : FramePolicy.stateOf (before.bank index) = 2)
    (replacement : OneCellReplacement before.bank after.bank index next)
    (retired : FramePolicy.stateOf next = 4)
    (head : after.fields.head = before.fields.head)
    (count : after.fields.freeCount = before.fields.freeCount) :
    CompleteFreeChain after chain := by
  have absent := allocated_not_free_chain old allocated
  have unchanged : ∀ other ∈ chain, after.bank other = before.bank other := by
    intro other member
    apply replacement.2
    intro same
    subst other
    exact absent member
  refine ⟨old.simple,head.trans old.head,chain_links_transport old.links unchanged,?_,count.trans old.count⟩
  intro other
  constructor
  · intro member
    rw [unchanged other member]
    exact (old.complete other).mp member
  · intro isFree
    by_cases same : other = index
    · subst other
      rw [replacement.1,retired] at isFree
      cases isFree
    · rw [replacement.2 other same] at isFree
      exact (old.complete other).mpr isFree

end Aurora.SourceBinding.MemoryManagerRelease
