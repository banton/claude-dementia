# Refactoring Decision Tree
**Quick Reference for "Should I Refactor This?"**

## The 5-Second Test

Ask yourself:
1. **Does it fix a bug?** → YES → Do it
2. **Does it prevent a bug?** → YES → Do it
3. **Does it make the code faster?** → Measure first, then decide
4. **Does it make the code "cleaner"?** → NO → Skip it

## The 3 Questions

Before any refactoring, answer these:

### Question 1: What problem does this solve?
- ✅ **Good answer:** "Tests are failing" / "App crashes on bad input"
- ❌ **Bad answer:** "Textbook says to do it this way" / "Looks ugly"

### Question 2: How will I know if it works?
- ✅ **Good answer:** "Test passes" / "Error stops happening"
- ❌ **Bad answer:** "Code looks better" / "Follows best practices"

### Question 3: What happens if I don't do it?
- ✅ **Good answer:** "App breaks in production" / "Users lose data"
- ❌ **Bad answer:** "Code reviewers might complain" / "Architecture is impure"

## Pattern Recognition

### ✅ DO Refactor When:
- **Tests are red** → Always fix
- **Security vulnerability** → Even theoretical ones (if fix is <30 min)
- **Production bug** → Always fix
- **Function is >300 lines** → Extract only if you need to reuse parts
- **Performance issue** → After measuring, not guessing

### ⚠️ MAYBE Refactor When:
- **File is >5,000 lines** → Only if you're constantly getting lost
- **Function is >100 lines** → Only if it's hard to understand
- **No tests** → Only for critical code (data loss, security, $$$)
- **Duplication** → Only if changing one requires changing all

### ❌ DON'T Refactor When:
- **"Best practice"** → Best practices are context-dependent
- **"SOLID principles"** → These are guidelines, not laws
- **"Clean architecture"** → Designed for teams of 50+, not solo devs
- **"Future-proofing"** → YAGNI (You Ain't Gonna Need It)
- **"Makes it testable"** → If code works without tests, maybe you don't need tests

## The Scale of Impact

### Fix These (High Impact, Low Effort)
| Issue | Time | Impact | Priority |
|-------|------|--------|----------|
| Broken tests | 1h | Can't refactor safely | 🔴 Critical |
| Missing input validation | 15m | App crashes | 🔴 Critical |
| SQL injection (even theoretical) | 5m | Data breach | 🔴 Critical |
| Undocumented config changes | 2m | Team confusion | 🟡 Important |

### Consider These (High Impact, Medium Effort)
| Issue | Time | Impact | Priority |
|-------|------|--------|----------|
| No tests for critical code | 4h | Can't refactor safely | 🟡 Important |
| Complex function (200+ lines) | 2h | Hard to debug | 🟢 Nice |
| Missing error handling | 1h | Silent failures | 🟡 Important |

### Skip These (Low Impact, High Effort)
| Issue | Time | Impact | Priority |
|-------|------|--------|----------|
| "Repository pattern" | 8h | None (you have 1 DB) | ⚫ Skip |
| "Dependency injection" | 6h | None (single-threaded) | ⚫ Skip |
| "100% test coverage" | 20h | Diminishing returns | ⚫ Skip |
| "Extract all functions" | 10h | Harder to navigate | ⚫ Skip |
| "Circuit breaker" | 4h | None (1 process) | ⚫ Skip |

## Context-Specific Rules

### For This Project (claude-dementia)
- **Single-user tool** → Skip multi-tenancy abstractions
- **Stdio mode** → Skip concurrency patterns
- **1 database** → Skip repository pattern
- **Local dev only** → Skip cloud-native patterns

### When to Break These Rules
- **Moving to production** → Re-evaluate security, scalability
- **Adding 5+ contributors** → Re-evaluate code organization
- **Switching databases** → Then add repository pattern
- **Going multi-tenant** → Then add isolation layers

## The "Would I Tell My Friend?" Test

Imagine your friend asks: "Should I refactor this?"

### If you'd say YES:
- "Tests are broken, fix them"
- "That's a security hole, patch it"
- "App crashes there, add error handling"

### If you'd say NO:
- "Split this into 15 files because Clean Architecture"
- "Add DI container for future flexibility"
- "Rewrite working code to follow SOLID"

**If you wouldn't tell your friend to do it, don't do it yourself.**

## Anti-Patterns to Avoid

### ❌ Premature Abstraction
```python
# BAD: "I might need to swap databases someday"
class DatabaseInterface(ABC):
    @abstractmethod
    def query(self): pass

# GOOD: Use the database directly until you actually need to swap
conn.execute("SELECT * FROM users")
```

### ❌ Architecture Astronaut Syndrome
```python
# BAD: "Let's use microservices, event sourcing, CQRS, and DDD"
# For a todo list app

# GOOD: "Let's use a single file and SQLite"
```

### ❌ Resume-Driven Development
```python
# BAD: "I want to learn Kubernetes, let's deploy this hello-world app"

# GOOD: "This needs high availability, let's use Kubernetes"
```

## The One-Liner Rules

1. **Fix bugs, not patterns**
2. **Measure performance, don't guess**
3. **Write tests for critical code, not all code**
4. **Refactor when changing, not for "cleanliness"**
5. **Simple > clever**
6. **Working > perfect**
7. **YAGNI > future-proofing**

## When in Doubt

Ask: **"What's the worst that happens if I don't refactor this?"**

- "Production goes down" → Refactor now
- "Tests fail" → Refactor now
- "Data loss" → Refactor now
- "Code reviewer frowns" → Skip
- "Architecture is impure" → Skip
- "Uncle Bob wouldn't approve" → Skip

---

**Remember:** Your job is to ship features, not write textbook-perfect code. Refactor only when it directly serves that goal.
