import SourceBinding.RuntimeSourceLeaf
import SourceBinding.RuntimeFormals
import SourceBinding.RuntimeScopeOperations
namespace Aurora.SourceBinding

def SourceLocal.runtimeDeclaration (binding : SourceLocal) : RuntimeLocalDecl :=
  ⟨binding.kind,binding.mutable,binding.scope⟩

def RuntimeLocals.readBound (state : RuntimeLocals) (binding : SourceLocal) : Outcome Value :=
  if state.declarations binding.slot = some binding.runtimeDeclaration then
    state.read binding.slot
  else .trap .type

/-- Source-visible calls are keyed by source module/namespace/name. No IR id,
    target machine state or supplied callee result appears in an event. -/
inductive RuntimeSourceEvent where
  | invoke (key : RuntimeSourceKey) (arguments : List Value)
  | returned (key : RuntimeSourceKey) (value : Value)
  deriving BEq, DecidableEq

/-- A terminal source statement retains the state at that point. Returning or
    trapping does not invent lexical cleanup, rollback or machine unwinding. -/
inductive RuntimeBodyOutcome where
  | continued (state : RuntimeLocals)
  | returned (value : Value) (state : RuntimeLocals)
  | trapped (fault : Fault) (state : RuntimeLocals)


end Aurora.SourceBinding
