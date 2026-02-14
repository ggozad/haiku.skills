---
name: rag
description: Search and query a knowledge base using haiku.rag.
---

# RAG Knowledge Base

Use the search_documents tool to find relevant content in the knowledge base.
Use the ask_question tool to get answers with citations from the knowledge base.

- Search returns ranked results with relevance scores
- Questions are answered with citations including page numbers and source documents
- Requires the HAIKU_RAG_DB_PATH environment variable pointing to a LanceDB database
