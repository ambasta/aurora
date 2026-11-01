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
  let [path] := args | throw (IO.userError "usage: publication-probe ARTIFACT")
  let limits : Limits := {}
  let bytes ← readBounded path limits.fileBytes
  let start ← IO.monoMsNow
  let some framing := frame limits bytes | throw (IO.userError "framing rejected")
  let last :: _ := framing.reversed | throw (IO.userError "empty document")
  let some ending := decodeEnd bytes last | throw (IO.userError "final ir-end payload rejected")
  let elapsed := (← IO.monoMsNow) - start
  IO.println s!"FRAMING-ONLY bytes={bytes.size} lines={framing.reversed.length} trailer_bodies={ending.value} ms={elapsed}"
  IO.println "NOT full-schema acceptance, source binding, or a concrete kernel proof."
  return 0
