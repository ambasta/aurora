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
  let root :: module :: classPath :: member :: paths := args |
    throw (IO.userError "usage: source-binding-probe ROOT_MODULE SELECT_MODULE CLASS_PATH MEMBER SOURCE ...")
  if paths.isEmpty then throw (IO.userError "no source files")
  let start ← IO.monoMsNow
  let mut total := 0
  let mut files : List SourceFile := []
  for path in paths do
    let bytes ← readSource path
    let some result := namedSource bytes | throw (IO.userError s!"source shell/bindings rejected: {path}")
    let h := result.source.header.declarations
    total := total + bytes.size
    files := files ++ [⟨bytes,result⟩]
    IO.println s!"SOURCE-SHELL module={showName h.module.name} imports={h.imports.names.map showName} bytes={bytes.size} top_declarations={result.source.shell.declarations.length}"
  let rootName := (root.splitOn ".").map String.toUTF8
  let some checked := checkedSelection files rootName ((module.splitOn ".").map String.toUTF8)
    ((classPath.splitOn "::").map String.toUTF8) member.toUTF8 |
    throw (IO.userError "graph or selected member not bound")
  let selected := checked.selected
  let method := selected.method.function
  let declared := fields selected.classDecl.members
  IO.println s!"SOURCE-MEMBER class={classPath} member={member} fields={declared.length} formals={method.formals.length} body_begin={method.body.opening.span.first} body_end={method.body.closing.span.last} body_tokens={method.body.tokens.length}"
  for (field, index) in declared.zipIdx do
    IO.println s!"SOURCE-FIELD ordinal={index} name={String.fromUTF8! field.name}"
  IO.println s!"SOURCE-GRAPH files={files.length} bytes={total} ms={(← IO.monoMsNow) - start}"
  IO.println "NATIVE receipt only. Shell/opaque-body binding, not full Aurora admission, typed method AST, IR correspondence, capture authenticity or concrete kernel acceptance."
  return 0
