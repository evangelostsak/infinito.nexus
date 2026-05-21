.ONESHELL:
SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

# SPOT: Global environment is defined in scripts/meta/env/load.sh.
ENV_SH ?= $(CURDIR)/scripts/meta/env/load.sh
export ENV_SH

# For non-interactive bash, BASH_ENV is sourced so the env layer applies to *all* Make recipes.
ifneq ("$(wildcard $(ENV_SH))","")
export BASH_ENV := $(ENV_SH)
else
$(error Missing env file: $(ENV_SH))
endif

.PHONY: act-all
# Run all act-based deploy checks.
act-all:
	@bash scripts/tests/deploy/act/all.sh

.PHONY: act-app
# Run the act-based app deploy check.
act-app:
	@bash scripts/tests/deploy/act/app.sh

.PHONY: act-workflow
# Run the act-based workflow deploy check.
act-workflow:
	@bash scripts/tests/deploy/act/workflow.sh

.PHONY: install-agent
# Install OS-level sandbox dependencies (bubblewrap, socat) required by the Claude Code sandbox.
install-agent:
	@bash scripts/install/sandbox.sh

.PHONY: security-apparmor-restore
# Restore AppArmor profiles.
security-apparmor-restore:
	@echo "==> AppArmor: restore profiles"
	@if grep -q '^[Yy1]' /sys/module/apparmor/parameters/enabled 2>/dev/null; then \
		sudo bash scripts/system/apparmor/restore.sh; \
	else \
		echo "[apparmor] AppArmor module is not loaded — skipping restore"; \
	fi

.PHONY: security-apparmor-teardown
# Tear down AppArmor for local development.
security-apparmor-teardown:
	@echo "==> AppArmor: full teardown (local dev)"
	@if grep -q '^[Yy1]' /sys/module/apparmor/parameters/enabled 2>/dev/null; then \
		sudo bash scripts/system/apparmor/teardown.sh; \
	else \
		echo "[apparmor] AppArmor module is not loaded — skipping teardown"; \
	fi

.PHONY: autoformat
# Auto-format all source files (skips tools that are not installed).
autoformat: install-lint
	@bash scripts/lint/wrapper.sh autoformat

.PHONY: bootstrap
# Install dependencies and prepare the project.
bootstrap: install setup

.PHONY: build
# Build the local image.
build: fix-dockerignore
	@IMAGE_TAG="$$(bash scripts/meta/resolve/image/local.sh)" \
		bash scripts/image/build.sh

.PHONY: build-cleanup
# Clean up image artifacts.
build-cleanup:
	@bash scripts/image/cleanup.sh

.PHONY: build-dependency
# Pull the build dependency image.
build-dependency:
	@docker pull ghcr.io/kevinveenbirkenbach/pkgmgr-$${INFINITO_DISTRO}:stable

.PHONY: build-missing
# Build the local image if it is missing.
build-missing:
	@IMAGE_TAG="$$(bash scripts/meta/resolve/image/local.sh)" \
		bash scripts/image/build.sh --missing

.PHONY: build-no-cache
# Build the local image without cache.
build-no-cache: build-dependency
	@IMAGE_TAG="$$(bash scripts/meta/resolve/image/local.sh)" \
		bash scripts/image/build.sh --no-cache

.PHONY: build-no-cache-all
# Build the no-cache image for every distro.
build-no-cache-all:
	@set -euo pipefail; \
	for d in $${INFINITO_DISTROS}; do \
		echo "=== build-no-cache: $$d ==="; \
		INFINITO_DISTRO="$$d" "$(MAKE)" build-no-cache; \
	done

.PHONY: clean-cache
# Wipe on-disk caches under /var/cache/infinito/core/cache/ (stops cache containers first; re-run `make compose-up` to recreate).
clean-cache:
	@bash scripts/system/cache/clean.sh

.PHONY: fix-chmod
# Mark all shell scripts under scripts/ as executable.
fix-chmod:
	@find scripts/ -name "*.sh" -exec chmod +x {} \;

