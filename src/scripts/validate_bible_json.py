#!/usr/bin/env python3
import json
import argparse
import os
import re

def extract_aliases_from_main(main_path):
    """
    Stupid simple parser to extract _BIBLE_BOOK_ALIASES from main.py without importing it.
    Imports are dangerous due to transitive deps and path issues.
    """
    if not os.path.exists(main_path):
        return {}
    
    with open(main_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    match = re.search(r"_BIBLE_BOOK_ALIASES: dict\[str, str\] = \{(.*?)\}", content, re.DOTALL)
    if not match:
        return {}
        
    inner = match.group(1)
    aliases = {}
    # Match "key": "value"
    for m in re.finditer(r'"([^"]+)"\s*:\s*"([^"]+)"', inner):
        aliases[m.group(1).lower()] = m.group(2)
    return aliases

def validate_bible_json(json_path, main_path):
    if not os.path.exists(json_path):
        print(f"Error: JSON file {json_path} not found.")
        return False

    with open(json_path, 'r', encoding='utf-8') as f:
        verses = json.load(f)

    aliases = extract_aliases_from_main(main_path)
    if not aliases:
        print(f"Warning: Could not extract aliases from {main_path}. Skipping book name validation.")
    
    errors = []
    
    # Check book names (AC #3)
    found_books = set()
    for i, v in enumerate(verses):
        book = v.get("book", "").strip()
        found_books.add(book)
        
        # Check if book is valid
        if aliases:
            normalized_key = re.sub(r"\s+", " ", book.lower())
            if normalized_key not in aliases and book not in aliases.values():
                errors.append(f"Verse {i}: Unknown book name '{book}'")

    print(f"Validated {len(verses)} verses across {len(found_books)} unique books.")

    # Smoke test (AC #4)
    golden_verses = [
        {"book": "John", "chapter": 3, "verse": 16, "snippet": "For God so loved the world"},
        {"book": "Jean", "chapter": 3, "verse": 16, "snippet": "Car Dieu a tant aimé le monde"},
        {"book": "Genesis", "chapter": 1, "verse": 1, "snippet": "In the beginning God created"},
        {"book": "Genèse", "chapter": 1, "verse": 1, "snippet": "Au commencement, Dieu créa"}
    ]
    
    found_golden = []
    for golden in golden_verses:
        match = None
        for v in verses:
            if v["book"] == golden["book"] and v["chapter"] == golden["chapter"] and v["verse"] == golden["verse"]:
                match = v
                break
        
        if match:
            if golden["snippet"].lower() in match["text"].lower():
                found_golden.append(f"Found Golden Verse: {golden['book']} {golden['chapter']}:{golden['verse']}")
            else:
                errors.append(f"Golden Verse {golden['book']} {golden['chapter']}:{golden['verse']} text mismatch. Expected snippet: '{golden['snippet']}'")
        # Don't error if not found, as a single file might only contain one translation
        
    for msg in found_golden:
        print(msg)

    if errors:
        print(f"\nValidation FAILED with {len(errors)} errors:")
        for err in errors[:10]: # Limit output
            print(f" - {err}")
        if len(errors) > 10:
            print(f" ... and {len(errors)-10} more errors.")
        return False
    else:
        print("\nValidation PASSED!")
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate ZachAI Bible JSON integrity")
    parser.add_argument("file", help="Path to JSON file to validate")
    parser.add_argument("--main-py", default="src/api/fastapi/main.py", help="Path to main.py for book aliases")
    args = parser.parse_args()
    
    success = validate_bible_json(args.file, args.main_py)
    if not success:
        exit(1)
