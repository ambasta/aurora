import SourceBinding.LocalBinding
namespace Aurora.SourceBinding

mutual
theorem ScopedStatementWith.cursors
    (scopeProof : ScopedStatementWith profile uses writes members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := by
  cases scopeProof with
  | declare => simp [addLocal]
  | assign | receiverAssign => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | returnValue => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | call => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | branch names child =>
    have monotone := child.cursors
    simp only [enterLocalScope,leaveLocalScope] at monotone ⊢
    exact ⟨Nat.le_trans (Nat.le_succ _) monotone.1,monotone.2⟩
  | branchElse enabled names yes no =>
    have first := yes.cursors
    have second := no.cursors
    simp only [enterLocalScope,leaveLocalScope] at first second ⊢
    exact ⟨Nat.le_trans (Nat.le_trans (Nat.le_succ _) first.1)
      (Nat.le_trans (Nat.le_succ _) second.1),Nat.le_trans first.2 second.2⟩

theorem ScopedStatementsWith.cursors
    (scopeProof : ScopedStatementsWith profile uses writes members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := by
  cases scopeProof with
  | nil => exact ⟨Nat.le_refl _,Nat.le_refl _⟩
  | cons head tail =>
    have first := head.cursors
    have rest := tail.cursors
    exact ⟨Nat.le_trans first.1 rest.1,Nat.le_trans first.2 rest.2⟩
end

theorem ScopedStatementWith.visible_subset
    (scopeProof : ScopedStatementWith profile uses writes members module path formals before raw after declaredItems) :
    ∀ binding ∈ before.visible, binding ∈ after.visible := by
  cases scopeProof with
  | declare => intro binding present; exact List.mem_cons_of_mem _ present
  | assign | receiverAssign | returnValue | call => intro binding present; exact present
  | branch | branchElse => intro binding present; exact present

theorem ScopedStatementsWith.visible_subset
    (scopeProof : ScopedStatementsWith profile uses writes members module path formals before raw after declaredItems) :
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
theorem ScopedStatementWith.formal_clear
    (scopeProof : ScopedStatementWith profile uses writes members module path formals before raw after declaredItems)
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
  | assign | receiverAssign | returnValue | call => exact clear
  | branch | branchElse => exact clear

theorem ScopedStatementsWith.formal_clear
    (scopeProof : ScopedStatementsWith profile uses writes members module path formals before raw after declaredItems)
    (clear : ∀ binding ∈ before.visible, binding.name ∉ formals.map (·.name)) :
    ∀ binding ∈ after.visible, binding.name ∉ formals.map (·.name) := by
  induction raw generalizing before after declaredItems with
  | nil => cases scopeProof; exact clear
  | cons first rest ih =>
    cases scopeProof with
    | cons head tail => exact ih tail (head.formal_clear clear)

theorem ScopedStatementWith.scope_eq
    (scopeProof : ScopedStatementWith profile uses writes members module path formals before raw after declaredItems) :
    after.scope = before.scope := by
  cases scopeProof <;> rfl

theorem ScopedStatementsWith.scope_eq
    (scopeProof : ScopedStatementsWith profile uses writes members module path formals before raw after declaredItems) :
    after.scope = before.scope := by
  induction raw generalizing before after declaredItems with
  | nil => cases scopeProof; rfl
  | cons first rest ih =>
    cases scopeProof with
    | cons head tail => exact (ih tail).trans head.scope_eq

theorem ScopedStatement.cursors
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := ScopedStatementWith.cursors scopeProof

theorem ScopedStatement.visible_subset
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    ∀ binding ∈ before.visible, binding ∈ after.visible := ScopedStatementWith.visible_subset scopeProof

theorem ScopedStatement.scope_eq
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems) :
    after.scope = before.scope := ScopedStatementWith.scope_eq scopeProof

theorem ScopedStatement.formal_clear
    (scopeProof : ScopedStatement members module path formals before raw after declaredItems)
    (clear : ∀ binding ∈ before.visible, binding.name ∉ formals.map (·.name)) :
    ∀ binding ∈ after.visible, binding.name ∉ formals.map (·.name) :=
  ScopedStatementWith.formal_clear scopeProof clear

theorem ScopedStatements.cursors
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    before.nextScope ≤ after.nextScope ∧ before.nextSlot ≤ after.nextSlot := ScopedStatementsWith.cursors scopeProof

theorem ScopedStatements.visible_subset
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    ∀ binding ∈ before.visible, binding ∈ after.visible := ScopedStatementsWith.visible_subset scopeProof

theorem ScopedStatements.scope_eq
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems) :
    after.scope = before.scope := ScopedStatementsWith.scope_eq scopeProof

theorem ScopedStatements.formal_clear
    (scopeProof : ScopedStatements members module path formals before raw after declaredItems)
    (clear : ∀ binding ∈ before.visible, binding.name ∉ formals.map (·.name)) :
    ∀ binding ∈ after.visible, binding.name ∉ formals.map (·.name) :=
  ScopedStatementsWith.formal_clear scopeProof clear

@[simp] theorem leaveLocalScope_visible (before after : LocalContext) :
    (leaveLocalScope before after).visible = before.visible := rfl
@[simp] theorem leaveLocalScope_scope (before after : LocalContext) :
    (leaveLocalScope before after).scope = before.scope := rfl

end Aurora.SourceBinding
