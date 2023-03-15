PREFIX := /usr/local/bin
CONFIG_PREFIX := /etc

TCLS := example.tcl u250.tcl u280.tcl

INSTALL_SCRIPT := $(PREFIX)/fpga-util.py
INSTALL_FILES := $(CONFIG_PREFIX)/fpga-util/mapping $(foreach tcl,$(TCLS),$(CONFIG_PREFIX)/fpga-util/$(tcl))

.PHONY: $(INSTALL_SCRIPT)

$(INSTALL_SCRIPT): $(PREFIX)/% : %
	mkdir -p $(@D)
	cp -a $^ $@
	sed -iE 's|^# MAKEFILE_EXTENSION.*$$|mappingSearchPath.append("$(CONFIG_PREFIX)/fpga-util/mapping")|' $@
	chmod +x $@

$(INSTALL_FILES): $(CONFIG_PREFIX)/fpga-util/% : %
	mkdir -p $(@D)
	cp -a $^ $@

install: $(INSTALL_SCRIPT) $(INSTALL_FILES)

uninstall:
	rm -f $(INSTALL_SCRIPT)
	rm -f $(INSTALL_FILES)
	rm -fr $(CONFIG_PREFIX)/fpga-util

