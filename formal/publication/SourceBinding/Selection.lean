import SourceBinding.Graph
namespace Aurora.SourceBinding

/-- Selection traverses declared namespaces/classes, never opaque bodies. -/
inductive ClassAt : List Declaration → Name → List Declaration → Prop
  | here : Declaration.classDecl name members ∈ decls → ClassAt decls [name] members
  | nested : Declaration.namespaceDecl name exported children ∈ decls →
      ClassAt children path members → ClassAt decls (name :: path) members

theorem ClassAt.prepend {decls members : List Declaration} {path : Name} (found : ClassAt decls path members)
    (head : Declaration) : ClassAt (head :: decls) path members := by
  cases found with
  | here present => exact .here (List.mem_cons_of_mem head present)
  | nested present nested => exact .nested (List.mem_cons_of_mem head present) nested

theorem ClassAt.bindings {decls members : List Declaration} {path : Name}
    (found : ClassAt decls path members) (binding : ScopeBindings decls) : ScopeBindings members := by
  induction found with
  | here present =>
    have valid := binding.member present
    cases valid with
    | classDecl nameOK membersOK classOK => exact membersOK
  | nested present nested ih =>
    have valid := binding.member present
    cases valid with
    | namespaceDecl nameOK childOK => exact ih childOK

structure FoundClass (decls : List Declaration) (path : Name) where
  members : List Declaration
  grammar : ClassAt decls path members

def findClass : (fuel : Nat) → (decls : List Declaration) → (path : Name) → Option (FoundClass decls path)
  | 0, _, _ => none
  | fuel + 1, decls, path => match decls, path with
    | [], _ | _, [] => none
    | head :: tail, name :: rest =>
      let candidate : Option (FoundClass (head :: tail) (name :: rest)) := match head with
        | .classDecl actual members =>
          if same : actual = name then
            if last : rest = [] then
              some ⟨members,by subst actual; subst rest; exact .here List.mem_cons_self⟩
            else none
          else none
        | .namespaceDecl actual exported children => do
          if same : actual = name then
            let child ← findClass fuel children rest
            return ⟨child.members,.nested (exported := exported) (by subst actual; exact List.mem_cons_self) child.grammar⟩
          else none
        | _ => none
      match candidate with
      | some found => some found
      | none => do
        let found ← findClass fuel tail (name :: rest)
        return ⟨found.members,found.grammar.prepend head⟩

structure FoundFunction (members : List Declaration) (name : ByteArray) where
  function : Function
  present : Declaration.functionDecl function ∈ members
  named : function.name = name

def findFunction : (members : List Declaration) → (name : ByteArray) → Option (FoundFunction members name)
  | [], _ => none
  | head :: tail, name =>
    let candidate : Option (FoundFunction (head :: tail) name) := match head with
      | .functionDecl function =>
        if same : function.name = name then
          some ⟨function,List.mem_cons_self,same⟩
        else none
      | _ => none
    match candidate with
    | some found => some found
    | none => do
      let found ← findFunction tail name
      return ⟨found.function,List.mem_cons_of_mem head found.present,found.named⟩

structure FoundFile (files : List SourceFile) (name : Name) where
  file : SourceFile
  present : file ∈ files
  named : moduleName file = name

def findFile : (files : List SourceFile) → (name : Name) → Option (FoundFile files name)
  | [], _ => none
  | file :: tail, name =>
    if same : moduleName file = name then some ⟨file,List.mem_cons_self,same⟩
    else do
      let found ← findFile tail name
      return ⟨found.file,List.mem_cons_of_mem file found.present,found.named⟩

structure SelectedMember (files : List SourceFile) (module : Name) (path : Name) (member : ByteArray) where
  file : FoundFile files module
  classDecl : FoundClass file.file.checked.source.shell.declarations path
  method : FoundFunction classDecl.members member

def selectMember (files : List SourceFile) (module : Name) (path : Name) (member : ByteArray) :
    Option (SelectedMember files module path member) := do
  let file ← findFile files module
  let cls ← findClass 4096 file.file.checked.source.shell.declarations path
  let method ← findFunction cls.members member
  return ⟨file,cls,method⟩

/-- Raw-source identity, complete source shell, selected scope/member and its binding
    invariants are composed here. The function body is still an opaque token sequence. -/
theorem selected_member_sound (files : List SourceFile) (module : Name) (path : Name) (member : ByteArray)
    (result : SelectedMember files module path member)
    (_accepted : selectMember files module path member = some result) :
    result.file.file ∈ files ∧ moduleName result.file.file = module ∧
    Coverage result.file.file.bytes result.file.file.checked.source.header.lexical.reversed result.file.file.bytes.size ∧
    ClassAt result.file.file.checked.source.shell.declarations path result.classDecl.members ∧
    ScopeBindings result.classDecl.members ∧
    Declaration.functionDecl result.method.function ∈ result.classDecl.members ∧ result.method.function.name = member :=
  ⟨result.file.present,result.file.named,result.file.file.checked.source.header.lexical.grammar,
    result.classDecl.grammar,result.classDecl.grammar.bindings result.file.file.checked.bindings,
    result.method.present,result.method.named⟩

/-- Public graph-backed selection: both certificates mention exactly the SAME input files. -/
structure CheckedSelection (files : List SourceFile) (root module : Name) (path : Name) (member : ByteArray) where
  graph : GraphReady files root
  selected : SelectedMember files module path member

def checkedSelection (files : List SourceFile) (root module : Name) (path : Name) (member : ByteArray) :
    Option (CheckedSelection files root module path member) := do
  let graph ← checkGraph files root
  let selected ← selectMember files module path member
  return ⟨graph.property,selected⟩

theorem checked_selection_sound (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (result : CheckedSelection files root module path member)
    (_accepted : checkedSelection files root module path member = some result) :
    GraphReady files root ∧ result.selected.file.file ∈ files ∧
    moduleName result.selected.file.file = module ∧
    ClassAt result.selected.file.file.checked.source.shell.declarations path result.selected.classDecl.members ∧
    ScopeBindings result.selected.classDecl.members ∧
    Declaration.functionDecl result.selected.method.function ∈ result.selected.classDecl.members ∧
    result.selected.method.function.name = member :=
  ⟨result.graph,result.selected.file.present,result.selected.file.named,result.selected.classDecl.grammar,
    result.selected.classDecl.grammar.bindings result.selected.file.file.checked.bindings,
    result.selected.method.present,result.selected.method.named⟩

/-- Canonical ordinal is counted from ALL field declarations in source order. -/
structure FieldAt (members : List Declaration) (name : ByteArray) where
  ordinal : Nat
  field : Formal
  declaration : (fields members)[ordinal]? = some field
  named : field.name = name

def fieldAt (members : List Declaration) (name : ByteArray) : Option (FieldAt members name) := do
  let candidate := (fields members).zipIdx.find? fun entry => entry.1.name == name
  let (field, ordinal) ← candidate
  if declared : (fields members)[ordinal]? = some field then
    if named : field.name = name then return ⟨ordinal,field,declared,named⟩ else none
  else none

theorem field_at_sound (members : List Declaration) (name : ByteArray) (result : FieldAt members name)
    (_accepted : fieldAt members name = some result) :
    (fields members)[result.ordinal]? = some result.field ∧ result.field.name = name :=
  ⟨result.declaration,result.named⟩

end Aurora.SourceBinding
