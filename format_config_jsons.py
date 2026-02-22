import json
from pathlib import Path

base = Path(__file__).resolve().parent / "service_trading_crypto" / "config" / "json"
for path in sorted(base.glob("*.json")):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Formatted:", path.name)
