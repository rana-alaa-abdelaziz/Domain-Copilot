import sys
import time

import requests

API_URL = "http://localhost:8000/api/ingest"

def run_ingestion():
    print("Starting full corpus ingestion...")
    try:
        response = requests.post(API_URL)
        if response.status_code == 200:
            data = response.json()
            print(f"Success! {data.get('message')}")
            print(f"Chunks Embedded: {data.get('chunks_embedded')}")
        else:
            print(f"Failed: {response.text}")
    except requests.exceptions.ConnectionError:
        print("Error: Backend server is not running on port 8000.")
        sys.exit(1)

if __name__ == "__main__":
    time.sleep(2) # Give server time to boot if run together
    run_ingestion()
