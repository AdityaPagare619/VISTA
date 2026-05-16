"""Check what YAMNet already knows about crash-related sounds."""
import csv

with open("src/vista/models/yamnet_class_map.csv", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Total YAMNet classes: {len(rows)}")
print()

keywords = [
    "crash", "bang", "explosion", "thump", "impact", "siren",
    "horn", "screech", "skid", "car", "vehicle", "engine",
    "tire", "brake", "alarm", "emergency", "squeal", "smash",
    "glass", "shatter", "crack", "collision"
]

print("Crash-relevant classes YAMNet ALREADY knows:")
print("-" * 50)
for row in rows:
    name = row.get("display_name", "")
    idx = row.get("index", "?")
    if any(k in name.lower() for k in keywords):
        print(f"  [{idx:>3s}] {name}")
