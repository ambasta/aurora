import SourceBinding.GuardSemantics
namespace Aurora.SourceBinding

/-- Numerical policy only: no native record authenticity or ownership premise.
    Accessed/dirty bits alone are ignored by the flag comparison. -/
def LeafAccepted (leaf physical mapping tableBase slot limit : Nat) : Prop :=
  leaf &&& 18442240474082185119 = 9223372036854775811 ∧
  leaf &&& 4503599627366400 = physical ∧ physical ≠ 0 ∧ physical < limit ∧
  tableBase &&& 2097151 = 0 ∧ slot < 512 ∧ mapping = (tableBase ||| (slot * 4096) ||| 3)

def leafNumeric (leaf physical mapping tableBase slot limit : Nat) : Bool :=
  (leaf &&& 18442240474082185119 == 9223372036854775811) &&
  (leaf &&& 4503599627366400 == physical) && (physical != 0) &&
  (physical < limit) && (tableBase &&& 2097151 == 0) && (slot < 512) &&
  (mapping == (tableBase ||| (slot * 4096) ||| 3))

theorem leaf_numeric_iff : leafNumeric leaf physical mapping tableBase slot limit = true ↔
    LeafAccepted leaf physical mapping tableBase slot limit := by
  simp [leafNumeric,LeafAccepted,Bool.and_eq_true,and_assoc]

/-- Constructive fixed-mask identity; the general library mask theorem uses
    Classical.choice. This profile needs exactly these 21 low bits. -/
private theorem low21_mod (x : Nat) : x &&& 2097151 = x % 2^21 := by
  apply Nat.eq_of_testBit_eq
  intro i
  have mask : Nat.testBit 2097151 i = decide (i < 21) := by
    by_cases low : i < 21
    · have cases : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 ∨ i = 5 ∨ i = 6 ∨ i = 7 ∨ i = 8 ∨ i = 9 ∨ i = 10 ∨ i = 11 ∨ i = 12 ∨ i = 13 ∨ i = 14 ∨ i = 15 ∨ i = 16 ∨ i = 17 ∨ i = 18 ∨ i = 19 ∨ i = 20 := by omega
      rcases cases with h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h | h
      all_goals subst i; decide
    · have bound : 2097151 < 2^i := Nat.lt_of_lt_of_le (by decide : 2097151 < 2^21)
        (Nat.pow_le_pow_right (by decide) (by omega))
      rw [Nat.testBit_lt_two_pow bound,decide_eq_false low]
  rw [Nat.testBit_and,Nat.testBit_mod_two_pow,mask]
  exact Bool.and_comm _ _

theorem prefix_slot_or_add (aligned : tableBase &&& 2097151 = 0) (bounded : slot < 512) :
    tableBase ||| (slot * 4096) = tableBase + slot * 4096 := by
  have alignedMod : tableBase % 2^21 = 0 := by rw [low21_mod] at aligned; exact aligned
  have decomposition := Nat.mod_add_div tableBase (2^21)
  have prefixEq : 2^21 * (tableBase / 2^21) = tableBase := by omega
  have low : slot * 4096 < 2^21 := by omega
  have fact := Nat.two_pow_add_eq_or_of_lt low (tableBase / 2^21)
  rw [prefixEq] at fact
  exact fact.symm

theorem LeafAccepted.mapping_native (accepted : LeafAccepted leaf physical mapping tableBase slot limit) :
    mapping = ((tableBase + slot * 4096) ||| 3) := by
  rw [accepted.2.2.2.2.2.2,prefix_slot_or_add accepted.2.2.2.2.1 accepted.2.2.2.2.2.1]

theorem mapping_or_add_tag (aligned : tableBase &&& 2097151 = 0) (bounded : slot < 512) :
    (tableBase ||| (slot * 4096) ||| 3) = tableBase + slot * 4096 + 3 := by
  have alignedMod : tableBase % 2097152 = 0 := by rw [low21_mod] at aligned; exact aligned
  have decomposition := Nat.mod_add_div tableBase 2097152
  have pageEq : 2^12 * (512 * (tableBase / 2097152) + slot) = tableBase + slot * 4096 := by omega
  have tag := Nat.two_pow_add_eq_or_of_lt (i := 12) (b := 3) (by decide)
    (512 * (tableBase / 2097152) + slot)
  rw [pageEq] at tag
  rw [prefix_slot_or_add aligned bounded]
  exact tag.symm

theorem mapping_sum_bounded (aligned : tableBase &&& 2097151 = 0) (bounded : slot < 512)
    (word : tableBase < wordLimit) : tableBase + slot * 4096 + 3 < wordLimit := by
  have alignedMod : tableBase % 2097152 = 0 := by rw [low21_mod] at aligned; exact aligned
  have decomposition := Nat.mod_add_div tableBase 2097152
  unfold wordLimit at *
  omega

theorem LeafAccepted.physical_aligned (accepted : LeafAccepted leaf physical mapping tableBase slot limit) :
    physical % 4096 = 0 := by
  have fact := Nat.and_mod_two_pow (a := leaf) (b := 4503599627366400) (n := 12)
  rw [accepted.2.1] at fact
  simpa only [Nat.reducePow,Nat.reduceMod,Nat.and_zero] using fact

theorem LeafAccepted.physical_width (accepted : LeafAccepted leaf physical mapping tableBase slot limit) :
    physical < 2^52 := by
  have bound := (Nat.and_le_right (n := leaf) (m := 4503599627366400))
  rw [accepted.2.1] at bound
  omega

def leafGuard (leaf physical mapping tableBase slot limit : GuardExpr .word) : GuardExpr .boolean :=
  .and (.and (.and (.and (.and (.and
    (.compare .eq (.bitAnd leaf (.wordLit 18442240474082185119)) (.wordLit 9223372036854775811))
    (.compare .eq (.bitAnd leaf (.wordLit 4503599627366400)) physical))
    (.compare .ne physical (.wordLit 0)))
    (.compare .lt physical limit))
    (.compare .eq (.bitAnd tableBase (.wordLit 2097151)) (.wordLit 0)))
    (.compare .lt slot (.wordLit 512)))
    (.compare .eq mapping (.bitOr (.bitOr tableBase (.shift12 slot)) (.wordLit 3)))
end Aurora.SourceBinding
