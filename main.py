"""Entry point: read every case in the input directory and write its forecast to the output directory."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import model  # noqa: E402

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case_file in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(case_file.read_text(encoding="utf-8"))
        forecast = model.forecast(case)
        target = OUTPUT_DIR / (case_file.stem + ".out")
        target.write_text(json.dumps(forecast, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
