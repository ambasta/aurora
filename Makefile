# Convenience entrypoints. Meson owns the compiler and complete native test graph.
.DEFAULT_GOAL := all

# Image and standalone script outputs are shared; serialize shortcut execution.
.NOTPARALLEL:
export QEMU QEMU_DATA OVMF OVMF_CODE OVMF_VARS OVMF_DIR UEFI_LD
export EVENT_TOOL_PREFIX EVENT_BUILD_RECEIPT EVENT_CODE EVENT_VARS EVENT_DATA EVENT_ESP_DIR EVENT_OUTPUT_PARENT MTOOLS_DIR
export AURORA_BAR_FIRMWARE AURORA_BAR_COVERAGE AURORA_BAR_RECEIPTS AURORA_NVME_RECEIPTS
export CLEAN_PATHS

.PHONY: all compiler kernel kernel-uefi test test-release test-exhaustive
all:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel bios --publish-compiler

compiler:
	$(MAKE) -C compiler

kernel:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel bios

kernel-uefi:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel uefi

test:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite merge

test-release:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite release

test-exhaustive:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite exhaustive

.PHONY: help
help:
	@printf '%s\n' \
	  'make                  Build the compiler and BIOS kernel image' \
	  'make kernel-uefi      Build the separate UEFI loader/payload' \
	  'make run              Build and verify one normal BIOS QEMU boot' \
	  'make run-uefi         Build and verify one normal UEFI QEMU boot' \
	  'make console          Open an opt-in BIOS serial console in QEMU' \
	  'make console-uefi     Open an opt-in UEFI timer-polled serial console' \
	  'make program-console-uefi  Build/check and open the protected command console' \
	  'make smoke-program-console-uefi  Build/check and test the protected command console' \
	  'make smoke-production  Build/check and test the production UEFI image (both consoles)' \
	  'make capture-framebuffer  Build/check and save a local PNG preview under build/' \
	  'make smoke-iommu-event  Opt-in custom-model Event guests with current admission and normal restoration' \
	  'make smoke-graphical-console  Build/check graphical guests, capture pixels and restore normal UEFI' \
	  'make smoke-console    Build and verify BIOS console PTY acceptance' \
	  'make smoke-console-uefi  Build and verify UEFI console PTY acceptance' \
	  'make test             Build and run the merge suite (every merge)' \
	  'make test-release     Run the opt-in release suite (releases, compiler bumps)' \
	  'make test-exhaustive  Run the separate complete combinatorial library sweeps' \
	  'make smoke-all        Run the full emulator suite, including both consoles' \
	  'make clean-dry-run    Show Meson product cleanup commands; MESON_BUILD_DIR selects one build' \
	  'make clean            Meson clean for default builds; preserve configuration/logs/test scratch' \
	  'make clean-scratch-dry-run / clean-scratch CLEAN_PATHS="build/..."  Select reviewed scratch' \
	  '' \
	  'run/run-uefi are bounded boot self-tests; console is an experimental serial prompt.' \
	  'Overrides: CXX, UEFI_LD, QEMU, QEMU_DATA, OVMF or OVMF_CODE/OVMF_VARS, OVMF_DIR.' \
	  'See docs/local-development.md for dependencies, scripts and test scope.'

.PHONY: clean clean-dry-run
clean clean-dry-run:
	python3 -B scripts/clean.py $(if $(filter clean-dry-run,$@),--dry-run,)

.PHONY: clean-scratch clean-scratch-dry-run
clean-scratch clean-scratch-dry-run:
	python3 -B scripts/clean.py --scratch $(if $(filter clean-scratch-dry-run,$@),--dry-run,)

.PHONY: run
run:
	./scripts/kernel-run.sh bios

.PHONY: run-uefi
run-uefi:
	./scripts/kernel-run.sh uefi

.PHONY: console
console:
	./scripts/kernel-console.sh

.PHONY: console-uefi
console-uefi:
	./scripts/kernel-uefi-console.sh

.PHONY: program-console-uefi
program-console-uefi:
	./scripts/kernel-program-console.sh

.PHONY: smoke-program-console-uefi
smoke-program-console-uefi:
	./scripts/kernel-program-console-smoke.sh

.PHONY: smoke-production
smoke-production:
	./scripts/kernel-run.sh production --smoke

.PHONY: smoke-iommu-event
smoke-iommu-event:
	./scripts/kernel-run.sh iommu-event --smoke

