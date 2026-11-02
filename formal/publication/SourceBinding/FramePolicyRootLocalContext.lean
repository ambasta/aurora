import SourceBinding.FramePolicyRootInputUpdates
namespace Aurora.SourceBinding.FramePolicyAttachment
open Aurora.Publication
variable {input : ByteArray} {files : List SourceFile} {root : Name}
variable {bound : RuntimeDAGBinding input files root frameModule framePath rootName}
variable {profile : ExactProfile bound}

/-- Actual declaration cursor and inventory; initializer execution is not assumed. -/
theorem ExactProfile.root_const_declaration (profile : ExactProfile bound)
    (scopedDecl : ScopedStatement (rootInputContext profile).members frameModule framePath
      (rootInputContext profile).formals before (localDecl name true value) after items) :
    after = addLocal before (declaredLocal before (bytes name) (.scalar .word) false) ∧
    items = [declaredLocal before (bytes name) (.scalar .word) false] := by
  cases scopedDecl with
  | declare typing allowed fresh unshadowed names =>
    cases typing with
    | mutable typing =>
      cases typing with
      | nominal present named =>
        simp only [formal,EnumSourceName] at named
        rcases named with impossible | impossible <;> cases impossible
    | constant typing =>
      have same := RuntimeSourceType.unique profile.root_input_context.scope typing RuntimeSourceType.word
      subst_vars
      exact ⟨rfl,rfl⟩

private theorem add_local_valid (profile : ExactProfile bound)
    (valid : RuntimeContextValid (rootCursorContext profile before))
    (allowed : NameAllowed binding.name)
    (fresh : binding.name ∉ visibleNames (rootInputContext profile).formals before.visible)
    (lower : 8 * (rootInputContext profile).formals.length < binding.slot)
    (aligned : binding.slot % 8 = 0)
    (later : ∀ old ∈ before.visible, old.slot < binding.slot) :
    RuntimeContextValid (rootCursorContext profile (addLocal before binding)) := by
  obtain ⟨formalNames,visibleNamesUnique,slotsUnique,oldValid,types⟩ := valid.names
  have clearFormal : binding.name ∉ (rootInputContext profile).formals.map (·.name) :=
    fun found => fresh (List.mem_append_left _ found)
  have clearLocal : binding.name ∉ before.visible.map (·.name) :=
    fun found => fresh (List.mem_append_right _ found)
  refine ⟨valid.scope,formalNames,?_,?_,?_,types⟩
  · exact List.nodup_cons.mpr ⟨clearLocal,visibleNamesUnique⟩
  · apply List.nodup_cons.mpr
    refine ⟨?_,slotsUnique⟩
    intro found
    obtain ⟨old,member,equal⟩ := List.mem_map.mp found
    have less := later old member
    change old.slot = binding.slot at equal
    omega
  · intro old member
    change old ∈ binding :: before.visible at member
    rcases List.mem_cons.mp member with equal | member
    · subst old
      exact ⟨allowed,clearFormal,lower,aligned⟩
    · exact oldValid old member

theorem ExactProfile.root_const_context (profile : ExactProfile bound)
    (valid : RuntimeContextValid (rootCursorContext profile before))
    (scopedDecl : ScopedStatement (rootInputContext profile).members frameModule framePath
      (rootInputContext profile).formals before (localDecl name true value) after items)
    (lower : 5 ≤ before.nextSlot)
    (later : ∀ old ∈ before.visible, old.slot < runtimeParameterSlot before.nextSlot) :
    RuntimeContextValid (rootCursorContext profile after) := by
  cases scopedDecl with
  | declare typing allowed fresh unshadowed names =>
    cases typing with
    | mutable typing =>
      cases typing with
      | nominal present named =>
        simp only [formal,EnumSourceName] at named
        rcases named with impossible | impossible <;> cases impossible
    | constant typing =>
      have same := RuntimeSourceType.unique profile.root_input_context.scope typing RuntimeSourceType.word
      subst_vars
      apply add_local_valid profile valid allowed fresh
      · rw [profile.root_input_formals]
        change 8 * 5 < 8 * (before.nextSlot + 1)
        omega
      · simp only [declaredLocal,Nat.mul_mod,Nat.mod_self,Nat.zero_mul,Nat.zero_mod]
      · exact later

/-- Both real scoped declarations, including actual private-slot advancement. -/
theorem ExactProfile.root_two_local_contexts (profile : ExactProfile bound)
    (empty : before.visible = []) (lower : 5 ≤ before.nextSlot)
    (stateDecl : ScopedStatement (rootInputContext profile).members frameModule framePath
      (rootInputContext profile).formals before
      (localDecl "state" true (bin .bitAnd (v "record") (.word 15))) middle stateItems)
    (currentDecl : ScopedStatement (rootInputContext profile).members frameModule framePath
      (rootInputContext profile).formals middle
      (localDecl "current" true (bin .bitAnd
        (bin .rightShift (v "record") (.signedCount 4)) (call "generation_limit"))) after currentItems) :
    RuntimeContextValid (rootCursorContext profile middle) ∧
    RuntimeContextValid (rootCursorContext profile after) := by
  have initial : RuntimeContextValid (rootCursorContext profile before) := by
    change RuntimeContextValid (runtimeStatementContext bound.checked.shape.rootNode.source.context.members
      frameModule framePath bound.checked.shape.rootNode.source.context.formals before)
    rw [profile.root_input_cursor before empty]
    exact profile.root_input_context
  have middleValid := profile.root_const_context initial stateDecl lower (by simp [empty])
  refine ⟨middleValid,profile.root_const_context middleValid currentDecl ?_ ?_⟩
  · rw [(profile.root_const_declaration stateDecl).1]
    change 5 ≤ before.nextSlot + 1
    omega
  · rw [(profile.root_const_declaration stateDecl).1]
    intro old member
    simp only [addLocal,empty,List.mem_cons,List.not_mem_nil,or_false] at member
    subst old
    change 8 * (before.nextSlot + 1) < 8 * (before.nextSlot + 1 + 1)
    omega
end Aurora.SourceBinding.FramePolicyAttachment
