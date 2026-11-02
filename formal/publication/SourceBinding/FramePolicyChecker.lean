import SourceBinding.FramePolicyProfile
namespace Aurora.SourceBinding.FramePolicyAttachment

/-- Select a role only from the already checked exact DAG. Every stored field
    is a finite source/signature equality, not an evaluated helper result. -/
def checkRoleNode (dag : RuntimeDAGCertificate t files root frameModule framePath rootName)
    (operations rejections : NominalIdentity) (role : Role) :
    Option (RoleNode dag operations rejections role) := do
  match found : dag.shape.nodes.find? (fun node => node.name == role.name) with
  | none => none
  | some node =>
    if named : node.name = role.name then
      if formals : node.source.function.formals = role.shape.formals then
        if resultSyntax : node.source.function.result = role.shape.result then
          if body : node.source.parsed.statements = role.shape.body then
            if parameters : node.source.parameters = role.parameterKinds operations rejections then
              if resultKind : node.source.result = role.resultKind then
                if members : node.source.context.members = dag.shape.rootNode.source.context.members then
                  return ⟨node,List.mem_of_find?_eq_some found,named,formals,resultSyntax,body,parameters,resultKind,members⟩
                else none
              else none
            else none
          else none
        else none
      else none
    else none

/-- A total ten-role map is built by cases, without selecting Type data from a
    propositional existential. The actual graph root is not pinned here. -/
def checkPolicyRoles (dag : RuntimeDAGCertificate t files root frameModule framePath rootName)
    (operations rejections : NominalIdentity) :
    Option ((role : Role) → RoleNode dag operations rejections role) := do
  let free ← checkRoleNode dag operations rejections .free
  let allocated ← checkRoleNode dag operations rejections .allocated
  let kernel ← checkRoleNode dag operations rejections .kernel
  let retired ← checkRoleNode dag operations rejections .retired
  let generationLimit ← checkRoleNode dag operations rejections .generationLimit
  let kernelOwner ← checkRoleNode dag operations rejections .kernelOwner
  let frameRecord ← checkRoleNode dag operations rejections .frameRecord
  let frameReject ← checkRoleNode dag operations rejections .frameReject
  let recordValid ← checkRoleNode dag operations rejections .recordValid
  let transition ← checkRoleNode dag operations rejections .transition
  return fun role => match role with
    | .free => free | .allocated => allocated | .kernel => kernel | .retired => retired
    | .generationLimit => generationLimit | .kernelOwner => kernelOwner
    | .frameRecord => frameRecord | .frameReject => frameReject
    | .recordValid => recordValid | .transition => transition

/-- Attach the exact policy to the SAME already decoded artifact and selected
    source graph. Enum declarations reuse the root's byte-backed namespace;
    there is no second artifact decode or replacement source inventory. -/
def checkFramePolicy (bound : RuntimeDAGBinding input files root frameModule framePath rootName) :
    Option (ExactProfile bound) := do
  let selected := bound.checked.shape.rootNode.identified.selected
  let operationDecl ← findEnum selected.scope.members operationName
  let rejectionDecl ← findEnum selected.scope.members rejectionName
  let operations : SelectedEnum files root frameModule framePath operationName :=
    ⟨selected.graph,selected.file,selected.scope,operationDecl⟩
  let rejections : SelectedEnum files root frameModule framePath rejectionName :=
    ⟨selected.graph,selected.file,selected.scope,rejectionDecl⟩
  if operationCasesEq : operations.declaration.cases = operationCases then
    if rejectionCasesEq : rejections.declaration.cases = rejectionCases then
      let roles ← checkPolicyRoles bound.checked operations.nominal rejections.nominal
      if uniqueNames : (bound.checked.shape.nodes.map (·.name)).Nodup then
        if coverage : ∀ node ∈ bound.checked.shape.nodes, ∃ role ∈ Role.all, node.name = role.name then
          if parameters : bound.checked.shape.rootNode.source.parameters =
              [.nominal operations.nominal,.scalar .word,.scalar .word,.scalar .word,.scalar .word] then
            if resultKind : bound.checked.shape.rootNode.source.result = .scalar .word then
              return ⟨operations,rejections,operationCasesEq,rejectionCasesEq,rfl,rfl,roles,
                uniqueNames,coverage,parameters,resultKind⟩
            else none
          else none
        else none
      else none
    else none
  else none

end Aurora.SourceBinding.FramePolicyAttachment
