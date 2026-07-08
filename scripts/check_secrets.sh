#!/usr/bin/env bash
# Pre-push secret grep. Fails if a likely secret or a banned source is staged.
set -euo pipefail

staged=$(git diff --cached --name-only)
[ -z "$staged" ] && exit 0

# Never commit real API keys, or any Consensus output (paid, non-redistributable).
if git diff --cached | grep -nEi '(sk-ant-[a-z0-9-]{20,}|api[_-]?key\s*=\s*["'\''][a-z0-9-]{16,}|consensus\.app)'; then
  echo "❌ Blocked: possible secret or Consensus output in staged changes. Remove before committing."
  exit 1
fi
echo "✅ secret scan clean"
