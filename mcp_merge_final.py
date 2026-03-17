#!/usr/bin/env python3
"""
Merge all MCP server data into a final comprehensive JSON + CSV.
Combines: parsed data, GitHub stats, DeepSeek extractions.
"""

import json
import csv
from pathlib import Path

BASE = Path(__file__).parent
FULL = BASE / "mcp_servers_full.json"
EXTRACTED = BASE / "mcp_servers_extracted.jsonl"
OUTPUT_JSON = BASE / "mcp_servers_final.json"
OUTPUT_CSV = BASE / "mcp_servers_final.csv"


BATCH_SIZE = 30  # Must match the batch size used in extraction


def load_extractions():
    """Load DeepSeek extractions from JSONL as ordered list."""
    items = []
    if not EXTRACTED.exists():
        return items
    for line in EXTRACTED.read_text().splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def build_extraction_index(extractions, entries):
    """Build name -> extraction mapping using positional matching.

    DeepSeek returns items in the same order per batch.
    We reconstruct which extraction corresponds to which entry by position.
    """
    # First try exact name match
    by_name = {}
    for item in extractions:
        name = item.get("name", "")
        if name:
            by_name[name] = item

    index = {}
    exact = 0
    positional = 0

    # Reconstruct batches: entries were sent in order, BATCH_SIZE at a time
    # Extractions come back in the same order
    ext_idx = 0
    for batch_start in range(0, len(entries), BATCH_SIZE):
        batch_entries = entries[batch_start:batch_start + BATCH_SIZE]
        batch_size = len(batch_entries)
        batch_extractions = extractions[ext_idx:ext_idx + batch_size]
        ext_idx += batch_size

        for entry, ext in zip(batch_entries, batch_extractions):
            ename = entry["name"]
            # Use exact match if available, otherwise positional
            if ename in by_name:
                index[ename] = by_name[ename]
                exact += 1
            else:
                # Positional match: trust the ordering
                index[ename] = ext
                positional += 1

    print(f"  Matched: {exact} exact, {positional} positional, {len(entries) - exact - positional} unmatched")
    return index


def fix_censored_text(text):
    """Fix DeepSeek's censorship of 'MCP' and related terms."""
    if not text:
        return text
    replacements = [
        (" M server", " MCP server"),
        (" M protocol", " MCP protocol"),
        (" M tools", " MCP tools"),
        (" M client", " MCP client"),
        (" M connection", " MCP connection"),
        (" M interface", " MCP interface"),
        (" M framework", " MCP framework"),
        ("an M ", "an MCP "),
        (" FH ", " FHIR "),  # FHIR also gets censored
        (" CR ", " CRUD "),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


VALID_USE_CASES = {"integration", "automation", "data-access", "development",
                   "communication", "search", "security", "monitoring",
                   "ai-bridge", "file-management", "other"}


def main():
    entries = json.loads(FULL.read_text())
    extractions = load_extractions()
    ext_index = build_extraction_index(extractions, entries)
    matched = sum(1 for e in entries if e["name"] in ext_index)
    print(f"Loaded {len(entries)} entries, {len(extractions)} extractions, {matched} matched")

    # Merge
    final = []
    for e in entries:
        ext = ext_index.get(e["name"], {})
        stats = e.get("stats", {})

        row = {
            "name": e["name"],
            "url": e["url"],
            "category": e["category"],
            "description": e.get("description", ""),
            "summary": ext.get("summary", ""),
            "keywords": ext.get("keywords", []),
            "api_key_required": ext.get("api_key_required"),
            "primary_use_case": ext.get("primary_use_case", ""),
            "languages": e.get("languages", []),
            "scopes": e.get("scopes", []),
            "os": e.get("os", []),
            "official": e.get("official", False),
            "stars": stats.get("stars"),
            "forks": stats.get("forks"),
            "open_issues": stats.get("open_issues"),
            "last_push": stats.get("last_push", ""),
            "created_at": stats.get("created_at", ""),
            "license": stats.get("license", ""),
            "topics": stats.get("topics", []),
            "archived": stats.get("archived"),
        }
        final.append(row)

    # Sort by stars (descending), nulls last
    final.sort(key=lambda x: x.get("stars") or 0, reverse=True)

    # Fix DeepSeek censored terms and normalize
    for row in final:
        row["summary"] = fix_censored_text(row["summary"])
        row["description"] = fix_censored_text(row["description"])
        # Clean empty keywords
        row["keywords"] = [k for k in row["keywords"] if k.strip()]
        # Normalize invalid use cases to "other"
        if row["primary_use_case"] not in VALID_USE_CASES:
            row["primary_use_case"] = row["primary_use_case"] or "other"

    # Save JSON
    OUTPUT_JSON.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"Saved {len(final)} entries to {OUTPUT_JSON}")

    # Save CSV
    csv_fields = [
        "name", "url", "category", "description", "summary",
        "keywords", "api_key_required", "primary_use_case",
        "languages", "scopes", "os", "official",
        "stars", "forks", "open_issues", "last_push", "created_at",
        "license", "topics", "archived",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()
        for row in final:
            csv_row = {**row}
            # Flatten lists for CSV
            for key in ("keywords", "languages", "scopes", "os", "topics"):
                csv_row[key] = "; ".join(csv_row.get(key) or [])
            writer.writerow(csv_row)
    print(f"Saved CSV to {OUTPUT_CSV}")

    # Summary stats
    with_extraction = sum(1 for r in final if r["summary"])
    with_stars = sum(1 for r in final if r["stars"] is not None)
    print(f"\nCoverage: {with_extraction} with AI summary, {with_stars} with GitHub stats")
    print(f"Categories: {len(set(r['category'] for r in final))}")
    print(f"Top 10 by stars:")
    for r in final[:10]:
        print(f"  {r['stars'] or 0:6d} ⭐  {r['name']:40s}  {r['category']}")


if __name__ == "__main__":
    main()
