import SourceBinding.EntryBinding
open Aurora.SourceBinding

def formals : List Formal := [⟨"a".toUTF8,guardSourceType .word⟩,⟨"b".toUTF8,guardSourceType .boolean⟩]
def good : Program
  | 0 => some (.bind .word 0 8)
  | 1 => some (.bind .boolean 1 16)
  | _ => none
#eval do
  unless (checkEntry good formals).isSome do throw (IO.userError "good rejected")
  for bad in ([fun n => if n == 1 then some (.bind .boolean 0 16) else good n,
              fun n => if n == 1 then some (.bind .boolean 1 8) else good n,
              fun n => if n == 1 then some (.bind .word 1 16) else good n,
              fun n => if n == 0 then some (.bind .word 0 0) else good n,
              fun n => if n == 0 then some .push else good n] : List Program) do
    unless (checkEntry bad formals).isNone do throw (IO.userError "bad accepted")
  IO.println "entry native fixtures6 passed"
