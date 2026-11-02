import SourceBinding.RuntimeExpressions
namespace Aurora.SourceBinding

private theorem named_member_unique {α β : Type} (f : α → β) {items : List α} {a b : α}
    (unique : (items.map f).Nodup) (left : a ∈ items) (right : b ∈ items) (same : f a = f b) : a = b := by
  induction items generalizing a b with
  | nil => simp at left
  | cons head tail ih =>
    have valid := List.nodup_cons.mp unique
    rcases List.mem_cons.mp left with rfl | leftTail
    · rcases List.mem_cons.mp right with rfl | rightTail
      · rfl
      · exact False.elim (valid.1 (same ▸ List.mem_map.mpr ⟨b,rightTail,rfl⟩))
    · rcases List.mem_cons.mp right with rfl | rightTail
      · exact False.elim (valid.1 (same ▸ List.mem_map.mpr ⟨a,leftTail,rfl⟩))
      · exact ih valid.2 leftTail rightTail same

private theorem named_index_unique {α β : Type} (f : α → β) {items : List α} {a b : α} {i j : Nat}
    (unique : (items.map f).Nodup) (left : items[i]? = some a) (right : items[j]? = some b)
    (same : f a = f b) : i = j := by
  apply List.getElem?_inj (xs := items.map f)
  · simpa only [List.length_map] using (List.getElem?_eq_some_iff.mp left).1
  · exact unique
  · simp only [List.getElem?_map,left,right,Option.map_some,same]

private theorem filtered_member_unique {α β : Type} (f : α → Option β) {items : List α} {a b : α} {name : β}
    (unique : (items.filterMap f).Nodup) (left : a ∈ items) (right : b ∈ items)
    (leftName : f a = some name) (rightName : f b = some name) : a = b := by
  induction items generalizing a b with
  | nil => simp at left
  | cons head tail ih =>
    rcases List.mem_cons.mp left with rfl | leftTail
    · rcases List.mem_cons.mp right with rfl | rightTail
      · rfl
      · have valid : name ∉ tail.filterMap f := by
          rw [List.filterMap_cons_some leftName] at unique
          exact (List.nodup_cons.mp unique).1
        exact False.elim (valid (List.mem_filterMap.mpr ⟨b,rightTail,rightName⟩))
    · rcases List.mem_cons.mp right with rfl | rightTail
      · have valid : name ∉ tail.filterMap f := by
          rw [List.filterMap_cons_some rightName] at unique
          exact (List.nodup_cons.mp unique).1
        exact False.elim (valid (List.mem_filterMap.mpr ⟨a,leftTail,leftName⟩))
      · have tailUnique : (tail.filterMap f).Nodup := by
          cases value : f head with
          | none => simpa [List.filterMap_cons,value] using unique
          | some v =>
            rw [List.filterMap_cons_some value] at unique
            exact (List.nodup_cons.mp unique).2
        exact ih tailUnique leftTail rightTail leftName rightName

private theorem enum_source_last (found : EnumSourceName path name source) :
    ∃ names, source = .named names ∧ names.getLast? = some name := by
  rcases found with rfl | rfl
  · exact ⟨[name],rfl,rfl⟩
  · exact ⟨path ++ [name],rfl,by simp⟩

private theorem enum_source_same (left : EnumSourceName path a source) (right : EnumSourceName path b source) : a = b := by
  rcases enum_source_last left with ⟨names,sourceEq,last⟩
  rcases enum_source_last right with ⟨others,otherEq,otherLast⟩
  have same : names = others := SourceType.named.inj (sourceEq.symm.trans otherEq)
  subst others
  exact Option.some.inj (last.symm.trans otherLast)

private theorem enum_not_scalar (scope : ScopeBindings members)
    (present : Declaration.enumDecl name cases ∈ members)
    (named : EnumSourceName path name (.named [scalar.toUTF8]))
    (builtinName : scalar ∈ (["bool","u64"] : List String)) : False := by
  have bound := scope.member present
  cases bound with
  | enumDecl allowed _ _ =>
    have same : name = scalar.toUTF8 := enum_source_same named (Or.inl rfl)
    subst name
    apply allowed scalar
    · have cases : scalar = "bool" ∨ scalar = "u64" := by simpa using builtinName
      rcases cases with rfl | rfl <;> simp
    · rfl

