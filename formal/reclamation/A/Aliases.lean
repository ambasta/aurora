import A.Safety
namespace Aurora.A.Aliases

/-- A finite view may be scattered and the interpretation need not be injective:
different logical addresses may designate the same canonical backing cell.
Correctness of a native page/frame/IOMMU interpretation is a separate obligation. -/
def image (interpret : Address → Nat) (view : List Address) : Footprint := view.map interpret

theorem image_contains (interpret : Address → Nat) (member : address ∈ view) :
    (image interpret view).Contains (interpret address) :=
  List.mem_map.mpr ⟨address,member,rfl⟩

/-- A logical name cannot conceal a conflict when both operational accesses use
an alias-preserving interpretation. This does not verify a native decoder. -/
theorem enabled_aliases_are_readers (interpret : Address → Nat)
    (h : Invariant allocation s) (aliasing : interpret a = interpret b)
    (left : Enabled s i (interpret a) wi) (right : Enabled s j (interpret b) wj)
    (distinct : i ≠ j) : wi = false ∧ wj = false := by
  apply overlapping_enabled_streams_are_readers h left _ distinct
  simpa only [aliasing] using right

/-- Disjointness is checked on backing images, not on names of views or frames. -/
theorem disjoint_images_separate (interpret : Address → Nat)
    (disjoint : ∀ cell, cell ∈ image interpret left → cell ∈ image interpret right → False)
    (ha : a ∈ left) (hb : b ∈ right) : interpret a ≠ interpret b := by
  intro same
  exact disjoint (interpret a) (image_contains interpret ha)
    (by simpa only [same] using image_contains interpret hb)
end Aurora.A.Aliases
