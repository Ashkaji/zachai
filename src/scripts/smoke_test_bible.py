#!/usr/bin/env python3
import sys
import argparse
import requests
import os


def smoke_test_bible(api_url: str, jwt: str) -> bool:
    """
    Verifies GET /v1/bible/verses for Golden Verses (LSG + KJV).
    Exits successfully only when every check returns 200 and the expected snippet matches.
    """
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }

    golden_verses = [
        {"ref": "Jean 3:16", "translation": "LSG", "snippet": "Car Dieu a tant aimé le monde"},
        {"ref": "Genèse 1:1", "translation": "LSG", "snippet": "Au commencement, Dieu créa"},
        {"ref": "John 3:16", "translation": "KJV", "snippet": "For God so loved the world"},
        {"ref": "Genesis 1:1", "translation": "KJV", "snippet": "In the beginning God created"},
    ]

    success_count = 0
    total_count = len(golden_verses)

    print(f"Starting Bible Smoke Test against {api_url}...")

    for golden in golden_verses:
        ref = golden["ref"]
        translation = golden["translation"]
        snippet = golden["snippet"]

        params = {"ref": ref, "translation": translation}

        try:
            response = requests.get(
                f"{api_url}/v1/bible/verses", params=params, headers=headers, timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                raw_verses = data.get("verses", [])
                parts = []
                for v in raw_verses:
                    if isinstance(v, dict):
                        parts.append(str(v.get("text", "")))
                verses_text = " ".join(parts)

                if snippet.lower() in verses_text.lower():
                    print(f"[PASS] {translation} {ref}: Found expected snippet.")
                    success_count += 1
                else:
                    print(f"[FAIL] {translation} {ref}: Snippet mismatch.")
                    print(f"       Expected: {snippet}")
                    print(f"       Got: {verses_text[:100]}...")
            elif response.status_code == 404:
                print(
                    f"[FAIL] {translation} {ref}: Not found (404). "
                    "Ingest this translation or fix the reference."
                )
            else:
                print(f"[FAIL] {translation} {ref}: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[ERROR] {translation} {ref}: {e}")

    print(f"\nSmoke Test Complete: {success_count}/{total_count} passed.")

    if success_count < total_count:
        print(
            "At least one golden verse failed. Fix ingest/data or auth, then re-run. "
            "After re-ingestion with Redis cache enabled, GET should reflect updated text "
            "(generation bump per Story 13.2)."
        )
        return False
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test ZachAI Bible API")
    parser.add_argument("--url", default="http://localhost:8000", help="FastAPI Base URL")
    parser.add_argument("--jwt", help="JWT token for authentication (overrides ZACHAI_TEST_JWT env var)")

    args = parser.parse_args()

    jwt = args.jwt or os.environ.get("ZACHAI_TEST_JWT")
    if not jwt:
        print("Error: JWT is required. Provide it via --jwt or ZACHAI_TEST_JWT environment variable.")
        sys.exit(1)

    base = args.url.rstrip("/")
    success = smoke_test_bible(base, jwt)
    if not success:
        sys.exit(1)
