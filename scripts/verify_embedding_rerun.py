from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.rag.benchmark import verify_selected_rerun


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the selected embedding model rerun")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--rerun", type=Path, required=True)
    args = parser.parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    rerun = json.loads(args.rerun.read_text(encoding="utf-8"))
    evidence = verify_selected_rerun(benchmark, rerun)
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
