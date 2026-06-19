import os
import sys

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or 'utf-8'
        print(text.encode(enc, errors='replace').decode(enc))

with open(r'.\static\js\detail.js', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
safe_print(f"Total lines: {len(lines)}")
for idx in range(max(0, len(lines)-25), len(lines)):
    safe_print(f"{idx+1}: {lines[idx].rstrip()}")