theorem RuntimeSourceType.unique (scope : ScopeBindings members)
    (left : RuntimeSourceType members module path source a)
    (right : RuntimeSourceType members module path source b) : a = b := by
  cases left with
  | word =>
    cases right with
    | word => rfl
    | nominal present named => exact False.elim (enum_not_scalar scope present named (by simp))
  | boolean =>
    cases right with
    | boolean => rfl
    | nominal present named => exact False.elim (enum_not_scalar scope present named (by simp))
  | nominal present named =>
    cases right with
    | word => exact False.elim (enum_not_scalar scope present named (by simp))
    | boolean => exact False.elim (enum_not_scalar scope present named (by simp))
    | nominal other otherName =>
      have names := enum_source_same named otherName
      subst names
      have declarations := filtered_member_unique declarationName scope.unique present other rfl rfl
      cases declarations
      rfl

theorem RuntimeVariableBinding.unique (valid : RuntimeContextValid context)
    (left : RuntimeVariableBinding context name a) (right : RuntimeVariableBinding context name b) : a = b := by
  cases left with
  | formal present named typ clear =>
    cases right with
    | formal other otherName otherType otherClear =>
      have indices := named_index_unique Formal.name valid.names.1.1 present other (named.trans otherName.symm)
      subst indices
      have declarations := Option.some.inj (present.symm.trans other)
      subst declarations
      have kinds := typ.unique valid.scope otherType
      subst kinds
      rfl
    | localValue other otherName otherClear =>
      exact False.elim (clear (List.mem_map.mpr ⟨_,other,otherName⟩))
  | localValue present named clear =>
    cases right with
    | formal other otherName otherType otherClear =>
      exact False.elim (otherClear (List.mem_map.mpr ⟨_,present,named⟩))
    | localValue other otherName otherClear =>
      exact named_member_unique SourceLocal.name valid.names.2.1 present other (named.trans otherName.symm)

private theorem enum_value_ends (found : RuntimeEnumValue context source identity ordinal) :
    ∃ enumName caseName cases,
      Declaration.enumDecl enumName cases ∈ context.members ∧ cases[ordinal]? = some caseName ∧
      source.getLast? = some caseName ∧ source.dropLast.getLast? = some enumName ∧
      identity = ⟨enumSymbol context.module context.path enumName,cases.length⟩ := by
  cases found with
  | caseValue present index named _ =>
    refine ⟨_,_,_,present,index,?_,?_,rfl⟩
    · rcases named with rfl | rfl <;> simp
    · rcases named with rfl | rfl <;> simp

theorem RuntimeEnumValue.unique (valid : RuntimeContextValid context)
    (left : RuntimeEnumValue context source a i) (right : RuntimeEnumValue context source b j) : a = b ∧ i = j := by
  rcases enum_value_ends left with ⟨name,caseName,cases,present,index,last,prior,identity⟩
  rcases enum_value_ends right with ⟨otherName,otherCase,otherCases,otherPresent,otherIndex,otherLast,otherPrior,otherIdentity⟩
  have names := Option.some.inj (prior.symm.trans otherPrior)
  have values := Option.some.inj (last.symm.trans otherLast)
  subst otherName; subst otherCase
  have declarations := filtered_member_unique declarationName valid.scope.unique present otherPresent rfl rfl
  cases declarations
  have bound := valid.scope.member present
  cases bound with
  | enumDecl _ unique _ =>
    refine ⟨identity.trans otherIdentity.symm,?_⟩
    exact List.getElem?_inj (List.getElem?_eq_some_iff.mp index).1 unique (index.trans otherIndex.symm)

theorem RuntimeEnumValue.not_singleton (found : RuntimeEnumValue context [name] identity ordinal) : False := by
  rcases enum_value_ends found with ⟨enumName,caseName,cases,present,index,last,prior,result⟩
  simp at prior

theorem RuntimeWordOperator.unique (left : RuntimeWordOperator source a ka)
    (right : RuntimeWordOperator source b kb) : a = b ∧ ka = kb := by
  cases left <;> cases right <;> exact ⟨rfl,rfl⟩

end Aurora.SourceBinding
