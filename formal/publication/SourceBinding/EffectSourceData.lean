import SourceBinding.RuntimeEvaluationData
import SourceBinding.Stateful
import SourceBinding.RuntimeReceiverSource
namespace Aurora.SourceBinding

abbrev SourceResourceKey := RuntimeSourceResource

/-- Source-visible shared state. Private locals are never part of a resource
    request or an external response, and a saved caller cannot restore this state. -/
structure SourceShared (World : Type) where
  receiver : Nat → Option Value
  world : World

structure SourceEffectState (World : Type) where
  locals : RuntimeLocals
  shared : SourceShared World

structure SourceResourceRequest (World : Type) where
  key : SourceResourceKey
  arguments : List Value
  before : SourceShared World

/-- Returned data is deliberately raw. The actual consuming operator/store/
    require performs its own check; external resumption does not validate it. -/
inductive SourceExternalOutcome (ExternalFault : Type) where
  | returned (value : Option Value)
  | fault (reason : ExternalFault)

abbrev SourceExternalRelation (World ExternalFault : Type) :=
  SourceResourceRequest World → SourceExternalOutcome ExternalFault →
    SourceShared World → Prop

/-- A finite source observation may stop at an outstanding request. This does
    not assert that no response exists, nor classify waiting as divergence.
    The machine correspondence supplies the real resumable continuation. -/
inductive SourceEffectStop (World ExternalFault : Type) where
  | localFault (reason : EffectFault)
  | externalFault (reason : ExternalFault)
  | waiting (request : SourceResourceRequest World)

inductive SourceEffectOutcome (World ExternalFault : Type) where
  | value (value : Option Value)
  | stopped (reason : SourceEffectStop World ExternalFault)

inductive SourceEffectEvent (World ExternalFault : Type) where
  | invoke (key : RuntimeSourceKey) (arguments : List Value)
  | returned (key : RuntimeSourceKey) (value : Value)
  | fieldStore (field : ByteArray) (value : Value)
  | externalInvoke (request : SourceResourceRequest World)
  | externalReturn (value : Option Value) (after : SourceShared World)
  | externalFault (reason : ExternalFault) (after : SourceShared World)

/-- Statement-local terminal state, as in the previous source judgement. A nested
    fault does not claim that this private map is the active callee machine map;
    shared state and the unmatched invocation trace are retained separately. -/
inductive SourceEffectBodyOutcome (World ExternalFault : Type) where
  | continued (state : SourceEffectState World)
  | returned (value : Value) (state : SourceEffectState World)
  | stopped (outcome : SourceEffectStop World ExternalFault)
      (state : SourceEffectState World)

end Aurora.SourceBinding
