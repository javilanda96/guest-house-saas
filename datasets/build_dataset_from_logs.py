import json

INPUT_FILE = "logs_classifier.txt"
OUTPUT_FILE = "datasets/classification_dataset_from_logs.json"


def parse_line(line):
    try:
        message_part = line.split("message='")[1]
        message = message_part.split("'")[0]

        category_part = line.split("category=")[1]
        category = category_part.split(" |")[0]

        return {
            "message": message,
            "category": category
        }
    except Exception:
        return None


dataset = []
seen = set()

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line in f:
        item = parse_line(line)
        if item:
            key = (item["message"], item["category"])
            if key not in seen:
                seen.add(key)
                dataset.append(item)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(dataset, f, indent=2, ensure_ascii=False)

print(f"Dataset generado con {len(dataset)} ejemplos")