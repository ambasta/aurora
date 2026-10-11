# Convenience routes use only the configured, predecessor-backed Meson graph.
# There is no C++ seed build or legacy sealed inner graph.
override .DEFAULT_GOAL := all
ifneq ($(strip $(foreach name,MAKECMDGOALS CURDIR MAKEFILE_LIST,$(if $(filter command,$(origin $(name))),$(name)))),)
$(error Make goal, directory, and makefile-list overrides are unsupported)
endif
override _AURORA_TEST_GOALS := $(if $(MAKECMDGOALS),$(MAKECMDGOALS),all)

# Export only supplied controls; configured Meson options remain authoritative.
# Historical output aliases cannot select a different compiler.
override _AURORA_USER_CONTROLS := MESON_BUILD_DIR AURORA_BUILD_JOBS AURORA_TEST_JOBS CXX CXXFLAGS IR_TEST_CXXFLAGS IR_TEST_BUILD_PREFIX OUT FORMAT_OUT AURORAC CPPFLAGS LDFLAGS UEFI_LD \
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
override _AURORA_CAP_CONTROLS := AURORA_BUILD_JOBS AURORA_TEST_JOBS PACKAGE_IDENTITY_CAP_MIB PACKAGE_MANIFEST_CAP_MIB PACKAGE_GRAPH_CAP_MIB KERNEL_BUDGET_CAP_MIB ROUND_ROBIN_TEST_CAP_MIB IPC_TRANSACTION_CAP_MIB
override _AURORA_CAP_EMPTY :=
override _AURORA_CAP_SPACE := $(_AURORA_CAP_EMPTY) $(_AURORA_CAP_EMPTY)
override _AURORA_CAP_TAB := $(_AURORA_CAP_EMPTY)	$(_AURORA_CAP_EMPTY)
override _AURORA_BAD_CAPS := $(foreach name,$(_AURORA_CAP_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(if $(value $(name)),$(if $(subst 9,,$(subst 8,,$(subst 7,,$(subst 6,,$(subst 5,,$(subst 4,,$(subst 3,,$(subst 2,,$(subst 1,,$(subst 0,,$(subst $(_AURORA_CAP_TAB),x,$(subst $(_AURORA_CAP_SPACE),x,$(value $(name)))))))))))))),$(name)),$(name))))
ifneq ($(strip $(_AURORA_BAD_CAPS)),)
$(error cap overrides must be unsigned decimal integers; invalid controls: $(_AURORA_BAD_CAPS))
endif

# Output selectors belonged to the removed hand-written build graph. Reject even
# empty supplied values, before Make can expand them during export.
override _AURORA_UNSUPPORTED_CONTROLS := OUT FORMAT_OUT AURORAC LEXER_EVENTS AURORA_TEST_CONTEXT AURORA_TEST_MODE AURORA_TEST_COMPILER AURORA_TEST_IDENTITY_ARGS
override _AURORA_BAD_CONTROLS := $(foreach name,$(_AURORA_UNSUPPORTED_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(name)))
ifneq ($(strip $(_AURORA_BAD_CONTROLS)),)
$(error unsupported legacy compiler controls: $(strip $(_AURORA_BAD_CONTROLS)); use a configured MESON_BUILD_DIR; outputs are build/aurorac and build/aurora-fmt)
endif

$(foreach name,$(_AURORA_USER_CONTROLS),$(if $(filter undefined default,$(origin $(name))),,$(eval export $(name))))

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
ifneq ($(words $(_AURORA_TEST_GOALS)),1)
$(error invoke one compiler build or test goal at a time; mixed goals are unsupported)
endif


.PHONY: all formatter test
all:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --build-only aurorac --publish-compiler
formatter:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --build-only aurora-fmt --publish-formatter
test:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --suite compiler

.PHONY: test-modules
test-modules:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests modules source-depth host-sources-tests host-output-tests

.PHONY: test-storage
test-storage:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests storage-binary xfs-offline-native

.PHONY: test-initialization-facts
test-initialization-facts:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests initialization-facts

.PHONY: test-utf8
test-utf8:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests utf8

.PHONY: test-utf8-encoding
test-utf8-encoding:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests utf8-encoding

.PHONY: test-xfs-geometry
test-xfs-geometry:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests xfs-geometry

.PHONY: test-xfs-root
test-xfs-root:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests xfs-root xfs-root-api xfs-root-entry

.PHONY: test-utf8-range
test-utf8-range:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests utf8-range

.PHONY: test-utf8-lines
test-utf8-lines:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests utf8-lines

.PHONY: test-function-overloads
test-function-overloads:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests function-overloads

.PHONY: test-readonly-windows
test-readonly-windows:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests readonly-windows readonly-windows-ir readonly-windows-ir-native

.PHONY: test-short-circuit
test-short-circuit:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests short-circuit short-circuit-ir short-circuit-ir-native

.PHONY: test-token-scan
test-token-scan:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests token-scan

.PHONY: test-json
test-json:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests json-profile json-owned

.PHONY: test-json-codecs
test-json-codecs:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests json-codecs

.PHONY: test-json-integers
test-json-integers:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests json-integers

.PHONY: test-json-lookup
test-json-lookup:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests json-lookup

.PHONY: test-borrowed-objects
test-borrowed-objects:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests borrowed-objects borrowed-objects-ir borrowed-objects-abi

.PHONY: test-json-string-write
test-json-string-write:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests json-string-write

.PHONY: test-console-service
test-console-service:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests console-service-source-native console-service-ir console-session

.PHONY: test-display-service
test-display-service:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests display-service-source-native display-service-ir

.PHONY: test-iommu-event-service
test-iommu-event-service:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests iommu-event-source-native iommu-event-session

.PHONY: test-formatter
test-formatter:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests hosted-lexer-format hosted-lexer-format-cli

.PHONY: test-lint
test-lint:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --tests semantic-lint
