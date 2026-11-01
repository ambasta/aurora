import SourceBinding.Declarations
namespace Aurora.SourceBinding

/-- A conservative item-name policy; not the full Aurora reserved vocabulary. -/
def NameAllowed (name : ByteArray) : Prop :=
  ∀ reservedType ∈ (["builtin","bool","i64","u64","u8","void"] : List String), name ≠ reservedType.toUTF8
instance (name : ByteArray) : Decidable (NameAllowed name) := by unfold NameAllowed; infer_instance

def declarationName : Declaration → Option ByteArray
  | .namespaceDecl name _ _ | .classDecl name _ | .enumDecl name _ => some name
  | .functionDecl f => some f.name
  | .fieldDecl f => some f.name
  | .constructorDecl _ => some ByteArray.empty
  | .access _ => none

def fields (members : List Declaration) : List Formal := members.filterMap fun d =>
  match d with | .fieldDecl f => some f | _ => none

def FormalNames (params : List Formal) : Prop :=
  (params.map (·.name)).Nodup ∧ ∀ p ∈ params, NameAllowed p.name
instance (params : List Formal) : Decidable (FormalNames params) := by unfold FormalNames; infer_instance

def MemberBindings (members : List Declaration) (member : Declaration) : Prop :=
  let names := (fields members).map (·.name)
  match member with
    | .functionDecl f => ∀ p ∈ f.formals, p.name ∉ names
    | .constructorDecl c => (c.initializers.map (·.name)).Nodup ∧
        (∀ i ∈ c.initializers, i.name ∈ names) ∧ (∀ p ∈ c.formals, p.name ∉ names)
    | _ => True
instance (members : List Declaration) (member : Declaration) : Decidable (MemberBindings members member) := by
  unfold MemberBindings
  cases member <;> dsimp <;> infer_instance

def ClassBindings (members : List Declaration) : Prop := ∀ member ∈ members, MemberBindings members member
instance (members : List Declaration) : Decidable (ClassBindings members) := by
  unfold ClassBindings; infer_instance

mutual
  inductive DeclarationBindings : Declaration → Prop
    | namespaceDecl : NameAllowed name → ScopeBindings decls →
        DeclarationBindings (.namespaceDecl name exported decls)
    | classDecl : NameAllowed name → ScopeBindings members → ClassBindings members →
        DeclarationBindings (.classDecl name members)
    | enumDecl : NameAllowed name → names.Nodup → (∀ item ∈ names, NameAllowed item) →
        DeclarationBindings (.enumDecl name names)
    | functionDecl : NameAllowed function.name → FormalNames function.formals →
        DeclarationBindings (.functionDecl function)
    | constructorDecl : FormalNames constructor.formals → DeclarationBindings (.constructorDecl constructor)
    | fieldDecl : NameAllowed field.name → DeclarationBindings (.fieldDecl field)
    | access : DeclarationBindings (.access visibility)
  inductive ScopeBindings : List Declaration → Prop
    | scope : (decls.filterMap declarationName).Nodup →
        ListBindings decls → ScopeBindings decls
  inductive ListBindings : List Declaration → Prop
    | empty : ListBindings []
    | next : DeclarationBindings item → ListBindings decls → ListBindings (item :: decls)
end

mutual
  def checkDeclarationBindings : (fuel : Nat) → (item : Declaration) →
      Option { _witness : Unit // DeclarationBindings item }
    | 0, _ => none
    | fuel + 1, decl => match decl with
      | .namespaceDecl name _ children => do
        if nameOK : NameAllowed name then
          let child ← checkScopeBindings fuel children
          return ⟨(),.namespaceDecl nameOK child.property⟩
        else none
      | .classDecl name members => do
        if nameOK : NameAllowed name then
          let child ← checkScopeBindings fuel members
          if classOK : ClassBindings members then return ⟨(),.classDecl nameOK child.property classOK⟩ else none
        else none
      | .enumDecl name names =>
        if nameOK : NameAllowed name then
          if unique : names.Nodup then
            if casesOK : ∀ item ∈ names, NameAllowed item then return ⟨(),.enumDecl nameOK unique casesOK⟩ else none
          else none
        else none
      | .functionDecl function =>
        if nameOK : NameAllowed function.name then
          if params : FormalNames function.formals then return ⟨(),.functionDecl nameOK params⟩ else none
        else none
      | .constructorDecl constructor =>
        if params : FormalNames constructor.formals then return ⟨(),.constructorDecl params⟩ else none
      | .fieldDecl field => if nameOK : NameAllowed field.name then return ⟨(),.fieldDecl nameOK⟩ else none
      | .access _ => some ⟨(),.access⟩
  def checkListBindings : (fuel : Nat) → (decls : List Declaration) →
      Option { _witness : Unit // ListBindings decls }
    | 0, _ => none
    | fuel + 1, decls => match decls with
      | [] => some ⟨(),.empty⟩
      | head :: tail => do
        let first ← checkDeclarationBindings fuel head
        let remaining ← checkListBindings fuel tail
        return ⟨(),.next first.property remaining.property⟩
  def checkScopeBindings : (fuel : Nat) → (decls : List Declaration) →
      Option { _witness : Unit // ScopeBindings decls }
    | 0, _ => none
    | fuel + 1, decls => do
      if unique : (decls.filterMap declarationName).Nodup then
        let checked ← checkListBindings fuel decls
        return ⟨(),.scope unique checked.property⟩
      else none
end

structure NamedSource (input : ByteArray) where
  source : ShellSource input
  bindings : ScopeBindings source.shell.declarations

def namedSource (input : ByteArray) : Option (NamedSource input) := do
  let source ← shellSource input
  let checked ← checkScopeBindings 4096 source.shell.declarations
  return ⟨source,checked.property⟩

theorem ScopeBindings.unique {decls : List Declaration} (binding : ScopeBindings decls) :
    (decls.filterMap declarationName).Nodup := by cases binding; assumption

theorem ListBindings.member {decls : List Declaration} (binding : ListBindings decls)
    {item : Declaration} (present : item ∈ decls) : DeclarationBindings item := by
  induction decls with
  | nil => simp at present
  | cons head tail ih =>
    cases binding with
    | next first remaining =>
      rcases List.mem_cons.mp present with same | later
      · subst item; exact first
      · exact ih remaining later

theorem ScopeBindings.member {decls : List Declaration} (binding : ScopeBindings decls)
    {item : Declaration} (present : item ∈ decls) : DeclarationBindings item := by
  cases binding with
  | scope unique rows => exact rows.member present

theorem named_source_sound (input : ByteArray) (result : NamedSource input)
    (_accepted : namedSource input = some result) :
    Coverage input result.source.header.lexical.reversed input.size ∧
    Declarations input .outer false result.source.header.declarations.imports.rest result.source.shell.declarations [] ∧
    ScopeBindings result.source.shell.declarations :=
  ⟨result.source.header.lexical.grammar,result.source.complete ▸ result.source.shell.grammar,result.bindings⟩

end Aurora.SourceBinding
