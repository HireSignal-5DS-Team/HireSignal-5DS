#!/usr/bin/env bash
# HireSignal QA suite, MOCK mode: no model, no LLM server, no network. Safe in compute window 0.
#   tests/qa/run_qa.sh            existing tests (matcher, benchmark) + S5 QA tests; summary in docs/qa/last_run_mock.txt
#   tests/qa/run_qa.sh --live     additionally runs tests/live (needs HS_LIVE=1 and running servers; window 1+ only)
# A strict xfail is an open defect (docs/qa/FAILURES.md). An XPASS fails the run: the defect is fixed, remove its marker.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=docs/qa/last_run_mock.txt
LIVE=0; if [[ "${1:-}" == "--live" ]]; then LIVE=1; shift; fi

echo "== HireSignal QA (MOCK backends: results are not model results) =="
set +e
python -m pytest matcher benchmark/tests tests/qa -q -rxXs -p no:cacheprovider "$@" | tee /tmp/hs_qa_mock.$$
rc=${PIPESTATUS[0]}
set -e
{
  echo "label: MOCK (scripted backends, stub HTTP servers, keyword NLI stand-in; no model weights)"
  echo "commit: $(git rev-parse --short HEAD)  date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "defects reproduced (strict xfail):"
  grep -oE 'QA-[0-9]{3} \(owner S[0-9]\)' /tmp/hs_qa_mock.$$ | sort | uniq -c || true
  tail -n 1 /tmp/hs_qa_mock.$$
} > "$OUT"
rm -f /tmp/hs_qa_mock.$$
cat "$OUT"

if [[ $LIVE == 1 ]]; then
  echo "== LIVE suite (real models; provenance in \$HS_LIVE_OUT or tests/live/out/) =="
  HS_LIVE="${HS_LIVE:-1}" python -m pytest tests/live -q -rxXs -p no:cacheprovider || rc=$?
fi
exit $rc
