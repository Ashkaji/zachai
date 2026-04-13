#!/usr/bin/env python3
import json
import argparse
import os
import re
import xml.etree.ElementTree as ET

# Zefania `bname` (lowercased, whitespace-normalized) → JSON `book` string that
# `_BIBLE_BOOK_ALIASES` / `validate_bible_json.py` accept (French where listed in
# main.py; otherwise English canonical where the French XML label is absent there).
LSG_BNAME_MAP = {
    "psaumes": "Psalm",
    "proverbes": "Proverbs",
    "ecclésiaste": "Ecclesiastes",
    "ecclesiaste": "Ecclesiastes",
    "abdias": "Obadiah",
    "michée": "Micah",
    "michee": "Micah",
    "habacuc": "Habakkuk",
    "philémon": "Philemon",
    "philemon": "Philemon",
    "joël": "Joel",
}


def _map_lsg_bname(bname):
    if not bname or not str(bname).strip():
        return bname or ""
    raw = str(bname).strip()
    key = re.sub(r"\s+", " ", raw.lower())
    return LSG_BNAME_MAP.get(key, raw)


def convert_lsg(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} not found.")
        return

    try:
        tree = ET.parse(input_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return

    verses = []
    
    # Zefania XML structure: XMLBIBLE -> BIBLEBOOK -> CHAPTER -> VERS
    for book in root.findall('BIBLEBOOK'):
        book_name = _map_lsg_bname(book.get('bname'))
        for chapter in book.findall('CHAPTER'):
            chapter_num = int(chapter.get('cnumber'))
            for verse in chapter.findall('VERS'):
                verse_num = int(verse.get('vnumber'))
                text = verse.text if verse.text else ""
                
                verses.append({
                    "book": book_name,
                    "chapter": chapter_num,
                    "verse": verse_num,
                    "text": text.strip()
                })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(verses, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(verses)} verses to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert LSG XML to ZachAI JSON")
    parser.add_argument("input", help="Path to raw LSG XML file")
    parser.add_argument("output", help="Path to output JSON file")
    args = parser.parse_args()
    
    convert_lsg(args.input, args.output)
