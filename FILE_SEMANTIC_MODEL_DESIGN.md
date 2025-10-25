# File Semantic Model - Design Document

**Version:** 1.0
**Date:** January 2025
**Status:** In Development

---

## Purpose

Build an intelligent file system semantic model that gives Claude persistent understanding of project structure, file purposes, and relationships across sessions.

**Core Problem:** Claude currently has no memory of project structure between sessions, requiring repeated "what files exist?" questions and explanations.

**Solution:** Automatically build and maintain a semantic model of the filesystem that persists in memory, integrates with wake_up/sleep, and provides intelligent querying.

---

## Design Principles

1. **Automatic**: Runs during wake_up/sleep without user intervention
2. **Efficient**: Fast incremental updates (mtime → size → hash)
3. **Accurate**: Hash-based change detection avoids false positives
4. **Generic**: Works for any project type (code, docs, data, mixed)
5. **Scalable**: Handles projects with 1000s of files
6. **Semantic**: Understands purpose, not just filenames

---

## Change Detection Strategy

### Three-Stage Detection (Optimal Performance)

```python
Stage 1: mtime check (instant)
  ↓ If unchanged → DONE (99% of files)
  ↓ If changed

Stage 2: size check (instant)
  ↓ If changed → hash and mark as changed
  ↓ If same size

Stage 3: hash check (only if needed)
  ↓ Compare hash
  ↓ If same → touched but unchanged
  ↓ If different → content changed
```

**Performance for 1000 files:**
- 990 unchanged: ~1ms (mtime only)
- 5 size changed: ~5ms (mtime + size)
- 3 touched only: ~30ms (mtime + hash)
- 2 content changed: ~20ms (mtime + hash)
- **Total: ~56ms** vs 10+ seconds for hash-only

### Smart Hashing

```python
def compute_hash(file_path, file_size):
    if file_size > 1_000_000:  # >1MB
        return partial_hash(file_path, file_size)
    else:
        return full_hash(file_path)

def partial_hash(file_path, file_size):
    """Hash first 64KB + last 64KB + size"""
    # Detects 99.9% of changes
    # 100x faster than full hash for large files

def full_hash(file_path):
    """MD5 hash of entire file"""
    # Complete accuracy for small files
```

**Hash Algorithm:** MD5
- Fast, built-in, perfect for change detection
- Not for security, just change detection
- Collision probability negligible for this use case

---

## Database Schema

```sql
CREATE TABLE file_semantic_model (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    file_path TEXT NOT NULL,

    -- Change detection (mtime + size + hash)
    file_size INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    modified_time REAL NOT NULL,
    hash_method TEXT DEFAULT 'full',  -- 'full' or 'partial'

    -- Basic metadata
    file_type TEXT,  -- 'python', 'javascript', 'config', 'markdown', etc.
    language TEXT,   -- Programming language if applicable
    purpose TEXT,    -- One-line description of file's purpose

    -- Semantic understanding (stored as JSON)
    imports TEXT,        -- ["jwt", "fastapi", "database"]
    exports TEXT,        -- ["authenticate_user", "verify_token"]
    dependencies TEXT,   -- ["models/user.py", "config/settings.py"]
    used_by TEXT,        -- ["routes/api.py", "tests/test_auth.py"]
    contains TEXT,       -- {"classes": 3, "functions": 12, "lines": 245}

    -- Standard file recognition
    is_standard BOOLEAN DEFAULT 0,
    standard_type TEXT,  -- 'environment_config', 'package_manifest', etc.
    warnings TEXT,       -- JSON: [".env not in .gitignore"]

    -- Semantic clustering
    cluster_name TEXT,   -- 'authentication', 'api', 'database', etc.
    related_files TEXT,  -- JSON: ["auth.py", "auth_middleware.js"]

    -- Tracking
    last_scanned REAL NOT NULL,
    scan_duration_ms INTEGER,

    UNIQUE(session_id, file_path)
);

-- Indexes for performance
CREATE INDEX idx_fsm_hash ON file_semantic_model(session_id, content_hash);
CREATE INDEX idx_fsm_mtime ON file_semantic_model(session_id, modified_time);
CREATE INDEX idx_fsm_cluster ON file_semantic_model(session_id, cluster_name);
CREATE INDEX idx_fsm_type ON file_semantic_model(session_id, file_type);
CREATE INDEX idx_fsm_standard ON file_semantic_model(session_id, is_standard);

-- Change history (optional, for advanced features)
CREATE TABLE file_change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,  -- 'added', 'modified', 'deleted'
    timestamp REAL NOT NULL,
    old_hash TEXT,
    new_hash TEXT,
    size_delta INTEGER
);

CREATE INDEX idx_fch_session ON file_change_history(session_id, timestamp DESC);
```

