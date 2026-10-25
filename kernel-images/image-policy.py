"""Declarative per-profile policy for kernel_image_check.py and kernel_stack_check.py.

A Python literal (read with ast.literal_eval, never executed). Every rule whose
`profiles` globs match a profile id (platform/mode) applies; lists merge.
  imports    - the complete set of symbols each generated Aurora object may import
  imports:STEM - further imports allowed only for the generated object STEM.o
  reachable  - Aurora policy entry points the supervisor must actually call
  forbidden  - symbol globs the linked kernel image must not define
  callbacks  - reviewed indirect calls, "CALLER=CALLEE" C++ signature fragments;
               an empty CALLEE is an intentional call into non-code (a fault fixture)
  user_traps - vectors entered only from user mode, on the separate TSS.RSP0 stack
"""

RULES = [
    {
        "profiles": ["uefi/*"],
        "user_traps": [
            "aurora_exception_*",
            "aurora_timer_interrupt",
            "aurora_program_return",
            "aurora_program_call",
            "aurora_user_return",
            "aurora_unexpected_interrupt",
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
    # The storage fixture's scratchpad object reaches only Console; its snapshot
    # producer object only the byte region.
    {
        "profiles": ["uefi/storage-fixture"],
        "imports:language": ["__au_runtime_console_next", "__au_runtime_console_put"],
        "imports:producer": [
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
