.PHONY: install uninstall run

install:
	./scripts/install-macos.sh

uninstall:
	./scripts/uninstall-macos.sh

run:
	.venv/bin/python busybar-controller.py
