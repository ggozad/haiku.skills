# graphiti-memory

Knowledge graph memory skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [Graphiti](https://github.com/getzep/graphiti) and [FalkorDB](https://github.com/FalkorDB/FalkorDB).

Enables agents to remember facts across conversations, recall relevant context, and forget outdated information.

## Prerequisites

### FalkorDB

Run FalkorDB via Docker:

```bash
docker run -p 6379:6379 -p 3000:3000 \
  -v falkordb_data:/var/lib/falkordb/data \
  falkordb/falkordb:latest
```

- Port `6379` — Redis-compatible protocol (what the skill connects to)
- Port `3000` — Web UI for browsing the graph
- The volume mount ensures data persists across container restarts

### Ollama models

The skill uses Ollama for LLM and embeddings by default. Pull the required models:

```bash
ollama pull gpt-oss
ollama pull qwen3-embedding:4b
```

## Configuration

All configuration is via environment variables:

### FalkorDB

| Variable | Default | Description |
|---|---|---|
| `FALKORDB_URI` | `falkor://localhost:6379` | FalkorDB connection URI. Format: `falkor://[user:password@]host:port[/database]` |

### LLM

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL (shared with haiku.rag) |
| `GRAPHITI_LLM_MODEL` | `gpt-oss` | Model for entity extraction and edge resolution |
| `GRAPHITI_SMALL_LLM_MODEL` | Same as `GRAPHITI_LLM_MODEL` | Smaller model for lightweight LLM tasks |

### Embeddings

| Variable | Default | Description |
|---|---|---|
| `GRAPHITI_EMBEDDING_MODEL` | `qwen3-embedding:4b` | Embedding model name |
| `GRAPHITI_EMBEDDING_DIM` | `2560` | Embedding vector dimensions (must match the model) |

### Multi-tenancy

| Variable | Default | Description |
|---|---|---|
| `GRAPHITI_GROUP_ID` | `default` | Namespace for isolating memories between tenants/agents |

## Tools

- **remember** — Store facts, observations, and context into the knowledge graph
- **recall** — Search the knowledge graph for relevant memories
- **forget** — Remove outdated or incorrect memories

## Installation

```bash
uv add haiku-skills-graphiti-memory
```
