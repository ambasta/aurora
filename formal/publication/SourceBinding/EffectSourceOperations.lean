import SourceBinding.EffectSourceData
namespace Aurora.SourceBinding

/-- Lift the existing pure primitive result; no arithmetic is reimplemented. -/
def sourceLift (result : Outcome Value) : SourceEffectOutcome World ExternalFault :=
  match result with
  | .value value => .value (some value)
  | .trap fault => .stopped (.localFault (.scalar fault))

/-- Missing operands fault at the actual consuming boundary. No general resource
    expression rule exists in the initial receiver profile; raw resource results
    are consumed directly by localStore/require in ResourceStatementRules. -/
def sourceThen (result : SourceEffectOutcome World ExternalFault)
    (next : Value → Outcome Value) : SourceEffectOutcome World ExternalFault :=
  match result with
  | .value (some value) => sourceLift (next value)
  | .value none => .stopped (.localFault (.scalar .type))
  | .stopped reason => .stopped reason

inductive EffectArgumentOutcome (World ExternalFault : Type) where
  | values (values : List Value)
  | stopped (reason : SourceEffectStop World ExternalFault)

def EffectArgumentOutcome.prepend (result : EffectArgumentOutcome World ExternalFault)
    (value : Value) : EffectArgumentOutcome World ExternalFault :=
  match result with
  | .values items => .values (value :: items)
  | .stopped reason => .stopped reason

/-- Ordered source parameter checks, corresponding to real fresh callee binds.
    The call rule emits invoke BEFORE using this check. A failure must retain
    the active callee and already executed bind prefix in the machine proof.
    Old pure successful argument derivations prove this check succeeds; no new
    readiness condition is imposed on the old source API. -/
def checkSourceArguments : List RuntimeType → List Value → Outcome Unit
  | [], [] => .value ()
  | kind :: kinds, value :: values =>
      match readRuntime kind (some value) with
      | .trap fault => .trap fault
      | .value _ => checkSourceArguments kinds values
  | _, _ => .trap .type

end Aurora.SourceBinding