.PHONY: clean
# Remove ignored files from the working tree; falls back to sudo for container-owned __pycache__/*.pyc, warns and continues if both fail.
clean:
	@echo "Removing ignored git files"
	@if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then \
		if ! git clean -fdX; then \
			echo "git clean failed (likely container-owned files). Retrying with sudo..."; \
			sudo -n git clean -fdX || { \
				echo "WARNING: sudo cleanup also failed; continuing"; \
				exit 0; \
			}; \
		fi; \
	else \
		echo "WARNING: not inside a git repository -> skipping 'git clean -fdX'"; \
		echo "WARNING: (cleanup continues)"; \
	fi

.PHONY: clean-pycache-dirs
# Remove tracked directories whose only child is a __pycache__ folder (orphans left after moving / deleting source files).
clean-pycache-dirs:
	@"$${PYTHON}" -m utils.cleanup.pycache_only_dirs

.PHONY: clean-sudo
# Remove ignored files from the working tree with sudo.
clean-sudo:
	@echo "Removing ignored git files with sudo"
	sudo git clean -fdX;

.PHONY: console
# Interactive REPL for the infinito.nexus CLI, running on the host. Each line is forwarded to `python -m cli`; Ctrl+C only cancels the current input — exit with `exit`, `quit`, or Ctrl+D.
console:
	@"$${PYTHON}" -m cli.console

.PHONY: container-purge-entity
# Purge one or more app entities from the container.
container-purge-entity:
	@bash scripts/tests/deploy/local/purge/entity.sh

.PHONY: container-purge-system
# Purge the broader container-level deploy artifacts.
container-purge-system: container-purge-entity
	@bash scripts/tests/deploy/local/purge/inventory.sh
	@bash scripts/tests/deploy/local/purge/web.sh
	@bash scripts/tests/deploy/local/purge/lib.sh

.PHONY: container-refresh-inventory
# Refresh the container inventory without deploying apps.
container-refresh-inventory:
	@bash scripts/tests/deploy/local/reset/inventory.sh

.PHONY: deploy
# Run the local deploy router. Args: mode=initialize|reinstall|update (default initialize), apps=<csv>, purge=true|false (default false), type=server|workstation|universal (default from default.env), bundles=<csv>, disabled=<csv>, full_cycle=true|false. Example: `make deploy mode=reinstall apps=web-app-matomo full_cycle=true`. See scripts/tests/deploy/local/deploy/main.sh for the full table.
deploy:
	@$(if $(apps),INFINITO_APPS="$(apps)") \
	 $(if $(mode),INFINITO_DEPLOY_MODE="$(mode)") \
	 $(if $(purge),INFINITO_PURGE_ENTITIES="$(purge)") \
	 $(if $(type),INFINITO_DEPLOY_TYPE="$(type)") \
	 $(if $(bundles),INFINITO_BUNDLES="$(bundles)") \
	 $(if $(disabled),INFINITO_SERVICES_DISABLED="$(disabled)") \
	 $(if $(full_cycle),INFINITO_FULL_CYCLE="$(full_cycle)") \
	 bash scripts/tests/deploy/local/deploy/main.sh

.PHONY: diagnose-network
# Run the network-diagnose script inside the infinito container (DNS/TCP/TLS/PMTU v4+v6).
diagnose-network:
	@$(MAKE) compose-exec INFINITO_CMD="python3 -m cli.contributing.network.diagnose"

.PHONY: network-ipv6-disable
# Disable IPv6 for local development.
network-ipv6-disable:
	@sudo bash scripts/system/network/ipv6/disable.sh
	@"$(MAKE)" network-refresh

.PHONY: network-dns-remove
# Remove the DNS configuration.
network-dns-remove:
	@bash scripts/system/network/dns/remove.sh

.PHONY: network-dns-setup
# Configure DNS on Linux.
network-dns-setup: wsl2-dns-setup
	@bash scripts/system/network/dns/setup/linux.sh

.PHONY: fix-dockerignore
# Regenerate .dockerignore from .gitignore (which carries the .git entry Docker needs). Race-safe under parallel make setup invocations.
fix-dockerignore:
	@echo "Create .dockerignore"
	cat .gitignore > .dockerignore

.PHONY: dotenv
# Regenerate .env (SPOT) from default.env + runtime context (distro, cache sizes, secrets, ...).
dotenv:
	@python3 -m cli.meta.env

.PHONY: dotenv-force
# Force a clean .env regeneration in a stripped env (avoids stale BASH_ENV INFINITO_* values pinning via setdefault).
dotenv-force:
	@rm -f .env
	@env -i HOME="$${HOME}" PATH="$${PATH}" python3 -m cli.meta.env

