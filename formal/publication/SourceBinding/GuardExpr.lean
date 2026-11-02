import Publication.Selection
namespace Aurora.SourceBinding

abbrev GuardType := Aurora.Publication.Scalar

inductive CompareOp where
  | eq | ne | lt | le | gt | ge
  deriving BEq, DecidableEq, Repr

/-- Pure typed guard expressions. Name/index/type correspondence and word literal
    bounds are established separately by TypedGuard, not asserted by these data. -/
inductive GuardExpr : GuardType → Type where
  | wordLit (value : Nat) : GuardExpr .word
  | boolLit (value : Bool) : GuardExpr .boolean
  | parameter (kind : GuardType) (name : ByteArray) (index : Nat) : GuardExpr kind
  | field (kind : GuardType) (name : ByteArray) (ordinal : Nat) : GuardExpr kind
  | not : GuardExpr .boolean → GuardExpr .boolean
  | sub : GuardExpr .word → GuardExpr .word → GuardExpr .word
  | bitAnd : GuardExpr .word → GuardExpr .word → GuardExpr .word
  | bitOr : GuardExpr .word → GuardExpr .word → GuardExpr .word
  | shift12 : GuardExpr .word → GuardExpr .word
  | compare : CompareOp → GuardExpr .word → GuardExpr .word → GuardExpr .boolean
  | and : GuardExpr .boolean → GuardExpr .boolean → GuardExpr .boolean
  | or : GuardExpr .boolean → GuardExpr .boolean → GuardExpr .boolean

end Aurora.SourceBinding
