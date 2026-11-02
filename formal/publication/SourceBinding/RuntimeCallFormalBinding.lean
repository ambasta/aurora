import SourceBinding.RuntimeCallBinding
namespace Aurora.SourceBinding
open Aurora.Publication

theorem RuntimeSignature.tail
    (signature : RuntimeSignature t members module path first (result :: sources) kinds) :
    RuntimeSignature t members module path (first + 1) sources kinds.tail := by
  cases signature with
  | cons _ _ rest => exact rest

/-- Optional contextual-entry profile: the selected occurrence has no visible
    locals, so its source environment is entirely derived from actual formals.
    This does not establish execution reaches the selected candidate PC. -/
structure FormalRuntimeCallInterval (identified : IdentifiedRuntimeFree t files root module path name) where
  interval : RuntimeCallInterval identified
  emptyVisible : interval.occurrence.context.visible = []
  entry : RuntimeEntryCode (canonicalEffects t identified.id) identified.details.types.kinds.tail

def FormalRuntimeCallInterval.parameters
    {identified : IdentifiedRuntimeFree t files root module path name}
    (_checked : FormalRuntimeCallInterval identified) : List RuntimeType := identified.details.types.kinds.tail

theorem FormalRuntimeCallInterval.signature
    {identified : IdentifiedRuntimeFree t files root module path name}
    (checked : FormalRuntimeCallInterval identified) :
    RuntimeSignature t checked.interval.occurrence.context.members module path
      ((atRow t.callables identified.id).integer 4 + 1)
      (checked.interval.occurrence.context.formals.map (·.type)) checked.parameters :=
  identified.details.types.grammar.tail

def checkFormalRuntimeCallInterval {identified : IdentifiedRuntimeFree t files root module path name}
    (interval : RuntimeCallInterval identified) :
    Option (FormalRuntimeCallInterval identified) :=
  if emptyVisible : interval.occurrence.context.visible = [] then
    if entry : RuntimeEntryCode (canonicalEffects t identified.id) identified.details.types.kinds.tail then
      some ⟨interval,emptyVisible,entry⟩
    else none
  else none

structure RuntimeCallFormalBinding (input : ByteArray) (files : List SourceFile)
    (root module path : Name) (name : ByteArray) where
  bound : RuntimeFreeBinding input files root module path name
  checked : FormalRuntimeCallInterval bound.checked

def bindRuntimeFormalCallInterval (files : List SourceFile) (root module path : Name) (name : ByteArray)
    (indices : List Nat) (start : Nat) (input : ByteArray) :
    Option (RuntimeCallFormalBinding input files root module path name) := do
  let general ← bindRuntimeCallInterval files root module path name indices start input
  let checked ← checkFormalRuntimeCallInterval general.interval
  return ⟨general.bound,checked⟩

end Aurora.SourceBinding
