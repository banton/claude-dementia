# Changelog

All notable changes to Claude Dementia will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2024-08-14

### Added
- MCP (Model Context Protocol) server implementation
- Smart database location detection (project vs user cache)
- Intelligent file tagging with structured metadata
- Mock data and placeholder detection
- Context locking with version control
- Per-project database isolation
- Session management (wake_up/sleep)
- Semantic search across all memory
- Project intelligence and insights
- File quality indicators

### Changed
- Complete migration from file-based to database-only system
- Improved separation between task TODOs and code improvement markers
- Better semantic naming for quality tags
- Enhanced project scanning with auto-tagging

### Fixed
- JSON output for proper MCP communication
- Project context bleeding between different codebases
- Database location for Claude Desktop vs Claude Code

### Removed
- File-based markdown memory system
- Shell script memory management
- Manual compression workflows

## [3.0.0] - 2024-06-11

### Added
- Initial file-based memory system
- CLAUDE.md documentation
- Memory compression scripts
- Pattern detection

## [2.0.0] - 2024-05-01

### Added
- Basic memory persistence
- Session tracking

## [1.0.0] - 2024-04-01

### Added
- Initial prototype