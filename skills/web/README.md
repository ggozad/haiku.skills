# web

Web search and page fetching skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [Brave Search](https://brave.com/search/api/) and [trafilatura](https://github.com/adbar/trafilatura).

## Prerequisites

A [Brave Search API](https://brave.com/search/api/) key is required.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `BRAVE_API_KEY` | — | Brave Search API key (required) |

## Tools

- **search** — Search the web using Brave Search
- **fetch_page** — Fetch a web page and extract its readable content

## Installation

```bash
uv add haiku-skills-web
```
