import json
from pathlib import Path

root_path = Path("/home/user/GitChameleonBenchmark/persisted_data")
ds_path = Path("/home/user/GitChameleonBenchmark/dataset/dataset.jsonl")

ds = [ json.loads(x) for x in open(ds_path).readlines()]
ds_dict = {d["example_id"]: d for d in ds}

count_notser = 0
count_notser_webdev = 0


for filepath in root_path.iterdir():
    try:
        json.load(open(filepath))

        content = open(filepath).read()
        if "at 0x" in content:
            count_notser += 1
            example_id = filepath.name.split(".")[0]
            d = ds_dict[example_id]
            if d["webdev"] != 0:
                count_notser_webdev +=1


    except Exception as e:
        print(f"Failed to load file {filepath}: {e}")


print(f"Count not ser: {count_notser}")
print(f"Count not ser webdev: {count_notser_webdev}")