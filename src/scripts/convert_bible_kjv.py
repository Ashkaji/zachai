#!/usr/bin/env python3
import re
import json
import argparse
import os

# Mapping from Gutenberg header patterns to normalized English keys
# This covers common variants found in Project Gutenberg eBook #10
GUTENBERG_BOOK_MAPPING = [
    (re.compile(r"First Book of Moses.*Genesis", re.I), "Genesis"),
    (re.compile(r"Second Book of Moses.*Exodus", re.I), "Exodus"),
    (re.compile(r"Third Book of Moses.*Leviticus", re.I), "Leviticus"),
    (re.compile(r"Fourth Book of Moses.*Numbers", re.I), "Numbers"),
    (re.compile(r"Fifth Book of Moses.*Deuteronomy", re.I), "Deuteronomy"),
    (re.compile(r"Book of Joshua", re.I), "Joshua"),
    (re.compile(r"Book of Judges", re.I), "Judges"),
    (re.compile(r"Book of Ruth", re.I), "Ruth"),
    (re.compile(r"First Book of the Kings.*1 Samuel", re.I), "1 Samuel"),
    (re.compile(r"Second Book of the Kings.*2 Samuel", re.I), "2 Samuel"),
    (re.compile(r"Third Book of the Kings.*1 Kings", re.I), "1 Kings"),
    (re.compile(r"Fourth Book of the Kings.*2 Kings", re.I), "2 Kings"),
    (re.compile(r"First Book of the Chronicles", re.I), "1 Chronicles"),
    (re.compile(r"Second Book of the Chronicles", re.I), "2 Chronicles"),
    (re.compile(r"Book of Ezra", re.I), "Ezra"),
    (re.compile(r"Book of Nehemiah", re.I), "Nehemiah"),
    (re.compile(r"Book of Esther", re.I), "Esther"),
    (re.compile(r"Book of Job", re.I), "Job"),
    (re.compile(r"Book of Psalms", re.I), "Psalm"),
    (re.compile(r"Proverbs", re.I), "Proverbs"),
    (re.compile(r"Ecclesiastes", re.I), "Ecclesiastes"),
    (re.compile(r"Song of Solomon", re.I), "Song of Solomon"),
    (re.compile(r"Book of the Prophet Isaiah", re.I), "Isaiah"),
    (re.compile(r"Book of the Prophet Jeremiah", re.I), "Jeremiah"),
    (re.compile(r"Lamentations of Jeremiah", re.I), "Lamentations"),
    (re.compile(r"Book of the Prophet Ezekiel", re.I), "Ezekiel"),
    (re.compile(r"Book of Daniel", re.I), "Daniel"),
    (re.compile(r"Hosea", re.I), "Hosea"),
    (re.compile(r"Joel", re.I), "Joel"),
    (re.compile(r"Amos", re.I), "Amos"),
    (re.compile(r"Obadiah", re.I), "Obadiah"),
    (re.compile(r"Jonah", re.I), "Jonah"),
    (re.compile(r"Micah", re.I), "Micah"),
    (re.compile(r"Nahum", re.I), "Nahum"),
    (re.compile(r"Habakkuk", re.I), "Habakkuk"),
    (re.compile(r"Zephaniah", re.I), "Zephaniah"),
    (re.compile(r"Haggai", re.I), "Haggai"),
    (re.compile(r"Zechariah", re.I), "Zechariah"),
    (re.compile(r"Malachi", re.I), "Malachi"),
    (re.compile(r"Gospel According to (S\.|St\.|Saint) Matthew", re.I), "Matthew"),
    (re.compile(r"Gospel According to (S\.|St\.|Saint) Mark", re.I), "Mark"),
    (re.compile(r"Gospel According to (S\.|St\.|Saint) Luke", re.I), "Luke"),
    (re.compile(r"Gospel According to (S\.|St\.|Saint) John", re.I), "John"),
    (re.compile(r"Acts of the Apostles", re.I), "Acts"),
    (re.compile(r"Epistle.*Paul.*Romans", re.I), "Romans"),
    (re.compile(r"First Epistle.*Paul.*Corinthians", re.I), "1 Corinthians"),
    (re.compile(r"Second Epistle.*Paul.*Corinthians", re.I), "2 Corinthians"),
    (re.compile(r"Epistle.*Paul.*Galatians", re.I), "Galatians"),
    (re.compile(r"Epistle.*Paul.*Ephesians", re.I), "Ephesians"),
    (re.compile(r"Epistle.*Paul.*Philippians", re.I), "Philippians"),
    (re.compile(r"Epistle.*Paul.*Colossians", re.I), "Colossians"),
    (re.compile(r"First Epistle.*Paul.*Thessalonians", re.I), "1 Thessalonians"),
    (re.compile(r"Second Epistle.*Paul.*Thessalonians", re.I), "2 Thessalonians"),
    (re.compile(r"First Epistle.*Paul.*Timothy", re.I), "1 Timothy"),
    (re.compile(r"Second Epistle.*Paul.*Timothy", re.I), "2 Timothy"),
    (re.compile(r"Epistle.*Paul.*Titus", re.I), "Titus"),
    (re.compile(r"Epistle.*Paul.*Philemon", re.I), "Philemon"),
    (re.compile(r"Epistle.*Hebrews", re.I), "Hebrews"),
    (re.compile(r"General Epistle of James", re.I), "James"),
    (re.compile(r"First Epistle General of Peter", re.I), "1 Peter"),
    (re.compile(r"Second Epistle General of Peter", re.I), "2 Peter"),
    (re.compile(r"First Epistle General of John", re.I), "1 John"),
    (re.compile(r"Second Epistle of John", re.I), "2 John"),
    (re.compile(r"Third Epistle of John", re.I), "3 John"),
    (re.compile(r"General Epistle of Jude", re.I), "Jude"),
    (re.compile(r"Revelation of (S\.|St\.|Saint) John", re.I), "Revelation"),
]

