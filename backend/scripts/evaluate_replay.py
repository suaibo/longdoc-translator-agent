import argparse
import json
from pathlib import Path


def evaluate(path: Path) -> dict[str, float | int]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    chunks = [item for item in records if item["recordType"] == "chunk"]
    completed = [item for item in chunks if item["status"] == "COMPLETED"]
    risky = [item for item in chunks if item["riskTypes"]]
    return {
        "chunks": len(chunks),
        "completionRate": len(completed) / len(chunks) if chunks else 0,
        "riskRate": len(risky) / len(chunks) if chunks else 0,
        "revisionCount": sum(item["revisionCount"] for item in chunks),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.replay), ensure_ascii=False, indent=2))
