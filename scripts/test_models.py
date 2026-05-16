import os
import requests
from dotenv import load_dotenv

load_dotenv("src/vista/.env")
api_key = os.environ.get("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
r = requests.get(url)
print("STATUS:", r.status_code)
if r.status_code == 200:
    data = r.json()
    for m in data.get("models", []):
        print(m.get("name"))
else:
    print(r.text)