.PHONY: compose-down
# Stop the development stack.
compose-down:
	@"$${PYTHON}" -m cli.administration.deploy.development down

.PHONY: environment-bootstrap
# Bootstrap the local development environment.
environment-bootstrap: wsl2-systemd-check install-python-dev install-lint security-apparmor-teardown network-dns-setup network-ipv6-disable

.PHONY: environment-teardown
# Tear down the local development environment.
environment-teardown: security-apparmor-restore network-dns-remove network-ipv6-restore

.PHONY: compose-exec
# Run a shell (`make compose-exec`) or command (`make compose-exec INFINITO_CMD="..."`) in the running container.
compose-exec:
	@bash scripts/tests/deploy/local/exec/container.sh

.PHONY: help
# Print every Make target with the description from its preceding comment line.
help:
	@bash scripts/make/help.sh

.PHONY: install
# Install all runtime dependencies, incremental via a stamp file (see scripts/install/all.sh).
install:
	@bash scripts/install/all.sh

.PHONY: install-ansible
# Install Ansible dependencies.
install-ansible:
	@ANSIBLE_COLLECTIONS_DIR="$(HOME)/.ansible/collections" \
	bash scripts/install/ansible.sh

.PHONY: install-force
# Force a full reinstall (drop the stamp and rebuild it).
install-force:
	@bash scripts/install/all.sh --force

.PHONY: install-lint
# Install lint deps (host/docker via INFINITO_LINT_RUNNER, per-env stamp).
install-lint:
	@bash scripts/install/wrapper.sh

.PHONY: install-lint-force
# Force a full lint reinstall (drop the per-env stamp and rebuild it).
install-lint-force:
	@bash scripts/install/wrapper.sh --force

.PHONY: install-python
# Install Python tooling.
install-python: install-venv
	@bash scripts/install/python.sh

.PHONY: install-python-dev
# Install Python tooling including lint and dev dependencies.
install-python-dev: install-python
	@bash scripts/install/python.sh dev
	@bash scripts/install/pre-commit.sh

.PHONY: install-skills
# Install agent skills from skills-lock.json.
install-skills:
	@bash scripts/install/skills/install.sh

.PHONY: install-system-python
# Install the system Python prerequisites.
install-system-python:
	@bash roles/dev-python/files/install.sh ensure

.PHONY: install-venv
# Install the virtual environment.
install-venv: install-system-python
	@bash scripts/install/venv.sh

.PHONY: lint
# Run all lint checks in parallel (per-check host/docker via INFINITO_LINT_RUNNER).
lint: install-lint
	@bash scripts/make/parallel.sh lint-action \
		lint-ansible \
		lint-javascript \
		lint-makefile \
		lint-markdown \
		lint-python \
		lint-shellcheck

.PHONY: lint-action
# Run the GitHub Actions lint checks.
lint-action: install-lint
	@bash scripts/lint/wrapper.sh action

.PHONY: lint-ansible
# Run Ansible lint checks (syntax-check + ansible-lint).
lint-ansible: install-lint setup
	@bash scripts/lint/wrapper.sh ansible

.PHONY: lint-javascript
# Run ESLint over the project's JavaScript files (Playwright specs + persona helpers).
lint-javascript: install-lint
	@bash scripts/lint/wrapper.sh javascript

.PHONY: lint-makefile
# Run checkmake against the Makefile.
lint-makefile: install-lint
	@bash scripts/lint/wrapper.sh makefile

.PHONY: lint-markdown
# Run Markdown lint checks via markdownlint-cli2.
lint-markdown: install-lint
	@bash scripts/lint/wrapper.sh markdown

.PHONY: lint-python
# Run Python lint checks.
lint-python: install-lint
	@bash scripts/lint/wrapper.sh python

.PHONY: lint-shellcheck
# Run shellcheck lint checks.
lint-shellcheck: install-lint
	@bash scripts/lint/wrapper.sh shellcheck

.PHONY: meta-list
# Print the repository role list.
meta-list:
	@echo "Generating the roles list"
	@"$${PYTHON}" -m cli.build.list

.PHONY: meta-mig
# Build the meta graph inputs.
meta-mig: meta-list meta-tree
	@echo "Creating meta data for meta infinity graph"

