#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Olivier Ami
# SPDX-License-Identifier: Apache-2.0 OR MIT

set -euo pipefail

patterns=(
  '-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'
  'gh[pousr]_[A-Za-z0-9]{30,}'
  'github_pat_[A-Za-z0-9_]{60,}'
  'AKIA[0-9A-Z]{16}'
  'AIza[0-9A-Za-z_-]{35}'
  'xox[baprs]-[0-9A-Za-z-]{20,}'
)

failed=0
for pattern in "${patterns[@]}"; do
  if matches="$(git grep --untracked -I -l -E -- "$pattern" -- . ':!scripts/scan-secrets.sh')"; then
    echo "Potential credential signature detected in tracked or untracked file(s):" >&2
    echo "$matches" >&2
    failed=1
  else
    grep_status=$?
    if [[ "$grep_status" -ne 1 ]]; then
      echo "Credential scan failed while evaluating a supported signature" >&2
      exit 2
    fi
  fi
done

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "PASS: no supported credential signature found in tracked or untracked text files"
