import SourceBinding.CallCode
import SourceBinding.LocalBodyCertificate
namespace Aurora.SourceBinding
open Aurora.Publication

/-- A selected ordinary invocation is backed by its actual call-free source and
    complete code in the root's SAME tables. This is not a callee summary. -/
structure CheckedCallLeaf (shape : CallShapeBinding files root module path member bytes)
    (target : OrdinaryDescriptor) where
  identity : OrdinaryCallIdentity (tables shape.ir.publication.artifact.document.reversed.reverse)
    module path shape.selected.selected.classDecl.members target
  source : BodyMethod shape.selected.selected.file.file.bytes identity.found.function
    (fields shape.selected.selected.classDecl.members)
  body : LocalBodyCertificate (tables shape.ir.publication.artifact.document.reversed.reverse) target.id source
  selected : target.id ∈ shape.ir.publication.slice.selected

def checkCallLeaf (shape : CallShapeBinding files root module path member bytes) (target : OrdinaryDescriptor) :
    Option (CheckedCallLeaf shape target) := do
  let bound ← bindOrdinaryCall (tables shape.ir.publication.artifact.document.reversed.reverse)
    module path shape.selected.selected.classDecl.members target.member
  if same : bound.target = target then
    let identity := same ▸ bound.identity
    let source ← bodyMethod shape.selected.selected.file.file.bytes identity.found.function
      (fields shape.selected.selected.classDecl.members)
    let body ← checkLocalBody (tables shape.ir.publication.artifact.document.reversed.reverse) target.id source
    if selected : target.id ∈ shape.ir.publication.slice.selected then
      return ⟨identity,source,body,selected⟩
    else none
  else none

/-- Pointwise certificates cover every ordinary occurrence, even unreachable
    suffixes. Leaf typing rejects further calls rather than assuming acyclicity. -/
inductive CallLeaves (shape : CallShapeBinding files root module path member bytes) : List CallPiece → Type
  | nil : CallLeaves shape []
  | localBody : CallLeaves shape rest → CallLeaves shape (.localBody body :: rest)
  | ordinary {target : OrdinaryDescriptor} {arguments : CallArguments target.parameters} :
      CheckedCallLeaf shape target → CallLeaves shape rest →
      CallLeaves shape (.invoke (.ordinary target arguments) :: rest)
  | resourceAssert {target : ResourceDescriptor} {arguments : CallArguments target.parameters} :
      CallLeaves shape rest → CallLeaves shape (.invoke (.resourceAssert target arguments) :: rest)

def checkCallLeaves (shape : CallShapeBinding files root module path member bytes) :
    (pieces : List CallPiece) → Option (CallLeaves shape pieces)
  | [] => some .nil
  | .localBody _ :: rest => do return .localBody (← checkCallLeaves shape rest)
  | .invoke (.ordinary target _) :: rest => do
    return .ordinary (← checkCallLeaf shape target) (← checkCallLeaves shape rest)
  | .invoke (.resourceAssert _ _) :: rest => do return .resourceAssert (← checkCallLeaves shape rest)

structure CallFamilyBinding (files : List SourceFile) (root module path : Name) (member bytes : ByteArray) where
  shape : CallShapeBinding files root module path member bytes
  leaves : CallLeaves shape shape.source.pieces

def bindCallFamily (files : List SourceFile) (root module path : Name) (member bytes : ByteArray) :
    Option (CallFamilyBinding files root module path member bytes) := do
  let shape ← bindCallShape files root module path member bytes
  return ⟨shape,← checkCallLeaves shape shape.source.pieces⟩

theorem checked_call_leaf_complete
    {shape : CallShapeBinding files root module path member bytes} (leaf : CheckedCallLeaf shape target) :
    SourceIRIdentity (tables shape.ir.publication.artifact.document.reversed.reverse) target.id
      module path target.member shape.selected.selected.classDecl.members leaf.identity.found.function
      leaf.identity.visible ∧
    leaf.body.stop = (functionCode (tables shape.ir.publication.artifact.document.reversed.reverse) target.id).size ∧
    target.id ∈ shape.ir.publication.slice.selected :=
  ⟨leaf.identity.identity,leaf.body.complete,leaf.selected⟩
end Aurora.SourceBinding