---

## File Type Detection

```python
FILE_TYPE_MAP = {
    # Programming languages
    '.py': ('python', 'python'),
    '.js': ('javascript', 'javascript'),
    '.ts': ('typescript', 'typescript'),
    '.jsx': ('javascript_react', 'javascript'),
    '.tsx': ('typescript_react', 'typescript'),
    '.java': ('java', 'java'),
    '.go': ('go', 'go'),
    '.rs': ('rust', 'rust'),
    '.cpp': ('cpp', 'cpp'),
    '.c': ('c', 'c'),
    '.rb': ('ruby', 'ruby'),
    '.php': ('php', 'php'),

    # Markup/data
    '.md': ('markdown', 'markdown'),
    '.html': ('html', 'html'),
    '.css': ('stylesheet', 'css'),
    '.json': ('json_data', 'json'),
    '.yaml': ('yaml_config', 'yaml'),
    '.yml': ('yaml_config', 'yaml'),
    '.xml': ('xml_data', 'xml'),
    '.toml': ('toml_config', 'toml'),

    # Config files
    '.env': ('environment_config', None),
    '.conf': ('config', None),
    '.ini': ('config', None),

    # Documentation
    '.txt': ('text', None),
    '.rst': ('restructured_text', 'rst'),

    # Build/package
    'Dockerfile': ('container_config', 'dockerfile'),
    'Makefile': ('build_config', 'makefile'),
    'package.json': ('package_manifest', 'json'),
    'requirements.txt': ('package_manifest', 'text'),
    'Cargo.toml': ('package_manifest', 'toml'),
    'go.mod': ('package_manifest', 'go'),
}

STANDARD_FILES = {
    '.env': 'environment_config',
    '.env.local': 'environment_config',
    '.env.production': 'environment_config',
    'package.json': 'package_manifest',
    'package-lock.json': 'package_lock',
    'requirements.txt': 'python_dependencies',
    'Pipfile': 'python_dependencies',
    'Cargo.toml': 'rust_manifest',
    'go.mod': 'go_module',
    'docker-compose.yml': 'container_orchestration',
    'Dockerfile': 'container_config',
    '.gitignore': 'vcs_config',
    'README.md': 'documentation',
    'LICENSE': 'license',
}
```

---

## Semantic Analysis

### Python Files

```python
def analyze_python_file(file_path, content):
    """Extract semantic information from Python file"""

    # Simple regex-based extraction (fast, good enough)
    imports = extract_imports(content)
    # import x, from y import z

    exports = extract_python_exports(content)
    # def func(), class ClassName

    dependencies = []  # Local imports

    contains = {
        'classes': len(re.findall(r'^class \w+', content, re.M)),
        'functions': len(re.findall(r'^def \w+', content, re.M)),
        'lines': content.count('\n')
    }

    return {
        'imports': imports,
        'exports': exports,
        'dependencies': dependencies,
        'contains': contains
    }
```

### JavaScript/TypeScript Files

