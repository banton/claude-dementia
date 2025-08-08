# 🚨 UNAVOIDABLE DOCUMENTATION SYSTEM - IMPLEMENTATION PLAN

## Executive Summary
A documentation enforcement system that makes it **physically impossible** to skip documentation. Every undocumented item creates "documentation debt" that blocks all operations until resolved.

## System Architecture

### Core Components

```
unavoidable-docs/
├── database/
│   ├── schema.sql              # PostgreSQL schema
│   ├── migrations/             # Database migrations
│   └── seed.sql               # Initial data
├── watchers/
│   ├── file_monitor.py        # Watchdog-based file system monitor
│   ├── constant_extractor.py # Detects hardcoded values
│   └── function_parser.py    # Parses functions/methods
├── enforcement/
│   ├── pre_commit_hook.sh    # Git pre-commit blocker
│   ├── mcp_wrapper.py        # Wraps MCP tools
│   └── doc_mode.py          # Forces documentation mode
├── debt/
│   ├── tracker.py            # Debt tracking system
│   ├── priority.py          # Priority escalation
│   └── interest.py         # Debt interest calculator
├── auto_doc/
│   ├── templates.py         # Documentation templates
│   ├── constant_doc.py     # Constant documenter
│   └── function_doc.py    # Function documenter
├── reporting/
│   ├── dashboard.py        # Metrics dashboard
│   ├── daily_report.py    # Daily documentation report
│   └── session_tracker.py # Track Claude sessions
└── integration/
    ├── memory_link.py     # Links to CLAUDE.md system
    ├── project_map.py    # Updates PROJECT_MAP.md
    └── constants_reg.py  # Constants registry integration
```

## Database Schema Design

### Tables

#### 1. file_documentation_status
```sql
CREATE TABLE file_documentation_status (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    status VARCHAR(20) CHECK (status IN ('undocumented', 'documented', 'outdated', 'ignored')),
    first_seen TIMESTAMP DEFAULT NOW(),
    last_modified TIMESTAMP,
    last_documented TIMESTAMP,
    doc_completeness INTEGER CHECK (doc_completeness >= 0 AND doc_completeness <= 100),
    has_constants BOOLEAN DEFAULT FALSE,
    constants_documented INTEGER DEFAULT 0,
    total_constants INTEGER DEFAULT 0,
    has_functions BOOLEAN DEFAULT FALSE,
    functions_documented INTEGER DEFAULT 0,
    total_functions INTEGER DEFAULT 0,
    debt_level VARCHAR(10) CHECK (debt_level IN ('critical', 'high', 'medium', 'low')),
    debt_age_hours INTEGER DEFAULT 0,
    times_skipped INTEGER DEFAULT 0,
    file_type VARCHAR(20),
    file_size INTEGER,
    line_count INTEGER,
    complexity_score INTEGER
);
```

#### 2. documentation_debt
```sql
CREATE TABLE documentation_debt (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_documentation_status(id),
    debt_type VARCHAR(30) CHECK (debt_type IN (
        'new_file', 'new_function', 'new_constant', 
        'modified_logic', 'new_endpoint', 'new_dependency'
    )),
    description TEXT,
    priority VARCHAR(10) DEFAULT 'low',
    created_at TIMESTAMP DEFAULT NOW(),
    escalated_at TIMESTAMP,
    is_blocking BOOLEAN DEFAULT FALSE,
    blocks_operations TEXT[], -- Array of blocked operations
    assigned_session VARCHAR(100),
    resolution_attempts INTEGER DEFAULT 0,
    auto_detected BOOLEAN DEFAULT TRUE,
    context TEXT -- Surrounding code context
);
```

#### 3. undocumented_constants
```sql
CREATE TABLE undocumented_constants (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_documentation_status(id),
    constant_value TEXT NOT NULL,
    constant_type VARCHAR(30), -- 'url', 'port', 'api_endpoint', 'env_var', 'ip'
    line_number INTEGER,
    confidence_score DECIMAL(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    probable_name VARCHAR(100),
    probable_purpose TEXT,
    context_before TEXT,
    context_after TEXT,
    detected_at TIMESTAMP DEFAULT NOW(),
    documented_at TIMESTAMP,
    documentation TEXT
);
```

#### 4. documentation_sessions
```sql
CREATE TABLE documentation_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    debt_created INTEGER DEFAULT 0,
    debt_resolved INTEGER DEFAULT 0,
    net_debt INTEGER GENERATED ALWAYS AS (debt_created - debt_resolved) STORED,
    items_documented JSON,
    quality_score INTEGER,
    time_spent_minutes INTEGER,
    forced_documentation BOOLEAN DEFAULT FALSE,
    session_blocked BOOLEAN DEFAULT FALSE
);
```

## Implementation Phases

### Phase 1: Core Detection System (Week 1)

#### Day 1-2: Database and File Watching
- Set up PostgreSQL database with schema
- Implement watchdog file system monitor
- Create basic debt entry system
- Test file creation/modification detection

#### Day 3-4: Constant and Function Extraction
- Build regex patterns for constant detection
- Implement AST parsing for functions
- Create confidence scoring system
- Test extraction accuracy

### Phase 2: Enforcement Mechanisms (Week 2)

#### Day 5-6: Git Hooks and Blocking
- Create pre-commit hook script
- Implement debt checking logic
- Build commit message validator
- Test blocking scenarios

#### Day 7-8: MCP Tool Integration
- Wrap existing MCP tools
- Add debt checking before operations
- Create documentation mode trigger
- Test tool blocking

