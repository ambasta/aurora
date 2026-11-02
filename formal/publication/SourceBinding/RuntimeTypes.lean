import SourceBinding.GuardExpr
namespace Aurora.SourceBinding

/-- Canonical nominal name and its checked, closed declaration cardinality.
    Source/table correspondence is a separate obligation; this data alone is
    not evidence that an enum declaration exists. -/
structure NominalIdentity where
  name : ByteArray
  cases : Nat
  deriving BEq, DecidableEq

instance : Repr NominalIdentity where
  reprPrec identity _ := "NominalIdentity " ++ repr identity.name.data ++ " " ++ repr identity.cases

/-- The scalar subprofile is unchanged. Enums are not words or booleans. -/
inductive RuntimeType where
  | scalar (kind : GuardType)
  | nominal (identity : NominalIdentity)
  deriving BEq, DecidableEq, Repr

/-- Supported signed literal count profile, not general signed arithmetic. -/
inductive SignedLiteralCount where
  | four | twelve | thirtyTwo
  deriving BEq, DecidableEq, Repr

def SignedLiteralCount.value : SignedLiteralCount → Nat
  | .four => 4 | .twelve => 12 | .thirtyTwo => 32

theorem SignedLiteralCount.in_range (count : SignedLiteralCount) : count.value < 64 := by
  cases count <;> decide

end Aurora.SourceBinding
