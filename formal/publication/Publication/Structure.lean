import Publication.Document
namespace Aurora.Publication

def Record.integer (row : Record) (index : Nat) : Int :=
  match row.fields[index]? with | some (.integer n) => n | _ => 0

def Record.blob (row : Record) (index : Nat) : ByteArray :=
  match row.fields[index]? with | some (.bytes b) => b | _ => ByteArray.empty

def rows (records : List Record) (tag : String) : Array Record :=
  (records.filter (fun r => !r.display && r.tag == tag)).toArray

structure Tables where
  all : List Record
  counts : Record
  names : ByteArray
  literals : ByteArray
  types : Array Record
  enums : Array Record
  classes : Array Record
  fields : Array Record
  leaves : Array Record
  callables : Array Record
  slots : Array Record
  catalogs : Array Record
  resources : Array Record
  methods : Array Record
  operands : Array Record
  bodies : Array Record
  codes : Array Record
  ends : Array Record

/-- Tables are a projection of the entire parsed document, never host excerpts. -/
def tables (records : List Record) : Tables :=
  let empty : Record := ⟨"", [], false⟩
  { all := records, counts := (rows records "ir-counts")[0]?.getD empty
    names := ((rows records "ir-name-bytes")[0]?.getD empty).blob 0
    literals := ((rows records "ir-literal-bytes")[0]?.getD empty).blob 0
    types := rows records "ir-type", enums := rows records "ir-enum"
    classes := rows records "ir-class", fields := rows records "ir-field"
    leaves := rows records "ir-leaf-offset", callables := rows records "ir-callable"
    slots := rows records "ir-slot", catalogs := rows records "ir-catalog-type"
    resources := rows records "ir-resource", methods := rows records "ir-resource-method"
    operands := rows records "ir-operand", bodies := rows records "ir-body"
    codes := rows records "ir-code", ends := rows records "ir-end-body" }

def Range (first count : Int) (bound : Nat) : Prop :=
  0 ≤ first ∧ 0 ≤ count ∧ first + count ≤ Int.ofNat bound
instance (first count : Int) (bound : Nat) : Decidable (Range first count bound) :=
  inferInstanceAs (Decidable (0 ≤ first ∧ 0 ≤ count ∧ first + count ≤ Int.ofNat bound))

def Index (index : Int) (bound : Nat) : Prop := 0 ≤ index ∧ index < Int.ofNat bound
instance (index : Int) (bound : Nat) : Decidable (Index index bound) :=
  inferInstanceAs (Decidable (0 ≤ index ∧ index < Int.ofNat bound))

def Dense (pool : Array Record) (field : Nat := 0) : Prop :=
  ∀ entry ∈ pool.toList.zipIdx, entry.1.integer field = Int.ofNat entry.2
instance (pool : Array Record) (field : Nat) : Decidable (Dense pool field) :=
  inferInstanceAs (Decidable (∀ entry ∈ pool.toList.zipIdx,
    entry.1.integer field = Int.ofNat entry.2))

def AllRows (pool : Array Record) (predicate : Record → Prop) : Prop :=
  ∀ row ∈ pool.toList, predicate row
instance (pool : Array Record) (predicate : Record → Prop) [DecidablePred predicate] :
    Decidable (AllRows pool predicate) :=
  inferInstanceAs (Decidable (∀ row ∈ pool.toList, predicate row))

def nameRange (t : Tables) (row : Record) (first : Nat) : Prop :=
  Range (row.integer first) (row.integer (first + 1)) t.names.size
instance (t : Tables) (row : Record) (first : Nat) : Decidable (nameRange t row first) :=
  inferInstanceAs (Decidable (Range (row.integer first) (row.integer (first + 1)) t.names.size))

def typeRanges (t : Tables) (r : Record) : Prop := nameRange t r 2
instance (t : Tables) (r : Record) : Decidable (typeRanges t r) := inferInstanceAs (Decidable (nameRange t r 2))

def classRanges (t : Tables) (r : Record) : Prop :=
  nameRange t r 1 ∧ Range (r.integer 4) (r.integer 5) t.types.size ∧
  0 ≤ r.integer 6 ∧ 0 ≤ r.integer 7 ∧ 0 ≤ r.integer 8 ∧ 0 < r.integer 9 ∧ 0 ≤ r.integer 10
