import SourceBinding.OwnedWordsModel
namespace Aurora.SourceBinding

@[simp] theorem OwnedWordsBank.write_size (bank : OwnedWordsBank)
    (index : Fin bank.size) (value : Nat) : (bank.write index value).size = bank.size := rfl

@[simp] theorem OwnedWordsBank.write_same (bank : OwnedWordsBank)
    (index : Fin bank.size) (value : Nat) : (bank.write index value).cells index = value := by
  simp only [OwnedWordsBank.write,ite_true]

theorem OwnedWordsBank.write_other (bank : OwnedWordsBank)
    (index other : Fin bank.size) (value : Nat) (different : other ≠ index) :
    (bank.write index value).cells other = bank.cells other := by
  simp only [OwnedWordsBank.write,if_neg different]

theorem OwnedWordsBank.write_valid (bank : OwnedWordsBank)
    (index : Fin bank.size) (value : Nat) (valid : bank.Valid) (bounded : value < wordLimit) :
    (bank.write index value).Valid := by
  refine ⟨valid.1,valid.2.1,?_⟩
  intro other
  by_cases same : other = index
  · subst other
    exact (bank.write_same index value).symm ▸ bounded
  · rw [bank.write_other index other value same]
    exact valid.2.2 other

@[simp] theorem OwnedWordsWorld.write_same (world : OwnedWordsWorld Other)
    (identity : Nat) (bank : OwnedWordsBank) :
    (world.write identity bank).banks identity = some bank := by
  simp only [OwnedWordsWorld.write,ite_true]

theorem OwnedWordsWorld.write_other_bank (world : OwnedWordsWorld Other)
    (identity other : Nat) (bank : OwnedWordsBank) (different : other ≠ identity) :
    (world.write identity bank).banks other = world.banks other := by
  simp only [OwnedWordsWorld.write,if_neg different]

@[simp] theorem OwnedWordsWorld.write_other (world : OwnedWordsWorld Other)
    (identity : Nat) (bank : OwnedWordsBank) :
    (world.write identity bank).other = world.other := rfl

/-- Initial abstract admission, not a repeated successful-resource-call oracle. -/
def OwnedWordsInterface.Admitted (interface : OwnedWordsInterface)
    (shared : SourceShared (OwnedWordsWorld Other)) : Prop :=
  ∃ bank, shared.world.banks interface.bank = some bank ∧ bank.Valid

theorem OwnedWordsResponse.receiver_frame
    (responded : OwnedWordsResponse interface request outcome after) :
    after.receiver = request.before.receiver := by cases responded <;> rfl

theorem OwnedWordsResponse.other_frame
    (responded : OwnedWordsResponse interface request outcome after) :
    after.world.other = request.before.world.other := by cases responded <;> rfl

theorem OwnedWordsResponse.bank_frame
    (responded : OwnedWordsResponse interface request outcome after)
    (different : other ≠ interface.bank) :
    after.world.banks other = request.before.world.banks other := by
  cases responded with
  | set found valid write inside bounded => exact OwnedWordsWorld.write_other_bank _ _ _ _ different
  | size | read | missing | invalid | atBounds | setBounds | denied => rfl

theorem OwnedWordsResponse.preserves_admission
    (responded : OwnedWordsResponse interface request outcome after)
    (admitted : interface.Admitted request.before) : interface.Admitted after := by
  cases responded with
  | set found valid write inside bounded =>
      exact ⟨_,OwnedWordsWorld.write_same _ _ _,OwnedWordsBank.write_valid _ _ _ valid bounded⟩
  | size | read | missing | invalid | atBounds | setBounds | denied => exact admitted

theorem OwnedWordsBank.write_replacement (bank : OwnedWordsBank)
    (index : Fin bank.size) (value : Nat) :
    MemoryManagerRelease.OneCellReplacement bank.cells (bank.write index value).cells index value :=
  ⟨bank.write_same index value,fun other different => bank.write_other index other value different⟩

end Aurora.SourceBinding