```python
def analyze_javascript_file(file_path, content):
    """Extract semantic information from JS/TS file"""

    imports = extract_js_imports(content)
    # import x from 'y', require('z')

    exports = extract_js_exports(content)
    # export function, export class, module.exports

    return {...}
```

### Configuration Files

```python
def analyze_config_file(file_path, content):
    """Analyze configuration files"""

    if file_path.endswith('.env'):
        # Check for secrets
        has_secrets = any(key in content.upper()
                         for key in ['PASSWORD', 'SECRET', 'TOKEN', 'KEY'])

        # Check if in .gitignore
        in_gitignore = check_gitignore('.env')

        warnings = []
        if has_secrets and not in_gitignore:
            warnings.append('.env contains secrets but not in .gitignore')

        return {'warnings': warnings}

    # Similar for other config types
```

---

## Standard File Warnings

```python
STANDARD_FILE_CHECKS = {
    '.env': {
        'should_be_ignored': True,
        'check_secrets': True,
        'warnings': [
            'Contains secrets but not in .gitignore',
            'No .env.example template found'
        ]
    },

    'package.json': {
        'check_outdated': True,
        'warnings': [
            'Dependencies may be outdated',
            'No package-lock.json found'
        ]
    },

    'requirements.txt': {
        'check_pinned': True,
        'warnings': [
            'Unpinned dependencies found',
            'Virtual environment may need updating'
        ]
    },

    'docker-compose.yml': {
        'check_ports': True,
        'warnings': [
            'Port conflicts detected',
            'No .dockerignore found'
        ]
    }
}
```

---

## Semantic Clustering

```python
def cluster_files_by_semantics(files):
    """Group files by semantic relationships"""

    clusters = {}

    # 1. Explicit naming patterns
    for file in files:
        if 'auth' in file.path.lower():
            add_to_cluster(clusters, 'authentication', file)
        elif 'api' in file.path.lower():
            add_to_cluster(clusters, 'api', file)
        # ... more patterns

    # 2. Import/dependency relationships
    for file in files:
        for dep in file.dependencies:
            # If A imports B, they're related
            relate_files(clusters, file, dep)

    # 3. Directory-based clustering
    for file in files:
        dir_cluster = file.path.split('/')[0]
        add_to_cluster(clusters, dir_cluster, file)

    return clusters
```

---

## Tool Implementations

### 1. scan_project_files()

```python
@mcp.tool()
async def scan_project_files(
    full_scan: bool = False,
    max_files: int = 10000,
    respect_gitignore: bool = True
) -> str:
    """
    Scan project files and build/update semantic model.

    Parameters:
    - full_scan: Force full rescan (default: incremental)
    - max_files: Safety limit (default: 10,000)
    - respect_gitignore: Skip .gitignore patterns (default: True)

    Returns: JSON with scan results and statistics
    """

    conn = get_db()
    session_id = get_current_session_id()
    project_root = get_project_root()

    start_time = time.time()

    # Get stored model
    stored_model = load_stored_model(conn, session_id)

    # Walk filesystem
    all_files = walk_filesystem(
        project_root,
        respect_gitignore=respect_gitignore,
        max_files=max_files
    )

    # Detect changes (mtime + size + hash)
    changes = detect_changes(all_files, stored_model, full_scan)

    # Analyze changed/new files
    for file_path in changes['added'] + changes['modified']:
        analyze_and_store(conn, session_id, file_path)

    # Mark deleted files
    for file_path in changes['deleted']:
        mark_deleted(conn, session_id, file_path)

    # Build clusters
    if len(changes['added']) + len(changes['modified']) > 0:
        rebuild_clusters(conn, session_id)

    scan_time = (time.time() - start_time) * 1000

    return json.dumps({
        'scan_type': 'full' if full_scan else 'incremental',
        'scan_time_ms': round(scan_time, 2),
        'total_files': len(all_files),
        'changes': {
            'added': len(changes['added']),
            'modified': len(changes['modified']),
            'deleted': len(changes['deleted']),
            'unchanged': len(changes['unchanged'])
        },
        'file_types': get_type_distribution(conn, session_id),
        'clusters': get_cluster_summary(conn, session_id),
        'warnings': get_warnings(conn, session_id)
    }, indent=2)
```