.PHONY: network-refresh
# Refresh the running development stack only when it already exists.
network-refresh:
	@bash scripts/system/network/docker/stack_refresh.sh

.PHONY: compose-restart
# Restart the development stack.
compose-restart:
	@"$${PYTHON}" -m cli.administration.deploy.development restart

.PHONY: network-ipv6-restore
# Restore IPv6 settings.
network-ipv6-restore:
	@sudo bash scripts/system/network/ipv6/restore.sh
	@"$(MAKE)" network-refresh

.PHONY: compose-inner-run
# Run a one-off `docker run` inside the running container.
compose-inner-run:
	@bash scripts/tests/deploy/local/exec/run.sh

.PHONY: setup
# Run the setup step after generating .dockerignore.
setup: fix-dockerignore dotenv
	@bash scripts/setup.sh

.PHONY: setup-clean
# Run setup after cleaning ignored files.
setup-clean: clean setup
	@echo "Full build with cleanup before was executed."

.PHONY: compose-stop
# Stop the development stack without removing volumes.
compose-stop:
	@"$${PYTHON}" -m cli.administration.deploy.development stop

.PHONY: diagnose-disk-usage
# Show disk and Docker resource usage to identify what to clean up.
diagnose-disk-usage:
	@bash scripts/system/meta/disk-usage.sh

.PHONY: system-purge
# Run the broad low-hardware cleanup routine.
system-purge:
	@bash scripts/system/purge/system.sh

.PHONY: test
# Run the full test pipeline (lint + tests) in parallel; fail-fast.
test: install install-lint
	@bash scripts/make/parallel.sh \
		lint \
		test-external \
		test-integration \
		test-lint \
		test-unit

.PHONY: test-external
# Run the external test suite.
test-external: install
	@INFINITO_TEST_TYPE="external" \
	INFINITO_COMPILE=0 \
	bash scripts/tests/code/wrapper.sh

.PHONY: test-integration
# Run the integration test suite.
test-integration: install
	@INFINITO_TEST_TYPE="integration" \
	INFINITO_COMPILE=0 \
	bash scripts/tests/code/wrapper.sh

.PHONY: test-lint
# Run the lint test suite.
test-lint: install
	@INFINITO_TEST_TYPE="lint" \
	INFINITO_COMPILE=0 \
	bash scripts/tests/code/wrapper.sh

.PHONY: test-signed
# Verify HEAD is signed (`git log %G?` returns N for unsigned); gates the pre-push hook against unsigned tips.
test-signed:
	@status="$$(git log -1 --pretty=%G?)"; \
	if [ "$$status" = "N" ]; then \
		echo "❌ HEAD commit is not signed. Use 'git-sign-push' or 'git commit -S'." >&2; \
		exit 1; \
	fi; \
	echo "✅ HEAD commit signature status: $$status"

.PHONY: test-unit
# Run the unit test suite.
test-unit: install
	@INFINITO_TEST_TYPE="unit" \
	INFINITO_COMPILE=0 \
	bash scripts/tests/code/wrapper.sh

.PHONY: meta-tree
# Print the repository tree.
meta-tree:
	@echo "Generating Tree"
	@"$${PYTHON}" -m cli.build.tree -D 2

.PHONY: network-trust-ca
# Trust the local CA on Linux and WSL2.
network-trust-ca:
	@bash scripts/system/tls/trust/linux.sh
	@bash scripts/system/tls/trust/wsl2.sh

.PHONY: compose-up
# Start the development stack.
compose-up: install
	@"$${PYTHON}" -m cli.administration.deploy.development up

.PHONY: update-skills
# Update all agent skills to latest versions and refresh skills-lock.json.
update-skills:
	@bash scripts/install/skills/update.sh

.PHONY: wsl2-dns-setup
# Set up DNS on WSL2.
wsl2-dns-setup:
	@sudo bash scripts/system/network/dns/setup/wsl.sh

.PHONY: wsl2-systemd-check
# Enable systemd on WSL2.
wsl2-systemd-check:
	@bash scripts/system/systemd/enable/wsl2.sh

.PHONY: wsl2-trust-windows
# Trust Windows certificates in WSL2.
wsl2-trust-windows:
	@bash scripts/system/tls/trust/wsl2.sh