instance (t : Tables) (r : Record) : Decidable (classRanges t r) := by unfold classRanges; infer_instance

def callableRanges (t : Tables) (r : Record) : Prop :=
  nameRange t r 1 ∧ nameRange t r 6 ∧ Range (r.integer 4) (r.integer 5) t.types.size ∧
  0 < r.integer 5 ∧ 0 ≤ r.integer 9 ∧ 0 ≤ r.integer 13 ∧ Range (r.integer 14) (r.integer 15) t.slots.size
instance (t : Tables) (r : Record) : Decidable (callableRanges t r) := by unfold callableRanges; infer_instance

def slotRanges (t : Tables) (r : Record) : Prop := Index (r.integer 3) t.types.size
instance (t : Tables) (r : Record) : Decidable (slotRanges t r) := by unfold slotRanges; infer_instance

/-- Raw operand payloads are preserved globally. Their role-dependent references
    are checked only where a supported selected instruction consumes them. -/
def codeRanges (t : Tables) (r : Record) : Prop :=
  Index (r.integer 0) t.callables.size ∧ 0 ≤ r.integer 1 ∧
  0 < r.integer 2 ∧ r.integer 2 ≤ t.counts.integer 6 ∧
  Range (r.integer 11) (r.integer 12) t.operands.size
instance (t : Tables) (r : Record) : Decidable (codeRanges t r) := by unfold codeRanges; infer_instance

def atRow (pool : Array Record) (index : Int) : Record :=
  pool[index.toNat]?.getD ⟨"", [], false⟩

def fieldRanges (t : Tables) (r : Record) : Prop :=
  Index (r.integer 0) t.classes.size ∧ Index (r.integer 2) t.types.size ∧
  Index (r.integer 1) ((atRow t.classes (r.integer 0)).integer 6).toNat ∧
  Range (r.integer 3) (r.integer 4) ((atRow t.classes (r.integer 0)).integer 7).toNat ∧
  (r.integer 5 = 0 ∨ r.integer 5 = 1) ∧ 0 ≤ r.integer 6 ∧
  0 ≤ r.integer 7 ∧ r.integer 7 ≤ (atRow t.classes (r.integer 0)).integer 8
instance (t : Tables) (r : Record) : Decidable (fieldRanges t r) := by unfold fieldRanges; infer_instance

def leafRanges (t : Tables) (r : Record) : Prop :=
  Index (r.integer 0) t.classes.size ∧
  Index (r.integer 1) ((atRow t.classes (r.integer 0)).integer 7).toNat ∧
  0 ≤ r.integer 2 ∧ r.integer 2 ≤ (atRow t.classes (r.integer 0)).integer 8
instance (t : Tables) (r : Record) : Decidable (leafRanges t r) := by unfold leafRanges; infer_instance

def group (pool : Array Record) (id : Int) : Array Record := pool.filter (fun r => r.integer 0 == id)

def classComplete (t : Tables) (r : Record) : Prop :=
  let fs := group t.fields (r.integer 0)
  let ls := group t.leaves (r.integer 0)
  Int.ofNat fs.size = r.integer 6 ∧ Dense fs 1 ∧ Int.ofNat ls.size = r.integer 7 ∧ Dense ls 1
instance (t : Tables) (r : Record) : Decidable (classComplete t r) := by unfold classComplete; infer_instance

/-- Canonical source method names in this publication profile are nonempty ASCII
    identifiers. These are exact published bytes, not decoded native linkages. -/
def SourceNameStart (b : Nat) : Prop := (65 ≤ b ∧ b ≤ 90) ∨ (97 ≤ b ∧ b ≤ 122) ∨ b = 95
def SourceNameByte (b : Nat) : Prop := SourceNameStart b ∨ (48 ≤ b ∧ b ≤ 57)
instance (b : Nat) : Decidable (SourceNameStart b) := by unfold SourceNameStart; infer_instance
instance (b : Nat) : Decidable (SourceNameByte b) := by unfold SourceNameByte; infer_instance