### 2. query_files()

```python
@mcp.tool()
async def query_files(
    query: str,
    file_type: Optional[str] = None,
    cluster: Optional[str] = None,
    limit: int = 20
) -> str:
    """
    Search file semantic model.

    Parameters:
    - query: Search term (searches path, purpose, imports, exports)
    - file_type: Filter by type ('python', 'javascript', etc.)
    - cluster: Filter by cluster ('authentication', 'api', etc.)
    - limit: Max results (default: 20)

    Returns: JSON with matching files and semantic info
    """

    conn = get_db()
    session_id = get_current_session_id()

    sql = """
        SELECT
            file_path, file_type, purpose, language,
            imports, exports, dependencies, used_by,
            cluster_name, related_files, is_standard,
            file_size, modified_time
        FROM file_semantic_model
        WHERE session_id = ?
          AND (
              file_path LIKE ?
              OR purpose LIKE ?
              OR imports LIKE ?
              OR exports LIKE ?
          )
    """

    params = [session_id, f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%']

    if file_type:
        sql += " AND file_type = ?"
        params.append(file_type)

    if cluster:
        sql += " AND cluster_name = ?"
        params.append(cluster)

    sql += f" LIMIT {limit}"

    cursor = conn.execute(sql, params)
    results = cursor.fetchall()

    # Format results
    formatted = []
    for row in results:
        formatted.append({
            'path': row['file_path'],
            'type': row['file_type'],
            'purpose': row['purpose'],
            'language': row['language'],
            'imports': json.loads(row['imports'] or '[]'),
            'exports': json.loads(row['exports'] or '[]'),
            'dependencies': json.loads(row['dependencies'] or '[]'),
            'used_by': json.loads(row['used_by'] or '[]'),
            'cluster': row['cluster_name'],
            'is_standard': bool(row['is_standard']),
            'size_kb': round(row['file_size'] / 1024, 2),
            'modified': datetime.fromtimestamp(row['modified_time']).isoformat()
        })

    return json.dumps({
        'query': query,
        'filters': {'file_type': file_type, 'cluster': cluster},
        'total_found': len(formatted),
        'results': formatted
    }, indent=2)
```

### 3. get_file_clusters()

```python
@mcp.tool()
async def get_file_clusters() -> str:
    """
    Get semantic file clusters.

    Returns: JSON with clusters and their files
    """

    conn = get_db()
    session_id = get_current_session_id()

    cursor = conn.execute("""
        SELECT
            cluster_name,
            COUNT(*) as file_count,
            SUM(file_size) as total_size,
            GROUP_CONCAT(file_type) as types
        FROM file_semantic_model
        WHERE session_id = ?
        GROUP BY cluster_name
        ORDER BY file_count DESC
    """, (session_id,))

    clusters = []
    for row in cursor.fetchall():
        # Get sample files from cluster
        files_cursor = conn.execute("""
            SELECT file_path, purpose
            FROM file_semantic_model
            WHERE session_id = ? AND cluster_name = ?
            LIMIT 5
        """, (session_id, row['cluster_name']))

        sample_files = [
            {'path': f['file_path'], 'purpose': f['purpose']}
            for f in files_cursor.fetchall()
        ]

        clusters.append({
            'name': row['cluster_name'],
            'file_count': row['file_count'],
            'total_size_mb': round(row['total_size'] / (1024*1024), 2),
            'file_types': list(set(row['types'].split(','))),
            'sample_files': sample_files
        })

    return json.dumps({
        'total_clusters': len(clusters),
        'clusters': clusters
    }, indent=2)
```

### 4. file_model_status()

