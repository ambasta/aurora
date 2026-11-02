import SourceBinding.RuntimeExpressionProof
import SourceBinding.RuntimeExpressionNames
import SourceBinding.NominalFreeIdentity
import SourceBinding.EntryBinding
namespace Aurora.SourceBinding

def runtimeParameterSlot (index : Nat) : Nat := 8*(index+1)
def runtimeBind (kind : RuntimeType) (index : Nat) : EffectOp :=
  match kind with
  | .scalar scalar => .pure (.bind scalar index (runtimeParameterSlot index))
  | .nominal identity => .enumBind identity index (runtimeParameterSlot index)

def RuntimeEntryCode (program : EffectProgram) (kinds : List RuntimeType) : Prop :=
  ∀ entry ∈ kinds.zipIdx, program entry.2 = some (runtimeBind entry.1 entry.2)
instance (program : EffectProgram) (kinds : List RuntimeType) : Decidable (RuntimeEntryCode program kinds) := by
  unfold RuntimeEntryCode; infer_instance

def RuntimeEntryArguments (kinds : List RuntimeType) (arguments : Nat → Option Value) : Prop :=
  ∀ index kind, kinds[index]? = some kind → ∃ value,
    arguments index = some value ∧ readRuntime kind (some value) = .value value

theorem RuntimeEntryCode.at_index (code : RuntimeEntryCode program kinds)
    (present : kinds[index]? = some kind) : program index = some (runtimeBind kind index) := by
  exact code (kind,index) (List.mem_zipIdx_iff_getElem?.mpr present)

theorem runtime_entry_runs (code : RuntimeEntryCode program kinds) (base : Machine)
    (arguments : RuntimeEntryArguments kinds base.arguments) :
    EffectRuns program (preparedEntry base runtimeParameterSlot 0) []
      (.next (preparedEntry base runtimeParameterSlot kinds.length)) := by
  have go : ∀ n, n ≤ kinds.length → EffectRuns program (preparedEntry base runtimeParameterSlot 0) []
      (.next (preparedEntry base runtimeParameterSlot n)) := by
    intro n bound
    induction n with
    | zero => exact .reflexive
    | succ n ih =>
      have less : n < kinds.length := by omega
      have present := List.getElem?_eq_getElem less
      obtain ⟨value,valueEq,typed⟩ := arguments n _ present
      have operation := code.at_index present
      apply (ih (by omega)).trans
      apply EffectRuns.next (events := []) (later := []) (middle := preparedEntry base runtimeParameterSlot (n+1)) _ .reflexive
      cases kind : kinds[n] with
      | scalar scalar =>
        rw [kind] at operation typed
        simp only [runtimeBind] at operation
        simp only [readRuntime] at typed
        simp only [effectStep,prepared_pc,operation,pureView,step,prepared_arguments,valueEq]
        rw [typed]
        simp only [retainState,preparedEntry,prepared_arguments,valueEq]
      | nominal identity =>
        rw [kind] at operation typed
        simp only [runtimeBind] at operation
        simp only [effectStep,prepared_pc,operation,prepared_arguments,valueEq,typed,preparedEntry]
  exact go kinds.length (Nat.le_refl _)

/-- Values come from actual executed entry bindings, not a fabricated total map.
    Metadata is the immutable scope-zero formal declaration environment. -/
def formalRuntimeLocals (kinds : List RuntimeType) (base : Machine) : RuntimeLocals :=
  ⟨1,[0],fun slot =>
    if slot % 8 = 0 ∧ 0 < slot then
      (kinds[slot/8-1]?).map fun kind => ⟨kind,false,0⟩
    else none,
    (preparedEntry base runtimeParameterSlot kinds.length).locals⟩

theorem formal_runtime_declared (present : kinds[index]? = some kind) :
    (formalRuntimeLocals kinds base).declarations (runtimeParameterSlot index) = some ⟨kind,false,0⟩ := by
  have remainder : runtimeParameterSlot index % 8 = 0 := by unfold runtimeParameterSlot; omega
  have positive : 0 < runtimeParameterSlot index := by unfold runtimeParameterSlot; omega
  have quotient : runtimeParameterSlot index / 8 - 1 = index := by unfold runtimeParameterSlot; omega
  simp only [formalRuntimeLocals,remainder,positive,and_self,if_pos,quotient,present,Option.map_some]

theorem RuntimeSignature.lookup {index : Nat} {sourceType : SourceType} (signature : RuntimeSignature t members module path first sources kinds)
    (present : sources[index]? = some sourceType) :
    ∃ kind, kinds[index]? = some kind ∧ RuntimeSourceType members module path sourceType kind := by
  induction signature generalizing index with
  | nil => simp at present
  | cons typ identity rest ih =>
    cases index with
    | zero => cases present; exact ⟨_,rfl,typ⟩
    | succ index => exact ih present

theorem RuntimeSignature.length (signature : RuntimeSignature t members module path first sources kinds) :
    kinds.length = sources.length := by
  induction signature with
  | nil => rfl
  | cons _ _ _ ih => simp only [List.length_cons,ih]

/-- Formal metadata follows the SAME source/table signature; equality of kinds
    is proved through source type uniqueness, not trusted from a slot default. -/
theorem runtime_formal_bindings (valid : RuntimeContextValid context)
    (signature : RuntimeSignature t context.members context.module context.path first
      (context.formals.map (·.type)) kinds) (emptyVisible : context.visible = []) :
    RuntimeBindingsPresent context (formalRuntimeLocals kinds base) := by
  intro name binding bound
  cases bound with
  | formal present named typ clear =>
    have sourceAt := congrArg (Option.map (·.type)) present
    rw [← List.getElem?_map] at sourceAt
    obtain ⟨kind,kindAt,declaredType⟩ := signature.lookup sourceAt
    have same := typ.unique valid.scope declaredType
    subst kind
    exact ⟨formal_runtime_declared kindAt,by simp only [formalRuntimeLocals,List.mem_singleton]⟩
  | localValue present named clear => simp only [emptyVisible,List.not_mem_nil] at present

end Aurora.SourceBinding
