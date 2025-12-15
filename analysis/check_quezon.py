import json

def check_quezon():
    with open("static/data/20th_congress_representatives.json", "r") as f:
        data = json.load(f)
        
    for item in data:
        if "Quezon" in item.get("province", ""):
            print(item)

if __name__ == "__main__":
    check_quezon()
