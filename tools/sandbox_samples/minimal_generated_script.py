import json
import sys
from pathlib import Path


def main():
    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "success": True,
        "input_file": str(input_file),
        "message": "sandbox smoke test completed",
        "charts": [],
    }

    with (output_dir / "analysis_result.json").open("w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)

    with (output_dir / "report_data.json").open("w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
