# Convenience entrypoints. Meson owns the compiler and complete native test graph.
.DEFAULT_GOAL := all

# Image and standalone script outputs are shared; serialize shortcut execution.
.NOTPARALLEL:
export QEMU QEMU_DATA OVMF OVMF_CODE OVMF_VARS OVMF_DIR UEFI_LD
export EVENT_TOOL_PREFIX EVENT_BUILD_RECEIPT EVENT_CODE EVENT_VARS EVENT_DATA EVENT_ESP_DIR EVENT_OUTPUT_PARENT MTOOLS_DIR
export AURORA_BAR_FIRMWARE AURORA_BAR_COVERAGE AURORA_BAR_RECEIPTS AURORA_NVME_RECEIPTS
export CLEAN_PATHS

.PHONY: all compiler kernel kernel-uefi test test-compiler
all:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel bios --publish-compiler

compiler:
	$(MAKE) -C compiler

kernel:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel bios

kernel-uefi:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --kernel uefi

test:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite full

test-compiler:
	python3 -B scripts/meson_test.py --repo-root "$(abspath .)" --suite compiler

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
	  'make test-program-stream  Run copied-stream and two-role authority host tests' \
	  'make capture-framebuffer  Build/check and save a local PNG preview under build/' \
	  'make smoke-iommu-event  Opt-in custom-model Event guests with current admission and normal restoration' \
	  'make smoke-graphical-console  Build/check graphical guests, capture pixels and restore normal UEFI' \
	  'make smoke-console    Build and verify BIOS console PTY acceptance' \
	  'make smoke-console-uefi  Build and verify UEFI console PTY acceptance' \
	  'make test-compiler    Run the incremental Meson compiler suite' \
	  'make test             Configure/build and run the complete Meson native graph' \
	  'make smoke-all        Run the full emulator suite, including both consoles' \
	  'make test-developer-commands  Check shortcuts with fake tools only' \
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

.PHONY: test-clean
test-clean:
	python3 -B tests/test_clean.py

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

.PHONY: smoke-iommu-event
smoke-iommu-event:
	./scripts/kernel-run.sh iommu-event --smoke

.PHONY: smoke-graphical-console
smoke-graphical-console:
	./scripts/kernel-run.sh graphical-console --smoke

.PHONY: capture-framebuffer
capture-framebuffer:
	./scripts/kernel-run.sh framebuffer

.PHONY: test-program-stream
test-program-stream:
	./scripts/kernel-program-tests.sh

.PHONY: smoke-console
smoke-console:
	./scripts/kernel-console-smoke.sh bios

.PHONY: smoke-console-uefi
smoke-console-uefi:
	./scripts/kernel-console-smoke.sh uefi

.PHONY: test-developer-commands
test-developer-commands:
	python3 -B tests/kernel-graphical-image-policy.py
	python3 -B -O tests/kernel-graphical-image-policy.py
	python3 -B tests/kernel-graphical-profile-metadata.py
	python3 -B -O tests/kernel-graphical-profile-metadata.py
	python3 -B tests/framebuffer-preview.py
	python3 -B -O tests/framebuffer-preview.py
	python3 -B tests/developer-commands.py
	python3 -B -O tests/developer-commands.py
	python3 -B tests/uefi-firmware.py
	python3 -B -O tests/uefi-firmware.py
	python3 -B tests/kernel-console-routing.py
	python3 -B -O tests/kernel-console-routing.py
	python3 -B tests/kernel-uefi-bar-runner.py
	python3 -B -O tests/kernel-uefi-bar-runner.py

.PHONY: test-uefi
test-uefi:
	./scripts/kernel-uefi-tests.sh

.PHONY: test-acpi
test-acpi:
	./scripts/kernel-acpi-tests.sh

.PHONY: test-pci
test-pci:
	./scripts/kernel-pci-tests.sh

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
	./scripts/kernel-uefi-all.sh

.PHONY: smoke-acpi
smoke-acpi:
	./scripts/kernel-acpi-all.sh

.PHONY: smoke-division
smoke-division:
	./scripts/kernel-division-smoke.sh

.PHONY: smoke-pci
smoke-pci:
	./scripts/kernel-pci-all.sh

.PHONY: smoke-unsigned
smoke-unsigned:
	./scripts/kernel-unsigned-smoke.sh

.PHONY: smoke-uefi-runtime
smoke-uefi-runtime:
	./scripts/kernel-uefi-runtime-all.sh

.PHONY: smoke-uefi-ipc
smoke-uefi-ipc:
	./scripts/kernel-uefi-ipc-all.sh

.PHONY: smoke-uefi-budget
smoke-uefi-budget:
	./scripts/kernel-uefi-budget-all.sh

.PHONY: smoke-uefi-dispatch
smoke-uefi-dispatch:
	./scripts/kernel-uefi-dispatch-all.sh

.PHONY: smoke-uefi-user-phases
smoke-uefi-user-phases:
	./scripts/kernel-uefi-user-phases-all.sh

