#!/usr/bin/env python3
"""
Batch MCP server data to DeepSeek for structured extraction.
Sends batches of entries and asks for JSON back with:
- keywords, api_key_required, summary, use_cases
"""

import json
import subprocess
import sys
import time
from pathlib import Path

INPUT = Path(__file__).parent / "mcp_servers_full.json"
OUTPUT = Path(__file__).parent / "mcp_servers_extracted.jsonl"
PROGRESS = Path(__file__).parent / "mcp_extract_progress.json"
RELAY = Path.home() / "Documents/GitHub/deepseek-api/relay-send.sh"

BATCH_SIZE = 30
SLEEP_BETWEEN = 3  # seconds between batches


def build_prompt(batch):
    """Build a prompt for DeepSeek to extract structured info from a batch."""
    entries_text = ""
    for i, entry in enumerate(batch):
        entries_text += f"\n--- ENTRY {i} (name: {entry['name']}) ---\n"
        entries_text += f"URL: {entry['url']}\n"
        entries_text += f"Category: {entry['category']}\n"
        entries_text += f"Description: {entry.get('description', 'N/A')}\n"
        entries_text += f"Languages: {', '.join(entry.get('languages', []))}\n"
        entries_text += f"Scopes: {', '.join(entry.get('scopes', []))}\n"
        entries_text += f"Stars: {entry.get('stats', {}).get('stars', 'N/A')}\n"
        entries_text += f"Topics: {', '.join(entry.get('stats', {}).get('topics', []))}\n"
        readme = entry.get("readme_snippet", "")
        if readme:
            # Trim to 1500 chars to fit more entries
            entries_text += f"README (first 1500 chars):\n{readme[:1500]}\n"

    prompt = f"""Here are {len(batch)} MCP (Model Context Protocol) server entries to analyze.
For each, return: name, summary (1-2 sentences), keywords (3-8), api_key_required (bool/null), primary_use_case.

{entries_text}"""
    return prompt


def send_to_deepseek(prompt):
    """Send prompt to DeepSeek via relay and get response."""
    # Write data to temp file, keep instruction short as positional arg
    data_file = Path("/tmp/mcp_ds_data.txt")
    # Split: instruction as arg, data as file attachment
    instruction = "Hi! I'd really appreciate your help analyzing these tool servers in the attached file. Could you please return a JSON array where each object has: name (string, exactly as given), summary (1-2 sentences of what it does), keywords (3-8 searchable strings), api_key_required (bool or null), primary_use_case (one of: integration, automation, data-access, development, communication, search, security, monitoring, ai-bridge, file-management, other). Just the JSON array please, no markdown fences. Thanks so much!"
    data_file.write_text(prompt, encoding="utf-8")

    result = subprocess.run(
        [str(RELAY), "--no-throttle", instruction, str(data_file)],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        print(f"  DeepSeek error: {result.stderr[:200]}")
        return None
    return result.stdout.strip()


def parse_json_response(response):
    """Try to extract JSON array from DeepSeek response."""
    if not response:
        return None
    # Strip markdown fences if present
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def main():
    entries = json.loads(INPUT.read_text())

    # Load progress
    done_names = set()
    if PROGRESS.exists():
        progress = json.loads(PROGRESS.read_text())
        done_names = set(progress.get("done", []))
        print(f"Resuming: {len(done_names)} entries already processed")

    # Filter to unprocessed
    remaining = [e for e in entries if e["name"] not in done_names]
    print(f"Total: {len(entries)}, remaining: {len(remaining)}")

    # Open output file in append mode with proper resource management
    try:
        with open(OUTPUT, "a", encoding="utf-8") as out_f:
            batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
            print(f"Processing {len(batches)} batches of ~{BATCH_SIZE} entries each")

            for batch_idx, batch in enumerate(batches):
                print(f"\nBatch {batch_idx + 1}/{len(batches)} ({len(batch)} entries)...")
                prompt = build_prompt(batch)

                response = send_to_deepseek(prompt)
                extracted = parse_json_response(response)

                if extracted and isinstance(extracted, list):
                    # Validate that we got extractions for all entries in the batch
                    # Handle case where AI returns fewer items than batch size
                    if len(extracted) != len(batch):
                        print(f"  WARNING: batch size {len(batch)} but got {len(extracted)} extractions")
                        # Only save the ones that came back; don't mark batch as complete
                        for i, item in enumerate(extracted):
                            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                        out_f.flush()
                        print(f"  Saved {len(extracted)} extractions but NOT marking batch as complete")
                    else:
                        for item in extracted:
                            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
                        out_f.flush()

                        # Update progress - only mark batch as done if we got all items
                        for e in batch:
                            done_names.add(e["name"])
                        PROGRESS.write_text(json.dumps({"done": list(done_names)}))
                        print(f"  OK: got {len(extracted)} extractions")
                else:
                    print(f"  FAILED to parse response. Raw (first 300): {(response or '')[:300]}")
                    print(f"  NOT marking batch as done - will retry next run")

                if batch_idx < len(batches) - 1:
                    time.sleep(SLEEP_BETWEEN)

        print(f"\nDone! Extracted data in {OUTPUT}")
    except Exception as e:
        print(f"Error during processing: {e}")
        raise


if __name__ == "__main__":
    main()
