import SourceBinding.LocalBinding
import SourceBinding.FreeIdentity
namespace Aurora.SourceBinding
open Aurora.Publication

inductive RuntimeSignature (t : Tables) (members : List Declaration) (module path : Name) :
    Int → List SourceType → List RuntimeType → Prop
  | nil : RuntimeSignature t members module path index [] []
  | cons : RuntimeSourceType members module path source kind → RuntimeTypeIdentity t index kind →
      RuntimeSignature t members module path (index + 1) sources kinds →
      RuntimeSignature t members module path index (source :: sources) (kind :: kinds)

structure CheckedRuntimeSignature (t : Tables) (members : List Declaration) (module path : Name)
    (index : Int) (sources : List SourceType) where
  kinds : List RuntimeType
  grammar : RuntimeSignature t members module path index sources kinds

def checkRuntimeSignature (t : Tables) (members : List Declaration) (module path : Name) :
    (index : Int) → (sources : List SourceType) →
    Option (CheckedRuntimeSignature t members module path index sources)
  | _, [] => some ⟨[],.nil⟩
  | index, source :: sources => do
    let resolved ← resolveRuntimeType members module path source
    if identity : RuntimeTypeIdentity t index resolved.kind then
      let remaining ← checkRuntimeSignature t members module path (index + 1) sources
      return ⟨resolved.kind :: remaining.kinds,.cons resolved.typing identity remaining.grammar⟩
    else none

def hasNominal (kinds : List RuntimeType) : Bool :=
  kinds.any fun kind => match kind with | .nominal _ => true | .scalar _ => false

/-- The value-function linkage tag is selected by the actual nominal signature;
    it is not an enum-to-word coercion or a producer-fidelity theorem. -/
def runtimeFreeSymbol (root module path : Name) (name : ByteArray) (kinds : List RuntimeType) : ByteArray :=
  if module = root ∧ path = [] ∧ hasNominal kinds = false then name else
    (if hasNominal kinds then "__au_v_m" else "__au_f_m").toUTF8 ++
      namePrefix module ++ "_n".toUTF8 ++ namePrefix path ++ "_d".toUTF8 ++ lengthName name

def RuntimeFrameSlot (t : Tables) (callable : Record) (entry : RuntimeType × Nat) : Prop :=
  let slot := atRow (frameSlots t callable) (Int.ofNat entry.2)
  slot.integer 1 = 10 ∧ slot.integer 2 = Int.ofNat (8 * (entry.2 + 1)) ∧
  RuntimeTypeIdentity t (slot.integer 3) entry.1 ∧
  slot.integer 4 = 0 ∧ slot.integer 5 = 0 ∧ slot.integer 2 ≤ callable.integer 13
instance (t : Tables) (callable : Record) (entry : RuntimeType × Nat) :
    Decidable (RuntimeFrameSlot t callable entry) := by unfold RuntimeFrameSlot; infer_instance

/-- Shared ordinary free-function header; frame-slot completeness remains a
    separate source-bound obligation, not a zero-local restriction on calls. -/
def RuntimeFreeHeader (t : Tables) (id : Int) : Prop :=
  let c := atRow t.callables id
  Index id t.callables.size ∧ nameBytes t c 6 = ByteArray.empty ∧
  c.integer 8 = 0 ∧ c.integer 9 = 0 ∧ c.integer 10 = 0 ∧ c.integer 11 = 0 ∧ c.integer 12 = 0 ∧
  (Aurora.Publication.group t.bodies id).size = 1 ∧
  (atRow (Aurora.Publication.group t.bodies id) 0).integer 2 = 0 ∧
  0 < (functionCode t id).size ∧ (functionCode t id).size ≤ 4096
instance (t : Tables) (id : Int) : Decidable (RuntimeFreeHeader t id) := by
  unfold RuntimeFreeHeader; infer_instance

def RuntimeFreeShape (t : Tables) (id : Int) (parameters : List RuntimeType) (locals : List SourceLocal) : Prop :=
  let c := atRow t.callables id
  let kinds := parameters ++ locals.map (·.kind)
  RuntimeFreeHeader t id ∧
  c.integer 15 = Int.ofNat kinds.length ∧
  (∀ entry ∈ kinds.zipIdx, RuntimeFrameSlot t c entry) ∧
  (∀ entry ∈ locals.zipIdx, entry.1.slot = 8 * (parameters.length + entry.2 + 1))

instance (t : Tables) (id : Int) (parameters : List RuntimeType) (locals : List SourceLocal) :
    Decidable (RuntimeFreeShape t id parameters locals) := by unfold RuntimeFreeShape; infer_instance

