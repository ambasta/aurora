import SourceBinding.Selection
import Publication.Closure
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Restricted non-template, non-overloaded linkage spelling. Independently stated
    against resolution_linkage.au; no claim that the compiler implements this correctly. -/
def lengthName (name : ByteArray) : ByteArray := (toString name.size).toUTF8 ++ name

def namePrefix (parts : Name) : ByteArray :=
  (toString parts.length).toUTF8 ++ "_".toUTF8 ++
    (parts.map lengthName).foldl (· ++ ·) ByteArray.empty

def classSymbol (module path : Name) : ByteArray :=
  "__au_c_m".toUTF8 ++ namePrefix module ++ "_n".toUTF8 ++ namePrefix path.dropLast ++
    "_d".toUTF8 ++ lengthName (path.getLast?.getD ByteArray.empty)

def methodSymbol (module path : Name) (member : ByteArray) : ByteArray :=
  "__au_m_m".toUTF8 ++ namePrefix module ++ "_n".toUTF8 ++ namePrefix path ++
    "_d".toUTF8 ++ lengthName member

def sourceName (name : Name) : ByteArray :=
  ((name.map (fun x => x)).intersperse "::".toUTF8).foldl (· ++ ·) ByteArray.empty

/-- Namespace/resource spelling is read from the published catalogue, not guessed
    from the nominal native name or a hard-coded MemoryManager field table. -/
def ResourceTypeIdentity (t : Tables) (name : Name) (id : Int) : Prop :=
  name.head? = some "builtin".toUTF8 ∧ name.length = 2 ∧ Index id t.types.size ∧
  (atRow t.types id).integer 1 = 26 ∧ PlainTail (atRow t.types id) ∧
  (t.resources.filter (fun resource => resource.blob 3 == sourceName name)).size = 1 ∧
  ∃ resource ∈ t.resources.toList,
    resource.blob 3 = sourceName name ∧ Index (resource.integer 1) t.catalogs.size ∧
    nameBytes t (atRow t.types id) 2 = (atRow t.catalogs (resource.integer 1)).blob 2 ∧
    (atRow t.catalogs (resource.integer 1)).integer 1 = -1
instance (t : Tables) (name : Name) (id : Int) : Decidable (ResourceTypeIdentity t name id) := by
  unfold ResourceTypeIdentity; infer_instance

def TypeIdentity (t : Tables) (source : SourceType) (id : Int) : Prop :=
  match source with
  | .named name =>
    (name = ["u64".toUTF8] ∧ ScalarType t id ∧ scalarKind t id = some .word) ∨
    (name = ["bool".toUTF8] ∧ ScalarType t id ∧ scalarKind t id = some .boolean) ∨
    ResourceTypeIdentity t name id
  | _ => False
instance (t : Tables) (source : SourceType) (id : Int) : Decidable (TypeIdentity t source id) := by
  cases source <;> unfold TypeIdentity <;> infer_instance

/-- Source labels determine public visibility in declaration order; default class access is private. -/
inductive VisibilityAt : Bool → List Declaration → ByteArray → Bool → Prop
  | here : function.name = name → VisibilityAt initial (.functionDecl function :: tail) name initial
  | access : VisibilityAt (visibility == "public") tail name found →
      VisibilityAt initial (.access visibility :: tail) name found
  | skip : (∀ visibility, item ≠ .access visibility) →
      (∀ function, item = .functionDecl function → function.name ≠ name) →
      VisibilityAt initial tail name found → VisibilityAt initial (item :: tail) name found

structure FoundVisibility (members : List Declaration) (name : ByteArray) where
  visible : Bool
  grammar : VisibilityAt false members name visible

