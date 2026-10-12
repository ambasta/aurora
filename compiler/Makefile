# Convenience routes use the configured predecessor-backed Meson graph.
# Run a focused test directly: meson test -C ../build/meson-compiler NAME
.DEFAULT_GOAL := all

.PHONY: all formatter test
all:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --build-only aurorac --publish-compiler
formatter:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --build-only aurora-fmt --publish-formatter
test:
	python3 -B ../scripts/meson_test.py --repo-root "$(abspath ..)" --suite compiler