@[irreducible] def RuntimeFunctionIdentity (t : Tables) (id : Int) (root module path : Name) (name : ByteArray)
    (function : Function) (kinds : List RuntimeType) (locals : List SourceLocal) : Prop :=
  function.mode = .ordinary ∧
  nameBytes t (atRow t.callables id) 1 = runtimeFreeSymbol root module path name kinds ∧
  (namedCallables t (runtimeFreeSymbol root module path name kinds)).size = 1 ∧
  ((atRow t.callables id).integer 3 = 0 ↔ module = root) ∧
  (atRow t.callables id).integer 5 = Int.ofNat (function.formals.length + 1) ∧
  RuntimeFreeShape t id kinds.tail locals
instance (t : Tables) (id : Int) (root module path : Name) (name : ByteArray)
    (function : Function) (kinds : List RuntimeType) (locals : List SourceLocal) :
    Decidable (RuntimeFunctionIdentity t id root module path name function kinds locals) := by
  unfold RuntimeFunctionIdentity; infer_instance

/-- SAME byte-backed declaration, lexical namespace, signature and complete
    private-frame layout. This is identity/scoping, not body execution. -/
structure RuntimeFreeDetails (t : Tables) (selected : CheckedFreeSelection files root module path name) (id : Int) where
  lexical : ScopedMethod selected.file.file.bytes selected.function.function selected.scope.members module path
  types : CheckedRuntimeSignature t selected.scope.members module path ((atRow t.callables id).integer 4)
    (selected.function.function.result :: selected.function.function.formals.map (·.type))
  identity : RuntimeFunctionIdentity t id root module path name selected.function.function types.kinds lexical.lexical.declaredItems

structure IdentifiedRuntimeFree (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) where
  selected : CheckedFreeSelection files root module path name
  id : Int
  details : RuntimeFreeDetails t selected id

def checkRuntimeFreeDetails (t : Tables) (selected : CheckedFreeSelection files root module path name) (id : Int) :
    Option (RuntimeFreeDetails t selected id) := do
  let lexical ← scopeMethod selected.file.file.bytes selected.function.function selected.scope.members module path
  let types ← checkRuntimeSignature t selected.scope.members module path ((atRow t.callables id).integer 4)
    (selected.function.function.result :: selected.function.function.formals.map (·.type))
  if identity : RuntimeFunctionIdentity t id root module path name selected.function.function types.kinds lexical.lexical.declaredItems then
    return RuntimeFreeDetails.mk (files := files) (root := root) (module := module) (path := path) (name := name) (t := t) (selected := selected) (id := id) lexical types identity
  else none

def identifyRuntimeFree (t : Tables) (files : List SourceFile) (root module path : Name) (name : ByteArray) :
    Option (IdentifiedRuntimeFree t files root module path name) := do
  let selected ← checkFreeSelection files root module path name
  let function := selected.function.function
  let sources := function.result :: function.formals.map (·.type)
  let kinds ← sources.mapM fun source => do
    let resolved ← resolveRuntimeType selected.scope.members module path source
    pure resolved.kind
  let candidate ← (namedCallables t (runtimeFreeSymbol root module path name kinds))[0]?
  let id := candidate.integer 0
  let details ← checkRuntimeFreeDetails t selected id
  return ⟨selected,id,details⟩

/-- No independently supplied source member or source AST is used by the public identity endpoint. -/
theorem identified_runtime_free_source (checked : IdentifiedRuntimeFree t files root module path name) :
    GraphReady files root ∧
    StatementsSyntax checked.selected.file.file.bytes false checked.selected.function.function.body.tokens
      checked.details.lexical.parsed.statements [] ∧
    RuntimeSignature t checked.selected.scope.members module path ((atRow t.callables checked.id).integer 4)
      (checked.selected.function.function.result :: checked.selected.function.function.formals.map (·.type))
      checked.details.types.kinds ∧
    RuntimeFreeShape t checked.id checked.details.types.kinds.tail checked.details.lexical.lexical.declaredItems :=
by
  have metadata := checked.details.identity
  unfold RuntimeFunctionIdentity at metadata
  exact ⟨checked.selected.graph,checked.details.lexical.parsed.grammar,
    checked.details.types.grammar,metadata.2.2.2.2.2⟩

/-- Full byte framing/structural publication admission is composed here. The
    reusable per-function identity above intentionally takes SAME decoded tables. -/
structure RuntimeFreeBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  artifact : CheckedArtifact input
  checked : IdentifiedRuntimeFree (tables artifact.document.reversed.reverse) files root module path name

def bindRuntimeFree (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (input : ByteArray) : Option (RuntimeFreeBinding input files root module path name) := do
  let artifact ← decodeArtifact {} input
  let checked ← identifyRuntimeFree (tables artifact.document.reversed.reverse) files root module path name
  return ⟨artifact,checked⟩

theorem runtime_free_publication (binding : RuntimeFreeBinding input files root module path name) :
    WireDocument input binding.artifact.document.reversed ∧
    CheckedStructure (tables binding.artifact.document.reversed.reverse) ∧ GraphReady files root :=
  ⟨binding.artifact.document.grammar,binding.artifact.structureProof,binding.checked.selected.graph⟩

end Aurora.SourceBinding
