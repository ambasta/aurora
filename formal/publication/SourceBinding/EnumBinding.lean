import SourceBinding.FreeSelection
import SourceBinding.IRIdentity
import Publication.Instructions
import SourceBinding.RuntimeTypes
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Exact nominal linkage profile; not a native integer-to-enum conversion. -/
def enumSymbol (module path : Name) (name : ByteArray) : ByteArray :=
  "__au_e_m".toUTF8 ++ namePrefix module ++ "_n".toUTF8 ++ namePrefix path ++
    "_d".toUTF8 ++ lengthName name

structure FoundEnum (members : List Declaration) (name : ByteArray) where
  cases : List ByteArray
  present : Declaration.enumDecl name cases ∈ members

def findEnum (members : List Declaration) (name : ByteArray) : Option (FoundEnum members name) :=
  match found : members.find? (fun item => match item with
    | .enumDecl actual _ => actual == name
    | _ => false) with
  | none => none
  | some candidate => match candidate with
    | .enumDecl actual cases =>
      if named : actual = name then
        some ⟨cases, by subst actual; exact List.mem_of_find?_eq_some found⟩
      else none
    | _ => none

/-- Source enum identity retains the SAME supplied graph and full byte-backed shell. -/
structure SelectedEnum (files : List SourceFile) (root module path : Name) (name : ByteArray) where
  graph : GraphReady files root
  file : FoundFile files module
  scope : FoundNamespace file.file.checked.source.shell.declarations path
  declaration : FoundEnum scope.members name

def selectEnum (files : List SourceFile) (root module path : Name) (name : ByteArray) :
    Option (SelectedEnum files root module path name) := do
  let graph ← checkGraph files root
  let file ← findFile files module
  let scope ← findNamespace 4096 file.file.checked.source.shell.declarations path
  let declaration ← findEnum scope.members name
  return ⟨graph.property,file,scope,declaration⟩

def SelectedEnum.nominal (_selected : SelectedEnum files root module path name) : NominalIdentity :=
  ⟨enumSymbol module path name,_selected.declaration.cases.length⟩

def nominalRows (t : Tables) (identity : NominalIdentity) : Array Record :=
  t.enums.filter (fun row => nameBytes t row 1 == identity.name)

/-- Case cardinality and exact nominal name, never merely equal storage width. -/
def NominalTypeIdentity (t : Tables) (typ : Int) (identity : NominalIdentity) : Prop :=
  Index typ t.types.size ∧ (atRow t.types typ).integer 1 = 9 ∧
  PlainTail (atRow t.types typ) ∧ nameBytes t (atRow t.types typ) 2 = identity.name ∧
  0 < identity.cases ∧ (nominalRows t identity).size = 1 ∧
  (atRow (nominalRows t identity) 0).integer 3 = Int.ofNat identity.cases
instance (t : Tables) (typ : Int) (identity : NominalIdentity) :
    Decidable (NominalTypeIdentity t typ identity) := by unfold NominalTypeIdentity; infer_instance

def RuntimeTypeIdentity (t : Tables) (typ : Int) : RuntimeType → Prop
  | .scalar kind => ScalarType t typ ∧ scalarKind t typ = some kind
  | .nominal identity => NominalTypeIdentity t typ identity
instance (t : Tables) (typ : Int) (kind : RuntimeType) : Decidable (RuntimeTypeIdentity t typ kind) := by
  cases kind <;> unfold RuntimeTypeIdentity <;> infer_instance

/-- Canonical private-frame storage has its own exact runtime type. Source
    constness and initialization are deliberately NOT inferred from slot flags. -/
def RuntimeMatchingSlot (t : Tables) (id offset typ : Int) (kind : RuntimeType) : Prop :=
  RuntimeTypeIdentity t typ kind ∧
  ∃ slot ∈ (frameSlots t (atRow t.callables id)).toList,
    slot.integer 1 = 10 ∧ slot.integer 2 = offset ∧
    RuntimeTypeIdentity t (slot.integer 3) kind
