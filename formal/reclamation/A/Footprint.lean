import Std
namespace Aurora.A
abbrev Footprint := List Nat
namespace Footprint
def Within (c p : Footprint) : Prop := c ⊆ p
def Contains (p : Footprint) (cell : Nat) : Prop := cell ∈ p
def subtract (p f : Footprint) : Footprint := p.filter (fun x => !(decide (x ∈ f)))
@[simp] theorem mem_subtract : x ∈ subtract p f ↔ x ∈ p ∧ x ∉ f := by simp [subtract]
instance (c p : Footprint) : Decidable (c.Within p) := inferInstanceAs (Decidable (c ⊆ p))
instance (p : Footprint) (cell : Nat) : Decidable (p.Contains cell) := inferInstanceAs (Decidable (cell ∈ p))
end Footprint
namespace Inventory
variable {Key : Type} [DecidableEq Key]
def move (m : Key → Footprint) (src dst : Key) (f : Footprint) : Key → Footprint :=
  fun k => if k = src then (m k).subtract f else if k = dst then m k ++ f else m k
variable {m : Key → Footprint} {src dst : Key} {f allocation : Footprint}
structure Partition (allocation : Footprint) (m : Key → Footprint) : Prop where
  bound : ∀ k, m k ⊆ allocation
  unique : ∀ a b cell, cell ∈ m a → cell ∈ m b → a = b
  cover : ∀ cell, cell ∈ allocation → ∃ k, cell ∈ m k
@[simp] theorem move_source : move m src dst f src = (m src).subtract f := by simp [move]
@[simp] theorem move_destination (distinct : src ≠ dst) : move m src dst f dst = m dst ++ f := by simp [move, Ne.symm distinct]
theorem move_partition (h : Partition allocation m) (distinct : src ≠ dst) (owned : f ⊆ m src) :
    Partition allocation (move m src dst f) := by
  constructor
  · intro k cell member
    by_cases source : k = src
    · subst k; simp [move] at member; exact h.bound src member.1
    · by_cases destination : k = dst
      · subst k; simp [move, source] at member
        rcases member with old | moved
        · exact h.bound dst old
        · exact h.bound src (owned moved)
      · exact h.bound k (by simpa [move, source, destination] using member)
  · intro a b cell ha hb
    have classify (k) (hk : cell ∈ move m src dst f k) :
        (cell ∈ m k ∧ (k = src → cell ∉ f)) ∨ (k = dst ∧ cell ∈ f) := by
      by_cases source : k = src
      · subst k; simp [move] at hk; exact Or.inl ⟨hk.1, fun _ => hk.2⟩
      · by_cases destination : k = dst
        · simp only [move, if_neg source, if_pos destination, List.mem_append] at hk
          exact hk.elim (fun old => Or.inl ⟨old, fun bad => False.elim (source bad)⟩) (fun moved => Or.inr ⟨destination,moved⟩)
        · exact Or.inl ⟨by simpa [move,source,destination] using hk, fun bad => False.elim (source bad)⟩
    rcases classify a ha with ⟨oldA,notMovedA⟩ | ⟨aDst,movedA⟩ <;>
      rcases classify b hb with ⟨oldB,notMovedB⟩ | ⟨bDst,movedB⟩
    · exact h.unique a b cell oldA oldB
    · have aSrc := h.unique a src cell oldA (owned movedB)
      exact False.elim (notMovedA aSrc movedB)
    · have bSrc := h.unique b src cell oldB (owned movedA)
      exact False.elim (notMovedB bSrc movedA)
    · exact aDst.trans bDst.symm
  · intro cell member
    obtain ⟨k,hk⟩ := h.cover cell member
    by_cases moved : cell ∈ f
    · exact ⟨dst, by simp [move, Ne.symm distinct, moved]⟩
    · exact ⟨k, by by_cases source : k = src <;> by_cases destination : k = dst <;> simp_all [move]⟩
end Inventory
end Aurora.A