### Phase 3: Auto-Documentation (Week 3)

#### Day 9-10: Template Generation
- Build JSDoc/docstring templates
- Create constant documentation format
- Generate file context descriptions
- Test template quality

#### Day 11-12: Smart Suggestions
- Implement context-aware suggestions
- Build purpose inference system
- Create documentation quality scorer
- Test suggestion accuracy

### Phase 4: Integration & Reporting (Week 4)

#### Day 13-14: Memory System Integration
- Link to CLAUDE.md system
- Update PROJECT_MAP.md automatically
- Integrate with constants registry
- Test cross-system functionality

#### Day 15-16: Dashboard and Reports
- Build metrics dashboard
- Create daily/weekly reports
- Implement session tracking
- Test reporting accuracy

## Detection Patterns

### Constants to Auto-Detect
```python
PATTERNS = {
    'url': r'https?://[^\s]+',
    'localhost': r'localhost:\d+',
    'port': r'(?:PORT|port)\s*=\s*\d+',
    'api_endpoint': r'/api/[^\s]+',
    'env_var': r'process\.env\.[A-Z_]+',
    'api_key': r'(?:sk_|pk_|api_)[a-zA-Z0-9]+',
    'database': r'(?:mongodb|postgres|mysql)://[^\s]+',
    'timeout': r'(?:timeout|TIMEOUT)\s*=\s*\d+',
    'limit': r'(?:limit|LIMIT|max|MAX)\s*=\s*\d+',
    'ip_address': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
}
```

### Priority Escalation Rules
```python
def calculate_priority(debt_age_hours, file_importance, debt_type):
    if debt_age_hours > 24:
        return 'critical'
    elif debt_age_hours > 12:
        return 'high'
    elif file_importance == 'core' or debt_type in ['new_endpoint', 'new_dependency']:
        return 'high'
    elif debt_age_hours > 4:
        return 'medium'
    else:
        return 'low'
```

## Enforcement Strategies

### Progressive Blocking Timeline
| Hours | Action | Severity |
|-------|--------|----------|
| 0-4   | Gentle reminders on operations | Info |
| 4-12  | Warnings on every operation | Warning |
| 12-24 | Block non-essential operations | Error |
| 24+   | BLOCK EVERYTHING except documentation | Critical |

### Blocked Operations by Priority
| Priority | Blocked Operations |
|----------|-------------------|
| Low | None (reminders only) |
| Medium | New feature development |
| High | All code modifications |
| Critical | ALL operations including read |

## Success Metrics

### Key Performance Indicators
1. **Documentation Coverage**: Target 100%
2. **Average Debt Age**: Target <4 hours
3. **Constants Documented**: Target 100%
4. **Function Documentation**: Target 100%
5. **Session Net Debt**: Target ≤0

### Quality Metrics
- Documentation completeness (0-100%)
- Documentation freshness (hours since update)
- Documentation accuracy (matches code)
- Documentation clarity (readability score)

## Integration Points

### With Memory System
- Check documentation status before memory operations
- Block undocumented files from memory
- Add documentation warnings to recalls
- Sync debt status with memory updates

### With Constants Registry
- Auto-add detected constants to pending
- Block constant usage until documented
- Link constant docs to registry
- Track constant documentation coverage

### With PROJECT_MAP.md
- Add status indicators (🔴🟡🟢)
- Show debt counts per directory
- Block navigation to undocumented areas
- Auto-update on documentation changes

## Anti-Skip Mechanisms

### Common Skip Attempts
| Attempt | Prevention |
|---------|------------|
| "I'll document later" | Immediate blocking |
| "Self-documenting code" | Explicit docs required |
| "Temporary code" | Must document temporary |
| "Small change" | All changes need docs |
| "TODO: document" | Not valid documentation |

### Detection of Bad Documentation
- Generic descriptions ("This is a function")
- Copy-pasted documentation
- Mismatched documentation
- Placeholder text
- Documentation older than code

## Example Enforcement Flow

```python
# Claude attempts to write code
Claude: client.create_file("new_feature.py")
System: ❌ BLOCKED: Outstanding documentation debt

# System shows debt
DOCUMENTATION DEBT CRITICAL:
1. /api/endpoint.py - 48 hours old - NEW_ENDPOINT
2. PORT = 3002 - 36 hours old - NEW_CONSTANT  
3. calculateTax() - 24 hours old - NEW_FUNCTION

ENTERING FORCED DOCUMENTATION MODE...
Only documentation operations allowed.

# Claude must document
Claude: document_constant("PORT", "API server port for production")
System: ✅ 1/3 documented

Claude: document_function("calculateTax", "Calculates tax based on region")
System: ✅ 2/3 documented

Claude: document_file("/api/endpoint.py", "Handles payment processing")
System: ✅ 3/3 documented

DOCUMENTATION COMPLETE. Normal operations resumed.
```

## Next Steps

1. **Immediate**: Create project structure and database
2. **Day 1**: Implement basic file watcher
3. **Day 2**: Build constant extractor
4. **Day 3**: Create pre-commit hook
5. **Week 1**: Complete Phase 1
6. **Month 1**: Full system operational

## Success Criteria Checklist

- [ ] Zero undocumented code can be committed
- [ ] Claude cannot skip documentation tasks
- [ ] Documentation debt never exceeds 24 hours
- [ ] Every constant is captured and documented
- [ ] Documentation quality score stays above 80%
- [ ] No surprise undocumented code in production
- [ ] 100% enforcement with zero escape routes

---

**Remember**: Documentation is not optional. It is UNAVOIDABLE.