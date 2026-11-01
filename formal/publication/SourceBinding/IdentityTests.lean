import SourceBinding.IRIdentity
open Aurora.SourceBinding Aurora.Publication

-- Tiny kernel spelling fixtures, not concrete full-artifact acceptance.
example : namePrefix [] = "0_".toUTF8 := by decide
example : classSymbol ["m".toUTF8] ["C".toUTF8] = "__au_c_m1_1m_n0__d1C".toUTF8 := by decide
example : methodSymbol ["m".toUTF8] ["C".toUTF8] "f".toUTF8 = "__au_m_m1_1m_n1_1C_d1f".toUTF8 := by decide

namespace IdentityFixtures
-- Synthetic relation inputs only. These Tables are NOT claimed to pass D1/D2;
-- raw-source/artifact provenance and full structural admission are separate gates.
def ints (tag : String) (values : List Int) : Record := ⟨tag,values.map Field.integer,false⟩
def setInt (record : Record) (index : Nat) (value : Int) : Record :=
  { record with fields := record.fields.set index (.integer value) }
def setBlob (record : Record) (index : Nat) (value : ByteArray) : Record :=
  { record with fields := record.fields.set index (.bytes value) }
def moduleName : Aurora.SourceBinding.Name := ["m".toUTF8]
def classPath : Aurora.SourceBinding.Name := ["n".toUTF8,"C".toUTF8]
def memberName : ByteArray := "f".toUTF8
def cls := classSymbol moduleName classPath
def meth := methodSymbol moduleName classPath memberName
def nativeName := "__resource".toUTF8
def resourceName : Aurora.SourceBinding.Name := ["builtin".toUTF8,"Resource".toUTF8]
def sourceResource := sourceName resourceName

def scalarTypeRow (id kind : Int) : Record := ints "ir-type" [id,kind,0,0,0,0,0,0,0]
def resourceTypeRow : Record := ints "ir-type"
  [4,26,Int.ofNat (cls.size + meth.size),Int.ofNat nativeName.size,0,0,0,0,0]
def classRow : Record := ints "ir-class" [0,0,Int.ofNat cls.size,7,0,0,3,0,0,8,0]
def callableRow : Record := ints "ir-callable"
  [0,Int.ofNat cls.size,Int.ofNat meth.size,7,0,2,0,Int.ofNat cls.size,5,0,0,1,0,8,0,1]
def fieldRow (ordinal type : Int) : Record := ints "ir-field" [0,ordinal,type,0,1,0,1,0]
def catalog (id : Int) (native : ByteArray) : Record :=
  ⟨"ir-catalog-type",[.integer id,.integer (-1),.bytes native],false⟩
def resource (id catalogId : Int) (source : ByteArray) : Record :=
  ⟨"ir-resource",[.integer id,.integer catalogId,.integer 0,.bytes source],false⟩
def base : Tables := tables [
  ⟨"ir-name-bytes",[.bytes (cls ++ meth ++ nativeName)],false⟩,
  scalarTypeRow 0 1,scalarTypeRow 1 7,scalarTypeRow 2 7,scalarTypeRow 3 7,resourceTypeRow,
  classRow,callableRow,fieldRow 0 4,fieldRow 1 2,fieldRow 2 3,
  catalog 0 nativeName,resource 0 0 sourceResource]

def word : SourceType := .named ["u64".toUTF8]
def boolean : SourceType := .named ["bool".toUTF8]
def body : Body := ⟨⟨⟨0,0⟩,.punctuation⟩,[],⟨⟨0,0⟩,.punctuation⟩⟩
def function : Function := ⟨memberName,[⟨"p".toUTF8,word⟩],.ordinary,boolean,body⟩
def members : List Declaration := [.fieldDecl ⟨"authority".toUTF8,.named resourceName⟩,
  .fieldDecl ⟨"first".toUTF8,word⟩,.access "public",.functionDecl function,.fieldDecl ⟨"last".toUTF8,word⟩]
def accepts (t : Tables) (f : Function := function) (visible : Bool := true) : Bool :=
  decide (SourceIRIdentity t 0 moduleName classPath memberName members f visible)
def acceptsResource (t : Tables) : Bool := decide (ResourceTypeIdentity t resourceName 4)
def acceptsFields (t : Tables) : Bool := decide (OrderedFieldsIdentity t 0 (fields members))

