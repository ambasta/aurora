import SourceBinding.LocalBinding
namespace Aurora.SourceBinding

mutual
theorem ScopedStatement.cursors
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := by
  cases scopeProof with
  | declare => simp [addLocal]
  | assign => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | returnValue => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | call => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | branch names child =>
    have monotone := child.cursors
    simp only [enterLocalScope,leaveLocalScope] at monotone ⊢
    exact ⟨Nat.le_trans (Nat.le_succ _) monotone.1,monotone.2⟩

theorem ScopedStatements.cursors
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := by
  cases scopeProof with
  | nil => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | cons head tail =>
    have first := head.cursors
    have rest := tail.cursors
    exact ⟨Nat.le_trans first.1 rest.1,Nat.le_trans first.2 rest.2⟩
end

theorem ScopedStatement.visible_subset
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    ∀ binding ∈ before.visible, binding ∈ after.visible := by
  cases scopeProof with
  | declare => intro binding present; exact List.mem_cons_of_mem _ present
  | assign | returnValue | call => intro binding present; exact present
  | branch => intro binding present; exact present

theorem ScopedStatements.visible_subset
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    ∀ binding ∈ before.visible, binding ∈ after.visible := by
  induction raw generalizing before after declaredItems with
  | nil => cases scopeProof; intro binding present; exact present
  | cons first rest ih =>
    cases scopeProof with
    | cons head tail =>
      intro binding present
      exact ih tail binding (head.visible_subset binding present)

/-- Scoping never lets a visible local shadow a formal, including when a
    statement list ends immediately after a declaration. -/
theorem ScopedStatement.formal_clear
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems)
    (clear : ∀ binding ∈ before.visible, binding.name ∉ formals.map (·.name)) :
    ∀ binding ∈ after.visible, binding.name ∉ formals.map (·.name) := by
  cases scopeProof with
  | declare typ allowed fresh typeClear expression =>
    intro binding present
    rcases List.mem_cons.mp present with same | old
    · subst binding
      intro collision
      exact fresh (List.mem_append_left _ collision)
    · exact clear binding old
  | assign | returnValue | call => exact clear
  | branch => exact clear

theorem ScopedStatements.formal_clear
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems)
    (clear : ∀ binding ∈ before.visible, binding.name ∉ formals.map (·.name)) :
    ∀ binding ∈ after.visible, binding.name ∉ formals.map (·.name) := by
  induction raw generalizing before after declaredItems with
  | nil => cases scopeProof; exact clear
  | cons first rest ih =>
    cases scopeProof with
    | cons head tail => exact ih tail (head.formal_clear clear)

theorem ScopedStatement.scope_eq
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    after.scope = before.scope := by
  cases scopeProof <;> rfl

theorem ScopedStatements.scope_eq
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    after.scope = before.scope := by
  induction raw generalizing before after declaredItems with
  | nil => cases scopeProof; rfl
  | cons first rest ih =>
    cases scopeProof with
    | cons head tail => exact (ih tail).trans head.scope_eq

@[simp] theorem leaveLocalScope_visible (before after : LocalContext) :
    (leaveLocalScope before after).visible = before.visible := rfl
@[simp] theorem leaveLocalScope_scope (before after : LocalContext) :
    (leaveLocalScope before after).scope = before.scope := rfl

end Aurora.SourceBinding
