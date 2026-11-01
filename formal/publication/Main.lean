import Publication
open Aurora.Publication

/-- Bounded file acquisition. File IO and native execution are receipt trust, not
    premises discharged by the generic kernel-checked grammar theorems. -/
def readBounded (path : System.FilePath) (limit : Nat) : IO ByteArray :=
  IO.FS.withFile path .read fun handle => do
    let mut bytes := ByteArray.empty
    for _ in [0:limit + 1] do
      let chunk ← handle.read (USize.ofNat (min 65536 (limit + 1 - bytes.size)))
      if chunk.size == 0 then return bytes
      bytes := bytes ++ chunk
      if bytes.size > limit then throw (IO.userError "input exceeds byte limit")
    throw (IO.userError "file-read budget exhausted")

def main (args : List String) : IO UInt32 := do
  let path :: requested := args | throw (IO.userError "usage: publication-probe ARTIFACT [ROOT_SYMBOL ...]")
  let limits : Limits := {}
  let bytes ← readBounded path limits.fileBytes
  let start ← IO.monoMsNow
  let some artifact := decodeArtifact limits bytes | throw (IO.userError "artifact structure rejected")
  let wire := artifact.document
  let t := tables wire.reversed.reverse
  if !requested.isEmpty then
    let roots := requested.map String.toUTF8
    let some slice := selectSlice t roots | throw (IO.userError "selected closure rejected")
    IO.println s!"CLOSED-SLICE profile=scalar-receiver-v1 callables={slice.selected} instructions={(slice.selected.map (fun id => (functionCode t id).size)).foldl (· + ·) 0} external_occurrences={(externalOccurrences t slice.selected).length}"
  let elapsed := (← IO.monoMsNow) - start
  IO.println s!"ARTIFACT-STRUCTURE records={wire.reversed.length} bytes={bytes.size} retained_bodies={t.bodies.size} ms={elapsed}"
  IO.println "NO value/effect safety, source correspondence, backend proof, or concrete kernel acceptance theorem."
  return 0
