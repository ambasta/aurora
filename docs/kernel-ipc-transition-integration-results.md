# IPC transition integration results

The bounded IPC checkpoint has completed independent review and its planned
integration gates. The six Mailbox operations—submit, receive, reply, consume,
cancel and recycle—use copied decisions from safe Aurora. Trusted C++ retains
participant identity, capability checks, transaction/generation binding, payload
storage and atomic commit. A refused or malformed decision cannot mutate that
Mailbox call's records or advance its generation. Composite dispatcher operations
retain an already committed prefix and fail on a later refusal; they do not
promise rollback. See the [contract](kernel-ipc-transition-contract.md).

## Two tested source checkpoints

The complete qualification of [PR28 checkpoint 851f288](https://github.com/ambasta/aurora/commit/851f288567b1e97d830089759052e17f5f591980)
used 608 files with manifest SHA256
`3522f7b87b7e3f0048581724a5ff4a19310612ee7c1f7474ad1376c04b3c6148`.
It includes the current scanner, developer workflow, memory assembly, PE-linker
selection and firmware helper. The following are separately reviewed gates:

| Gate on that source | Result and boundary |
|---|---|
| Full developer native workflow | `make --jobs=1 test` built one compiler and completed the full root graph; matching product receipts and retained corpora passed independent review. |
| Full prebuilt acceptance workflow | `make --jobs=1 test-acceptance` used an independently selected immutable compiler, explicit expected digest and zero bootstrap builds; the full graph and all six native consumers passed. |
| Fatal hosted sanitizers | Five existing IPC, dispatch, disposal and budget entrypoints passed with fatal ASan/UBSan settings. Eight retained binaries contain meaningful instrumentation; the tiny copy wrapper has initialization hooks only. |
| Fresh image/static review | 57 construction/preservation commands supplied 28 actual image variants, including both input guards. Independent review covered bounded ABI, mapping, output guards, memory helpers, both caller stacks and conditional timer arithmetic. |
| Full runtime matrix | 177 production modes, three BIOS capacity probes and two additional actual normal restoration boots passed. No failed prefix was credited. |
| Split firmware integration | Normal / budget-smp / normal produced raw statuses 33 / 35 / 33 with three distinct private VARS copies, unchanged templates and byte-identical restored normal artifacts. |

The selected compiler SHA256 is
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
Ordinary developer builds still require no historical compiler pin.

The subsequent [PR35](https://github.com/ambasta/aurora/pull/35) composition preserves
main `4c9af2cf0a30337a8c39a6b16e0a9164c23ced1f` and its terminal-stdin correction.
Its tested 608-file manifest is
`583439c752ef69dd8e57fb55d9759fd564399c861e1855807853ec6db8bc51e3`,
Git tree `c2de4c69bf2be6ba90dfe1d135be31ae0b7856a6`.
Independent composition review verified all 201 primary build inputs unchanged,
including all compiler, kernel and image-builder inputs. Nine paths differ from
851f288: stdin detachment, its synthetic test, necessary runner identity pins and
documentation. Strict validators and the complete mode/clock map are unchanged.
The later publication changes only four documentation files from this tested
composition; its new tree is not a claim of another test run.

## PR35 targeted qualification

Two shell syntax checks and 108 ordinary/optimized clock, developer-command and
firmware method executions passed. These use synthetic tools and earn no guest
credit. The real follow-on run completed **16 terminal-origin boots**:

- BIOS normal and fault; UEFI normal, budget, budget-root and user-retire-pending.
- Stock-firmware BAR refusal; clean-firmware BAR read/revoked and IVRS read/revoked.
- Three CPU-observed BIOS capacity probes, then actual BIOS and UEFI normal restores.

Original supervisor 19406 exited 0. Fourteen private controlling-terminal wrappers
contain the 16 guest executions; the capacity wrapper accounts for three boots.
All raw statuses and complete argument vectors match the reviewed plan. Three
selected timer cases use fixed instruction clock and thirteen retain the original
clock. Terminal, foreground-group and termios records agree before/after each
wrapper, with positive owned-process cleanup. QEMU's detached stdin is established
by pinned source and actual terminal-origin execution, not a direct QEMU-fd audit.

Independent corpus review read five complete device traces, reconstructed serial
and debugcon output, and checked bounded BAR/IVRS reads and revocation failures.
The retirement case drains the old owner before revoke/rebind, preserves its peer,
then completes a fresh transaction. Both normal restoration serial streams and
selected images match their initial counterparts. All 204 sealed files and 28
directories are accounted for. This targeted qualification composes with the
earlier source's full gates; it is not a second full native or 182-boot run.

## Runtime behavior and limits

The full matrix observed normal IPC value 42 and dispatcher values 42/73/42 in
client order 0,1,0. Cancellation, service restart, disposal and rebinding passed.
Four real request/cancellation input/output corruption modes failed before their
rejected commit. The 177-mode clock contract remains 51 fixed-instruction modes
and 126 original-clock modes, with unchanged 128/3 budgets and strict validators.
QEMU was the pinned 10.0.13 runtime; common UEFI routes used the exact combined
OVMF image, while declared BAR/IVRS and focused split routes used their separately
qualified firmware. No substitute firmware was synthesized.

The original wall-clock user-retire-pending failure remains preserved and
unexplained stress evidence. Fixed instruction-clock success does not explain or
repair it. The first targeted terminal harness attempt failed during private-PTY
setup before launcher execution; its failure and qualified source-based cleanup
assessment remain preserved. A reviewed Linux-UAPI binding correction and one
bounded private-PTY control preceded the successful guest run.

Static stack findings apply to fixed images, single-BSP execution and stated
interrupt/drain assumptions. The exact private timer-stop leaf exceptions do not
relax Aurora or opaque external ABI alignment. There is no general NMI or
whole-kernel stack theorem. Sanitizers exclude generated Aurora assembly, the
release compiler and leak detection. The hosted service-budget model does not
exercise IPC or round-robin restart; actual guest evidence supplies that separate
behavioral coverage. Storage accounting and snapshot reservations are sampled
engineering bounds, not hard filesystem quotas. These results establish neither
physical AMD support, general DMA isolation nor full-kernel memory safety.

## Evidence and history

Raw logs, binaries and independent audits are retained privately. The final
targeted terminal report SHA256 is
`8d6293954e486cf2b1c483e2a3cc0ea2e41ab7baa53f58d387db5f2b88927032`;
the corpus report is
`06ba1929127c7d3f4bb11dac53f21c7913cc14973c3dbc3ea68fd305ec0622cb`.
Their acceptance remains scoped as described above.

The verified raw archive is Library `libfile_f49ca43a552081919caa5cd9b91c4b5f`
version 0, SHA256 `55a03bf0f957e910b4af90197a4b8d4575a3801f1851790d245632b8ae06ccb5`
(4,176,962 bytes; 1,066 members). The final audit archive is
`libfile_481f105a1ebc8191a441caec387805b8` version 0, SHA256
`199e856ee7f8e601dc382b4ed584bbf23efc807d3b1ab47bb76899fac9095c3f`
(31,034 bytes; 18 members). Both were read back and checked member-by-member.
The raw packing command's numeric exit became unavailable after an interruption;
its complete archive and final receipt were verified independently. The guest
supervisor's exit 0 was directly observed before that interruption.

Earlier snapshots, original failures and interrupted review history remain in
the [851f288 result record](https://github.com/ambasta/aurora/blob/851f288567b1e97d830089759052e17f5f591980/docs/kernel-ipc-transition-integration-results.md)
and its [historical receipt index](https://github.com/ambasta/aurora/blob/851f288567b1e97d830089759052e17f5f591980/docs/evidence/ipc-transition-policy/receipts.json).
Their old pending/blocked statements describe those dates, not the completed
checkpoint above. Retired milestone archives remain in Git history.
