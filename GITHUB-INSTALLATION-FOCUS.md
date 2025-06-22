# Claude Memory System v3.0 - GitHub Installation Focus

## Overview

The Claude Memory System v3.0 has been updated to prioritize installation directly from GitHub by Claude Code. This approach makes it extremely easy for developers to give Claude Code persistent memory.

## Primary Use Case

A developer simply tells Claude Code:
```
"Install the Claude memory system from https://github.com/banton/claude-dementia"
```

Claude Code then:
1. Clones the repository
2. Copies the necessary files
3. Sets up the memory structure
4. Begins using persistent memory

## Key Documentation Updates

### For Humans
- **ASK-CLAUDE-CODE.md** - Simple copy-paste instructions
- **EXAMPLE-PROMPTS.md** - Various installation scenarios
- **README.md** - Refocused on GitHub quick start

### For Claude Code  
- **INSTALL-FOR-CLAUDE.md** - Detailed installation guide
- **CLAUDE.md** - Added GitHub installation section
- **install.sh** - One-line installation script

### Installation Methods

1. **Simple Request**
   ```
   "Install Claude memory from https://github.com/banton/claude-dementia"
   ```

2. **Specific Commands**
   ```bash
   git clone https://github.com/banton/claude-dementia /tmp/cm
   cp /tmp/cm/CLAUDE.md ./ && cp -r /tmp/cm/memory ./
   chmod +x memory/*.sh && rm -rf /tmp/cm
   ```

3. **One-liner** (if raw GitHub access works)
   ```bash
   curl -sSL https://raw.githubusercontent.com/banton/claude-dementia/main/install.sh | bash
   ```

## Benefits of GitHub Approach

1. **Zero Friction** - One command to persistent memory
2. **Always Latest** - Gets newest version automatically  
3. **No Manual Setup** - Claude Code handles everything
4. **Project Agnostic** - Works with any project type
5. **Immediate Value** - Memory system ready in seconds

## What Stays the Same

- 10,000 token budget management
- Automatic compression and archival
- Progressive context loading
- Session handoff patterns
- Memory structure and scripts

## Typical Workflow

1. Human starts new project with Claude Code
2. Human: "Install your memory from https://github.com/banton/claude-dementia"
3. Claude Code installs and initializes
4. Development proceeds with full memory
5. Every session builds on the last

## Repository Structure

```
claude-dementia/
├── README.md               # GitHub-focused quick start
├── CLAUDE.md              # Core guide with GitHub install
├── ASK-CLAUDE-CODE.md     # What humans should say
├── INSTALL-FOR-CLAUDE.md  # Claude's installation guide
├── EXAMPLE-PROMPTS.md     # Various use cases
├── install.sh             # One-line installer
├── memory/                # Memory structure to copy
│   ├── update.sh
│   ├── compress.sh
│   └── weekly-maintenance.sh
└── [other docs]           # Migration, comparison, etc.
```

## Success Metrics

- Installation time: <30 seconds
- Commands needed: 1 (just the GitHub URL)
- Success rate: ~100% (with git access)
- Token budget: Always maintained
- Memory persistence: Indefinite

---

The Claude Memory System v3.0 is now optimized for the most common use case: developers wanting to quickly give Claude Code persistent memory by pointing to the GitHub repository.
