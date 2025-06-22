# Architecture Reference

## Memory System Design
- **Token Budget**: 10,000 total (3k active + 5k reference + 2k buffer)
- **Compression**: Automatic when files exceed limits
- **Archival**: Weekly for files older than 7 days
- **Structure**: Three-tier (active/reference/archive)

## Directory Structure
```
memory/
├── active/          # Current work (3,000 tokens)
├── reference/       # Stable patterns (5,000 tokens)
├── archive/         # Historical compressed
├── patterns/        # Reusable solutions
├── fixes/           # Problem resolutions
├── implementations/ # Feature tracking
└── questions/       # Clarifications
```

## Key Principles
- Information density over verbosity
- Tables/lists compress 3:1 vs prose
- Reference paths instead of copying code
- Progressive loading to manage tokens
- Automated maintenance to prevent bloat