def map_book_name(line):
    for pattern, name in GUTENBERG_BOOK_MAPPING:
        if pattern.search(line):
            return name
    return None

def convert_kjv(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} not found.")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Strip Gutenberg headers and footers
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    
    start_idx = content.find(start_marker)
    if start_idx != -1:
        # Move past the line containing the marker
        start_idx = content.find("\n", start_idx) + 1
        content = content[start_idx:]
    
    end_idx = content.find(end_marker)
    if end_idx != -1:
        content = content[:end_idx]

    verses = []
    current_book = None
    
    # Split by lines and process
    lines = content.splitlines()
    
    # Verse regex: "Chapter:Verse Text"
    # Note: Verses can span multiple lines.
    verse_re = re.compile(r"^(\d+):(\d+)\s+(.*)$")
    
    current_verse = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Try to detect book change
        # Gutenberg books often have a few lines of title before the first verse
        new_book = map_book_name(line)
        if new_book:
            current_book = new_book
            continue
            
        match = verse_re.match(line)
        if match:
            # If we were already building a verse, it's done (though in this format,
            # we usually get a new line for a new verse)
            if current_verse:
                verses.append(current_verse)
            
            chapter = int(match.group(1))
            verse_num = int(match.group(2))
            text = match.group(3)
            
            if current_book is None:
                # Should not happen with valid Gutenberg file if mapping is complete
                continue
                
            current_verse = {
                "book": current_book,
                "chapter": chapter,
                "verse": verse_num,
                "text": text
            }
        elif current_verse:
            # Append to current verse text (multi-line)
            current_verse["text"] += " " + line

    # Add the last verse
    if current_verse:
        verses.append(current_verse)

    # Final cleanup: normalize spaces in text
    for v in verses:
        v["text"] = re.sub(r"\s+", " ", v["text"]).strip()

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(verses, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(verses)} verses to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Project Gutenberg KJV text to ZachAI JSON")
    parser.add_argument("input", help="Path to raw Gutenberg KJV text file")
    parser.add_argument("output", help="Path to output JSON file")
    args = parser.parse_args()
    
    convert_kjv(args.input, args.output)
