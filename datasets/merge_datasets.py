import json

DATASET_MANUAL = "tests/classification_dataset.json"
DATASET_LOGS = "datasets/classification_dataset_from_logs.json"
OUTPUT_FILE = "datasets/classification_dataset_merged.json"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


dataset_manual = load_json(DATASET_MANUAL)
dataset_logs = load_json(DATASET_LOGS)

combined = dataset_manual + dataset_logs

seen = set()
final_dataset = []

for item in combined:
    key = (item["message"], item["category"])
    if key not in seen:
        seen.add(key)
        final_dataset.append(item)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(final_dataset, f, indent=2, ensure_ascii=False)

print(f"Dataset final generado con {len(final_dataset)} ejemplos")