.PHONY: smoke-graphical-console
smoke-graphical-console:
	./scripts/kernel-run.sh graphical-console --smoke

.PHONY: capture-framebuffer
capture-framebuffer:
	./scripts/kernel-run.sh framebuffer

.PHONY: smoke-console
smoke-console:
	./scripts/kernel-console-smoke.sh bios

.PHONY: smoke-console-uefi
smoke-console-uefi:
	./scripts/kernel-console-smoke.sh uefi

.PHONY: smoke
smoke:
	./scripts/kernel-smoke.sh

.PHONY: smoke-fault
smoke-fault:
	./scripts/kernel-smoke.sh --fault

.PHONY: smoke-page-fault
smoke-page-fault:
	./scripts/kernel-smoke.sh --page-fault

.PHONY: smoke-scheduling
smoke-scheduling:
	./scripts/kernel-scheduling-smoke.sh

.PHONY: smoke-uefi
smoke-uefi:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-uefi

.PHONY: smoke-acpi
smoke-acpi:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-acpi

.PHONY: smoke-division
smoke-division:
	./scripts/kernel-division-smoke.sh

.PHONY: smoke-pci
smoke-pci:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-pci

.PHONY: smoke-unsigned
smoke-unsigned:
	./scripts/kernel-unsigned-smoke.sh

.PHONY: smoke-uefi-runtime
smoke-uefi-runtime:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-runtime

.PHONY: smoke-uefi-ipc
smoke-uefi-ipc:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-ipc

.PHONY: smoke-uefi-budget
smoke-uefi-budget:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-budget

.PHONY: smoke-uefi-dispatch
smoke-uefi-dispatch:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-dispatch

.PHONY: smoke-uefi-user-phases
smoke-uefi-user-phases:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-user-phases

.PHONY: smoke-all
smoke-all:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest
	./scripts/kernel-run.sh ivrs --smoke
	./scripts/kernel-run.sh bar --smoke
	./scripts/kernel-protection-smoke.sh
	./scripts/kernel-scheduling-smoke.sh
	./scripts/kernel-division-smoke.sh
	./scripts/kernel-unsigned-smoke.sh
	./scripts/kernel-console-smoke.sh bios
	./scripts/kernel-console-smoke.sh uefi

.PHONY: test-storage-model
test-storage-model:
	python3 -O storage/design/model/test_durability.py
	python3 -O storage/design/model/check_traceability.py
	python3 -O storage/design/model/test_traceability.py

.PHONY: test-nvme-queues
test-nvme-queues:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --tests kernel-nvme-queues kernel-nvme-queues-generation-3 kernel-nvme-queues-api kernel-compile-fail

.PHONY: smoke-nvme-prepare
smoke-nvme-prepare:
	@if [ -z "$${AURORA_NVME_RECEIPTS:-}" ]; then \
	    printf '%s\n' 'BLOCKED: Set AURORA_NVME_RECEIPTS to a fresh preparation receipt directory' >&2; exit 2; fi
	./scripts/kernel-run.sh bar-prepare --smoke \
	    --output "$${AURORA_NVME_RECEIPTS}"

.PHONY: smoke-uefi-bar
smoke-uefi-bar:
	./scripts/kernel-run.sh bar --smoke

.PHONY: smoke-uefi-span
smoke-uefi-span:
	./scripts/kernel-uefi-smoke.sh runtime-span

.PHONY: smoke-uefi-ivrs
smoke-uefi-ivrs:
	./scripts/kernel-run.sh ivrs --smoke

.PHONY: test-pin-ledger
test-pin-ledger:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --tests kernel-pin-ledger kernel-pin-ledger-generation-3 kernel-pin-api kernel-compile-fail

.PHONY: smoke-uefi-pins
smoke-uefi-pins:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-pins

.PHONY: test-dormant-tables
test-dormant-tables:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --tests kernel-dormant-tables kernel-dormant-decoder kernel-dormant-oracle \
	    kernel-dormant-generation kernel-dormant-api kernel-iommu-oracle kernel-iommu-event-completion kernel-compile-fail

.PHONY: smoke-uefi-tables
smoke-uefi-tables:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite guest-tables

.PHONY: test-boot-capacity
test-boot-capacity:
	python3 -B -O tests/kernel-boot-capacity.py

.PHONY: smoke-boot-capacity
smoke-boot-capacity:
	python3 -B tests/kernel-boot-capacity.py --qemu


.PHONY: formatter
formatter:
	$(MAKE) -C compiler formatter


smoke-all: smoke-boot-capacity
