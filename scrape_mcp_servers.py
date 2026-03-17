#!/usr/bin/env python3
"""
Scrape awesome-mcp-servers README, enrich with GitHub API stats,
fetch each repo's README snippet, and output structured JSON.
"""

import re
import json
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

RAW_MD = Path(__file__).parent / "awesome-mcp-servers-raw.md"
OUTPUT_PARSED = Path(__file__).parent / "mcp_servers_parsed.json"
OUTPUT_ENRICHED = Path(__file__).parent / "mcp_servers_enriched.json"
OUTPUT_FULL = Path(__file__).parent / "mcp_servers_full.json"

# Tag mappings
LANG_TAGS = {
    "🐍": "Python",
    "📇": "TypeScript/JS",
    "🏎️": "Go",
    "🦀": "Rust",
    "#️⃣": "C#",
    "☕": "Java",
    "🌊": "C/C++",
    "💎": "Ruby",
}

SCOPE_TAGS = {
    "☁️": "Cloud",
    "🏠": "Local",
    "📟": "Embedded",
}

OS_TAGS = {
    "🍎": "macOS",
    "🪟": "Windows",
    "🐧": "Linux",
}

ALL_TAGS = {**LANG_TAGS, **SCOPE_TAGS, **OS_TAGS, "🎖️": "Official"}


def parse_readme():
    """Parse the README markdown and extract all MCP server entries."""
    text = RAW_MD.read_text(encoding="utf-8")
    entries = []
    current_category = ""

    # Match category headers like ### 🔗 <a name="aggregators"></a>Aggregators
    cat_pattern = re.compile(r"^###\s+.+?</a>\s*(.+)$", re.MULTILINE)
    # Match entries like - [name](url) tags - description
    entry_pattern = re.compile(
        r"^-\s+(?:\[.*?\]\(.*?\)\s+)*"  # optional badge links
        r"\[([^\]]+)\]\(([^)]+)\)"       # name and URL
        r"\s*(.*?)$",                     # rest of line (tags + description)
        re.MULTILINE,
    )

    # Find all categories and their positions
    categories = []
    for m in cat_pattern.finditer(text):
        categories.append((m.start(), m.group(1).strip()))

    for m in entry_pattern.finditer(text):
        pos = m.start()
        # Determine category
        cat = ""
        for cpos, cname in categories:
            if cpos < pos:
                cat = cname
            else:
                break

        name = m.group(1).strip()
        url = m.group(2).strip()
        rest = m.group(3).strip()

        # Extract tags from the rest
        languages = []
        scopes = []
        os_list = []
        official = False

        for emoji, label in LANG_TAGS.items():
            if emoji in rest:
                languages.append(label)
        for emoji, label in SCOPE_TAGS.items():
            if emoji in rest:
                scopes.append(label)
        for emoji, label in OS_TAGS.items():
            if emoji in rest:
                os_list.append(label)
        if "🎖️" in rest:
            official = True

        # Extract description (after the last tag/badge, typically after " - ")
        # Remove badge images first
        desc_text = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", rest).strip()
        # Remove emoji tags
        for emoji in ALL_TAGS:
            desc_text = desc_text.replace(emoji, "")
        # Clean up separators
        desc_text = re.sub(r"^\s*[-–—]\s*", "", desc_text.strip()).strip()

        # Extract GitHub owner/repo if it's a GitHub URL
        gh_match = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:/.*)?$", url)
        gh_owner = gh_match.group(1) if gh_match else None
        gh_repo = gh_match.group(2) if gh_match else None

        entries.append({
            "name": name,
            "url": url,
            "github_owner": gh_owner,
            "github_repo": gh_repo,
            "category": cat,
            "description": desc_text,
            "languages": languages,
            "scopes": scopes,
            "os": os_list,
            "official": official,
        })

    return entries


def gh_api(endpoint):
    """Call GitHub API via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def enrich_with_stats(entries, max_workers=10):
    """Fetch GitHub stats for each entry."""
    github_entries = [e for e in entries if e["github_owner"] and e["github_repo"]]
    print(f"Fetching stats for {len(github_entries)} GitHub repos...")

    def fetch_stats(entry):
        owner = entry["github_owner"]
        repo = entry["github_repo"]
        data = gh_api(f"repos/{owner}/{repo}")
        if data:
            return {
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "last_push": data.get("pushed_at", ""),
                "created_at": data.get("created_at", ""),
                "license": (data.get("license") or {}).get("spdx_id", ""),
                "topics": data.get("topics", []),
                "archived": data.get("archived", False),
                "default_branch": data.get("default_branch", "main"),
            }
        return None

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_stats, e): e for e in github_entries}
        for future in as_completed(futures):
            entry = futures[future]
            stats = future.result()
            if stats:
                entry["stats"] = stats
            done += 1
            if done % 50 == 0:
                print(f"  ... {done}/{len(github_entries)} done")

    return entries


def fetch_readme_snippets(entries, max_workers=10, char_limit=2000):
    """Fetch first N chars of each repo's README."""
    github_entries = [e for e in entries if e["github_owner"] and e["github_repo"]]
    print(f"Fetching README snippets for {len(github_entries)} repos...")

    def fetch_readme(entry):
        owner = entry["github_owner"]
        repo = entry["github_repo"]
        data = gh_api(f"repos/{owner}/{repo}/readme")
        if data and "content" in data:
            import base64
            try:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                return content[:char_limit]
            except Exception:
                pass
        return None

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_readme, e): e for e in github_entries}
        for future in as_completed(futures):
            entry = futures[future]
            snippet = future.result()
            if snippet:
                entry["readme_snippet"] = snippet
            done += 1
            if done % 50 == 0:
                print(f"  ... {done}/{len(github_entries)} done")

    return entries


def save_json(entries, path):
    path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(entries)} entries to {path}")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"

    if phase in ("parse", "all"):
        print("=== Phase 1: Parsing README ===")
        entries = parse_readme()
        save_json(entries, OUTPUT_PARSED)
        print(f"Found {len(entries)} entries across categories")
        if phase == "parse":
            return

    if phase in ("stats", "all"):
        print("\n=== Phase 2: Enriching with GitHub stats ===")
        entries = json.loads(OUTPUT_PARSED.read_text())
        entries = enrich_with_stats(entries)
        save_json(entries, OUTPUT_ENRICHED)
        if phase == "stats":
            return

    if phase in ("readme", "all"):
        print("\n=== Phase 3: Fetching README snippets ===")
        entries = json.loads(OUTPUT_ENRICHED.read_text())
        entries = fetch_readme_snippets(entries)
        save_json(entries, OUTPUT_FULL)


if __name__ == "__main__":
    main()
