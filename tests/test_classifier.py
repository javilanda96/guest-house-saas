import sys
import os
import json
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import csv
from openai import OpenAI
from config import OPENAI_API_KEY, SYSTEM_CLASSIFIER
from services.openai_client import classify_with_ai

client = OpenAI(api_key=OPENAI_API_KEY)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATASET_PATH = os.path.join(BASE_DIR, "datasets", "message_classification_dataset.csv")


def run_tests():

    dataset_path = Path("datasets/classification_dataset_merged.json")

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    print(f"Loaded {len(dataset)} test cases")

    total = 0
    correct = 0

    for row in dataset:
        message = row["message"]
        expected = row["category"]

        result = classify_with_ai(client, SYSTEM_CLASSIFIER, message)
        predicted = result["category"]

        total += 1

        if predicted == expected:
            correct += 1
            status = "✓"
        else:
            status = "✗"

        print(f"{status} '{message}' → predicted={predicted} expected={expected}")

    print("\n--------------------")
    print(f"Accuracy: {correct}/{total} ({round(correct/total*100,1)}%)")

if __name__ == "__main__":
    run_tests()