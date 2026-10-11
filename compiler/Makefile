# Convenience routes use the configured predecessor-backed Meson graph.
.DEFAULT_GOAL := all

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
