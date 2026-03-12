import subprocess

print("Step 1: Build dataset from logs")
subprocess.run(["python", "datasets/build_dataset_from_logs.py"])

print("Step 2: Merge datasets")
subprocess.run(["python", "datasets/merge_datasets.py"])

print("Step 3: Run classifier tests")
subprocess.run(["python", "tests/test_classifier.py"])

print("Pipeline finished")