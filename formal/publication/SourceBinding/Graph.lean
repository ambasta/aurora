import SourceBinding.Symbols
namespace Aurora.SourceBinding

/-- Raw bytes remain attached to their derived source object. Acquisition authenticity is external. -/
structure SourceFile where
  bytes : ByteArray
  checked : NamedSource bytes

def moduleName (file : SourceFile) : Name := file.checked.source.header.declarations.module.name
def importedNames (file : SourceFile) : List Name := file.checked.source.header.declarations.imports.names

def Edge (files : List SourceFile) (parent child : Name) : Prop :=
  ∃ file ∈ files, moduleName file = parent ∧ child ∈ importedNames file
instance (files : List SourceFile) (parent child : Name) : Decidable (Edge files parent child) := by
  unfold Edge; infer_instance

inductive Reachable (files : List SourceFile) (root : Name) : Name → Prop
  | root : Reachable files root root
  | imported : Reachable files root parent → Edge files parent child → Reachable files root child

/-- A finite reachability witness; the producer's visitation order is not trusted. -/
inductive VisitOrder (files : List SourceFile) (root : Name) : List Name → Prop
  | root : VisitOrder files root [root]
  | next : VisitOrder files root previous → name ∉ previous →
      (∃ parent ∈ previous, Edge files parent name) → VisitOrder files root (name :: previous)

theorem VisitOrder.reachable {files : List SourceFile} {root : Name} {visited : List Name}
    (order : VisitOrder files root visited) {name : Name} (member : name ∈ visited) :
    Reachable files root name := by
  induction order generalizing name with
  | root =>
    have same := List.mem_singleton.mp member
    subst name
    exact .root
  | next prior fresh edge ih =>
    rcases List.mem_cons.mp member with same | old
    · subst name
      obtain ⟨parent, present, step⟩ := edge
      exact .imported (ih present) step
    · exact ih old

structure Visited (files : List SourceFile) (root : Name) where
  names : List Name
  order : VisitOrder files root names
  complete : ∀ file ∈ files, moduleName file ∈ names

def Next (files : List SourceFile) (previous : List Name) (name : Name) : Prop :=
  name ∉ previous ∧ ∃ parent ∈ previous, Edge files parent name
instance (files : List SourceFile) (previous : List Name) (name : Name) : Decidable (Next files previous name) := by
  unfold Next; infer_instance

/-- Candidate search is separated from the checked Next relation. -/
def nextCandidate (files : List SourceFile) (previous : List Name) : Option Name :=
  (files.map moduleName).find? fun name => decide (Next files previous name)

def visit (files : List SourceFile) (root : Name) : (fuel : Nat) → (previous : List Name) →
    VisitOrder files root previous → Option (Visited files root)
  | fuel, previous, prior =>
    if complete : ∀ file ∈ files, moduleName file ∈ previous then some ⟨previous,prior,complete⟩
    else match fuel with
      | 0 => none
      | fuel + 1 => do
        let next ← nextCandidate files previous
        if edge : Next files previous next then
          visit files root fuel (next :: previous) (.next prior edge.1 edge.2)
        else none

inductive GraphSymbols : List SourceFile → List Symbol → Prop
  | empty : GraphSymbols [] []
  | next : SymbolRows [] file.checked.source.shell.declarations names →
      GraphSymbols tail remaining → GraphSymbols (file :: tail) (names ++ remaining)

structure GraphInventory (files : List SourceFile) where
  names : List Symbol
  grammar : GraphSymbols files names

def graphInventory : (files : List SourceFile) → Option (GraphInventory files)
  | [] => some ⟨[],.empty⟩
  | file :: tail => do
    let first ← inventory 4096 [] file.checked.source.shell.declarations
    let remaining ← graphInventory tail
    return ⟨first.names ++ remaining.names,.next first.grammar remaining.grammar⟩

/-- Supplied graph consistency only: no filesystem search precedence or capture claim. -/
structure GraphReady (files : List SourceFile) (root : Name) : Prop where
  uniqueModules : (files.map moduleName).Nodup
  hasRoot : root ∈ files.map moduleName
  importsUnique : ∀ file ∈ files, (importedNames file).Nodup
  importsClosed : ∀ file ∈ files, ∀ name ∈ importedNames file, name ∈ files.map moduleName
  allReachable : ∀ file ∈ files, Reachable files root (moduleName file)
  unambiguous : ∃ symbols, GraphSymbols files symbols ∧ symbols.Pairwise Compatible

def checkGraph (files : List SourceFile) (root : Name) : Option { _witness : Unit // GraphReady files root } := do
  if unique : (files.map moduleName).Nodup then
    if hasRoot : root ∈ files.map moduleName then
      if importsUnique : ∀ file ∈ files, (importedNames file).Nodup then
        if closed : ∀ file ∈ files, ∀ name ∈ importedNames file, name ∈ files.map moduleName then
          let visited ← visit files root (files.length + 1) [root] .root
          let symbols ← graphInventory files
          if unambiguous : symbols.names.Pairwise Compatible then
            return ⟨(),⟨unique,hasRoot,importsUnique,closed,(fun file present =>
              visited.order.reachable (visited.complete file present)),
              ⟨symbols.names,symbols.grammar,unambiguous⟩⟩⟩
          else none
        else none
      else none
    else none
  else none

theorem graph_sound (files : List SourceFile) (root : Name)
    (result : { _witness : Unit // GraphReady files root })
    (_accepted : checkGraph files root = some result) : GraphReady files root := result.property

end Aurora.SourceBinding