.PHONY: smoke-all
smoke-all:
	./scripts/kernel-uefi-tables-all.sh
	./scripts/kernel-run.sh ivrs --smoke
	./scripts/kernel-uefi-pin-all.sh
	./scripts/kernel-uefi-span-all.sh
	./scripts/kernel-run.sh bar --smoke
	./scripts/kernel-protection-smoke.sh
	./scripts/kernel-scheduling-smoke.sh
	./scripts/kernel-uefi-all.sh
	./scripts/kernel-acpi-all.sh
	./scripts/kernel-division-smoke.sh
	./scripts/kernel-pci-all.sh
	./scripts/kernel-unsigned-smoke.sh
	./scripts/kernel-uefi-runtime-all.sh
	./scripts/kernel-uefi-ipc-all.sh
	./scripts/kernel-uefi-budget-all.sh
	./scripts/kernel-uefi-dispatch-all.sh
	./scripts/kernel-uefi-user-phases-all.sh
	./scripts/kernel-console-smoke.sh bios
	./scripts/kernel-console-smoke.sh uefi

.PHONY: test-storage-model
test-storage-model:
	python3 storage/design/model/test_durability.py
	python3 -O storage/design/model/test_durability.py
	python3 storage/design/model/check_traceability.py
	python3 -O storage/design/model/check_traceability.py
	python3 storage/design/model/test_traceability.py
	python3 -O storage/design/model/test_traceability.py

.PHONY: test-nvme-queues
test-nvme-queues:
	./scripts/kernel-nvme-queue-tests.sh

.PHONY: smoke-nvme-prepare
smoke-nvme-prepare:
	@if [ -z "$${AURORA_NVME_RECEIPTS:-}" ]; then \
	    printf '%s\n' 'BLOCKED: Set AURORA_NVME_RECEIPTS to a fresh preparation receipt directory' >&2; exit 2; fi
	./scripts/kernel-run.sh bar-prepare --smoke \
	    --output "$${AURORA_NVME_RECEIPTS}"

.PHONY: test-uefi-bar
test-uefi-bar:
	./scripts/kernel-uefi-bar-tests.sh

.PHONY: smoke-uefi-bar
smoke-uefi-bar:
	./scripts/kernel-run.sh bar --smoke

.PHONY: smoke-uefi-span
smoke-uefi-span:
	./scripts/kernel-uefi-span-all.sh

.PHONY: test-uefi-ivrs
test-uefi-ivrs:
	./scripts/kernel-uefi-ivrs-tests.sh

.PHONY: smoke-uefi-ivrs
smoke-uefi-ivrs:
	./scripts/kernel-run.sh ivrs --smoke

.PHONY: test-pin-ledger
test-pin-ledger:
	./scripts/kernel-pin-tests.sh

.PHONY: test-uefi-pins
test-uefi-pins:
	./scripts/kernel-uefi-pin-tests.sh

.PHONY: smoke-uefi-pins
smoke-uefi-pins:
	./scripts/kernel-uefi-pin-all.sh

.PHONY: test-dormant-tables
test-dormant-tables:
	./scripts/kernel-dormant-tests.sh

.PHONY: test-uefi-tables
test-uefi-tables:
	./scripts/kernel-uefi-tables-tests.sh

.PHONY: smoke-uefi-tables
smoke-uefi-tables:
	./scripts/kernel-uefi-tables-all.sh

.PHONY: test-boot
test-boot:
	python3 -B tests/kernel-boot-image.py
	python3 -B -O tests/kernel-boot-image.py

.PHONY: test-boot-capacity
test-boot-capacity:
	python3 -B tests/kernel-boot-capacity.py
	python3 -B -O tests/kernel-boot-capacity.py

.PHONY: smoke-boot-capacity
smoke-boot-capacity:
	python3 -B tests/kernel-boot-capacity.py --qemu

.PHONY: test-native-cap-contracts
test-native-cap-contracts:
	python3 -B tests/native-cap-contracts.py
	python3 -B -O tests/native-cap-contracts.py

.PHONY: test-compiler-contract
test-compiler-contract:
	python3 -B tests/test_compiler_contract.py
	python3 -B -O tests/test_compiler_contract.py

.PHONY: test-emulator-clock
test-emulator-clock:
	PYTHONDONTWRITEBYTECODE=1 python3 tests/kernel-emulator-clock.py
	PYTHONDONTWRITEBYTECODE=1 python3 -O tests/kernel-emulator-clock.py

.PHONY: test-iommu-diagnostics
test-iommu-diagnostics:
	PYTHONDONTWRITEBYTECODE=1 python3 tests/iommu-diagnostics.py
	PYTHONDONTWRITEBYTECODE=1 python3 -O tests/iommu-diagnostics.py

.PHONY: formatter
formatter:
	$(MAKE) -C compiler formatter

.PHONY: test-formatter
test-formatter:
	$(MAKE) -C compiler test-formatter

.PHONY: test-lint
test-lint:
	$(MAKE) -C compiler test-lint

.PHONY: test-graphical-controls
test-graphical-controls:
	python3 -B tests/kernel-graphical-admission-controls.py
	python3 -B -O tests/kernel-graphical-admission-controls.py
	python3 -B tests/kernel-graphical-smoke.py
	python3 -B -O tests/kernel-graphical-smoke.py

.PHONY: test-inventory
test-inventory:
	python3 -B tests/test-inventory.py

.PHONY: test-artifact-budget
test-artifact-budget:
	python3 -B tests/test_artifact_budget.py
	python3 -B -O tests/test_artifact_budget.py

smoke-all: smoke-boot-capacity
