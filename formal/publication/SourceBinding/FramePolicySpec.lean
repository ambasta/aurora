import Std.Tactic

namespace Aurora.SourceBinding.FramePolicy

/-! Independent numerical specification of the copied frame-record policy.
This module does not assert source/IR correspondence, ledger mutation, native
record authenticity, persistent retirement, ABA prevention or A/B authority.
The source's checked packing helper is not assumed total on arbitrary inputs. -/

inductive Operation where
  | none | initializeFree | initializeKernel | allocate | release
  deriving DecidableEq, Repr

/-- These ordinals are specification data, not an enum-to-word coercion. -/
def Operation.ordinal : Operation → Nat
  | .none => 0 | .initializeFree => 1 | .initializeKernel => 2
  | .allocate => 3 | .release => 4

theorem Operation.ordinal_injective (a b : Operation)
    (same : a.ordinal = b.ordinal) : a = b := by
  cases a <;> cases b <;> simp_all [Operation.ordinal]

inductive Rejection where
  | operation | record | owner | link | notFree | notAllocated
  | kernel | retired | wrongOwner | stale
  deriving DecidableEq, Repr

/-- Actual rejection reasons, excluding the source enum's unused `none` case. -/
def Rejection.ordinal : Rejection → Nat
  | .operation => 1 | .record => 2 | .owner => 3 | .link => 4
  | .notFree => 5 | .notAllocated => 6 | .kernel => 7
  | .retired => 8 | .wrongOwner => 9 | .stale => 10

inductive Outcome where
  | reject (reason : Rejection)
  | accept (state generation word : Nat)
  deriving DecidableEq, Repr

abbrev generationModulus : Nat := 268435456
abbrev generationMax : Nat := 268435455
abbrev wordModulus : Nat := 4294967296
abbrev wordMax : Nat := 4294967295
abbrev u64Modulus : Nat := 18446744073709551616

def stateOf (record : Nat) : Nat := record % 16
def generationOf (record : Nat) : Nat := record / 16 % generationModulus
def wordOf (record : Nat) : Nat := record / wordModulus

/-- Arithmetic packing; correspondence with checked shifts requires bounds. -/
def pack (state generation word : Nat) : Nat :=
  state + generation * 16 + word * wordModulus

def encode : Outcome → Nat
  | .reject reason => reason.ordinal * 16
  | .accept state generation word => pack state generation word

abbrev KernelOwner (owner : Nat) : Prop := 1 ≤ owner ∧ owner ≤ 15
abbrev UserOwner (owner : Nat) : Prop := 16 ≤ owner ∧ owner ≤ wordMax

/-- Canonical fields do not require retired generation to be maximal: the actual
policy accepts any retired generation with zero word as a valid input record. -/
def CanonicalFields (state generation word : Nat) : Prop :=
  generation ≤ generationMax ∧ word ≤ wordMax ∧
  (state = 1 ∨ (state = 2 ∧ UserOwner word) ∨
    (state = 3 ∧ KernelOwner word) ∨ (state = 4 ∧ word = 0))

/-- Exact equivalence to the source's disjunctive invalid-owner guard. -/
theorem user_owner_guard (owner : Nat) :
    ¬ UserOwner owner ↔ owner = 0 ∨ owner > wordMax ∨ KernelOwner owner := by
  constructor
  · intro invalid
    by_cases zero : owner = 0
    · exact Or.inl zero
    · by_cases large : owner > wordMax
      · exact Or.inr (Or.inl large)
      · right; right
        constructor
        · omega
        · by_cases outside : owner ≤ 15
          · exact outside
          · exact False.elim (invalid ⟨by omega, by omega⟩)
  · intro invalid user
    rcases invalid with zero | large | kernel <;> omega

/-- Input validity matches the source guard, not a stronger allocator invariant. -/
abbrev RecordValid (record : Nat) : Prop :=
  stateOf record = 1 ∨
  (stateOf record = 2 ∧ wordOf record ≠ 0 ∧ ¬ KernelOwner (wordOf record)) ∨
  (stateOf record = 3 ∧ KernelOwner (wordOf record)) ∨
  (stateOf record = 4 ∧ wordOf record = 0)

