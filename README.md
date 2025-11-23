# Claude Dementia: Lean Local MCP Server

**Give Claude Code perfect memory with a lightweight, local-first MCP server.**

This project provides a Model Context Protocol (MCP) server that gives Claude persistent memory using a local SQLite database and local embeddings via Ollama. No cloud dependencies, no complex setup.

## 🚀 Quick Start

### Prerequisites
1.  **Python 3.10+**
2.  **Ollama** (Optional, recommended for semantic search)
    *   If installed: `ollama pull nomic-embed-text`
    *   If not installed: Server falls back to keyword search.

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/banton/claude-dementia
    cd claude-dementia
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Start the server**:
    ```bash
    python server.py
    ```

### Connect to Claude Desktop
Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "claude-dementia": {
      "command": "python",
      "args": ["/absolute/path/to/claude-dementia/server.py"]
    }
  }
}
```

## ✨ Features

*   **Local Storage**: All memories are stored in a local SQLite database (`.claude-memory.db`) in your project root.
*   **Semantic Search**: Uses local embeddings (via Ollama) to find relevant memories based on meaning, not just keywords.
*   **Project Isolation**: Automatically creates separate memory contexts for different projects.
*   **Lean Architecture**: Minimal dependencies, fast startup, and full data privacy.

## 🛠️ Tools Provided

*   `store_memory(content, label, is_persistent)`: Save important information.
*   `retrieve_memory(label)`: Get back a specific memory.
*   `search_memories(query)`: Find memories using vector search.
*   `get_status()`: Check server health and configuration.

## 🧠 How It Works

1.  **You talk to Claude**: "Remember that the API key is in `.env.local`."
2.  **Claude uses `store_memory`**: The server generates an embedding for this text using your local Ollama instance.
3.  **Data is saved**: The text and embedding are stored in SQLite.
4.  **Later**: You ask "Where is the API key?"
5.  **Claude uses `search_memories`**: The server compares the meaning of your question to stored memories and returns the most relevant answer.

## 🔧 Configuration

The server uses environment variables for configuration (optional):

*   `OLLAMA_BASE_URL`: URL of your Ollama instance (default: `http://localhost:11434`)
*   `EMBEDDING_MODEL`: Model to use for embeddings (default: `nomic-embed-text`)
*   `CLAUDE_MEMORY_DB`: Custom path for the database (default: `.claude-memory.db`)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License
