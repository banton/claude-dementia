# CLAUDE.md - Local MCP Server Guide v3.1.0

> **You are Claude Code, utilizing a persistent local memory system via MCP.**

## 🧠 Memory System Overview

You have access to a local SQLite database and semantic search capabilities through the `claude-dementia-local` MCP server. This allows you to store and retrieve information across sessions without manual file management.

### Core Capabilities
1.  **Store Memory**: Save important context, decisions, and learnings.
2.  **Retrieve Memory**: Look up specific information by label.
3.  **Search Memories**: Find relevant information using semantic vector search.

## 🛠️ Tool Usage

### Storing Information
When you learn something valuable that should be persisted:
```python
# Store with a descriptive label
store_memory(
    content="The API key is located in .env.local (not .env)",
    label="api_key_location",
    is_persistent=True
)
```

### Retrieving Information
When you need to recall specific details:
```python
# Get exact content
content = retrieve_memory(label="api_key_location")
```

### Searching Context
When you need to understand a topic or find related info:
```python
# Semantic search finds related concepts
results = search_memories(query="where are credentials stored")
```

## � Workflow

1.  **Start of Session**:
    *   Check server status: `get_status()`
    *   Search for relevant context: `search_memories(query="current project status")`

2.  **During Work**:
    *   If you make a significant decision, **store it**.
    *   If you solve a tricky bug, **store the solution**.
    *   If you need context, **search for it**.

3.  **End of Session**:
    *   Store a summary of what was accomplished.
    *   Store next steps.

## 🚫 What NOT To Do
*   Do NOT create manual markdown files for memory (e.g., `memory/context.md`).
*   Do NOT try to run shell scripts for memory management.
*   Do NOT ask the user to manage memory files manually.

## 🏗️ Project Structure
*   `server.py`: The core MCP server (Python/SQLite/Ollama).
*   `.claude-memory.db`: The SQLite database file (automatically managed).
*   `requirements.txt`: Python dependencies.

## �️ Operating Principles
*   **Lean & Local**: No cloud dependencies, no complex file structures.
*   **Semantic First**: Rely on vector search to find relevant context.
*   **Zero Config**: The system just works.

---
**Version**: 3.1.0
**System**: Lean Local MCP (SQLite + Ollama)