/-- Variant with explicit initial access for recursive proof construction. -/
def visibilityAt (name : ByteArray) : (initial : Bool) → (members : List Declaration) →
    Option { visible : Bool // VisibilityAt initial members name visible }
  | initial, [] => none
  | initial, item :: tail => match item with
    | .access visibility => do
      let found ← visibilityAt name (visibility == "public") tail
      return ⟨found.val,.access found.property⟩
    | .functionDecl function =>
      if same : function.name = name then some ⟨initial,.here same⟩
      else do
        let found ← visibilityAt name initial tail
        return ⟨found.val,.skip (by intro visibility h; cases h)
          (by intro other eq; cases eq; exact same) found.property⟩
    | .namespaceDecl n e c => do
      let found ← visibilityAt name initial tail
      return ⟨found.val,.skip (by intro v h; cases h) (by intro f h; cases h) found.property⟩
    | .classDecl n c => do
      let found ← visibilityAt name initial tail
      return ⟨found.val,.skip (by intro v h; cases h) (by intro f h; cases h) found.property⟩
    | .enumDecl n c => do
      let found ← visibilityAt name initial tail
      return ⟨found.val,.skip (by intro v h; cases h) (by intro f h; cases h) found.property⟩
    | .constructorDecl c => do
      let found ← visibilityAt name initial tail
      return ⟨found.val,.skip (by intro v h; cases h) (by intro f h; cases h) found.property⟩
    | .fieldDecl f => do
      let found ← visibilityAt name initial tail
      return ⟨found.val,.skip (by intro v h; cases h) (by intro f h; cases h) found.property⟩

/-- All declaration descriptors participate, including unused/opaque resource fields.
    Names live on the source side; publication field identity is canonical ordinal. -/
def OrderedFieldsIdentity (t : Tables) (id : Int) (declared : List Formal) : Prop :=
  declared.length = (functionFields t id).size ∧
  ∀ entry ∈ declared.zipIdx,
    (atRow (functionFields t id) (Int.ofNat entry.2)).integer 1 = Int.ofNat entry.2 ∧
    TypeIdentity t entry.1.type ((atRow (functionFields t id) (Int.ofNat entry.2)).integer 2)
instance (t : Tables) (id : Int) (declared : List Formal) : Decidable (OrderedFieldsIdentity t id declared) := by
  unfold OrderedFieldsIdentity; infer_instance

/-- This is the checked source/publication profile convention, not a compiler layout theorem. -/
def SourceIRIdentity (t : Tables) (id : Int) (module path : Name) (member : ByteArray)
    (members : List Declaration) (function : Function) (visible : Bool) : Prop :=
  let callable := atRow t.callables id
  path ≠ [] ∧ module ≠ [] ∧ Index id t.callables.size ∧
  nameBytes t callable 1 = methodSymbol module path member ∧
  (namedCallables t (methodSymbol module path member)).size = 1 ∧
  nameBytes t callable 6 = classSymbol module path ∧
  (namedClasses t (classSymbol module path)).size = 1 ∧
  function.name = member ∧ function.mode = .ordinary ∧
  callable.integer 8 = (if visible then 5 else 1) ∧
  callable.integer 5 = Int.ofNat (function.formals.length + 1) ∧
  TypeIdentity t function.result (callable.integer 4) ∧
  (∀ entry ∈ function.formals.zipIdx, TypeIdentity t entry.1.type (callable.integer 4 + Int.ofNat entry.2 + 1)) ∧
  OrderedFieldsIdentity t id (fields members)
instance (t : Tables) (id : Int) (module path : Name) (member : ByteArray)
    (members : List Declaration) (function : Function) (visible : Bool) :
    Decidable (SourceIRIdentity t id module path member members function visible) := by
  unfold SourceIRIdentity; infer_instance

theorem OrderedFieldsIdentity.lookup {t : Tables} {id : Int} {members : List Declaration}
    (identity : OrderedFieldsIdentity t id (fields members)) {name : ByteArray} (field : FieldAt members name) :
    (atRow (functionFields t id) (Int.ofNat field.ordinal)).integer 1 = Int.ofNat field.ordinal ∧
    TypeIdentity t field.field.type ((atRow (functionFields t id) (Int.ofNat field.ordinal)).integer 2) :=
  identity.2 (field.field,field.ordinal) (List.mk_mem_zipIdx_iff_getElem?.mpr field.declaration)

theorem SourceIRIdentity.fields {t : Tables} {id : Int} {module path : Name} {member : ByteArray}
    {members : List Declaration} {function : Function} {visible : Bool}
    (identity : SourceIRIdentity t id module path member members function visible) :
    OrderedFieldsIdentity t id (fields members) := by
  rcases identity with ⟨_,_,_,_,_,_,_,_,_,_,_,_,_,ordered⟩
  exact ordered

structure BoundIR (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (source : CheckedSelection files root module path member) (bytes : ByteArray) where
  publication : CheckedSlice bytes [methodSymbol module path member]
  id : Int
  selected : id ∈ publication.slice.selected
  visible : Bool
  visibility : VisibilityAt false source.selected.classDecl.members member visible
  identity : SourceIRIdentity (tables publication.artifact.document.reversed.reverse) id module path member
    source.selected.classDecl.members source.selected.method.function visible

def bindIR (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (source : CheckedSelection files root module path member) (bytes : ByteArray) :
    Option (BoundIR files root module path member source bytes) := do
  let publication ← decodeSlice {} bytes [methodSymbol module path member]
  let t := tables publication.artifact.document.reversed.reverse
  let id := ((namedCallables t (methodSymbol module path member))[0]?.getD (⟨"",[],false⟩ : Record)).integer 0
  let visible ← visibilityAt member false source.selected.classDecl.members
  if selected : id ∈ publication.slice.selected then
    if identity : SourceIRIdentity t id module path member source.selected.classDecl.members
        source.selected.method.function visible.val then
      return ⟨publication,id,selected,visible.val,visible.property,identity⟩
    else none
  else none

theorem bound_ir_identity (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (source : CheckedSelection files root module path member) (bytes : ByteArray)
    (result : BoundIR files root module path member source bytes)
    (_accepted : bindIR files root module path member source bytes = some result) :
    SourceIRIdentity (tables result.publication.artifact.document.reversed.reverse) result.id module path member
      source.selected.classDecl.members source.selected.method.function result.visible := result.identity

end Aurora.SourceBinding