def SourceMethodName (name : ByteArray) : Prop :=
  0 < name.size ∧ SourceNameStart (byte name 0) ∧ ∀ index, index < name.size → SourceNameByte (byte name index)
instance (name : ByteArray) : Decidable (SourceMethodName name) := by unfold SourceMethodName; infer_instance

def resourceMethodNames (t : Tables) (kind : Int) : List ByteArray :=
  (group t.methods kind).toList.map (fun method => method.blob 9)

theorem source_method_name_nonempty (name : ByteArray) (valid : SourceMethodName name) : 0 < name.size := valid.1

/-- Uniqueness is local to a resource family; different resources may both have
    a method named finish. Ordinal membership remains independently checked. -/
theorem resource_method_name_unique (t : Tables) (kind : Int)
    (unique : (resourceMethodNames t kind).Nodup) (i j : Nat) (name : ByteArray)
    (first : (resourceMethodNames t kind)[i]? = some name)
    (second : (resourceMethodNames t kind)[j]? = some name) : i = j := by
  have bound : i < (resourceMethodNames t kind).length := by
    by_cases inside : i < (resourceMethodNames t kind).length
    · exact inside
    · have absent : (resourceMethodNames t kind)[i]? = none := List.getElem?_eq_none (Nat.le_of_not_gt inside)
      rw [absent] at first
      cases first
  exact List.getElem?_inj bound unique (first.trans second.symm)

def resourceRanges (t : Tables) (r : Record) : Prop :=
  Index (r.integer 1) t.catalogs.size ∧ 0 ≤ r.integer 2 ∧
  Int.ofNat (group t.methods (r.integer 0)).size = r.integer 2 ∧ Dense (group t.methods (r.integer 0)) 1 ∧
  (resourceMethodNames t (r.integer 0)).Nodup
instance (t : Tables) (r : Record) : Decidable (resourceRanges t r) := by unfold resourceRanges; infer_instance

def methodRanges (t : Tables) (r : Record) : Prop :=
  Index (r.integer 0) t.resources.size ∧
  Index (r.integer 1) ((atRow t.resources (r.integer 0)).integer 2).toNat ∧
  Index (r.integer 2) t.catalogs.size ∧
  r.integer 3 = (atRow t.catalogs (r.integer 2)).integer 1 ∧
  0 ≤ r.integer 4 ∧
  (r.integer 4 = 0 ∨ (Index (r.integer 5) t.catalogs.size ∧
    r.integer 6 = (atRow t.catalogs (r.integer 5)).integer 1)) ∧ SourceMethodName (r.blob 9)
instance (t : Tables) (r : Record) : Decidable (methodRanges t r) := by unfold methodRanges; infer_instance

/-- Adjacent strict increase is a deliberately restricted linear uniqueness
    check. Gaps are accepted. Reordered original IDs are not admitted yet. -/
def Increasing : List Int → Prop
  | [] | [_] => True
  | a :: b :: rest => a < b ∧ Increasing (b :: rest)
instance increasingDecidable : (values : List Int) → Decidable (Increasing values)
  | [] | [_] => isTrue trivial
  | a :: b :: rest =>
    letI := increasingDecidable (b :: rest)
    inferInstanceAs (Decidable (a < b ∧ Increasing (b :: rest)))

theorem Increasing.pairwise {values : List Int} (ordered : Increasing values) :
    values.Pairwise (· < ·) := by
  induction values with
  | nil => exact .nil
  | cons a tail ih =>
    cases tail with
    | nil => exact .cons (by simp) .nil
    | cons b rest =>
      have steps : a < b ∧ Increasing (b :: rest) := ordered
      have following := ih steps.2
      apply List.Pairwise.cons ?_ following
      intro value member
      rcases List.mem_cons.mp member with equal | later
      · simpa [equal] using steps.1
      · exact Int.lt_trans steps.1 ((List.pairwise_cons.mp following).1 value later)

/-- Canonical wire section order; class/field/leaf and resource/method subgroups
    are finite keyed facts, while body nesting is checked separately. -/
