import SourceBinding.RuntimeStatementMatcher
import SourceBinding.RuntimeCallFormalBinding
namespace Aurora.SourceBinding
open Aurora.Publication

/- Complete syntactic call inventory, including both branch arms and all
    unreachable suffixes. No supplied summary or reachable-only filter. -/
mutual
def runtimeStatementNames : Nat → SourceStatement → Option (List ByteArray)
  | 0, _ => none
  | fuel + 1, .localDecl _ value | fuel + 1, .assign _ value
  | fuel + 1, .returnValue value => runtimeCalledNames fuel value
  | fuel + 1, .ifThen condition body => do
    return (← runtimeCalledNames fuel condition) ++ (← runtimeStatementsNames fuel body)
  | fuel + 1, .ifElse condition yes no => do
    return (← runtimeCalledNames fuel condition) ++ (← runtimeStatementsNames fuel yes) ++
      (← runtimeStatementsNames fuel no)
  | _, .call _ _ => none

def runtimeStatementsNames : Nat → List SourceStatement → Option (List ByteArray)
  | 0, _ => none
  | _ + 1, [] => some []
  | fuel + 1, first :: rest => do
    return (← runtimeStatementNames fuel first) ++ (← runtimeStatementsNames fuel rest)
end

/-- Complete-body checked source/code relation. Execution is supplied by the
    separate whole-body simulation theorem. No caller-selected interval or
    successful-result premise occurs here. Callees remain complete call-free
    singleton-return certificates, not arbitrary summaries or a recursive DAG. -/
structure RuntimeBodyCertificate (identified : IdentifiedRuntimeFree t files root module path name) where
  leaves : List (RuntimeCallLeaf t files root module path)
  names : runtimeStatementsNames 4096 identified.details.lexical.parsed.statements = some (leaves.map (·.name))
  compatible : RuntimeLeavesCompatible leaves
  parameters : CheckedRuntimeSignature t identified.selected.scope.members module path
    ((atRow t.callables identified.id).integer 4 + 1)
    (identified.selected.function.function.formals.map (·.type))
  resultKind : RuntimeType
  resultSource : RuntimeSourceType identified.selected.scope.members module path
    identified.selected.function.function.result resultKind
  resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) resultKind
  entry : RuntimeEntryCode (canonicalEffects t identified.id) parameters.kinds
  code : RuntimeStatementsCode (canonicalRuntimeCalls t (leaves.map (·.target))) identified.id (leaves.map (·.toCallable))
    identified.selected.scope.members identified.selected.function.function.formals resultKind
    ⟨[],0,1,identified.selected.function.function.formals.length⟩
    identified.details.lexical.parsed.statements
    identified.details.lexical.lexical.after identified.details.lexical.lexical.declaredItems
    parameters.kinds.length (functionCode t identified.id).size
  noFallthrough : RuntimeNoFallthrough identified.details.lexical.parsed.statements

def checkRuntimeBody (identified : IdentifiedRuntimeFree t files root module path name) :
    Option (RuntimeBodyCertificate identified) := do
  let names ← runtimeStatementsNames 4096 identified.details.lexical.parsed.statements
  let leaves ← names.mapM (checkRuntimeCallLeaf t files root module path)
  if sourceNames : runtimeStatementsNames 4096 identified.details.lexical.parsed.statements = some (leaves.map (·.name)) then
    if compatible : RuntimeLeavesCompatible leaves then
      let parameters ← checkRuntimeSignature t identified.selected.scope.members module path
        ((atRow t.callables identified.id).integer 4 + 1)
        (identified.selected.function.function.formals.map (·.type))
      let result ← resolveRuntimeType identified.selected.scope.members module path
        identified.selected.function.function.result
      if resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) result.kind then
        if entry : RuntimeEntryCode (canonicalEffects t identified.id) parameters.kinds then
          let code ← checkRuntimeStatements (canonicalRuntimeCalls t (leaves.map (·.target))) identified.id (leaves.map (·.toCallable))
            identified.selected.scope.members identified.selected.function.function.formals result.kind 4096
            ⟨[],0,1,identified.selected.function.function.formals.length⟩
            identified.details.lexical.parsed.statements parameters.kinds.length
          if after : code.after = identified.details.lexical.lexical.after then
            if declaredItems : code.declaredItems = identified.details.lexical.lexical.declaredItems then
              if complete : code.stop = (functionCode t identified.id).size then
                let terminal ← checkRuntimeNoFallthrough identified.details.lexical.parsed.statements
                return ⟨leaves,sourceNames,compatible,parameters,result.kind,result.typing,resultIdentity,entry,
                  after ▸ declaredItems ▸ complete ▸ code.grammar,terminal.property⟩
              else none
            else none
          else none
        else none
      else none
    else none
  else none

structure RuntimeBodyBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  bound : RuntimeFreeBinding input files root module path name
  body : RuntimeBodyCertificate bound.checked

def bindRuntimeBody (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (input : ByteArray) : Option (RuntimeBodyBinding input files root module path name) := do
  let bound ← bindRuntimeFree files root module path name input
  let body ← checkRuntimeBody bound.checked
  return ⟨bound,body⟩

end Aurora.SourceBinding
