#!/usr/bin/env python3
import sys
import json
import argparse
import requests
import time

def ingest_bible(file_path, api_url, secret, translation, batch_size=100):
    """
    Reads a JSON file of Bible verses and sends them to the ZachAI ingest API.
    
    Expected JSON format:
    [
      { "book": "Jean", "chapter": 3, "verse": 16, "text": "..." },
      ...
    ]
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            verses_raw = json.load(f)
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return

    print(f"Read {len(verses_raw)} verses from {file_path}. Starting ingestion...")

    total_written = 0
    headers = {
        "X-ZachAI-Golden-Set-Internal-Secret": secret,
        "Content-Type": "application/json"
    }

    for i in range(0, len(verses_raw), batch_size):
        batch = verses_raw[i:i+batch_size]
        
        # Add translation to each verse in batch
        payload_verses = []
        for v in batch:
            payload_verses.append({
                "translation": translation,
                "book": v["book"],
                "chapter": v["chapter"],
                "verse": v["verse"],
                "text": v["text"]
            })
            
        payload = {"verses": payload_verses}
        
        try:
            response = requests.post(f"{api_url}/v1/bible/ingest", json=payload, headers=headers)
            if response.status_code == 201:
                data = response.json()
                total_written += data.get("count", 0)
                print(f"Progress: {total_written}/{len(verses_raw)} verses ingested...")
            else:
                print(f"Failed batch {i//batch_size}: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Network error on batch {i//batch_size}: {e}")
            
    print(f"Ingestion complete. Total successfully written: {total_written}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Bible data into ZachAI")
    parser.add_argument("file", help="Path to JSON file containing verses")
    parser.add_argument("--url", default="http://localhost:8000", help="FastAPI Base URL")
    parser.add_argument("--secret", required=True, help="Internal API secret")
    parser.add_argument("--translation", default="LSG", help="Translation code (e.g. LSG, KJV)")
    parser.add_argument("--batch", type=int, default=100, help="Batch size for ingestion")

    args = parser.parse_args()
    
    ingest_bible(args.file, args.url, args.secret, args.translation, args.batch)
