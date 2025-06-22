# Example Prompts for Claude Code

## Basic Installation

```
Install the Claude memory system from https://github.com/banton/claude-dementia
```

## Installation with Project Context

```
We're building a FastAPI application. First, install the Claude memory system from https://github.com/banton/claude-dementia so you can remember our work across sessions.
```

## Installation for Existing Project

```
This project needs persistent memory for you. Install the Claude memory system from https://github.com/banton/claude-dementia and update memory/active/status.md with what you learn about the existing codebase.
```

## Specific Installation Instructions

```
Run these commands to set up your memory system:

git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cp /tmp/claude-memory/CLAUDE.md ./
cp -r /tmp/claude-memory/memory ./  
chmod +x memory/*.sh
rm -rf /tmp/claude-memory
./memory/update.sh "Memory system installed for [project name]"

Then always start sessions by reading CLAUDE.md and memory/active/status.md
```

## For Complex Projects

```
We're working on a microservices architecture. Install your memory system from https://github.com/banton/claude-dementia and then document the service structure in memory/reference/architecture.md
```

## After Installation

```
Now that you have the memory system, let's work on [specific task]. Remember to update memory/active/status.md as you make progress.
```

---

**Pro tip**: After installation, Claude Code will always start sessions by reading CLAUDE.md and the active memory files, giving perfect continuity between sessions.
