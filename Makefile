# Bootstrap commands share the image/output directory; serialize their execution.
.NOTPARALLEL:
.PHONY: all compiler kernel test test-compiler test-image test-kernel test-semantics test-semantics-stress smoke smoke-fault smoke-page-fault smoke-scheduling smoke-uefi test-uefi test-acpi test-division smoke-acpi smoke-division test-pci test-unsigned smoke-pci smoke-unsigned test-uefi-runtime smoke-uefi-runtime test-uefi-ipc smoke-uefi-ipc test-uefi-budget smoke-uefi-budget test-uefi-dispatch smoke-uefi-dispatch test-uefi-user-phases smoke-uefi-user-phases smoke-all

all: compiler kernel

compiler:
	$(MAKE) -C compiler

kernel: compiler
	./scripts/kernel-build.sh

test-compiler: compiler
	$(MAKE) -C compiler test

test-image: kernel
	python3 tests/kernel-image.py

test-kernel:
	./scripts/kernel-tests.sh

test-semantics: compiler
	python3 tests/semantics/test_runner.py
	python3 tests/semantics/run.py build/aurorac

test-semantics-stress: compiler
	python3 tests/semantics/run.py build/aurorac --seed 404 --cases 1024

test-uefi:
	./scripts/kernel-uefi-tests.sh

test-acpi:
	./scripts/kernel-acpi-tests.sh

test-division:
	./scripts/kernel-division-tests.sh

test-pci:
	./scripts/kernel-pci-tests.sh

test-unsigned:
	./scripts/kernel-unsigned-tests.sh

test-uefi-runtime:
	./scripts/kernel-uefi-runtime-tests.sh

test-uefi-ipc:
	./scripts/kernel-uefi-ipc-tests.sh

test-uefi-budget:
	./scripts/kernel-uefi-budget-tests.sh

test-uefi-dispatch:
	./scripts/kernel-uefi-dispatch-tests.sh

test-uefi-user-phases:
	./scripts/kernel-uefi-user-phases-tests.sh

test: test-dormant-tables test-uefi-tables test-pin-ledger test-uefi-pins test-storage-model test-compiler test-image test-kernel test-uefi test-acpi test-division test-pci test-unsigned test-uefi-runtime test-uefi-ipc test-uefi-budget test-uefi-dispatch test-uefi-user-phases test-uefi-bar test-uefi-span test-uefi-ivrs test-semantics

# QEMU is intentionally a separate acceptance gate, never silently skipped.
smoke:
	./scripts/kernel-smoke.sh

smoke-fault:
	./scripts/kernel-smoke.sh --fault

smoke-page-fault:
	./scripts/kernel-smoke.sh --page-fault

smoke-scheduling:
	./scripts/kernel-scheduling-smoke.sh

smoke-uefi:
	./scripts/kernel-uefi-all.sh

smoke-acpi:
	./scripts/kernel-acpi-all.sh

smoke-division:
	./scripts/kernel-division-smoke.sh

smoke-pci:
	./scripts/kernel-pci-all.sh

smoke-unsigned:
	./scripts/kernel-unsigned-smoke.sh

smoke-uefi-runtime:
	./scripts/kernel-uefi-runtime-all.sh

smoke-uefi-ipc:
	./scripts/kernel-uefi-ipc-all.sh

smoke-uefi-budget:
	./scripts/kernel-uefi-budget-all.sh

smoke-uefi-dispatch:
	./scripts/kernel-uefi-dispatch-all.sh

smoke-uefi-user-phases:
	./scripts/kernel-uefi-user-phases-all.sh

smoke-all:
	./scripts/kernel-uefi-tables-all.sh
	./scripts/kernel-uefi-ivrs-all.sh
	./scripts/kernel-uefi-pin-all.sh
	./scripts/kernel-uefi-span-all.sh
	./scripts/kernel-uefi-bar-all.sh
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


.PHONY: test-storage-model
test-storage-model:
	python3 storage/design/model/test_durability.py
	python3 -O storage/design/model/test_durability.py
	python3 storage/design/model/check_traceability.py
	python3 -O storage/design/model/check_traceability.py
	python3 storage/design/model/test_traceability.py
	python3 -O storage/design/model/test_traceability.py

.PHONY: test-uefi-bar test-uefi-span smoke-uefi-bar smoke-uefi-span
test-uefi-bar:
	./scripts/kernel-uefi-bar-tests.sh

test-uefi-span:
	./scripts/kernel-uefi-span-tests.sh

smoke-uefi-bar:
	./scripts/kernel-uefi-bar-all.sh

smoke-uefi-span:
	./scripts/kernel-uefi-span-all.sh

.PHONY: test-uefi-ivrs smoke-uefi-ivrs
test-uefi-ivrs:
	./scripts/kernel-uefi-ivrs-tests.sh

smoke-uefi-ivrs:
	./scripts/kernel-uefi-ivrs-all.sh

.PHONY: test-pin-ledger test-uefi-pins smoke-uefi-pins
test-pin-ledger:
	./scripts/kernel-pin-tests.sh

test-uefi-pins:
	./scripts/kernel-uefi-pin-tests.sh

smoke-uefi-pins:
	./scripts/kernel-uefi-pin-all.sh

.PHONY: test-dormant-tables test-uefi-tables smoke-uefi-tables
test-dormant-tables:
	./scripts/kernel-dormant-tests.sh

test-uefi-tables:
	./scripts/kernel-uefi-tables-tests.sh

smoke-uefi-tables:
	./scripts/kernel-uefi-tables-all.sh
