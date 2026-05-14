"""
QUORUM Main Orchestrator
=========================
Pipeline entrypoint that wires together the three modules:
  Information Module -> Analytics Module -> Design Module

CHANGELOG (v2 API Integration)
------------------------------
- ADDED: --no-cache flag to force fresh API calls (bypasses cache)
- ADDED: Timing report for each module
- CHANGED: All user-facing error messages prefixed with quorum_chat:
- RETAINED: Module boundary ICD validation architecture

Usage
-----
    python main.py                  # normal run (uses cached API data)
    python main.py --no-cache       # force fresh API calls

The orchestrator enforces ICD validation at each module boundary.
If a contract is violated, the pipeline halts with a clear
quorum_chat: error message explaining what went wrong.
"""

import sys
import time

from .analytics_module import run_analytics_module
from .design_module import run_design_module
from .information_module import run_information_module


def main():
    use_cache = "--no-cache" not in sys.argv

    print("=" * 60)
    print("QUORUM v2: Climate-Migration Risk Assessment Pipeline")
    print("Data Source: HDX HAPI (food security + food prices)")
    print("=" * 60)

    if not use_cache:
        print("\n  [NOTE] Running with --no-cache. All API data will be fetched fresh.")

    t0 = time.time()

    # ── Information Module ─────────────────────────────────────────
    try:
        t1 = time.time()
        monthly, bundle = run_information_module(use_api_cache=use_cache)
        print(f"\n  [TIMING] Information Module: {time.time() - t1:.1f}s")
    except (FileNotFoundError, ValueError) as e:
        print(f"\n{e}")
        print("\nquorum_chat: Information Module failed. The pipeline cannot continue.")
        sys.exit(1)

    # ── Analytics Module ───────────────────────────────────────────
    try:
        t2 = time.time()
        analytics = run_analytics_module(monthly, bundle)
        print(f"\n  [TIMING] Analytics Module: {time.time() - t2:.1f}s")
    except ValueError as e:
        print(f"\n{e}")
        print(
            "\nquorum_chat: Analytics Module failed. "
            "This usually means the HAPI data does not overlap "
            "sufficiently with the migration data. Check your "
            "OVERLAP_YEAR_MIN and OVERLAP_YEAR_MAX in config.py."
        )
        sys.exit(2)

    # ── Design Module ──────────────────────────────────────────────
    try:
        t3 = time.time()
        run_design_module(analytics)
        print(f"\n  [TIMING] Design Module: {time.time() - t3:.1f}s")
    except Exception as e:
        print(f"\nquorum_chat: Design Module encountered an error: {e}")
        print(
            "  The analytical results are still valid. "
            "Check the output directory for partial outputs."
        )

    print(f"\n  [TIMING] Total pipeline: {time.time() - t0:.1f}s")
    print("\nquorum_chat: Pipeline complete. Check quorum_outputs/ for files.")


if __name__ == "__main__":
    main()