```python
@mcp.tool()
async def file_model_status() -> str:
    """
    Get file semantic model statistics.

    Returns: JSON with model status and health
    """

    conn = get_db()
    session_id = get_current_session_id()

    cursor = conn.execute("""
        SELECT
            COUNT(*) as total_files,
            SUM(file_size) as total_size,
            AVG(file_size) as avg_size,
            MIN(last_scanned) as oldest_scan,
            MAX(last_scanned) as newest_scan,
            AVG(scan_duration_ms) as avg_scan_time
        FROM file_semantic_model
        WHERE session_id = ?
    """, (session_id,))

    stats = cursor.fetchone()

    # Type distribution
    type_cursor = conn.execute("""
        SELECT file_type, COUNT(*) as count
        FROM file_semantic_model
        WHERE session_id = ?
        GROUP BY file_type
        ORDER BY count DESC
        LIMIT 10
    """, (session_id,))

    type_dist = {row['file_type']: row['count'] for row in type_cursor.fetchall()}

    # Standard files
    std_cursor = conn.execute("""
        SELECT file_path, standard_type, warnings
        FROM file_semantic_model
        WHERE session_id = ? AND is_standard = 1
    """, (session_id,))

    standard_files = [
        {
            'path': row['file_path'],
            'type': row['standard_type'],
            'warnings': json.loads(row['warnings'] or '[]')
        }
        for row in std_cursor.fetchall()
    ]

    return json.dumps({
        'overview': {
            'total_files': stats['total_files'],
            'total_size_mb': round(stats['total_size'] / (1024*1024), 2),
            'average_file_kb': round(stats['avg_size'] / 1024, 2),
            'last_full_scan': datetime.fromtimestamp(stats['oldest_scan']).isoformat() if stats['oldest_scan'] else None,
            'last_update': datetime.fromtimestamp(stats['newest_scan']).isoformat() if stats['newest_scan'] else None,
            'avg_scan_time_ms': round(stats['avg_scan_time'] or 0, 2)
        },
        'type_distribution': type_dist,
        'standard_files': standard_files,
        'health': 'healthy' if stats['total_files'] > 0 else 'no_data'
    }, indent=2)
```

---

## Integration with wake_up()

```python
async def wake_up() -> str:
    # ... existing code ...

    # Auto-scan project files (if project directory)
    file_model = None
    if is_project_directory():
        try:
            # Quick incremental scan
            scan_result = await scan_project_files(full_scan=False)
            file_model = json.loads(scan_result)
        except Exception as e:
            file_model = {'error': str(e)}

    return json.dumps({
        'session': {...},
        'git': {...},
        'contexts': {...},
        'stale_contexts': [...],
        'file_model': file_model,  # NEW
        'handover': {...},
        'memory_health': {...}
    }, indent=2)
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (Now)
- ✅ Database schema
- ✅ Change detection (mtime + size + hash)
- ✅ Smart hashing
- ✅ File type detection
- ✅ Basic tool: scan_project_files()

### Phase 2: Semantic Analysis
- Python file analysis (imports/exports)
- JavaScript file analysis
- Standard file recognition
- Warning generation

### Phase 3: Clustering & Query
- Semantic clustering algorithm
- query_files() tool
- get_file_clusters() tool
- file_model_status() tool

### Phase 4: Integration
- Integrate with wake_up()
- Integrate with sleep()
- Optimize performance
- Comprehensive testing

---

## Testing Strategy

```python
# Test change detection
test_mtime_unchanged()
test_size_changed()
test_content_changed()
test_touched_but_unchanged()

# Test hashing
test_full_hash()
test_partial_hash()
test_hash_consistency()

# Test semantic analysis
test_python_imports_extraction()
test_javascript_exports()
test_standard_file_warnings()

# Test clustering
test_cluster_by_naming()
test_cluster_by_dependencies()
test_cluster_by_directory()

# Test performance
test_scan_1000_files()
test_incremental_scan()
test_gitignore_respect()
```

---

**Ready to implement Phase 1!**
