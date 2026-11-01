import SourceBinding.Bindings
namespace Aurora.SourceBinding

structure Symbol where
  name : Name
  namespaceContainer : Bool
  deriving BEq, DecidableEq

/-- Namespace containers may merge, but cannot collide with terminal declarations. -/
def Compatible (left right : Symbol) : Prop :=
  left.name ≠ right.name ∨ (left.namespaceContainer = true ∧ right.namespaceContainer = true)
instance (left right : Symbol) : Decidable (Compatible left right) := by unfold Compatible; infer_instance

/- Conservative graph-wide symbol inventory: namespace containers merge, but
    classes, enums and free functions may not collide even across modules. -/
mutual
  inductive SymbolRow : Name → Declaration → List Symbol → Prop
    | namespaceDecl : SymbolRows (path ++ [name]) children names →
        SymbolRow path (.namespaceDecl name exported children) (⟨path ++ [name],true⟩ :: names)
    | classDecl : SymbolRow path (.classDecl name members) [⟨path ++ [name],false⟩]
    | enumDecl : SymbolRow path (.enumDecl name cases) [⟨path ++ [name],false⟩]
    | functionDecl : SymbolRow path (.functionDecl function) [⟨path ++ [function.name],false⟩]
    | constructorDecl : SymbolRow path (.constructorDecl constructor) []
    | fieldDecl : SymbolRow path (.fieldDecl field) []
    | access : SymbolRow path (.access visibility) []
  inductive SymbolRows : Name → List Declaration → List Symbol → Prop
    | empty : SymbolRows path [] []
    | next : SymbolRow path item names → SymbolRows path tail remaining →
        SymbolRows path (item :: tail) (names ++ remaining)
end

structure Inventory (path : Name) (decls : List Declaration) where
  names : List Symbol
  grammar : SymbolRows path decls names
structure RowInventory (path : Name) (decl : Declaration) where
  names : List Symbol
  grammar : SymbolRow path decl names

mutual
  def inventory : (fuel : Nat) → (path : Name) → (decls : List Declaration) → Option (Inventory path decls)
    | 0, _, _ => none
    | fuel + 1, path, decls => match decls with
      | [] => some ⟨[],.empty⟩
      | head :: tail => do
        let first ← rowInventory fuel path head
        let remaining ← inventory fuel path tail
        return ⟨first.names ++ remaining.names,.next first.grammar remaining.grammar⟩
  def rowInventory : (fuel : Nat) → (path : Name) → (decl : Declaration) → Option (RowInventory path decl)
    | 0, _, _ => none
    | fuel + 1, path, decl => match decl with
      | .namespaceDecl name _ children => do
        let found ← inventory fuel (path ++ [name]) children
        return ⟨⟨path ++ [name],true⟩ :: found.names,.namespaceDecl found.grammar⟩
      | .classDecl name _ => some ⟨[⟨path ++ [name],false⟩],.classDecl⟩
      | .enumDecl name _ => some ⟨[⟨path ++ [name],false⟩],.enumDecl⟩
      | .functionDecl function => some ⟨[⟨path ++ [function.name],false⟩],.functionDecl⟩
      | .constructorDecl _ => some ⟨[],.constructorDecl⟩
      | .fieldDecl _ => some ⟨[],.fieldDecl⟩
      | .access _ => some ⟨[],.access⟩
end

end Aurora.SourceBinding
