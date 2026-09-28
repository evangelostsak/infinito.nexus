#!/usr/bin/env bash
# Exception: the state is tagged rather than printed bare. Ansible allocates a
# pty whenever become needs a password, and a pty merges stderr into stdout, so
# a caller matching the whole stream would read login noise as the answer.
set -eu
: "${DIR_VAR_LIB:?DIR_VAR_LIB required}"

if grep -qF " ${DIR_VAR_LIB} " /proc/self/mountinfo; then
  echo "STATE=mounted"
elif [ -d "${DIR_VAR_LIB}" ] && [ -n "$(ls -A "${DIR_VAR_LIB}" 2>/dev/null)" ]; then
  echo "STATE=has-local-data"
  ls -A "${DIR_VAR_LIB}" 2>/dev/null | head -20
else
  echo "STATE=empty"
fi
