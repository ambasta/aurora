import SourceBinding.FreeBinding
import SourceBinding.CallMachine
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Only exact formal parameters, once each and in declaration order. -/
inductive ParameterArguments : Nat → {kinds : List GuardType} → CallArguments kinds → Prop
  | nil : ParameterArguments start .nil
  | cons : ParameterArguments (start + 1) tail →
      ParameterArguments start (.cons (.parameter kind name start) tail)

def checkParameterArguments : (start : Nat) → {kinds : List GuardType} →
    (args : CallArguments kinds) → Option { _unit : Unit // ParameterArguments start args }
  | _, _, .nil => some ⟨(),.nil⟩
  | start, _, .cons (.parameter _ _ index) tail => do
    if same : index = start then
      let rest ← checkParameterArguments (start + 1) tail
      return ⟨(),by subst index; exact .cons rest.property⟩
    else none
  | _, _, .cons _ _ => none

/-- Actual ordinary free Call19, not a fabricated receiver MethodCall38. -/
def FreeInvocationAt (t : Tables) (caller : Int) (pc : Nat) (target : ScalarOrdinary) : Prop :=
  match (functionCode t caller)[pc]? with
  | none => False
  | some row =>
    row.integer 0 = caller ∧ row.integer 1 = Int.ofNat pc ∧ row.integer 6 = 19 ∧
    operandRoles t row = [100] ∧ Selectors row ∧
    (∀ operand ∈ (operandsOf t row).toList, OperandPayload t operand) ∧ CodeEdges t caller row ∧
    FreeFunctionShape t target.id ∧
    callName t row = nameBytes t (atRow t.callables target.id) 1 ∧
    (namedCallables t (callName t row)).size = 1 ∧
    ((signature t (atRow t.callables target.id)).drop 1).map (scalarKind t) = target.parameters.map some ∧
    scalarKind t ((atRow t.callables target.id).integer 4) = some target.result
instance (t : Tables) (caller : Int) (pc : Nat) (target : ScalarOrdinary) :
    Decidable (FreeInvocationAt t caller pc target) := by
  unfold FreeInvocationAt; split <;> infer_instance

/-- Local-first projection; only the independently checked free call can fill a gap. -/
def freeCalls (t : Tables) (target : ScalarOrdinary) : CallProgram := fun caller pc =>
  match canonicalEffects t caller pc with
  | some operation => some (.local operation)
  | none => if FreeInvocationAt t caller pc target then some (.ordinary target) else none

theorem free_calls_local (t : Tables) (target : ScalarOrdinary) (caller : Int) :
    localProgram (freeCalls t target) caller = canonicalEffects t caller := by
  funext pc
  simp only [localProgram,freeCalls]
  cases canonicalEffects t caller pc <;> simp

/-- Bounded returning forwarder: complete original source and complete actual IR,
    same graph/table callee, direct exported import, six ordered scalar parameters. -/
structure ForwardWrapper (t : Tables) (files : List SourceFile) (root targetModule targetPath : Name)
    (wrapperName targetName : ByteArray) where
  wrapper : IdentifiedFree t files root root [] wrapperName
  leaf : LocalFreeBinding t files root targetModule targetPath targetName
  imported : targetModule ∈ importedNames wrapper.selected.file.file
  exportedModule : leaf.identified.selected.file.file.checked.source.header.declarations.module.exported = true
  exportedScope : leaf.identified.selected.scope.exported = true
  qualified : targetPath ≠ []
  unshadowed : ∀ formal ∈ wrapper.selected.function.function.formals,
    some formal.name ≠ targetPath.head?
  wrapperParameters : wrapper.selected.function.function.formals.map (·.type) =
    List.replicate 6 (guardSourceType .word)
  leafParameters : leaf.identified.selected.function.function.formals.map (·.type) =
    List.replicate 6 (guardSourceType .word)
  wrapperResult : wrapper.selected.function.function.result = guardSourceType .boolean
  leafResult : leaf.identified.selected.function.function.result = guardSourceType .boolean
  parsed : ParsedMethod wrapper.selected.file.file.bytes wrapper.selected.function.function
  sources : List SourceExpr
  sourceShape : parsed.statements = [.returnValue (.call (.named (targetPath ++ [targetName])) sources)]
  arguments : CallArguments (List.replicate 6 .word)
  typing : TypedArguments [] wrapper.selected.function.function.formals sources arguments
  ordered : ParameterArguments 0 arguments
  bindings : List ParameterBinding
  entry : EntryCode (pureView (canonicalEffects t wrapper.id)) wrapper.selected.function.function.formals bindings
  callPC : Nat
  argumentCode : PushedArgumentsCode (pureView (canonicalEffects t wrapper.id)) (parameterSlot bindings)
    arguments wrapper.selected.function.function.formals.length callPC
  invocation : FreeInvocationAt t wrapper.id callPC (ScalarOrdinary.ofScalars targetName leaf.identified.id (List.replicate 6 .word) .boolean)
  notLocal : canonicalEffects t wrapper.id callPC = none
  returning : canonicalEffects t wrapper.id (callPC + 1) = some (.pure .ret)
  complete : (functionCode t wrapper.id).size = callPC + 2

def checkForwardWrapper (t : Tables) (files : List SourceFile) (root targetModule targetPath : Name)
    (wrapperName targetName : ByteArray) :
    Option (ForwardWrapper t files root targetModule targetPath wrapperName targetName) := do
  let wrapper ← identifyFree t files root root [] wrapperName
  let leaf ← bindLocalFree t files root targetModule targetPath targetName
  if imported : targetModule ∈ importedNames wrapper.selected.file.file then
   if exportedModule : leaf.identified.selected.file.file.checked.source.header.declarations.module.exported = true then
    if exportedScope : leaf.identified.selected.scope.exported = true then
     if qualified : targetPath ≠ [] then
      if unshadowed : ∀ formal ∈ wrapper.selected.function.function.formals, some formal.name ≠ targetPath.head? then
       if wrapperParameters : wrapper.selected.function.function.formals.map (·.type) = List.replicate 6 (guardSourceType .word) then
        if leafParameters : leaf.identified.selected.function.function.formals.map (·.type) = List.replicate 6 (guardSourceType .word) then
         if wrapperResult : wrapper.selected.function.function.result = guardSourceType .boolean then
          if leafResult : leaf.identified.selected.function.function.result = guardSourceType .boolean then
           let parsed ← methodSyntax wrapper.selected.file.file.bytes wrapper.selected.function.function
           match statementsEq : parsed.statements with
           | [.returnValue (.call (.named actualName) sources)] =>
            if nameEq : actualName = targetPath ++ [targetName] then
             let sourceShape : parsed.statements = [.returnValue (.call (.named (targetPath ++ [targetName])) sources)] := by
               simpa only [nameEq] using statementsEq
             let arguments ← inferArguments [] wrapper.selected.function.function.formals (List.replicate 6 .word) sources
             let ordered ← checkParameterArguments 0 arguments.values
             let entry ← checkEntry (pureView (canonicalEffects t wrapper.id)) wrapper.selected.function.function.formals
             let code ← checkPushedArguments (pureView (canonicalEffects t wrapper.id)) (parameterSlot entry.bindings)
               arguments.values wrapper.selected.function.function.formals.length
             if invocation : FreeInvocationAt t wrapper.id code.stop (ScalarOrdinary.ofScalars targetName leaf.identified.id (List.replicate 6 .word) .boolean) then
              if notLocal : canonicalEffects t wrapper.id code.stop = none then
               if returning : canonicalEffects t wrapper.id (code.stop + 1) = some (.pure .ret) then
                if complete : (functionCode t wrapper.id).size = code.stop + 2 then
                 return ⟨wrapper,leaf,imported,exportedModule,exportedScope,qualified,unshadowed,
                   wrapperParameters,leafParameters,wrapperResult,leafResult,parsed,sources,sourceShape,
                   arguments.values,arguments.typing,ordered.property,entry.bindings,entry.code,
                   code.stop,code.code,invocation,notLocal,returning,complete⟩
                else none
               else none
              else none
             else none
            else none
           | _ => none
          else none
         else none
        else none
       else none
      else none
     else none
    else none
   else none
  else none

structure BoundForwardWrapper (files : List SourceFile) (root targetModule targetPath : Name)
    (wrapperName targetName : ByteArray) (bytes : ByteArray) where
  artifact : CheckedArtifact bytes
  checked : ForwardWrapper (tables artifact.document.reversed.reverse) files root targetModule targetPath wrapperName targetName

def bindForwardWrapper (files : List SourceFile) (root targetModule targetPath : Name)
    (wrapperName targetName : ByteArray) (bytes : ByteArray) :
    Option (BoundForwardWrapper files root targetModule targetPath wrapperName targetName bytes) := do
  let artifact ← decodeArtifact {} bytes
  let checked ← checkForwardWrapper (tables artifact.document.reversed.reverse) files root targetModule targetPath wrapperName targetName
  return ⟨artifact,checked⟩
end Aurora.SourceBinding
