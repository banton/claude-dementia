# 🧠 Claude Intelligence

**It just remembers.**

A dead-simple MCP server that gives Claude persistent memory of your project - understanding your tech stack, finding files by meaning, and tracking what you've been working on.

## Quick Start

```bash
# Install (30 seconds)
curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/main/claude-intelligence/install.sh | bash

# That's it. Claude now remembers your project.
```

## Features

- 🔍 **Smart File Search** - Find files by what they do, not their names
- 🛠️ **Tech Stack Detection** - Instantly knows your frameworks and tools
- 📝 **Change Tracking** - Remembers what you worked on between sessions

## How It Works

Claude Intelligence creates a lightweight SQLite database in your project (`.claude-memory.db`) that tracks:
- File contents and structure using FTS5 full-text search
- Your technology stack (Node.js, Python, React, etc.)
- Changes between sessions via git integration
- Session boundaries to know what's new

All searching happens locally with BM25 ranking. No external APIs, no cloud storage.

## Requirements

- Python 3.8+
- That's it

## License

MIT