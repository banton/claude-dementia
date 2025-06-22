# Instructions for Claude Code

Copy and paste this to Claude Code:

---

Please install the Claude memory system from GitHub into this project. Run these commands:

```bash
git clone https://github.com/banton/claude-dementia /tmp/claude-memory
cp /tmp/claude-memory/CLAUDE.md ./
cp -r /tmp/claude-memory/memory ./
chmod +x memory/*.sh
rm -rf /tmp/claude-memory
./memory/compress.sh
```

After installation, always start sessions by reading CLAUDE.md and memory/active/status.md. This gives you persistent memory across sessions.

---

That's it! Claude Code will handle the rest.
