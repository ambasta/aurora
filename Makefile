# Test goals enter one controlled compiler run. Ordinary builds and compiler-free
# focused gates retain their existing behavior. A dry run only prints this route.
override .DEFAULT_GOAL := all
ifneq ($(strip $(foreach name,MAKECMDGOALS CURDIR MAKEFILE_LIST,$(if $(filter command,$(origin $(name))),$(name)))),)
$(error Make goal, directory, and makefile-list overrides are unsupported)
endif
override _AURORA_TEST_GOALS := $(filter test test-acceptance test-compiler test-image test-semantics test-semantics-stress test-unsigned test-uefi-span test-package-identity test-package-manifest test-package-graph test-kernel-budget-native test-round-robin test-console test-ipc-transaction test-uefi-ipc test-uefi-budget test-uefi-dispatch test-uefi-user-phases,$(MAKECMDGOALS))
override _AURORA_DISPATCH :=

# Export supplied controls before defaults are introduced in the inner graph.
# In particular, default path aliases must not select a different compiler.
override _AURORA_USER_CONTROLS := CXX CXXFLAGS IR_TEST_CXXFLAGS IR_TEST_BUILD_PREFIX OUT AURORAC \
    ACCEPTANCE_COMPILER ACCEPTANCE_COMPILER_SHA256 PACKAGE_IDENTITY_COMPILER \
    PACKAGE_IDENTITY_COMPILER_SHA256 PACKAGE_IDENTITY_TEST_FLAGS PACKAGE_IDENTITY_CAP_MIB \
    PACKAGE_MANIFEST_COMPILER PACKAGE_MANIFEST_COMPILER_SHA256 PACKAGE_MANIFEST_TEST_FLAGS \
    PACKAGE_MANIFEST_CAP_MIB PACKAGE_GRAPH_COMPILER PACKAGE_GRAPH_COMPILER_SHA256 PACKAGE_GRAPH_TEST_FLAGS \
    PACKAGE_GRAPH_CAP_MIB KERNEL_BUDGET_COMPILER KERNEL_BUDGET_COMPILER_SHA256 KERNEL_BUDGET_CAP_MIB ROUND_ROBIN_TEST_CAP_MIB \
    IPC_TRANSACTION_COMPILER IPC_TRANSACTION_COMPILER_SHA256 IPC_TRANSACTION_CAP_MIB \
    UTF8_TEST_FLAGS UTF8_LINES_TEST_FLAGS UTF8_LINES_COMPILER_SHA256 UTF8_LINES_ARTIFACT_PARENT \
    UTF8_RANGE_TEST_FLAGS UTF8_RANGE_COMPILER_SHA256 UTF8_RANGE_ARTIFACT_PARENT XFS_GEOMETRY_TEST_FLAGS \
    XFS_ROOT_TEST_FLAGS XFS_ROOT_API_TEST_FLAGS XFS_ROOT_REPO XFS_ROOT_FIXTURES XFS_ROOT_ARTIFACT_PARENT \
    XFS_ROOT_COMPILER_SHA256 SANITIZE ASAN_OPTIONS UBSAN_OPTIONS
# Raw user flags are data: reject Make expansion before export can evaluate them.
# Diagnostics contain control names only. The Python policy validates full grammar.
override define _AURORA_RAW_FLAG_NEWLINE