instance (t : Tables) (id offset typ : Int) (kind : RuntimeType) :
    Decidable (RuntimeMatchingSlot t id offset typ kind) := by unfold RuntimeMatchingSlot; infer_instance

/-- The source spelling resolves only in this selected lexical enum scope. The
    final function binder must supply that SAME scope, not an arbitrary enum. -/
def EnumSourceName (path : Name) (enumName : ByteArray) (source : SourceType) : Prop :=
  source = .named [enumName] ∨ source = .named (path ++ [enumName])
instance (path : Name) (enumName : ByteArray) (source : SourceType) :
    Decidable (EnumSourceName path enumName source) := by unfold EnumSourceName; infer_instance

inductive EnumCaseAt (selected : SelectedEnum files root module path name) : Name → Nat → Prop
  | unqualified : selected.declaration.cases[ordinal]? = some caseName →
      EnumCaseAt selected [name,caseName] ordinal
  | qualified : selected.declaration.cases[ordinal]? = some caseName →
      EnumCaseAt selected (path ++ [name,caseName]) ordinal

structure FoundEnumCase (selected : SelectedEnum files root module path name) (source : Name) where
  ordinal : Nat
  grammar : EnumCaseAt selected source ordinal

def findEnumCase (selected : SelectedEnum files root module path name) (source : Name) :
    Option (FoundEnumCase selected source) := do
  let caseName ← source.getLast?
  let ordinal ← selected.declaration.cases.findIdx? (· == caseName)
  if presentCase : selected.declaration.cases[ordinal]? = some caseName then
    if short : source = [name,caseName] then
      return ⟨ordinal,short ▸ .unqualified presentCase⟩
    else if full : source = path ++ [name,caseName] then
      return ⟨ordinal,full ▸ .qualified presentCase⟩
    else none
  else none

/-- Exact published enum constant roles and ordinal; scalar constants are excluded.
    Complete artifact/CFG admission belongs to the enclosing checked program. -/
def EnumConstantIdentity (t : Tables) (row : Record) (identity : NominalIdentity) (ordinal : Nat) : Prop :=
  row.integer 6 = 6 ∧ row.integer 5 = 1 ∧ row.integer 7 = 0 ∧
  row.integer 8 = 0 ∧ row.integer 9 = 0 ∧ row.integer 10 = 0 ∧
  operandRoles t row = [12,13] ∧ AllRows (operandsOf t row) (OperandPayload t) ∧
  NominalTypeIdentity t (operandValue t row 0) identity ∧
  operandValue t row 1 = Int.ofNat ordinal ∧ ordinal < identity.cases
instance (t : Tables) (row : Record) (identity : NominalIdentity) (ordinal : Nat) :
    Decidable (EnumConstantIdentity t row identity ordinal) := by unfold EnumConstantIdentity; infer_instance

theorem selected_enum_sound (selected : SelectedEnum files root module path name) :
    GraphReady files root ∧ selected.file.file ∈ files ∧ moduleName selected.file.file = module ∧
    Coverage selected.file.file.bytes selected.file.file.checked.source.header.lexical.reversed
      selected.file.file.bytes.size ∧
    Declaration.enumDecl name selected.declaration.cases ∈ selected.scope.members ∧
    selected.declaration.cases.Nodup := by
  refine ⟨selected.graph,selected.file.present,selected.file.named,
    selected.file.file.checked.source.header.lexical.grammar,selected.declaration.present,?_⟩
  have bound := selected.scope.grammar.bindings selected.file.file.checked.bindings
  have declaration := bound.member selected.declaration.present
  cases declaration with
  | enumDecl _ unique _ => exact unique

theorem EnumCaseAt.bounded (found : EnumCaseAt selected source ordinal) :
    ordinal < selected.nominal.cases := by
  cases found with
  | unqualified presentCase => exact List.getElem?_eq_some_iff.mp presentCase |>.1
  | qualified presentCase => exact List.getElem?_eq_some_iff.mp presentCase |>.1

end Aurora.SourceBinding
