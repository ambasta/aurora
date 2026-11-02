import SourceBinding.FramePolicySpec

namespace Aurora.SourceBinding.FramePolicyAttachment
open FramePolicy

/-! Constructive fixed-width identities shared by record_valid and the root.
No source/IR correspondence or record authenticity is asserted here. -/

private theorem mask4_bits (i : Nat) :
    Nat.testBit 15 i = decide (i < 4) := by
  by_cases low : i < 4
  · have cases : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 := by omega
    rcases cases with h0 | h1 | h2 | h3
    all_goals subst i; decide
  · have bound : 15 < 2^i := Nat.lt_of_lt_of_le (by decide : 15 < 2^4)
      (Nat.pow_le_pow_right (by decide) (by omega))
    rw [Nat.testBit_lt_two_pow bound, decide_eq_false low]

private theorem mask28_bits (i : Nat) :
    Nat.testBit 268435455 i = decide (i < 28) := by
  by_cases low : i < 28
  · have cases : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 ∨ i = 5 ∨ i = 6 ∨ i = 7 ∨ i = 8 ∨ i = 9 ∨ i = 10 ∨ i = 11 ∨ i = 12 ∨ i = 13 ∨ i = 14 ∨ i = 15 ∨ i = 16 ∨ i = 17 ∨ i = 18 ∨ i = 19 ∨ i = 20 ∨ i = 21 ∨ i = 22 ∨ i = 23 ∨ i = 24 ∨ i = 25 ∨ i = 26 ∨ i = 27 := by omega
    rcases cases with h0 | h1 | h2 | h3 | h4 | h5 | h6 | h7 | h8 | h9 | h10 | h11 | h12 | h13 | h14 | h15 | h16 | h17 | h18 | h19 | h20 | h21 | h22 | h23 | h24 | h25 | h26 | h27
    all_goals subst i; decide
  · have bound : 268435455 < 2^i := Nat.lt_of_lt_of_le (by decide : 268435455 < 2^28)
      (Nat.pow_le_pow_right (by decide) (by omega))
    rw [Nat.testBit_lt_two_pow bound, decide_eq_false low]

private theorem fixed_mask_mod (x mask n : Nat)
    (bits : ∀ i, Nat.testBit mask i = decide (i < n)) : x &&& mask = x % 2^n := by
  apply Nat.eq_of_testBit_eq
  intro i
  rw [Nat.testBit_and, Nat.testBit_mod_two_pow, bits]
  exact Bool.and_comm _ _

theorem state_mask (record : Nat) : record &&& 15 = stateOf record := by
  exact fixed_mask_mod record 15 4 mask4_bits

theorem generation_mask (record : Nat) :
    (record / 16) &&& generationMax = generationOf record := by
  exact fixed_mask_mod (record / 16) 268435455 28 mask28_bits

theorem word_shift (record : Nat) : record >>> 32 = wordOf record := by
  exact Nat.shiftRight_eq_div_pow record 32

theorem generation_shift_mask (record : Nat) :
    (record >>> 4) &&& generationMax = generationOf record := by
  rw [Nat.shiftRight_eq_div_pow]
  exact generation_mask record

theorem word_bound (bounded : record < u64Modulus) : wordOf record ≤ wordMax := by
  simp only [wordOf, wordMax, wordModulus, u64Modulus] at *
  omega

end Aurora.SourceBinding.FramePolicyAttachment
