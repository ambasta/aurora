namespace Aurora.SourceBinding

/-- Explicit syntax admission: legacy scopes remain closed to receiver effects,
    including skipped branches and dead suffixes. -/
inductive ScopeProfile where
  | legacy
  | receiverEffects
  deriving BEq, DecidableEq

end Aurora.SourceBinding
