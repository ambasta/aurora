# Convenience routes use the configured predecessor-backed Meson graph.
.DEFAULT_GOAL := all

ROOT := $(abspath ..)
BUILD := $(if $(filter /%,$(MESON_BUILD_DIR)),$(MESON_BUILD_DIR),$(ROOT)/$(or $(MESON_BUILD_DIR),build/meson))

.PHONY: all formatter test
all:
	../scripts/watchdog.sh meson compile -C $(BUILD) aurorac
	install -m 755 $(BUILD)/aurorac ../build/aurorac
formatter:
	../scripts/watchdog.sh meson compile -C $(BUILD) aurora-fmt
	install -m 755 $(BUILD)/aurora-fmt ../build/aurora-fmt
test:
	../scripts/watchdog.sh meson test -C $(BUILD) --suite compiler --print-errorlogs
