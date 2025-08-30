# 2025-08-30 Dementia MCP Critical Bugs Fixed

## Problem 1: Database Connectivity Failure
**Error:** "unable to open database file" when run from non-project directories
**Impact:** Complete MCP tool failure in Claude Desktop

### Root Cause
- Path resolution logic was forcing database creation in non-project directories
- When `CLAUDE_PROJECT_DIR` pointed to non-project dir (no .git), code returned path instead of falling through
- Missing directory creation before database connection attempt

### Fix Applied
```python
# Before (line 52-53):
# Even if no markers, use project dir if explicitly set
return os.path.join(project_dir, '.claude-memory.db')

# After:
# Don't automatically use project dir if it's not a recognized project
# Fall through to Option 3 instead
```

Additional safeguards:
- Added directory creation before database connection
- Added try/catch with fallback to `/tmp` if all else fails
- Enhanced error diagnostics showing path, permissions, etc.

## Problem 2: Permission Denied on System Files
**Error:** "Permission denied: '/usr/sbin/weakpass_edit'"
**Impact:** project_update() function fails when scanning

### Root Cause
- `project_root.rglob('*')` could traverse symlinks
- No boundary checking to ensure paths stay within project
- No error handling for permission denied

### Fix Applied
```python
# Added three layers of protection:
1. Skip symlinks: if path.is_symlink(): continue
2. Verify path is relative: path.relative_to(project_root)
3. Wrap in try/except for permission errors
```

## Testing Performed
- Verified database creation in cache directory for non-project dirs
- Tested project_update stays within boundaries
- Confirmed error handling works gracefully

## Prevention
- Always validate paths before file operations
- Use defensive programming for external file access
- Provide detailed error messages for debugging
- Test from different working directories