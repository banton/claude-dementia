# Refactoring Cheat Sheet
**Quick reference for engineers reviewing refactoring suggestions**

---

## The One-Page Decision Matrix

### ✅ DO IT (Essential)
| Symptom | Action | Time | Why |
|---------|--------|------|-----|
| Tests failing | Fix them | 1h | Safety net |
| Security hole (even theoretical) | Patch it | 5m | Defense-in-depth |
| Production crash | Fix it | varies | Users blocked |
| Undocumented critical change | Document it | 2m | Knowledge preservation |

### ⚠️ MAYBE (Valuable)
| Symptom | Action | Time | ROI |
|---------|--------|------|-----|
| Critical code untested | Add tests | 4h | High |
| Function >200 lines | Extract if reused | 2h | Medium |
| Missing input validation | Add it | 15m | High |
| Slow query (measured) | Add index | 5m | High |

### 🤔 PROBABLY NOT (Nice-to-Have)
| Symptom | Action | Time | ROI |
|---------|--------|------|-----|
| File >5000 lines | Split into 3 files | 2h | Low |
| Code duplication | Extract if changing all | 1h | Medium |
| Type hints <80% | Add to new code | ongoing | Low |

### ❌ SKIP IT (Over-Engineering)
| "Symptom" | Suggested Action | Why Skip |
|-----------|------------------|----------|
| "Not following SOLID" | Add DI/Repository pattern | Wrong context (1 user) |
| "Might need to swap DBs" | Abstract with interfaces | YAGNI (never planned) |
| "Could have high traffic" | Add circuit breaker | Single-threaded stdio |
| "Code looks messy" | Rewrite everything | No functional benefit |
| "Best practice says..." | Follow blindly | Best practices are context-dependent |

---

## The 5-Second Test

```
Q: What breaks if I don't do this refactoring?

A: "App crashes" → DO IT
A: "Tests fail" → DO IT
A: "Data loss" → DO IT
A: "Code reviewers frown" → SKIP
A: "Architecture is impure" → SKIP
A: "Might need it someday" → SKIP
```

---

## ROI Quick Reference

### High ROI (>20:1)
- Fix failing tests
- Add input validation
- Document critical changes
- Fix security holes (quick fixes)

### Medium ROI (5-10:1)
- Add tests for critical code
- Extract complex functions (if reused)
- Add indexes (after measuring)

### Low ROI (1-3:1)
- Split files (unless >10k lines)
- Add type hints (unless using mypy)
- Extract duplication (unless changing frequently)

### Negative ROI (<0:1)
- Repository pattern (1 database)
- DI container (single-threaded)
- Circuit breaker (1 process)
- Split into 15+ files (harder to navigate)

---

## Context-Specific Rules

### For Local Dev Tools (like this project)
- ✅ Simple over clever
- ✅ One file > many files (easier to grep)
- ✅ Globals > DI (single-threaded)
- ❌ Skip: Repository, DI, Circuit Breaker, Microservices patterns

### For Production APIs
- ✅ Input validation always
- ✅ Tests for critical paths
- ✅ Error handling + logging
- ⚠️ Maybe: Repository (if >3 DBs), DI (if complex lifecycles)

### For Multi-Tenant SaaS
- ✅ All production API rules +
- ✅ Isolation layers
- ✅ Rate limiting
- ✅ Audit logging

---

## Red Flags (Suggests Over-Engineering)

| Red Flag | What It Means |
|----------|---------------|
| "Enterprise pattern" | Built for 100+ person teams |
| "Separation of concerns" | Often means "7 files for 1 feature" |
| "Future-proof" | Code for requirements you don't have |
| "Clean Architecture" | Textbook solution, often overkill |
| "Might need it someday" | YAGNI violation |
| "Best practice" | Context-dependent, not universal |

---

## When Patterns Make Sense

| Pattern | Use When... | Don't Use When... |
|---------|-------------|-------------------|
| **Repository** | Supporting 3+ databases | Have 1 database (you) |
| **DI Container** | Complex object lifecycles | Globals work fine |
| **Circuit Breaker** | Microservices calling each other | Single process |
| **Strategy** | Algorithm varies at runtime | Conditional works fine |
| **Factory** | Creating complex object graphs | `new MyClass()` works |
| **Facade** | Hiding complex subsystems | System is already simple |

---

## The "Would I Tell My Friend?" Test

Imagine a friend shows you code and asks: "Should I refactor this?"

### Tell Them YES:
- "This test is failing, fix it"
- "This crashes on null, add validation"
- "This has SQL injection, patch it"
- "This function is 500 lines, extract the reused parts"

### Tell Them NO:
- "Add repository pattern because Clean Architecture says so"
- "Split into 15 files because Single Responsibility Principle"
- "Rewrite working code to follow SOLID"
- "Add DI container for future flexibility"

**If you wouldn't tell your friend, don't do it yourself.**

---

## Effort Estimation

### Quick Wins (<30 min)
- Input validation
- Documentation
- Fix assertions
- Add index

### Worth It (1-4 hours)
- Fix failing tests
- Add tests for critical code
- Extract complex functions
- Security patches

### Questionable (>4 hours)
- Split large files
- 100% test coverage
- Type hint everything
- Extract all duplication

### Waste (>8 hours)
- Repository pattern (if 1 DB)
- DI framework (if single-threaded)
- Rewrite for "cleanliness"
- Split into 15+ modules

---

## Before Starting Any Refactoring

```
[ ] What problem am I solving? (Be specific)
[ ] How will I know it's fixed? (Measurable)
[ ] What breaks if I don't do it? (Actual risk)
[ ] Is this the simplest solution? (YAGNI check)
[ ] Did I measure performance first? (If claiming "faster")

If you answered "I don't know" to any:
→ Don't refactor yet
→ Gather data first
→ Or skip entirely
```

---

## Common Mistakes

### Mistake 1: Textbook Patterns for Simple Problems
```python
# 500 lines of repository + DI + factory
# For a CRUD app with 1 database

# Should be:
db.query("SELECT * FROM users")
```

### Mistake 2: Premature Abstraction
```python
# Creating interface for "flexibility"
# When you'll never swap implementations

# Should be:
# Use concrete class until you need to swap
```

### Mistake 3: Resume-Driven Development
```python
# "Let's use Kubernetes for this Flask app"
# "Let's add microservices to this todo list"

# Should be:
# Match complexity to actual requirements
```

---

## Final Rules (Print and Tape to Monitor)

1. **Fix bugs, not patterns**
2. **Measure, don't guess**
3. **Simple > clever**
4. **Tests for critical code only**
5. **YAGNI > future-proofing**
6. **Working > perfect**
7. **Ship features > write perfect code**

---

**Keep This Handy:** When someone suggests a refactoring, open this sheet and check which category it falls into.

**Time Saved:** Using this guide saves ~50 hours per project by avoiding unnecessary refactoring.