def phase : String → Nat
  | "aurora-published-ir" => 0 | "ir-counts" => 1 | "ir-name-bytes" => 2
  | "ir-type" => 3 | "ir-enum" => 4
  | "ir-class" | "ir-field" | "ir-leaf-offset" => 5
  | "ir-callable" => 6 | "ir-slot" => 7 | "ir-catalog-type" => 8
  | "ir-resource" | "ir-resource-method" => 9
  | "ir-operand" => 10 | "ir-literal-bytes" => 11
  | "ir-body" | "ir-code" | "ir-end-body" => 12 | "ir-end" => 13
  | _ => 14

def Nondecreasing : List Nat → Prop
  | [] | [_] => True
  | a :: b :: rest => a ≤ b ∧ Nondecreasing (b :: rest)
instance nondecreasingDecidable : (values : List Nat) → Decidable (Nondecreasing values)
  | [] | [_] => isTrue trivial
  | a :: b :: rest =>
    letI := nondecreasingDecidable (b :: rest)
    inferInstanceAs (Decidable (a ≤ b ∧ Nondecreasing (b :: rest)))

def envelope (t : Tables) : Prop :=
  (t.all.head?.map (·.tag)) = some "aurora-published-ir" ∧
  (t.all.getLast?.map (·.tag)) = some "ir-end" ∧
  (rows t.all "aurora-published-ir").size = 1 ∧ (rows t.all "ir-counts").size = 1 ∧
  (rows t.all "ir-name-bytes").size = 1 ∧ (rows t.all "ir-literal-bytes").size = 1 ∧
  (rows t.all "ir-end").size = 1 ∧
  Nondecreasing ((t.all.filter (fun r => !r.display)).map (fun r => phase r.tag))
instance (t : Tables) : Decidable (envelope t) := by unfold envelope; infer_instance

def poolCounts (t : Tables) : Prop :=
  t.counts.integer 0 = Int.ofNat t.names.size ∧ t.counts.integer 1 = Int.ofNat t.types.size ∧
  t.counts.integer 2 = Int.ofNat t.classes.size ∧ t.counts.integer 3 = Int.ofNat t.enums.size ∧
  t.counts.integer 4 = Int.ofNat t.callables.size ∧ t.counts.integer 5 = Int.ofNat t.slots.size ∧
  0 ≤ t.counts.integer 6 ∧ t.counts.integer 6 ≤ 262144 ∧
  t.counts.integer 7 = Int.ofNat t.operands.size ∧ t.counts.integer 8 = Int.ofNat t.literals.size ∧
  t.counts.integer 9 = Int.ofNat t.resources.size ∧ t.counts.integer 10 = Int.ofNat t.catalogs.size ∧
  t.types.size ≤ 65536 ∧ t.operands.size ≤ 131072 ∧ t.callables.size ≤ 4096 ∧ t.codes.size ≤ 65536
instance (t : Tables) : Decidable (poolCounts t) := by unfold poolCounts; infer_instance

def poolIdentities (t : Tables) : Prop :=
  Dense t.types ∧ Dense t.classes ∧ Dense t.enums ∧ Dense t.callables ∧
  Dense t.slots ∧ Dense t.catalogs ∧ Dense t.resources ∧ Dense t.operands ∧
  Increasing (t.codes.toList.map (fun r => r.integer 2)) ∧
  Increasing (t.bodies.toList.map (fun r => r.integer 0))
instance (t : Tables) : Decidable (poolIdentities t) := by unfold poolIdentities; infer_instance

def poolReferences (t : Tables) : Prop :=
  AllRows t.types (typeRanges t) ∧ AllRows t.enums (fun r => nameRange t r 1) ∧
  AllRows t.classes (classRanges t) ∧ AllRows t.classes (classComplete t) ∧
  AllRows t.fields (fieldRanges t) ∧ AllRows t.leaves (leafRanges t) ∧
  AllRows t.callables (callableRanges t) ∧ AllRows t.slots (slotRanges t) ∧
  AllRows t.resources (resourceRanges t) ∧ AllRows t.methods (methodRanges t) ∧
  AllRows t.codes (codeRanges t)
instance (t : Tables) : Decidable (poolReferences t) := by unfold poolReferences; infer_instance

end Aurora.Publication