/-- Ordered numerical decision. Initialization checks record before owner/link;
ordinary operations check validity and owner before kernel/retired state. -/
def transition (operation : Operation) (record owner generation link : Nat) : Outcome :=
  match operation with
  | .initializeFree =>
    if record ≠ 0 then .reject .record
    else if link > wordMax then .reject .link
    else .accept 1 0 link
  | .initializeKernel =>
    if record ≠ 0 then .reject .record
    else if ¬ KernelOwner owner then .reject .owner
    else .accept 3 0 owner
  | .none => .reject .operation
  | op =>
    if ¬ RecordValid record then .reject .record
    else if ¬ UserOwner owner then .reject .owner
    else if stateOf record = 3 then .reject .kernel
    else if stateOf record = 4 then .reject .retired
    else if op = .allocate then
      if stateOf record ≠ 1 then .reject .notFree
      else .accept 2 (generationOf record) owner
    else if stateOf record ≠ 2 then .reject .notAllocated
    else if wordOf record ≠ owner then .reject .wrongOwner
    else if generation ≠ generationOf record then .reject .stale
    else if link > wordMax then .reject .link
    else if generationOf record = generationMax then
      .accept 4 (generationOf record) 0
    else .accept 1 (generationOf record + 1) link

abbrev InputsBounded (record owner generation link : Nat) : Prop :=
  record < u64Modulus ∧ owner < u64Modulus ∧
  generation < u64Modulus ∧ link < u64Modulus

/-- Exact numeric result; bounded arguments belong to the source-entry theorem,
not to an assumption that the general checked packing helper is total. -/
def ResultSpec (operation : Operation) (record owner generation link result : Nat) : Prop :=
  result = encode (transition operation record owner generation link)

theorem result_unique (left : ResultSpec op record owner generation link a)
    (right : ResultSpec op record owner generation link b) : a = b := left.trans right.symm

theorem generation_bound (record : Nat) : generationOf record ≤ generationMax := by
  have bound := Nat.mod_lt (record / 16) (by decide : 0 < generationModulus)
  simp only [generationOf, generationModulus, generationMax] at *
  omega

theorem pack_bounded (state generation word : Nat) (hs : state < 16)
    (hg : generation ≤ generationMax) (hw : word ≤ wordMax) :
    pack state generation word < u64Modulus := by
  simp only [pack, generationMax, wordMax, wordModulus, u64Modulus] at *
  omega

theorem pack_fields (state generation word : Nat) (hs : state < 16)
    (hg : generation ≤ generationMax) :
    stateOf (pack state generation word) = state ∧
    generationOf (pack state generation word) = generation ∧
    wordOf (pack state generation word) = word := by
  simp only [stateOf, generationOf, wordOf, pack, generationMax,
    generationModulus, wordModulus] at *
  constructor
  · omega
  · constructor <;> omega

