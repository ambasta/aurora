import SourceBinding
open Aurora.SourceBinding

def readSource (path : System.FilePath) (limit : Nat := 1048576) : IO ByteArray :=
  IO.FS.withFile path .read fun handle => do
    let mut bytes := ByteArray.empty
    for _ in [0:limit + 1] do
      let chunk ← handle.read (USize.ofNat (min 65536 (limit + 1 - bytes.size)))
      if chunk.size == 0 then return bytes
      bytes := bytes ++ chunk
      if bytes.size > limit then throw (IO.userError "source exceeds byte limit")
    throw (IO.userError "file-read budget exhausted")

def showName (name : Name) : String :=
  String.intercalate "." (name.map String.fromUTF8!)

def main (args : List String) : IO UInt32 := do
  if args.isEmpty then throw (IO.userError "usage: source-binding-probe SOURCE ...")
  let start ← IO.monoMsNow
  let mut total := 0
  for path in args do
    let bytes ← readSource path
    let some result := headerSource bytes | throw (IO.userError s!"lexical/header profile rejected: {path}")
    let h := result.declarations
    total := total + bytes.size
    IO.println s!"SOURCE-HEADER module={showName h.module.name} imports={h.imports.names.map showName} bytes={bytes.size} remaining_tokens={h.imports.rest.length}"
  IO.println s!"SOURCE-HEADER files={args.length} bytes={total} ms={(← IO.monoMsNow) - start}"
  IO.println "NATIVE receipt only. No complete declaration shell, selected AST, graph authenticity, IR correspondence, or concrete kernel acceptance."
  return 0
