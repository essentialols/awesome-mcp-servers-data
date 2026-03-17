# awesome-mcp-servers-data

Structured dataset of **1,631 MCP (Model Context Protocol) servers** scraped from [punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers), enriched with GitHub repository statistics and AI-generated metadata.

## Quick stats

| Metric | Value |
|---|---|
| Total servers | 1,631 |
| Categories | 46 |
| With GitHub stars | 81% |
| With AI-generated summary | 99% |
| With keywords | 99% |
| With license info | 69% |

## Data pipeline

The dataset is built in four phases:

### Phase 1: Parse README (`scrape_mcp_servers.py parse`)

Parses `awesome-mcp-servers-raw.md` (a snapshot of the awesome-mcp-servers README) and extracts each server entry: name, URL, category, description, language/scope/OS emoji tags, and official status.

Output: `mcp_servers_parsed.json`

### Phase 2: GitHub API stats (`scrape_mcp_servers.py stats`)

For each GitHub-hosted server, fetches repository metadata via `gh api`: stars, forks, open issues, last push date, creation date, license, topics, and archived status. Uses 10 concurrent workers.

Output: `mcp_servers_enriched.json`

### Phase 3: README snippets (`scrape_mcp_servers.py readme`)

Fetches the first 2,000 characters of each repository's README via the GitHub API. These snippets provide context for the AI extraction step.

Output: `mcp_servers_full.json`

### Phase 4: AI extraction (`mcp_deepseek_extract.py`)

Sends batches of 30 servers to DeepSeek (via a local relay) for structured extraction: a 1-2 sentence summary, 3-8 searchable keywords, whether an API key is required, and a primary use-case classification.

Output: `mcp_servers_extracted.jsonl`

### Merge (`mcp_merge_final.py`)

Combines all intermediate outputs into the final dataset. Fixes DeepSeek's censorship artifacts (it redacts "MCP" and "FHIR"), normalizes use-case labels, and sorts by star count descending.

Output: `mcp_servers_final.json`, `mcp_servers_final.csv`

## Schema

The final dataset (`mcp_servers_final.json` / `mcp_servers_final.csv`) contains these fields:

| Field | Type | Description |
|---|---|---|
| `name` | string | Server name (typically `owner/repo`) |
| `url` | string | URL to the server (usually GitHub) |
| `category` | string | Category from the awesome list (e.g. "Databases", "Cloud Platforms") |
| `description` | string | Description from the awesome list entry |
| `summary` | string | AI-generated 1-2 sentence summary |
| `keywords` | string[] | AI-generated searchable keywords (3-8 per server) |
| `api_key_required` | bool/null | Whether the server requires an API key (AI-determined) |
| `primary_use_case` | string | One of: integration, automation, data-access, development, communication, search, security, monitoring, ai-bridge, file-management, other |
| `languages` | string[] | Programming languages (from emoji tags: Python, TypeScript/JS, Go, Rust, C#, Java, C/C++, Ruby) |
| `scopes` | string[] | Deployment scope: Cloud, Local, or Embedded |
| `os` | string[] | OS-specific: macOS, Windows, Linux |
| `official` | bool | Whether the server is marked as official |
| `stars` | int/null | GitHub star count |
| `forks` | int/null | GitHub fork count |
| `open_issues` | int/null | Open issue count |
| `last_push` | string | ISO timestamp of last push |
| `created_at` | string | ISO timestamp of repo creation |
| `license` | string | SPDX license identifier |
| `topics` | string[] | GitHub topics |
| `archived` | bool/null | Whether the repo is archived |

In the CSV, list fields (`keywords`, `languages`, `scopes`, `os`, `topics`) are semicolon-delimited.

## Files

| File | Description |
|---|---|
| `mcp_servers_final.json` | Final dataset (1.6 MB) |
| `mcp_servers_final.csv` | Same data in CSV format |
| `mcp_servers_parsed.json` | Phase 1 output: raw parse of the awesome list |
| `mcp_servers_enriched.json` | Phase 2 output: with GitHub stats |
| `mcp_servers_full.json` | Phase 3 output: with README snippets (3.8 MB) |
| `mcp_servers_extracted.jsonl` | Phase 4 output: DeepSeek extractions |
| `awesome-mcp-servers-raw.md` | Source README snapshot |
| `scrape_mcp_servers.py` | Phases 1-3 script |
| `mcp_deepseek_extract.py` | Phase 4 script (requires DeepSeek relay) |
| `mcp_merge_final.py` | Final merge script |

## Re-running the pipeline

Prerequisites: `gh` CLI (authenticated), Python 3.8+.

```bash
# Phase 1-3: parse, fetch GitHub stats, fetch README snippets
python scrape_mcp_servers.py all

# Phase 4: AI extraction (requires DeepSeek relay at ~/Documents/GitHub/deepseek-api/)
python mcp_deepseek_extract.py

# Merge into final output
python mcp_merge_final.py
```

To update the source data, re-download the awesome-mcp-servers README:

```bash
curl -sL https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md > awesome-mcp-servers-raw.md
```

## License

The dataset is derived from [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) (CC0). The scripts in this repo are provided as-is.