def duplicateResource : Tables := { base with
  resources := #[resource 0 0 sourceResource,resource 1 1 sourceResource]
  catalogs := #[catalog 0 nativeName,catalog 1 "__other_resource".toUTF8] }

def useSite (ordinal : Int) : Tables := { base with
  -- Only isolated identity is under test: these rows are not a complete typed body.
  codes := #[ints "ir-code" [0,0,0,0,0,1,32,0,0,0,0,0,2]]
  operands := #[ints "ir-operand" [0,23,ordinal,0,0,0],ints "ir-operand" [1,12,2,0,0,0]] }

def cases : List (String × Bool × Bool) := [
  ("complete identity",accepts base,true),
  ("correct resource join",acceptsResource base,true),
  ("complete fields before and after method",acceptsFields base,true),
  ("wrong module",decide (SourceIRIdentity base 0 ["other".toUTF8] classPath memberName members function true),false),
  ("wrong class",decide (SourceIRIdentity base 0 moduleName ["n".toUTF8,"D".toUTF8] memberName members function true),false),
  ("wrong member",decide (SourceIRIdentity base 0 moduleName classPath "g".toUTF8 members function true),false),
  ("wrong receiver encoding",accepts { base with callables := #[setInt callableRow 6 1] },false),
  ("wrong method encoding",accepts { base with callables := #[setInt callableRow 1 (Int.ofNat cls.size + 1)] },false),
  ("duplicate callable spelling",accepts { base with callables := #[callableRow,callableRow] },false),
  ("duplicate class spelling",accepts { base with classes := #[classRow,classRow] },false),
  ("empty module",decide (SourceIRIdentity base 0 [] classPath memberName members function true),false),
  ("wrong source visibility",accepts base function false,false),
  ("wrong IR visibility",accepts { base with callables := #[setInt callableRow 8 1] },false),
  ("wrong receiver mode",accepts base { function with mode := .readonly },false),
  ("wrong formal count",accepts { base with callables := #[setInt callableRow 5 1] },false),
  ("wrong formal type",accepts { base with types := base.types.set! 1 (scalarTypeRow 1 1) },false),
  ("wrong result type",accepts { base with types := base.types.set! 0 (scalarTypeRow 0 7) },false),
  ("cv/ref type not normalized",accepts base { function with result := .constant boolean },false),
  ("missing later field",acceptsFields { base with fields := #[fieldRow 0 4,fieldRow 1 2] },false),
  ("extra field",acceptsFields { base with fields := base.fields.push (fieldRow 3 2) },false),
  ("wrong field ordinal",acceptsFields { base with fields := base.fields.set! 1 (fieldRow 2 2) },false),
  ("wrong field type",acceptsFields { base with fields := base.fields.set! 1 (fieldRow 1 0) },false),
  ("resource source mismatch",acceptsResource { base with resources := #[resource 0 0 "builtin::Other".toUTF8] },false),
  ("resource catalogue missing",acceptsResource { base with resources := #[resource 0 1 sourceResource] },false),
  ("resource native mismatch",acceptsResource { base with catalogs := #[catalog 0 "__other_resource".toUTF8] },false),
  ("resource nonopaque catalogue",acceptsResource { base with catalogs := #[setInt (catalog 0 nativeName) 1 7] },false),
  ("resource wrong type kind",acceptsResource { base with types := base.types.set! 4 (setInt resourceTypeRow 1 7) },false),
  ("resource nonplain tail",acceptsResource { base with types := base.types.set! 4 (setInt resourceTypeRow 4 1) },false),
  ("resource source not builtin",decide (ResourceTypeIdentity base ["user".toUTF8,"Resource".toUTF8] 4),false),
  ("resource duplicate source and native",acceptsResource { base with resources := #[resource 0 0 sourceResource,resource 1 0 sourceResource] },false),
  ("resource duplicate source different native",acceptsResource duplicateResource,false),
  ("ambiguous resource rejects whole identity",accepts duplicateResource,false),
  ("first same-typed field use",accepts (useSite 1),true),
  ("swapped same-typed field use STILL identity-only accepted",accepts (useSite 2),true)]

#eval do
  for (label, actual, expected) in cases do
    unless actual == expected do throw (IO.userError s!"identity fixture failed: {label}")
  let some visibility := visibilityAt memberName false members | throw (IO.userError "visibility selection failed")
  unless visibility.val == true do throw (IO.userError "source visibility incorrect")
  let some first := fieldAt members "first".toUTF8 | throw (IO.userError "field before method missing")
  let some last := fieldAt members "last".toUTF8 | throw (IO.userError "field after method missing")
  unless first.ordinal == 1 && last.ordinal == 2 do throw (IO.userError "source ordered-field fixture failed")
  IO.println s!"NATIVE isolated identity fixtures: {cases.length + 2} passed; no source-use semantics or artifact acceptance claimed"
end IdentityFixtures