endef
override _AURORA_RAW_FLAG_CONTROLS := CXX CXXFLAGS IR_TEST_CXXFLAGS
override _AURORA_BAD_RAW_FLAGS := $(foreach name,$(_AURORA_RAW_FLAG_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(if $(findstring $$,$(value $(name))),$(name),$(if $(findstring `,$(value $(name))),$(name),$(if $(findstring %,$(subst $(_AURORA_RAW_FLAG_NEWLINE),%,$(value $(name)))),$(name))))))
ifneq ($(strip $(_AURORA_BAD_RAW_FLAGS)),)
$(error unsupported raw flag syntax in controls: $(_AURORA_BAD_RAW_FLAGS))
endif

# Inspect raw cap data before export can expand a Make expression. Never echo it.
override _AURORA_CAP_CONTROLS := PACKAGE_IDENTITY_CAP_MIB PACKAGE_MANIFEST_CAP_MIB PACKAGE_GRAPH_CAP_MIB KERNEL_BUDGET_CAP_MIB ROUND_ROBIN_TEST_CAP_MIB IPC_TRANSACTION_CAP_MIB
override _AURORA_CAP_EMPTY :=
override _AURORA_CAP_SPACE := $(_AURORA_CAP_EMPTY) $(_AURORA_CAP_EMPTY)
override _AURORA_CAP_TAB := $(_AURORA_CAP_EMPTY)	$(_AURORA_CAP_EMPTY)
override _AURORA_BAD_CAPS := $(foreach name,$(_AURORA_CAP_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(if $(value $(name)),$(if $(subst 9,,$(subst 8,,$(subst 7,,$(subst 6,,$(subst 5,,$(subst 4,,$(subst 3,,$(subst 2,,$(subst 1,,$(subst 0,,$(subst $(_AURORA_CAP_TAB),x,$(subst $(_AURORA_CAP_SPACE),x,$(value $(name)))))))))))))),$(name)),$(name))))
ifneq ($(strip $(_AURORA_BAD_CAPS)),)
$(error cap overrides must be unsigned decimal integers; invalid controls: $(_AURORA_BAD_CAPS))
endif

$(foreach name,$(_AURORA_USER_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(eval export $(name))))

ifneq ($(strip $(_AURORA_TEST_GOALS) $(AURORA_TEST_CONTEXT)),)
# These modes can skip a rejecting wrapper or turn a failure into success.
override _AURORA_SHORT_MAKE_FLAGS := $(foreach name,MAKEFLAGS MFLAGS,$(if $(filter --%,$(firstword $($(name)))),,$(firstword $($(name)))))
ifneq ($(strip $(foreach flag,i q t e,$(findstring $(flag),$(_AURORA_SHORT_MAKE_FLAGS)))),)
$(error supervised tests do not support Make -i, -q, -t, or -e)
endif
ifneq ($(filter --eval% --file% --makefile% --old-file% --assume-old% --what-if% --new-file% --assume-new%,$(MAKEFLAGS) $(MFLAGS) $(GNUMAKEFLAGS)),)
$(error supervised tests do not support Make recipe or dependency overrides)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error supervised tests do not support MAKEFILES)
endif
ifneq ($(words $(MAKEFILE_LIST)),1)
$(error supervised tests require this Makefile without additional makefiles)
endif
ifneq ($(strip $(foreach name,MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEOVERRIDES MAKEFILES MAKE_COMMAND,$(if $(filter command,$(origin $(name))),$(name)))),)
$(error supervised tests do not support command-line Make control overrides)
endif
ifneq ($(words $(SHELL)),1)
$(error supervised tests require one standard SHELL executable)
endif
ifeq ($(filter /bin/sh /bin/bash /usr/bin/sh /usr/bin/bash,$(SHELL)),)
$(error supervised tests require a standard sh or bash SHELL)
endif
ifneq ($(.SHELLFLAGS),-c)
$(error supervised tests do not support custom .SHELLFLAGS)
endif
ifneq ($(words $(MAKE)),1)
$(error supervised tests require one MAKE executable)
endif
ifeq ($(filter $(MAKE_COMMAND) make /usr/bin/make /bin/make,$(MAKE)),)
$(error supervised tests do not support a custom MAKE command)
endif
ifeq ($(strip $(AURORA_TEST_CONTEXT)),)
ifneq ($(words $(MAKECMDGOALS)),1)
$(error invoke one compiler-consuming test goal at a time; mixed goals are unsupported)
endif
override _AURORA_DISPATCH := yes
endif
endif

ifeq ($(_AURORA_DISPATCH),yes)
.PHONY: $(_AURORA_TEST_GOALS)
$(_AURORA_TEST_GOALS):
	python3 -B scripts/compiler_contract.py run --repo-root "$(CURDIR)" --entry root --goal "$@"
else
# The validated receipt, not a boolean flag, authorizes the sealed inner graph.
# Declare this prerequisite first, including on host-only aggregate prerequisites,
# so context rejection happens before any workload creates artifacts.
ifneq ($(strip $(AURORA_TEST_CONTEXT)),)
.NOTPARALLEL:
export AURORA_TEST_CONTEXT AURORA_TEST_MODE AURORA_TEST_COMPILER AURORA_TEST_IDENTITY_ARGS
export AURORAC OUT PACKAGE_IDENTITY_COMPILER PACKAGE_MANIFEST_COMPILER PACKAGE_GRAPH_COMPILER KERNEL_BUDGET_COMPILER IPC_TRANSACTION_COMPILER
.PHONY: aurora-test-context
all compiler kernel test-compiler test-image test-kernel test-semantics test-semantics-stress test-uefi \
    test-acpi test-division test-pci test-unsigned test-uefi-runtime test-uefi-ipc test-uefi-budget \
    test-uefi-dispatch test-uefi-user-phases test smoke smoke-fault smoke-page-fault smoke-scheduling \
    smoke-uefi smoke-acpi smoke-division smoke-pci smoke-unsigned smoke-uefi-runtime smoke-uefi-ipc \
    smoke-uefi-budget smoke-uefi-dispatch smoke-uefi-user-phases smoke-all test-storage-model \
    test-nvme-queues smoke-nvme-prepare \
    test-uefi-bar test-uefi-span smoke-uefi-bar smoke-uefi-span test-uefi-ivrs smoke-uefi-ivrs \
    test-pin-ledger test-uefi-pins smoke-uefi-pins test-dormant-tables test-uefi-tables smoke-uefi-tables \
    test-package-identity test-package-manifest test-package-graph test-kernel-budget-native test-boot \
    test-boot-capacity smoke-boot-capacity test-emulator-clock test-compiler-contract test-round-robin test-ipc-transaction test-native-cap-contracts \
    run run-uefi console console-uefi kernel-uefi test-console test-developer-commands: aurora-test-context
aurora-test-context:
	python3 -B scripts/compiler_contract.py check --repo-root "$(CURDIR)" --context "$$AURORA_TEST_CONTEXT"
endif

AURORAC ?= build/aurorac

# Bootstrap commands share the image/output directory; serialize their execution.
.NOTPARALLEL:
.PHONY: all compiler kernel test test-compiler test-image test-kernel test-semantics test-semantics-stress smoke smoke-fault smoke-page-fault smoke-scheduling smoke-uefi test-uefi test-acpi test-division smoke-acpi smoke-division test-pci test-unsigned smoke-pci smoke-unsigned test-uefi-runtime smoke-uefi-runtime test-uefi-ipc smoke-uefi-ipc test-uefi-budget smoke-uefi-budget test-uefi-dispatch smoke-uefi-dispatch test-uefi-user-phases smoke-uefi-user-phases smoke-all

all: compiler kernel

# Developer shortcuts reuse the existing build and validated smoke mechanisms.
# Export these selectors so both environment and make NAME=value syntax work.
export QEMU QEMU_DATA OVMF OVMF_CODE OVMF_VARS OVMF_DIR UEFI_LD
.PHONY: help run run-uefi console console-uefi kernel-uefi test-developer-commands
help:
	@printf '%s\n' \
	  'make                  Build the compiler and BIOS kernel image' \
	  'make kernel-uefi      Build the separate UEFI loader/payload' \
	  'make run              Build and verify one normal BIOS QEMU boot' \
	  'make run-uefi         Build and verify one normal UEFI QEMU boot' \
	  'make console          Open an opt-in BIOS serial console in QEMU' \
	  'make console-uefi     Open an opt-in UEFI timer-polled serial console' \
	  'make test-compiler    Run the compiler-only suite (fresh compiler)' \
	  'make test             Run the full native suite (fresh compiler)' \
	  'make smoke-all        Run the existing full emulator suite' \
	  'make test-developer-commands  Check shortcuts with fake tools only' \
	  '' \
	  'run/run-uefi are bounded boot self-tests; console is an experimental serial prompt.' \
	  'Overrides: CXX, UEFI_LD, QEMU, QEMU_DATA, OVMF or OVMF_CODE/OVMF_VARS, OVMF_DIR.' \
	  'See docs/local-development.md for dependencies, scripts and test scope.'

run:
	./scripts/kernel-run.sh bios

run-uefi:
	./scripts/kernel-run.sh uefi

console:
	./scripts/kernel-console.sh

console-uefi:
	./scripts/kernel-uefi-console.sh

kernel-uefi:
	./scripts/kernel-uefi-build.sh

# Synthetic shortcut checks remain outside the native aggregate.
test-developer-commands:
	python3 -B tests/developer-commands.py
	python3 -B -O tests/developer-commands.py
	python3 -B tests/uefi-firmware.py
	python3 -B -O tests/uefi-firmware.py

ifneq ($(strip $(AURORA_TEST_CONTEXT)),)
# The supervisor owns the selected compiler; never rebuild it here.
compiler: aurora-test-context
else
compiler:
	$(MAKE) -C compiler
endif

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
	python3 tests/semantics/run.py "$(AURORAC)"

test-semantics-stress: compiler
	python3 tests/semantics/run.py "$(AURORAC)" --seed 404 --cases 1024

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

test: test-console test-round-robin test-dormant-tables test-uefi-tables test-pin-ledger test-uefi-pins \
    test-storage-model test-compiler test-image test-kernel test-uefi test-acpi test-division test-pci \
    test-unsigned test-uefi-runtime test-uefi-ipc test-uefi-budget test-uefi-dispatch test-uefi-user-phases \
    test-nvme-queues test-uefi-bar test-uefi-span test-uefi-ivrs test-semantics

.PHONY: test-console
test-console: compiler
	AURORAC="$(AURORAC)" ./scripts/kernel-console-tests.sh

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

.PHONY: test-uefi-bar test-uefi-span smoke-uefi-bar smoke-uefi-span test-nvme-queues smoke-nvme-prepare
test-nvme-queues:
	./scripts/kernel-nvme-queue-tests.sh

smoke-nvme-prepare:
	python3 scripts/kernel-uefi-bar-run.py bar-prepare \
	    --output "$${AURORA_NVME_RECEIPTS:?Set a fresh preparation receipt directory}"

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

# Bounded native metadata: use fresh-build provenance or an explicit external pin.
PACKAGE_IDENTITY_COMPILER ?= build/aurorac
PACKAGE_IDENTITY_COMPILER_SHA256 ?=
PACKAGE_IDENTITY_TEST_FLAGS ?=
PACKAGE_IDENTITY_CAP_MIB ?= 128
# The inherited full regression build retains more than 128 MiB. Keep the
# focused gate small while giving the aggregate an explicit bounded ceiling.
test: PACKAGE_IDENTITY_CAP_MIB = 1024
.PHONY: test-package-identity
test-package-identity:
	python3 -B -O tests/compiler/package_identity.py $(abspath $(PACKAGE_IDENTITY_COMPILER)) $(AURORA_TEST_IDENTITY_ARGS) --candidate-cap-mib "$(PACKAGE_IDENTITY_CAP_MIB)" $(PACKAGE_IDENTITY_TEST_FLAGS)

test: test-package-identity

# Versioned declarative metadata only; no resolver, installer or execution authority.
PACKAGE_MANIFEST_COMPILER ?= build/aurorac
PACKAGE_MANIFEST_COMPILER_SHA256 ?=
PACKAGE_MANIFEST_TEST_FLAGS ?=
PACKAGE_MANIFEST_CAP_MIB ?= 256
test: PACKAGE_MANIFEST_CAP_MIB = 1024
.PHONY: test-package-manifest
test-package-manifest:
	python3 -B -O tests/compiler/package_manifest.py $(abspath $(PACKAGE_MANIFEST_COMPILER)) $(AURORA_TEST_IDENTITY_ARGS) --candidate-cap-mib "$(PACKAGE_MANIFEST_CAP_MIB)" $(PACKAGE_MANIFEST_TEST_FLAGS)

test: test-package-manifest

# Bounded exact-manifest consistency and dependency-first ordering; metadata only.
PACKAGE_GRAPH_COMPILER ?= build/aurorac
PACKAGE_GRAPH_COMPILER_SHA256 ?=
PACKAGE_GRAPH_TEST_FLAGS ?=
PACKAGE_GRAPH_CAP_MIB ?= 256
test: PACKAGE_GRAPH_CAP_MIB = 1024
.PHONY: test-package-graph
test-package-graph:
	python3 -B -O tests/compiler/package_graph.py $(abspath $(PACKAGE_GRAPH_COMPILER)) $(AURORA_TEST_IDENTITY_ARGS) --candidate-cap-mib "$(PACKAGE_GRAPH_CAP_MIB)" $(PACKAGE_GRAPH_TEST_FLAGS)

test: test-package-graph

# Real UEFI interrupt-count next-state policy, compiled with the accepted language.
KERNEL_BUDGET_COMPILER ?= build/aurorac
KERNEL_BUDGET_COMPILER_SHA256 ?=
KERNEL_BUDGET_CAP_MIB ?= 128
test: KERNEL_BUDGET_CAP_MIB = 1024
.PHONY: test-kernel-budget-native
test-kernel-budget-native:
	python3 -B -O tests/kernel-budget-native.py --compiler $(abspath $(KERNEL_BUDGET_COMPILER)) $(AURORA_TEST_IDENTITY_ARGS) --candidate-cap-mib "$(KERNEL_BUDGET_CAP_MIB)"

test: test-kernel-budget-native

ROUND_ROBIN_TEST_CAP_MIB ?= 128
test: ROUND_ROBIN_TEST_CAP_MIB = 1024
.PHONY: test-round-robin
test-round-robin: compiler
	ROUND_ROBIN_TEST_CAP_MIB="$(ROUND_ROBIN_TEST_CAP_MIB)" ./scripts/kernel-round-robin-tests.sh $(AURORA_TEST_IDENTITY_ARGS)

# Host-toolchain boot-layout checks need no compiler build or emulator.
.PHONY: test-boot
test-boot:
	python3 -B tests/kernel-boot-image.py
	python3 -B -O tests/kernel-boot-image.py

test: test-boot

# Fixed BIOS single-read capacity and exact ELF/raw layout, including boundaries.
.PHONY: test-boot-capacity smoke-boot-capacity
test-boot-capacity:
	python3 -B tests/kernel-boot-capacity.py
	python3 -B -O tests/kernel-boot-capacity.py

test: test-boot-capacity

smoke-boot-capacity:
	python3 -B tests/kernel-boot-capacity.py --qemu

smoke-all: smoke-boot-capacity

# Resource configuration only; this never substitutes for native behavioral gates.
.PHONY: test-native-cap-contracts
test-native-cap-contracts:
	python3 -B tests/native-cap-contracts.py
	python3 -B -O tests/native-cap-contracts.py

test: test-native-cap-contracts

# Synthetic provenance/dispatch controls; no Aurora/native qualification credit.
.PHONY: test-compiler-contract
test-compiler-contract:
	python3 -B tests/test_compiler_contract.py
	python3 -B -O tests/test_compiler_contract.py

test: test-compiler-contract

# Bounded operational IPC policy shares the immutable run-owned compiler.
IPC_TRANSACTION_COMPILER ?= $(AURORAC)
IPC_TRANSACTION_COMPILER_SHA256 ?=
IPC_TRANSACTION_CAP_MIB ?= 128
test: IPC_TRANSACTION_CAP_MIB = 1024
.PHONY: test-ipc-transaction
test-ipc-transaction: compiler
	AURORAC="$(IPC_TRANSACTION_COMPILER)" IPC_TRANSACTION_CAP_MIB="$(IPC_TRANSACTION_CAP_MIB)" ./scripts/kernel-ipc-transaction-tests.sh $(AURORA_TEST_IDENTITY_ARGS)

test: test-ipc-transaction

# Compiler-free clock argv contracts; never boot QEMU or select a compiler here.
.PHONY: test-emulator-clock
test-emulator-clock:
	PYTHONDONTWRITEBYTECODE=1 python3 tests/kernel-emulator-clock.py
	PYTHONDONTWRITEBYTECODE=1 python3 -O tests/kernel-emulator-clock.py

test: test-emulator-clock

# Compiler-owned Aurora source formatter; focused checks, not native acceptance.
.PHONY: formatter test-formatter test-lint
formatter:
	$(MAKE) -C compiler formatter
test-formatter:
	$(MAKE) -C compiler test-formatter
test-lint:
	$(MAKE) -C compiler test-lint

endif # controlled outer dispatcher / original inner graph
