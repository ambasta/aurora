import SourceBinding.RuntimeCallOccurrence
import SourceBinding.CallMachine
import SourceBinding.RuntimeSourceLeaf
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Every leaf retains its original byte-backed source and complete canonical
    entry/expression/return certificate. No callee result is supplied here. -/
structure RuntimeCallLeaf (t : Tables) (files : List SourceFile) (root module path : Name) where
  name : ByteArray
  identified : IdentifiedRuntimeFree t files root module path name
  body : RuntimeReturnCertificate identified

theorem RuntimeSignature.source_signature
    (signature : RuntimeSignature t members module path first sources kinds) :
    RuntimeSourceSignature members module path sources kinds := by
  induction signature with
  | nil => exact .nil
  | cons typ _ _ ih => exact .cons typ ih

def RuntimeCallLeaf.source (leaf : RuntimeCallLeaf t files root module path) : RuntimeSourceLeaf where
  input := leaf.identified.selected.file.file.bytes
  function := leaf.identified.selected.function.function
  parsed := leaf.identified.details.lexical.parsed
  context := runtimeReturnContext leaf.identified
  raw := leaf.body.raw
  singleton := leaf.body.source
  declared := leaf.identified.selected.function.present
  formals := rfl
  visible := rfl
  ordinary := by
    have identity := leaf.identified.details.identity
    unfold RuntimeFunctionIdentity at identity
    exact identity.1
  parameters := leaf.body.parameters.kinds
  result := leaf.body.resultKind
  parameterTypes := leaf.body.parameters.grammar.source_signature
  resultType := leaf.body.resultSource

def RuntimeCallLeaf.target (leaf : RuntimeCallLeaf t files root module path) : OrdinaryDescriptor :=
  ⟨leaf.name,leaf.identified.id,leaf.body.parameters.kinds,leaf.body.resultKind⟩

@[simp] theorem RuntimeCallLeaf.parameters_exact (leaf : RuntimeCallLeaf t files root module path) :
    leaf.source.parameters = leaf.target.parameters := rfl
@[simp] theorem RuntimeCallLeaf.result_exact (leaf : RuntimeCallLeaf t files root module path) :
    leaf.source.result = leaf.target.result := rfl
@[simp] theorem RuntimeCallLeaf.source_key (leaf : RuntimeCallLeaf t files root module path) :
    leaf.source.key = ⟨module,path,leaf.name⟩ := by
  change (⟨module,path,leaf.identified.selected.function.function.name⟩ : RuntimeSourceKey) = _
  rw [leaf.identified.selected.function.named]

def checkRuntimeCallLeaf (t : Tables) (files : List SourceFile) (root module path : Name)
    (name : ByteArray) : Option (RuntimeCallLeaf t files root module path) := do
  let identified ← identifyRuntimeFree t files root module path name
  let body ← checkRuntimeReturn identified
  return ⟨name,identified,body⟩

/-- Initial bounded resolution profile: a bare name in the same actual namespace.
    Qualified imports and receiver calls are not silently approximated. -/
def RuntimeBareCall (context : RuntimeExprContext) (leaf : RuntimeCallLeaf t files root module path)
    (sourceName : Name) : Prop :=
  context.module = module ∧ context.path = path ∧
  context.members = leaf.identified.selected.scope.members ∧ sourceName = [leaf.name] ∧
  leaf.name ∉ context.formals.map (·.name) ∧ leaf.name ∉ context.visible.map (·.name)
instance (context : RuntimeExprContext) (leaf : RuntimeCallLeaf t files root module path) (sourceName : Name) :
    Decidable (RuntimeBareCall context leaf sourceName) := by unfold RuntimeBareCall; infer_instance

/-- Full runtime signature, preserving nominal identities and cardinalities.
    Arity alone is insufficient even though the abstract call machine only needs
    the arity to collect its already evaluated operand stack. -/
def RuntimeDescriptorSignature (t : Tables) (target : OrdinaryDescriptor) : Prop :=
  Index target.id t.callables.size ∧
  (atRow t.callables target.id).integer 5 = Int.ofNat (target.parameters.length + 1) ∧
  RuntimeTypeIdentity t ((atRow t.callables target.id).integer 4) target.result ∧
  ∀ entry ∈ target.parameters.zipIdx,
    RuntimeTypeIdentity t ((atRow t.callables target.id).integer 4 + 1 + Int.ofNat entry.2) entry.1
instance (t : Tables) (target : OrdinaryDescriptor) : Decidable (RuntimeDescriptorSignature t target) := by
  unfold RuntimeDescriptorSignature; infer_instance

/-- Exact ordinary free Call19. The enclosing leaf certificate, not this raw-row
    predicate, supplies source selection and complete callee body semantics. -/
def RuntimeFreeInvocationAt (t : Tables) (caller : Int) (pc : Nat) (target : OrdinaryDescriptor) : Prop :=
  match (functionCode t caller)[pc]? with
  | none => False
  | some row =>
    row.integer 0 = caller ∧ row.integer 1 = Int.ofNat pc ∧ row.integer 6 = 19 ∧
    operandRoles t row = [100] ∧ Selectors row ∧
    (∀ operand ∈ (operandsOf t row).toList, OperandPayload t operand) ∧ CodeEdges t caller row ∧
    RuntimeDescriptorSignature t target ∧
    RuntimeFreeShape t target.id target.parameters [] ∧
    callName t row = nameBytes t (atRow t.callables target.id) 1 ∧
    (namedCallables t (callName t row)).size = 1
instance (t : Tables) (caller : Int) (pc : Nat) (target : OrdinaryDescriptor) :
    Decidable (RuntimeFreeInvocationAt t caller pc target) := by
  unfold RuntimeFreeInvocationAt; split <;> infer_instance

end Aurora.SourceBinding
