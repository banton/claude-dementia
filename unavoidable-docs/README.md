# 🚨 UNAVOIDABLE DOCUMENTATION SYSTEM

A documentation enforcement system that makes it **physically impossible** to skip documentation. Every undocumented item creates "documentation debt" that blocks all operations until resolved.

## 🎯 Core Concept

- **Every file** is tracked for documentation status
- **Every constant** must be documented
- **Every function** needs proper docs
- **Every change** creates debt if undocumented
- **Git commits are BLOCKED** when critical debt exists

## 📦 Installation

### Prerequisites

- PostgreSQL 12+ installed and running
- Python 3.8+
- Git repository initialized

### Quick Setup

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Set up database (requires PostgreSQL running)
cd database
./setup.sh
cd ..

# 3. Test the system
python test_system.py

# 4. Install git pre-commit hook
./enforcement/pre_commit_hook.sh --install
```

## 🚀 Usage

### Start File Monitoring

Monitor your project for undocumented code:

```bash
# Monitor current directory
python watchers/file_monitor.py

# Monitor specific directory
python watchers/file_monitor.py /path/to/project
```

### Scan for Constants

Find all hardcoded values that should be documented:

```bash
# Scan entire project
python watchers/constant_extractor.py

# Scan specific file
python watchers/constant_extractor.py src/config.py
```

### Check Documentation Status

```bash
# Run test suite to see current status
python test_system.py
```

## 🔒 Enforcement Levels

The system progressively blocks operations based on debt age:

| Hours | Action | Severity |
|-------|--------|----------|
| 0-4   | Gentle reminders | Info |
| 4-12  | Warnings on operations | Warning |
| 12-24 | Block non-essential ops | Error |
| 24+   | **BLOCK EVERYTHING** | Critical |

## 📊 Documentation Debt Types

### Critical Priority (Blocks immediately)
- Hardcoded credentials
- New API endpoints
- Database schema changes

### High Priority (Blocks after 12 hours)
- New files
- New classes
- New dependencies

### Medium Priority (Blocks after 24 hours)
- New functions
- New constants
- Modified logic

### Low Priority (Information only)
- New variables
- Config changes
- Minor updates

## 🛠️ Configuration

Edit `config.py` to customize:

```python
# Enforcement level
ENFORCEMENT_LEVEL = 'medium'  # low, medium, high, critical

# Directories to watch
WATCH_DIRECTORIES = ['.', 'src', 'lib']

# File types to monitor
MONITORED_EXTENSIONS = ['.py', '.js', '.ts', ...]
```

## 📈 Database Schema

The system tracks everything in PostgreSQL:

- **file_documentation_status** - Every file's doc status
- **documentation_debt** - All debt items
- **undocumented_constants** - Detected constants
- **undocumented_functions** - Functions needing docs
- **documentation_sessions** - Work tracking
- **enforcement_blocks** - Blocked operations

## 🚫 What Gets Blocked

When critical debt exists:

- ❌ Git commits
- ❌ Git pushes
- ❌ Build processes
- ❌ Deployments
- ❌ New feature development
- ✅ Only documentation allowed!

## 📝 Resolving Debt

### Option 1: Document in Code

Add proper documentation to your code:

```python
# For constants
API_URL = "https://api.example.com"  # Production API endpoint

# For functions
def process_payment(amount: float, currency: str) -> bool:
    """
    Process a payment transaction.
    
    Args:
        amount: Payment amount
        currency: ISO 4217 currency code
    
    Returns:
        True if payment successful
    """
    pass
```

### Option 2: Use Documentation Mode

When debt is critical, the system enters "Documentation Mode":
- All other operations are blocked
- You can only add documentation
- Once debt is resolved, normal operations resume

## 🎯 Success Metrics

The system tracks:
- **Documentation Coverage**: Target 100%
- **Average Debt Age**: Target <4 hours
- **Constants Documented**: Target 100%
- **Function Documentation**: Target 100%
- **Session Net Debt**: Target ≤0

## 🐛 Troubleshooting

### Database Connection Failed
```bash
# Check PostgreSQL is running
pg_isready

# Check connection details in config.py
# Ensure database exists and user has permissions
```

### Pre-commit Hook Not Working
```bash
# Ensure hook is installed
./enforcement/pre_commit_hook.sh --install

# Check hook is executable
chmod +x .git/hooks/pre-commit
```

### File Monitor Not Detecting Changes
```bash
# Check ignored patterns in config.py
# Ensure file extensions are monitored
# Check watchdog is installed: pip install watchdog
```

## 🤝 Integration with Claude Code

This system integrates with Claude's memory system:

1. Documentation status is tracked in memory
2. Constants are added to constants registry
3. Project map is updated with doc status
4. Session tracking helps Claude understand debt

## ⚠️ Important Notes

- **No escape routes**: The system is designed to be unavoidable
- **Documentation debt accumulates interest**: Older debt becomes more critical
- **Skipping is tracked**: Every skip increases debt priority
- **Quality matters**: Poor documentation is detected and rejected

## 📚 Examples

### Example: New File Created
```
📄 New file detected: src/payment.py
🚨 DOCUMENTATION DEBT CREATED: new_file - src/payment.py
   Debt ID: abc123
⚠️  WARNING: 1 CRITICAL DEBT ITEMS EXIST!
   Operations will be blocked until resolved.
```

### Example: Constant Detected
```
📋 Found 3 potential constants in config.py:
   🔴 Line 10: api_key = sk_test_123...
      Suggested name: API_KEY
      Purpose: ⚠️ HARDCODED CREDENTIAL - SECURITY RISK
      Confidence: 95%
```

### Example: Commit Blocked
```
🚨 UNAVOIDABLE DOCUMENTATION SYSTEM - COMMIT CHECK
==================================================
📊 Documentation Debt Summary
--------------------------------
Total debt items: 5
  ● Critical: 2
  ⏰ Overdue (>24h): 1

❌ COMMIT BLOCKED: Critical documentation debt exists

To resolve this:
1. Document all critical items listed above
2. Or use Claude Code: 'Please resolve all critical documentation debt'
```

## 🚀 Future Enhancements

- [ ] Web dashboard for metrics
- [ ] Auto-documentation with AI
- [ ] IDE integration
- [ ] Team leaderboards
- [ ] Documentation quality scoring
- [ ] Automatic PR comments

---

**Remember**: Documentation is not optional. It is UNAVOIDABLE.