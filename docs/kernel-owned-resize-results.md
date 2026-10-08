# Bounded raw kernel owner resize: focused results (2026-10-08)

Fresh focused adapter, generated-host, closed-link/image, independent pre-guest
review and bounded emulator checks qualify the raw OwnedBytes replacement path.
This is not complete ByteBuffer graph admission or a general kernel allocator.
The [contract](kernel-owned-resize.md) states the unchanged authority and bounds.

## Source and mechanism

The candidate starts from accepted PR83 commit
`ec8cfe43d3cc31a4eb71ff4a892bb71907d1a974`, tree
`79f884fd4414206e551419752cc2448342c51411`. All 861 base file Git blob identities
and executable modes were independently compared against a fresh untruncated
remote tree. The compiler implementation is unchanged; the explicitly reused
accepted compiler SHA256 is
`512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`.
Current-main reconciliation at publication is recorded separately.

Replacement uses one existing private preparing record, final committed payload
quota and actual fragmented PageLease ownership. Four metadata records, sixteen
pages, the 32-byte private owner ABI and the 3,072-byte metadata cap are unchanged.
No public allocation helper is called to stage a replacement. Same-size validates
before returning without a slot or fresh identity; changed-size successes copy
the prefix, zero extensions, scrub/release old pages, and commit a fresh identity.
Every recoverable failure restores the inactive staging record and preserves old
owner bytes and committed accounting. A terminal scrub/lease failure retains both
transaction records, including a zero-page peer, and faults the grant permanently.

## Focused gates

- Real kernel adapter and PhysicalPages: ordinary and fatal ASan/UBSan runs each
  pass 2,719,273 checks and 522 exact isolated faults. The independent test author
  adds 198 resize retention scenarios, including empty transaction peers, every
  partial rollback/readback position, foreign holders and unrelated live owners.
  Full-page hygiene, final quota, metadata/physical exhaustion, descriptor
  adversaries, final production-width identity and counter ceilings are covered.
- Exact generated Aurora fixture: seven host modes each pass 41 checks, normally
  and under fatal host sanitizers. Nonempty-to-empty readonly-length poisoning
  still rejects with its exact diagnostic and exit. The final selector fixture
  was recompiled/replayed after the earlier opcode-admission failure.
- Closed object admission: exactly six real imports, one positive and 30 negative
  controls. Actual ELF links resolve resize and reject an unknown helper and an
  independently generated mixed graph, without stubs or broadened definitions.
- Linked-stack controls: seven positives and 49 negative controls. Transcript
  controls: nine positives and 203 negatives. Both ordinary and optimized Python
  runs pass. Exact PE/PIC admission rejects 14 mutated images per selected build.
- Independent source review accepts private staging, retention and generated
  fixture accounting. Independent exact image/stack review reproduces
  2,592 +512 fault reserve =3,104 <=15,360 of the unchanged 16,384-byte stack.
  The decoded synchronous fault path is 159 bytes. Generated expression/cleanup
  pushes, exact resource/span records, C++ stack records/direct calls and the
  bounded four-level verifier are included. No historical PR80 bound is reused.
- Supervised owned-bytes, runtime-span and normal build-only admissions pass;
  runtime-span additionally verifies two independently linked high-VA RX images.
  The supervised final owned-bytes image is byte-identical to the independently
  reviewed image; all source/artifact hashes are retained.

## Bounded emulator evidence

The actual public owned-bytes guest passes original lengths and readonly spans,
then contiguous/fragmented replacement, same-size/invalid requests, grow/shrink/
regrow/zero transitions, full-pool refusal and partial-acquisition rollback.
Every required copied prefix and new zero byte is checked in Aurora. Trusted
readback checks complete released pages including padding, untouched neighbor
poison and the exact addresses/identities of independently held leases. Final
counters are 23 allocations and 23 releases, zero logical/live/held/retained use,
zero pool use and a closed Region. The actual guest-built linked-stack receipt
is byte-identical to the independently admitted receipt.

Actual runtime-span and normal regression guests also pass. After EVERY guest,
five normal-image artifact hashes equal the separately admitted normal image.
The public launchers use the verified original TCG clock, q35/qemu64, one CPU and
128 MiB; command receipts are combined with actual serial transcripts and exit
verification, never treated as guest success by themselves.

## Preserved corrections and limits

The preliminary adapter pass overlapped a test-author relocation of two helper
calls; it is preserved as uncredited concurrent-source evidence. Fresh ordinary
and fatal sanitizer replays on the final test source supersede it. Their source,
script, binary and log bindings were recorded retrospectively and independently
checked; later generated-host/build/guest supervisors record pre/post source hashes.

The first image build correctly rejected an unmodeled generated `setge` opcode.
The original image/log is preserved. The selector comparison was rewritten to an
equivalent signed comparison that uses already modeled instructions; the stack
verifier instruction allowlist was not widened. Fresh exact host/image/stack gates
qualify the corrected source. Python PASS-text line-length/formatting failures
are also retained with successful corrected style and real-link replays.

Host sanitizers instrument C++ only; generated Aurora assembly is uninstrumented
and leak checking is excluded. Bad-lease and unexpected post-preflight release
failures are source-reviewed, not directly injected; ordinary release failure is
excluded by the stated single-CPU nonreentrant lifetime contract and full preflight.
Scrub/readback terminal paths are injected and observed without unwinding.
No full native aggregate, full emulator matrix, ByteBuffer class graph, user owner
allocation, DMA/IOMMU/device activation, physical-machine change, self-hosting,
performance result or general memory-safety proof is claimed.
