import SourceBinding.RuntimeCallCode
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Syntactic called names from the actual raw expression, including all nested
    arguments and both short-circuit arms. Only bare free calls are supported. -/
def runtimeCalledNames : Nat → SourceExpr → Option (List ByteArray)
  | 0, _ => none
  | _ + 1, .word _ | _ + 1, .boolean _ | _ + 1, .name _
  | _ + 1, .signed12 | _ + 1, .signedCount _ => some []
  | fuel + 1, .not inner => runtimeCalledNames fuel inner
  | fuel + 1, .binary _ left right => do
    return (← runtimeCalledNames fuel left) ++ (← runtimeCalledNames fuel right)
  | fuel + 1, .call (.named [name]) args => do
    let nested ← args.mapM (runtimeCalledNames fuel)
    return name :: nested.flatten
  | _, .call _ _ => none

/-- A same-callable interval for a selected source return occurrence. It does not
    prove that execution reaches this interval, or that the surrounding branch
    lowering places this occurrence correctly. Those require statement/CFG proof. -/
structure RuntimeCallInterval (identified : IdentifiedRuntimeFree t files root module path name) where
  occurrence : RuntimeReturnOccurrence identified
  leaves : List (RuntimeCallLeaf t files root module path)
  names : runtimeCalledNames 4096 occurrence.selected.raw = some (leaves.map (·.name))
  compatible : RuntimeLeavesCompatible leaves
  start : Nat
  code : ParsedRuntimeCallExpression (canonicalRuntimeCalls t (leaves.map (·.target)))
    identified.id leaves occurrence.context occurrence.selected.raw start
  resultSource : RuntimeSourceType identified.selected.scope.members module path
    identified.selected.function.function.result code.kind
  resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) code.kind
  inBounds : start ≤ code.stop ∧ code.stop < (functionCode t identified.id).size
  returning : canonicalEffects t identified.id code.stop = some (.pure .ret)

def checkRuntimeCallInterval (identified : IdentifiedRuntimeFree t files root module path name)
    (indices : List Nat) (start : Nat) : Option (RuntimeCallInterval identified) := do
  let occurrence ← checkRuntimeReturnOccurrence identified indices
  let names ← runtimeCalledNames 4096 occurrence.selected.raw
  let leaves ← names.mapM (checkRuntimeCallLeaf t files root module path)
  if sourceNames : runtimeCalledNames 4096 occurrence.selected.raw = some (leaves.map (·.name)) then
    if compatible : RuntimeLeavesCompatible leaves then
      let code ← checkRuntimeCallExpressionCode (canonicalRuntimeCalls t (leaves.map (·.target)))
        identified.id leaves occurrence.context 4096 occurrence.selected.raw start
      let result ← resolveRuntimeType identified.selected.scope.members module path
        identified.selected.function.function.result
      if same : result.kind = code.kind then
        if resultIdentity : RuntimeTypeIdentity t ((atRow t.callables identified.id).integer 4) code.kind then
          if inBounds : start ≤ code.stop ∧ code.stop < (functionCode t identified.id).size then
            if returning : canonicalEffects t identified.id code.stop = some (.pure .ret) then
              return ⟨occurrence,leaves,sourceNames,compatible,start,code,same ▸ result.typing,
                resultIdentity,inBounds,returning⟩
            else none
          else none
        else none
      else none
    else none
  else none

structure RuntimeCallBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  bound : RuntimeFreeBinding input files root module path name
  interval : RuntimeCallInterval bound.checked

def bindRuntimeCallInterval (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (indices : List Nat) (start : Nat) (input : ByteArray) :
    Option (RuntimeCallBinding input files root module path name) := do
  let bound ← bindRuntimeFree files root module path name input
  let interval ← checkRuntimeCallInterval bound.checked indices start
  return ⟨bound,interval⟩

end Aurora.SourceBinding
