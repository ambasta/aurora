"""Declarative per-profile policy for kernel_image_check.py and kernel_stack_check.py.

A Python literal (read with ast.literal_eval, never executed). Every rule whose
`profiles` globs match a profile id (platform/mode) applies; lists merge.
  imports    - the complete set of symbols each generated Aurora object may import
  imports:STEM - further imports allowed only for the generated object STEM.o
  import_free - generated object stems which must have no undefined imports
  reachable  - Aurora policy entry points the supervisor must actually call
  forbidden  - symbol globs the linked kernel image must not define
  callbacks  - reviewed indirect calls, "CALLER=CALLEE" C++ signature fragments;
               an empty CALLEE is an intentional call into non-code (a fault fixture)
  user_traps - vectors eligible from user mode on TSS.RSP0; kernel_traps may overlap
  async_entries / ist_traps - actual hardware entry roots / separate double-fault stack
  stack_continuations / stack_guards - semantic physical stack/recursion authorities
  effect_scopes - closed synchronous lifecycle effects and disjoint source entries
"""

RULES = [
    {
        "profiles": ["*"],
        # Semantic stack authorities, not instruction identities. The checker
        # verifies exact storage operands, save depths, frame consumption and
        # the matching leave path; all other nonlocal RSP writes reject.
        "async_entries": [
            "aurora_exception_*",
            "aurora_timer_interrupt",
            "aurora_program_return",
            "aurora_program_call",
            "aurora_process_call",
            "aurora_user_return",
            "aurora_unexpected_interrupt",
            "uefi_process_exception_*",
            "uefi_process_timer_interrupt",
            "uefi_process_process_call",
            "uefi_process_unexpected_interrupt",
            "uefi_payload_fault",
            "uefi_payload_page_fault",
            "uefi_console_interrupt",
            "aurora_serial_interrupt",
        ],
        "kernel_traps": [
            "aurora_exception_*",
            "aurora_timer_interrupt",
            "aurora_unexpected_interrupt",
            "uefi_process_exception_*",
            "uefi_process_timer_interrupt",
            "uefi_process_unexpected_interrupt",
        ],
        "ist_traps": ["aurora_exception_8", "uefi_process_exception_8"],
        "stack_guards": [
            {
                "storage": "aurora_trap_guard",
                "emergency": "aurora_nested_fault",
                "entries": [
                    "aurora_exception_*",
                    "aurora_timer_interrupt",
                    "aurora_program_return",
                    "aurora_program_call",
                    "aurora_process_call",
                    "aurora_user_return",
                    "aurora_unexpected_interrupt",
                ],
            },
            {
                "storage": "uefi_process_trap_guard",
                "emergency": "uefi_process_nested_fault",
                "entries": [
                    "uefi_process_exception_*",
                    "uefi_process_timer_interrupt",
                    "uefi_process_process_call",
                    "uefi_process_unexpected_interrupt",
                ],
            },
            {
                "storage": "uefi_payload_trap_guard",
                "emergency": "uefi_payload_nested_fault",
                "entries": ["uefi_payload_fault", "uefi_payload_page_fault", "uefi_console_interrupt"],
            },
        ],
        "stack_continuations": [
            {
                "name": "process",
                "storage": "uefi_process_saved_rsp",
                "entries": ["uefi_process_enter"],
                "resumes": ["uefi_process_resume"],
                "leaves": ["uefi_process_leave_user"],
                "saved_bytes": 48,
                "frame_bytes": 176,
            },
            {
                "name": "runtime",
                "storage": "uefi_runtime_saved_rsp",
                "entries": ["uefi_runtime_enter"],
                "resumes": ["uefi_runtime_resume"],
                "leaves": ["aurora_leave_user"],
                "saved_bytes": 48,
                "frame_bytes": 176,
            },
            {
                "name": "bios",
                "storage": "aurora_saved_kernel_rsp",
                "entries": ["aurora_user_probe", "aurora_user_program", "aurora_resume_integer"],
                "resumes": [],
                "leaves": ["aurora_leave_user"],
                "saved_bytes": 48,
                "frame_bytes": 176,
            },
        ],
    },
    {
        "profiles": ["uefi/*"],
        "user_traps": [
            "aurora_exception_*",
            "aurora_timer_interrupt",
            "aurora_program_return",
            "aurora_program_call",
            "aurora_process_call",
            "uefi_process_exception_*",
            "uefi_process_timer_interrupt",
            "uefi_process_process_call",
            "uefi_process_unexpected_interrupt",
            "aurora_user_return",
            "aurora_unexpected_interrupt",
        ],
    },
    {
        "profiles": ["uefi/runtime-fixture"],
        # install_architecture clears/readbacks EFER.SCE and SYSENTER MSRs
        # before user entry. These are disabled-entry fault contracts, not a
        # system-call return ABI. The combined check binds every used opcode
        # to the actual CPL3 fault roots and their separate RSP0 bounds.
        "disabled_user_transfers": [
            {"instruction": "syscall", "faults": ["aurora_exception_6"]},
            {"instruction": "sysenter", "faults": ["aurora_exception_6", "aurora_exception_13"]},
        ],
    },
    {
        "profiles": ["uefi/platform-fixture"],
        "callbacks": ["payload_main(="],
    },
    {
        "profiles": ["bios/bios-fixture"],
        "callbacks": ["kernel_main(="],
    },
    # The pin and table supervisors' scrub callbacks, one per boot-selected row family.
    {
        "profiles": ["uefi/runtime-fixture"],
        "callbacks": ["PinLedger::release_reserved(=pin_scrub(", "PinLedger::release_reserved(=table_scrub("],
    },
    # Aurora imports: generated kernel code reaches hardware only through these runtime services.
    {
        "profiles": ["*"],
        "imports": [],
        "import_free": ["budget-root", "service-root"],
        "forbidden": ["__au_runtime_service_saturation_create", "*process_service_saturation_create*"],
    },
    {
        "profiles": [
            "bios/console",
            "uefi/program-*",
            "uefi/production",
            "uefi/text-fixture",
        ],
        "imports": ["__au_runtime_console_next", "__au_runtime_console_put"],
    },
    # The storage scratchpad reaches only Console; the snapshot primary reaches
    # only the byte region, in a separate bounded composition.
    {
        "profiles": ["uefi/storage-fixture"],
        "imports:language": ["__au_runtime_console_next", "__au_runtime_console_put"],
        "reachable": ["__au_runtime_namespace_input", "__au_runtime_namespace_response"],
    },
    {
        "profiles": ["uefi/snapshot-call-fixture"],
        "imports:language": [
            "__au_runtime_bytes_allocate",
            "__au_runtime_bytes_at",
            "__au_runtime_bytes_drop",
            "__au_runtime_bytes_set",
        ],
    },
    # The display fixture's graphical console reads Console input and paints
    # through Display; its framebuffer service object only paints.
    {
        "profiles": ["uefi/display-fixture"],
        "imports:language": ["__au_runtime_console_next", "__au_runtime_display_pixel"],
        "imports:display": ["__au_runtime_display_pixel"],
    },
    # The production terminal painter reaches the framebuffer only through the
    # sealed Display pixel service; the program-console object gains nothing.
    {
        "profiles": ["uefi/production"],
        "imports:terminal": ["__au_runtime_display_pixel"],
        "reachable": ["__au_runtime_terminal_paint"],
    },
    {
        "profiles": [
            "uefi/iommu-event",
        ],
        "imports": [
            "__au_runtime_console_put",
            "__au_runtime_iommu_event_acknowledge",
            "__au_runtime_iommu_event_poll",
        ],
    },
    # The device fixture's console service object reaches only Console, its UART
    # policy only the COM1 ports, and its owned-bytes object only the byte region.
    {
        "profiles": ["uefi/device-fixture"],
        "imports:language": ["__au_runtime_console_next", "__au_runtime_console_put"],
        "imports:kernel-uart": ["__au_runtime_port_read8", "__au_runtime_port_write8"],
        "imports:owned-bytes": [
            "__au_runtime_bytes_allocate",
            "__au_runtime_bytes_at",
            "__au_runtime_bytes_borrow_span",
            "__au_runtime_bytes_drop",
            "__au_runtime_bytes_resize",
            "__au_runtime_bytes_set",
        ],
    },
    {
        "profiles": ["bios/console"],
        "imports:kernel-uart": ["__au_runtime_port_read8", "__au_runtime_port_write8"],
    },
    # Kernel decisions stay in Aurora: the supervisor must actually call these policy entries.
    {
        "profiles": [
            "uefi/runtime*",
            "uefi/service-fixture",
            "uefi/storage-fixture",
            "uefi/snapshot-call-fixture",
            "uefi/text-fixture",
            "uefi/program-*",
            "uefi/production",
            "bios/*",
        ],
        "reachable": ["aurora_kernel_terminal_event"],
    },
    {
        "profiles": [
            "uefi/service-fixture",
            "uefi/storage-fixture",
            "uefi/snapshot-call-fixture",
            "uefi/text-fixture",
            "uefi/program-*",
            "uefi/production",
        ],
        "reachable": ["aurora_kernel_budget_tick"],
    },
    {
        "profiles": [
            "uefi/service-fixture",
            "uefi/storage-fixture",
            "uefi/snapshot-call-fixture",
            "uefi/text-fixture",
            "uefi/program-*",
            "uefi/production",
        ],
        "reachable": ["aurora_kernel_ipc_transition"],
    },
    # The dispatcher, user-run and resume rows of the service fixture.
    {
        "profiles": ["uefi/service-fixture"],
        "reachable": ["aurora_kernel_round_robin_next", "aurora_kernel_client_disposal"],
    },
    # Whole source allocation entry points replace the old native-to-transition
    # reachability requirement; transitions are now internal source calls.
    # Only the source allocation ledger can access the unique metadata bank.
    {
        "profiles": ["uefi/process-fixture", "uefi/production"],
        "effect_native_entries": [
            "memcpy",
            "memset",
            "__au_runtime_owned_words_at",
            "__au_runtime_owned_words_borrow_span",
            "__au_runtime_owned_words_set",
            "__au_runtime_owned_words_size",
            "__au_runtime_mapping_clear_expected_entry",
            "__au_runtime_mapping_clear_shared_entry",
            "__au_runtime_mapping_copy_source_frame",
            "__au_runtime_mapping_downgrade_snapshot_entry",
            "__au_runtime_mapping_fill_snapshot_chunk",
            "__au_runtime_mapping_frame_address",
            "__au_runtime_mapping_frame_index",
            "__au_runtime_mapping_initialize_shared_upper",
            "__au_runtime_mapping_observe_next_present",
            "__au_runtime_mapping_observe_snapshot_anchor",
            "__au_runtime_mapping_observe_table",
            "__au_runtime_mapping_publish_empty_entry",
            "__au_runtime_mapping_publish_shared_entry",
            "__au_runtime_mapping_reserved_end",
            "__au_runtime_mapping_reserved_first",
            "__au_runtime_mapping_revoke_root",
            "__au_runtime_mapping_scrub_unpublished_frame",
            "__au_runtime_mapping_shared_slot",
            "__au_runtime_mapping_shared_slots",
            "__au_runtime_mapping_shared_upper",
            "__au_runtime_mapping_shared_value",
            "__au_runtime_mapping_snapshot_anchor_clear",
            "__au_runtime_mapping_snapshot_anchor_publish",
        ],
        "effect_scopes": [
            {
                "root": "__au_runtime_execution_authority_prepare",
                "physical": [],
                "source_entries": [
                    "__au_runtime_manager_space_value",
                    "__au_runtime_service_phase",
                    "__au_runtime_service_generation",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_activate",
                "physical": [
                    "uefi_process_enter",
                    "uefi_process_resume",
                    "uefi_process_exception_dispatch",
                    "uefi_process_kernel_exception_dispatch",
                    "uefi_process_exception_0",
                    "uefi_process_exception_1",
                    "uefi_process_exception_2",
                    "uefi_process_exception_3",
                    "uefi_process_exception_4",
                    "uefi_process_exception_5",
                    "uefi_process_exception_6",
                    "uefi_process_exception_7",
                    "uefi_process_exception_8",
                    "uefi_process_exception_9",
                    "uefi_process_exception_10",
                    "uefi_process_exception_11",
                    "uefi_process_exception_12",
                    "uefi_process_exception_13",
                    "uefi_process_exception_14",
                    "uefi_process_exception_15",
                    "uefi_process_exception_16",
                    "uefi_process_exception_17",
                    "uefi_process_exception_18",
                    "uefi_process_exception_19",
                    "uefi_process_exception_20",
                    "uefi_process_exception_21",
                    "uefi_process_exception_22",
                    "uefi_process_exception_23",
                    "uefi_process_exception_24",
                    "uefi_process_exception_25",
                    "uefi_process_exception_26",
                    "uefi_process_exception_27",
                    "uefi_process_exception_28",
                    "uefi_process_exception_29",
                    "uefi_process_exception_30",
                    "uefi_process_exception_31",
                    "uefi_process_timer_interrupt",
                    "uefi_process_process_call",
                    "uefi_process_unexpected_interrupt",
                    "uefi_process_leave_user",
                    "uefi_process_drain",
                    "uefi_process_nested_fault",
                    "uefi_process_drain_begin",
                    "uefi_process_drain_end",
                ],
                "source_entries": [
                    "__au_runtime_manager_space_value",
                    "__au_runtime_manager_fault_access",
                    "__au_runtime_manager_commit_fault_block",
                    "__au_runtime_manager_validate_access",
                    "__au_runtime_manager_verify_space",
                    "__au_runtime_manager_space_executable",
                    "__au_runtime_manager_map_memory",
                    "__au_runtime_manager_remap_memory",
                    "__au_runtime_manager_unmap_memory",
                    "__au_runtime_budget_charge",
                    "__au_runtime_budget_progress",
                    "__au_runtime_budget_available",
                    "__au_runtime_budget_quantum",
                    "__au_runtime_budget_used",
                    "__au_runtime_process_trap",
                    "__au_runtime_process_call",
                    "__au_runtime_process_base64_group",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_complete",
                "physical": [],
                "source_entries": [
                    "__au_runtime_process_trap",
                    "__au_runtime_process_call",
                    "__au_runtime_manager_space_value",
                    "__au_runtime_manager_validate_access",
                    "__au_runtime_manager_verify_space",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_force",
                "physical": [],
                "source_entries": [
                    "__au_runtime_service_phase",
                    "__au_runtime_service_generation",
                    "__au_runtime_manager_space_value",
                    "__au_runtime_process_trap",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_retire",
                "physical": [],
                "source_entries": [
                    "__au_runtime_service_phase",
                    "__au_runtime_service_generation",
                    "__au_runtime_budget_used",
                    "__au_runtime_manager_space_value",
                    "__au_runtime_manager_verify_space",
                    "__au_runtime_manager_retire_space",
                    "__au_runtime_manager_audit_residents",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_invalidate_service",
                "physical": [],
                "source_entries": [
                    "__au_runtime_manager_space_value",
                    "__au_runtime_budget_used",
                    "__au_runtime_service_observe_terminal",
                    "__au_runtime_manager_snapshot_discard",
                ],
            },
            {
                "root": "__au_runtime_execution_authority_finish",
                "physical": [],
                "source_entries": ["__au_runtime_manager_audit_residents"],
            },
        ],
        "imports:execution-lifecycle": [
            "__au_runtime_execution_authority_prepare",
            "__au_runtime_execution_authority_activate",
            "__au_runtime_execution_authority_complete",
            "__au_runtime_execution_authority_force",
            "__au_runtime_execution_authority_retire",
            "__au_runtime_execution_authority_finish",
            "__au_runtime_execution_authority_invalidate_service",
        ],
        "reachable": [
            "__au_runtime_lifecycle_construct",
            "__au_runtime_lifecycle_prepare",
            "__au_runtime_lifecycle_can_prepare",
            "__au_runtime_lifecycle_execute",
            "__au_runtime_lifecycle_force",
            "__au_runtime_lifecycle_complete",
            "__au_runtime_lifecycle_phase",
            "__au_runtime_lifecycle_generation",
            "__au_runtime_lifecycle_pending",
            "__au_runtime_lifecycle_finish",
        ],
    },
    {
        "profiles": ["uefi/process-fixture", "uefi/production"],
        "imports:memory-manager": [
            "__au_runtime_owned_words_borrow_span",
            "__au_runtime_owned_words_size",
            "__au_runtime_owned_words_at",
            "__au_runtime_owned_words_set",
            "__au_runtime_owned_words_finish",
            "__au_runtime_mapping_observe_table",
            "__au_runtime_mapping_observe_next_present",
            "__au_runtime_mapping_publish_empty_entry",
            "__au_runtime_mapping_clear_expected_entry",
            "__au_runtime_mapping_scrub_unpublished_frame",
            "__au_runtime_mapping_downgrade_snapshot_entry",
            "__au_runtime_mapping_snapshot_anchor_publish",
            "__au_runtime_mapping_snapshot_anchor_clear",
            "__au_runtime_mapping_frame_address",
            "__au_runtime_mapping_frame_index",
            "__au_runtime_mapping_shared_slots",
            "__au_runtime_mapping_shared_slot",
            "__au_runtime_mapping_shared_value",
            "__au_runtime_mapping_shared_upper",
            "__au_runtime_mapping_reserved_first",
            "__au_runtime_mapping_reserved_end",
            "__au_runtime_mapping_initialize_shared_upper",
            "__au_runtime_mapping_publish_shared_entry",
            "__au_runtime_mapping_copy_source_frame",
            "__au_runtime_mapping_fill_snapshot_chunk",
            "__au_runtime_mapping_clear_shared_entry",
            "__au_runtime_mapping_revoke_root",
            "__au_runtime_mapping_observe_snapshot_anchor",
            "__au_runtime_mapping_finish",
        ],
        "reachable": [
            "__au_runtime_manager_construct",
            "__au_runtime_manager_frames_initialize",
            "__au_runtime_manager_frames_record",
        ],
    },
    {
        "profiles": ["uefi/process-fixture"],
        # Standalone native frame API fixtures. Production reaches the same
        # allocator internally through the retained source MemoryManager.
        "reachable": [
            "__au_runtime_manager_frames_allocate",
            "__au_runtime_manager_frames_release",
            "__au_runtime_manager_frames_audit",
        ],
        "callbacks": ["deliver_output(=execution_output_probe("],
    },
    # Retained source accounting is a real consumer, not unused ABI scaffolding.
    {
        "profiles": ["uefi/process-fixture", "uefi/production"],
        "reachable": [
            "__au_runtime_budget_create",
            "__au_runtime_budget_reset",
            "__au_runtime_budget_configure_next",
            "__au_runtime_budget_restart",
            "__au_runtime_budget_charge",
            "__au_runtime_budget_progress",
            "__au_runtime_budget_admitted",
            "__au_runtime_budget_available",
            "__au_runtime_budget_quantum",
            "__au_runtime_budget_used",
        ],
    },
    # Retained incarnation admission must be reached by real process paths.
    {
        "profiles": ["uefi/process-fixture", "uefi/production"],
        "reachable": [
            "__au_runtime_service_create",
            "__au_runtime_service_open_operation",
            "__au_runtime_service_close_operation",
            "__au_runtime_service_admit",
            "__au_runtime_service_mark_ready",
            "__au_runtime_service_lose",
            "__au_runtime_service_cleaned",
            "__au_runtime_service_generation",
            "__au_runtime_service_phase",
            "__au_runtime_service_reason",
            "__au_runtime_service_detail",
        ],
    },
    {
        "profiles": ["uefi/production"],
        "reachable": ["__au_runtime_service_disk_ready"],
    },
    # Fixture routes must retain both explicit shutdown intent and terminal observation.
    {
        "profiles": ["uefi/process-fixture"],
        "reachable": ["__au_runtime_service_begin_shutdown", "__au_runtime_service_observe_terminal"],
    },
    # The process image's frame, map, volume, export, program, trap and run decisions stay in Aurora.
    {
        "profiles": ["uefi/process-fixture"],
        "forbidden": [
            "__au_runtime_process_file_*",
            "__au_runtime_note_update",
            "__au_runtime_note_project",
            "__au_runtime_files_update",
            "__au_runtime_files_replace",
            "__au_runtime_process_directory_prefix",
            "*KernelStore*",
            "*FileService*",
        ],
        "reachable": [
            "__au_runtime_process_map_admit",
            "__au_runtime_process_volume_grant",
            "__au_runtime_process_frame_range",
            "__au_runtime_process_volume_admit",
            "__au_runtime_process_volume_find",
            "__au_runtime_process_volume_entry",
            "__au_runtime_process_base64_group",
            "__au_runtime_process_elf_admit",
            "__au_runtime_process_layout",
            "__au_runtime_process_region",
            "__au_runtime_process_elf_entry",
            "__au_runtime_process_trap",
            "__au_runtime_process_call",
            "__au_runtime_process_runs_admit",
            "__au_runtime_process_run",
            "aurora_kernel_round_robin_next",
        ],
    },
    # Startup has a separate, unpublished-owner grant. Only this source object
    # may drive its fixed authenticated effects; the retained root owns lifetime.
    {
        "profiles": ["uefi/production", "uefi/process-fixture"],
        "imports:service-bootstrap": [
            "__au_runtime_service_bootstrap_begin",
            "__au_runtime_service_bootstrap_preparation",
            "__au_runtime_service_bootstrap_begin_volume",
            "__au_runtime_service_bootstrap_copy_volume",
            "__au_runtime_service_bootstrap_seal_volume",
            "__au_runtime_service_bootstrap_admit_storage",
            "__au_runtime_service_bootstrap_advance",
            "__au_runtime_service_bootstrap_finish",
        ],
        "reachable": ["__au_runtime_process_bootstrap_service"],
    },
    # The retained slot owner is the parent authority for each fixed runtime
    # operation. Only its source object can use these exact field effects.
    {
        "profiles": ["uefi/production"],
        "imports:resident-owner": [
            "__au_runtime_resident_prepare",
            "__au_runtime_resident_run",
            "__au_runtime_resident_console",
            "__au_runtime_resident_reject",
            "__au_runtime_resident_begin_shutdown",
            "__au_runtime_resident_advance_shutdown",
            "__au_runtime_resident_finish",
        ],
    },
    # Production runs use the same source admission/memory decisions, but no
    # fixture run-list/export policy and only this copied supervisor output sink.
    {
        "profiles": ["uefi/production"],
        "callbacks": ["deliver_output(=production_output("],
        "imports:execution": [
            "__au_runtime_execution_prepare",
            "__au_runtime_execution_preparation",
            "__au_runtime_execution_advance",
            "__au_runtime_execution_output",
            "__au_runtime_execution_request",
            "__au_runtime_execution_cancel",
            "__au_runtime_execution_finish",
        ],
        "forbidden": [
            "__au_runtime_process_file_*",
            "__au_runtime_note_update",
            "__au_runtime_note_project",
            "__au_runtime_files_update",
            "__au_runtime_files_replace",
            "__au_runtime_process_path_text",
            "__au_runtime_process_directory_prefix",
            "__au_runtime_process_run",
            "__au_runtime_process_runs_admit",
            "__au_runtime_process_base64_group",
            "uefi_process_user_return",
            "uefi_process_program_return",
        ],
        "reachable": [
            "__au_runtime_resident_construct",
            "__au_runtime_process_resident_prepare",
            "__au_runtime_process_resident_run",
            "__au_runtime_process_resident_console",
            "__au_runtime_process_resident_reject",
            "__au_runtime_process_resident_finish",
            "__au_runtime_process_execute_command",
            "__au_runtime_process_map_admit",
            "__au_runtime_process_volume_grant",
            "__au_runtime_process_frame_range",
            "__au_runtime_process_volume_admit",
            "__au_runtime_process_volume_find",
            "__au_runtime_process_volume_entry",
            "__au_runtime_process_elf_admit",
            "__au_runtime_process_layout",
            "__au_runtime_process_region",
            "__au_runtime_process_elf_entry",
            "__au_runtime_process_trap",
            "__au_runtime_process_call",
            "aurora_kernel_budget_tick",
        ],
    },
    # No fixture state or capture handshake links into the production image.
    {
        "profiles": ["uefi/production"],
        "forbidden": ["*fixture*", "*Fixture*", "*hostile*", "*capture_gate*", "*capture_scenario*"],
    },
    # The BIOS image keeps only its own policies; UEFI supervisor policies must not link into it.
    {
        "profiles": ["bios/*"],
        "forbidden": [
            "*interrupt_budget*",
            "*round_robin*",
            "*ipc_transition*",
            "*TransactionSnapshot*",
            "*TransactionDecision*",
            "*TickDecision*",
            "*SelectionDecision*",
        ],
    },
]
