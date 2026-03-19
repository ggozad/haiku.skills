---
name: web
description: Search the web and fetch page content.
---

# Web

Use the **search** tool to find current information on the web using Brave Search.
Use the **fetch_page** tool to visit a URL and extract its readable content.

## Workflow

1. Start with `search` to find relevant URLs.
2. Use `fetch_page` to read the full content of promising results.
3. Summarize findings and cite sources with URLs.

Use a maximum of 3 search queries per task.

## Available Scripts

### `scripts/search.py`

Search the web using Brave Search.

```
--query     (required) The search query.
--count     (default: 5) Number of results to return.
```

### `scripts/fetch_page.py`

Fetch a web page and extract its readable content.

```
--url       (required) The URL of the page to fetch.
```

## Guidelines

- Always cite sources with URLs when presenting findings.
- Prefer specific search queries over broad ones.