theorem accepted_canonical
    (accepted : transition op record owner generation link = .accept state gen word) :
    CanonicalFields state gen word := by
  have bound := generation_bound record
  cases op with
  | none => simp [transition] at accepted
  | initializeFree =>
    by_cases hr : record = 0
    · by_cases hl : link ≤ wordMax
      · simp [transition, hr, Nat.not_lt.mpr hl] at accepted
        obtain ⟨rfl, rfl, rfl⟩ := accepted
        exact ⟨by decide, hl, Or.inl rfl⟩
      · simp [transition, hr, Nat.lt_of_not_ge hl] at accepted
    · simp [transition, hr] at accepted
  | initializeKernel =>
    by_cases hr : record = 0 <;> by_cases ho : KernelOwner owner
    all_goals simp [transition, hr, ho] at accepted
    obtain ⟨rfl, rfl, rfl⟩ := accepted
    refine ⟨by decide, (show owner ≤ 4294967295 by omega), ?_⟩
    exact Or.inr (Or.inr (Or.inl ⟨rfl, ho⟩))
  | allocate =>
    by_cases hv : RecordValid record
    · by_cases hu : UserOwner owner
      · by_cases hk : stateOf record = 3
        · simp [transition, hv, hu, hk] at accepted
        · by_cases ht : stateOf record = 4
          · simp [transition, hv, hu, ht] at accepted
          · by_cases hf : stateOf record = 1
            · simp [transition, hv, hu, hf] at accepted
              obtain ⟨rfl, rfl, rfl⟩ := accepted
              exact ⟨bound, hu.2, Or.inr (Or.inl ⟨rfl, hu⟩)⟩
            · simp [transition, hv, hu, hk, ht, hf] at accepted
      · simp [transition, hv, hu] at accepted
    · simp [transition, hv] at accepted
  | release =>
    by_cases hv : RecordValid record
    · by_cases hu : UserOwner owner
      · by_cases hk : stateOf record = 3
        · simp [transition, hv, hu, hk] at accepted
        · by_cases ht : stateOf record = 4
          · simp [transition, hv, hu, ht] at accepted
          · by_cases ha : stateOf record = 2
            · by_cases ho : wordOf record = owner
              · by_cases hg : generation = generationOf record
                · by_cases hl : link ≤ wordMax
                  · by_cases hm : generationOf record = generationMax
                    · simp [transition, hv, hu, ha, ho, hg,
                        Nat.not_lt.mpr hl, hm] at accepted
                      obtain ⟨rfl, rfl, rfl⟩ := accepted
                      simp [CanonicalFields]
                    · simp [transition, hv, hu, ha, ho, hg,
                        Nat.not_lt.mpr hl, hm] at accepted
                      obtain ⟨rfl, rfl, rfl⟩ := accepted
                      exact ⟨by omega, hl, Or.inl rfl⟩
                  · simp [transition, hv, hu, ha, ho, hg,
                      Nat.lt_of_not_ge hl] at accepted
                · simp [transition, hv, hu, ha, ho, hg] at accepted
              · simp [transition, hv, hu, ha, ho] at accepted
            · simp [transition, hv, hu, hk, ht, ha] at accepted
      · simp [transition, hv, hu] at accepted
    · simp [transition, hv] at accepted

theorem canonical_state_bound (canonical : CanonicalFields state gen word) : state < 16 := by
  rcases canonical.2.2 with h | h | h | h <;> omega

theorem accepted_bounded
    (accepted : transition op record owner generation link = .accept state gen word) :
    encode (.accept state gen word) < u64Modulus := by
  have canonical := accepted_canonical accepted
  exact pack_bounded _ _ _ (canonical_state_bound canonical) canonical.1 canonical.2.1

theorem allocation_preserves_generation
    (accepted : transition .allocate record owner generation link = .accept state gen word) :
    state = 2 ∧ gen = generationOf record ∧ word = owner := by
  by_cases hv : RecordValid record
  · by_cases hu : UserOwner owner
    · by_cases hk : stateOf record = 3
      · simp [transition, hv, hu, hk] at accepted
      · by_cases ht : stateOf record = 4
        · simp [transition, hv, hu, ht] at accepted
        · by_cases hf : stateOf record = 1
          · simpa [transition, hv, hu, hf] using accepted.symm
          · simp [transition, hv, hu, hk, ht, hf] at accepted
    · simp [transition, hv, hu] at accepted
  · simp [transition, hv] at accepted

/-- Matching valid allocated input, including link checking BEFORE exhaustion. -/
theorem matching_release (hs : stateOf record = 2) (ho : wordOf record = owner)
    (hu : UserOwner owner) (hg : generation = generationOf record) (hl : link ≤ wordMax) :
    transition .release record owner generation link =
      if generationOf record = generationMax then .accept 4 generationMax 0
      else .accept 1 (generationOf record + 1) link := by
  have valid : RecordValid record := by
    right; left
    refine ⟨hs, ?_, ?_⟩ <;> rw [ho] <;> omega
  simp [transition, valid, hu, hs, ho, hg, Nat.not_lt.mpr hl]
  split <;> simp_all

theorem matching_release_increments (hs : stateOf record = 2) (ho : wordOf record = owner)
    (hu : UserOwner owner) (hg : generation = generationOf record) (hl : link ≤ wordMax)
    (room : generationOf record < generationMax) :
    transition .release record owner generation link =
      .accept 1 (generationOf record + 1) link := by
  rw [matching_release hs ho hu hg hl, if_neg (by omega)]

