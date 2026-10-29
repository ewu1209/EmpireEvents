#!/usr/bin/env bash
# Store (or rotate) the OfficeRnD API credentials in Google Secret Manager.
# Input is hidden and piped straight to gcloud: nothing is echoed, logged, or written to disk.
# Usage: scripts/set-secrets.sh [PROJECT_ID]
set -euo pipefail
PROJECT="${1:-$(gcloud config get project 2>/dev/null)}"
[ -n "$PROJECT" ] || { echo "No project: pass one or run 'gcloud config set project …'" >&2; exit 1; }

put() { # name prompt
  local value
  printf '%s: ' "$2"; IFS= read -rs value; echo
  [ -n "$value" ] || { echo "Empty value, aborting." >&2; exit 1; }
  if gcloud secrets describe "$1" --project="$PROJECT" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$1" --project="$PROJECT" --data-file=- >/dev/null
  else
    printf '%s' "$value" | gcloud secrets create "$1" --project="$PROJECT" --replication-policy=automatic --data-file=- >/dev/null
  fi
  unset value
  echo "  stored $1"
}

echo "Project: $PROJECT"
put officernd-client-id "OfficeRnD client ID"
put officernd-client-secret "OfficeRnD client secret"

# Let the function's runtime service account read them: the dedicated one if it exists, else the default.
SA="empire-events-fn@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$SA" --project="$PROJECT" >/dev/null 2>&1 ||
  SA="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for s in officernd-client-id officernd-client-secret; do
  gcloud secrets add-iam-policy-binding "$s" --project="$PROJECT" \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor >/dev/null
done
echo "Done. $SA can read both secrets."
