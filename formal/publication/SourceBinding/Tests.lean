import SourceBinding
open Aurora.SourceBinding

-- Tiny kernel fixtures only; whole header/graph examples run natively.
example : (lex "".toUTF8 64 8).isSome = true := by decide
example : (lex "a".toUTF8 64 8).isSome = true := by decide
example : (lex "#".toUTF8 64 8).isSome = false := by decide
example : (lex "\"".toUTF8 64 8).isSome = false := by decide
example : (lex "/*".toUTF8 64 8).isSome = false := by decide
example : (lex "//".toUTF8 64 8).isSome = true := by decide
example : (lex "abc".toUTF8 2).isSome = false := by decide
example : Pair 58 58 := by decide
example : ¬ Pair 58 32 := by decide
example : Space 13 := by decide
example : ¬ CommentByte 10 := by decide
example : ¬ Letter 48 := by decide
