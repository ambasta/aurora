import Publication.Bytes
namespace Aurora.Publication

/-- A token consists of printable non-space bytes. Empty final tokens allow
    the format's empty hex pools; record grammars decide where they are legal. -/
inductive WordRun (input : ByteArray) : Nat → Nat → Prop
  | empty (start) : WordRun input start start
  | next : WordRun input start stop → stop < input.size →
      33 ≤ byte input stop → byte input stop ≤ 126 → WordRun input start (stop + 1)

inductive Words (input : ByteArray) : Nat → Nat → List Span → Prop
  | last : WordRun input start stop → Words input start stop [⟨start, stop⟩]
  | next : WordRun input start middle → middle < input.size → byte input middle = 32 →
      Words input (middle + 1) stop rest → Words input start stop (⟨start, middle⟩ :: rest)

structure WordEnd (input : ByteArray) (start stop : Nat) where
  finish : Nat
  run : WordRun input start finish
  ending : finish = stop ∨ (finish < stop ∧ finish < input.size ∧ byte input finish = 32)

def wordLoop (input : ByteArray) (start stop : Nat) :
    (fuel pos : Nat) → WordRun input start pos → Option (WordEnd input start stop)
  | fuel, pos, prior =>
    if done : pos = stop then some ⟨pos, prior, Or.inl done⟩
    else match fuel with
      | 0 => none
      | fuel + 1 =>
        if before : pos < stop then
          if bound : pos < input.size then
            if space : byte input pos = 32 then
              some ⟨pos, prior, Or.inr ⟨before, bound, space⟩⟩
            else if lo : 33 ≤ byte input pos then
              if hi : byte input pos ≤ 126 then
                wordLoop input start stop fuel (pos + 1) (.next prior bound lo hi)
              else none
            else none
          else none
        else none

structure Tokenization (input : ByteArray) (start stop : Nat) where
  tokens : List Span
  grammar : Words input start stop tokens

/-- Field-count and per-token byte limits reject, rather than truncating. -/
def tokensLoop (input : ByteArray) (tokenBytes : Nat) :
    (fuel start stop : Nat) → Option (Tokenization input start stop)
  | 0, _, _ => none
  | fuel + 1, start, stop =>
    match wordLoop input start stop tokenBytes start (.empty start) with
    | none => none
    | some word =>
      if final : word.finish = stop then
        some ⟨[⟨start, stop⟩], .last (final ▸ word.run)⟩
      else
        have separated := word.ending.resolve_left final
        match tokensLoop input tokenBytes fuel (word.finish + 1) stop with
        | none => none
        | some rest => some ⟨⟨start, word.finish⟩ :: rest.tokens,
            .next word.run separated.2.1 separated.2.2 rest.grammar⟩

theorem tokens_sound (input : ByteArray) (tokenBytes fuel start stop : Nat)
    (result : Tokenization input start stop)
    (_accepted : tokensLoop input tokenBytes fuel start stop = some result) :
    Words input start stop result.tokens := result.grammar

end Aurora.Publication