def retiredRecord : Nat := pack 4 generationMax 0

theorem matching_release_retires (hs : stateOf record = 2) (ho : wordOf record = owner)
    (hu : UserOwner owner) (hg : generation = generationOf record) (hl : link ≤ wordMax)
    (full : generationOf record = generationMax) :
    ResultSpec .release record owner generation link retiredRecord := by
  unfold ResultSpec
  rw [matching_release hs ho hu hg hl, if_pos full]
  rfl

/-- Retired input always rejects, but the earlier guards select the reason.
This is a policy-invocation fact, not evidence that any ledger stores the result. -/
theorem retired_priority (op : Operation) (owner generation link : Nat) :
    transition op retiredRecord owner generation link = .reject
      (match op with
       | .none => .operation
       | .initializeFree | .initializeKernel => .record
       | .allocate | .release => if UserOwner owner then .retired else .owner) := by
  have valid : RecordValid retiredRecord := by decide
  have state : stateOf retiredRecord = 4 := by decide
  have nonzero : retiredRecord ≠ 0 := by decide
  cases op <;> by_cases user : UserOwner owner <;>
    simp [transition, valid, state, nonzero, user]

theorem retired_rejects (op : Operation) (owner generation link : Nat) :
    ∃ reason, transition op retiredRecord owner generation link = .reject reason := by
  exact ⟨_, retired_priority op owner generation link⟩

/-- Every mathematical branch yields a bounded word; source totality still
requires correspondence and checking each actually executed helper call. -/
theorem result_bounded (specified : ResultSpec op record owner generation link result) :
    result < u64Modulus := by
  unfold ResultSpec at specified
  cases h : transition op record owner generation link with
  | reject reason =>
    rw [h] at specified
    subst result
    cases reason <;> decide
  | accept state gen word =>
    rw [h] at specified
    subst result
    exact accepted_bounded h

theorem packing_shift_bounds (hg : generation ≤ generationMax) (hw : word ≤ wordMax) :
    generation * 16 < u64Modulus ∧ word * wordModulus < u64Modulus := by
  simp only [generationMax, wordMax, wordModulus, u64Modulus] at *
  constructor <;> omega

/-- Numeric no-overlap identity only; checked shift semantics are separate. -/
theorem packing_or (hs : state < 16) (hg : generation ≤ generationMax) :
    (state ||| (generation * 16) ||| (word * wordModulus)) = pack state generation word := by
  have first := Nat.two_pow_add_eq_or_of_lt (i := 4) (b := state) hs generation
  have low : state + generation * 16 < 2^32 := by
    simp only [generationMax] at hg
    omega
  have second := Nat.two_pow_add_eq_or_of_lt low word
  simp only [Nat.reducePow] at first second
  have first' : state ||| (generation * 16) = state + generation * 16 := by
    simpa [Nat.mul_comm, Nat.add_comm, Nat.or_comm] using first.symm
  rw [first']
  simpa [pack, wordModulus, Nat.mul_comm, Nat.add_comm, Nat.or_comm] using second.symm

theorem retired_canonical : CanonicalFields 4 generationMax 0 := by
  unfold CanonicalFields
  decide

theorem retired_fields : stateOf retiredRecord = 4 ∧
    generationOf retiredRecord = generationMax ∧ wordOf retiredRecord = 0 := by decide

/-- Exhaustion does not bypass link admission. -/
example : transition .release (pack 2 generationMax 16) 16 generationMax (wordMax + 1) =
    .reject .link := by decide

/-- Owner mismatch wins over the simultaneously stale generation. -/
example : transition .release (pack 2 5 17) 16 6 0 = .reject .wrongOwner := by decide

example : transition .release retiredRecord 0 generationMax 0 = .reject .owner := by decide
example : transition .initializeFree retiredRecord 0 0 0 = .reject .record := by decide
example : transition .allocate 0 0 0 0 = .reject .record := by decide


end Aurora.SourceBinding.FramePolicy
