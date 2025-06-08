# Example Usage: Claude Code Memory System

This example shows a typical development session using the Claude Code Memory System.

## Session 1: Project Setup

### You:
```
Here's your operating guide. Read CLAUDE.md first and follow it for all development on this project. 

We're building a task management API with Python/FastAPI. Set up the initial project structure.
```

### Claude Code:
```
I'll read CLAUDE.md first to understand the development workflow.

[Reads CLAUDE.md]

Following the protocol, I'll first update the Current Working Context and then set up the project.

Let me start by creating memory/current-session.md:

## Session Start: 2024-01-15 10:00 AM

### Objective
Set up initial project structure for task management API using Python/FastAPI

### Plan
1. Create project structure
2. Set up FastAPI boilerplate
3. Create initial tests
4. Document in memory/implementations/

[Creates project structure, writes tests first, implements code...]

Before ending this session, I'll update the documentation:

## Session End: 2024-01-15 11:30 AM

### What I Accomplished
- Created project structure with src/, tests/, docs/
- Set up FastAPI application with health check endpoint
- Created pytest configuration
- Added requirements.txt with dependencies

### Current State
- Branch: main
- Last commit: a1b2c3d "feat: initial FastAPI project setup"
- Tests status: 2 passing (health check tests)

### Next Session Should
- Create database models for tasks
- Set up PostgreSQL connection
- Add task CRUD endpoints

### Files Created
- src/main.py
- src/api/health.py
- tests/test_health.py
- requirements.txt
```

## Session 2: Next Day

### You:
```
Continue development on the task management API.
```

### Claude Code:
```
I'll start by reading CLAUDE.md and checking where I left off.

[Reads CLAUDE.md]
[Reads memory/current-session.md]

I see from yesterday's session that I completed the initial setup and should now:
1. Create database models for tasks
2. Set up PostgreSQL connection
3. Add task CRUD endpoints

Let me also check if there are any questions I should address first...
[Checks memory/questions/]

🤔 **I need clarification before proceeding:**

I'm about to design the task model but need to understand the requirements better.

**Specific questions:**
1. Should tasks have categories/labels, or just title and description?
2. Do we need user authentication, or is this a simple API without users?
3. Should tasks have due dates and priority levels?

I'll document this in memory/questions/2024-01-16-task-model.md and wait for your response.
```

### You:
```
1. Yes, tasks should have multiple tags (many-to-many relationship)
2. No authentication for MVP
3. Yes to both due dates (optional) and priority (low/medium/high)
```

### Claude Code:
```
Thank you for the clarification! I'll update the questions file with your answers and proceed.

[Updates memory/questions/2024-01-16-task-model.md with answers]

Now I'll implement the task model with these requirements. Following TDD, I'll write tests first:

[Creates tests/test_models.py]
[Creates src/models/task.py]
[Updates memory/implementations/task-model.md]

## Session Progress Update

I've created the task model with:
- id (UUID)
- title (required)
- description (optional) 
- priority (enum: low/medium/high)
- due_date (optional)
- tags (many-to-many)
- created_at, updated_at

The model is fully tested. Next, I'll create the database connection...
```

## Session 3: Encountering and Fixing Issues

### You:
```
Continue with the API development.
```

### Claude Code:
```
[Reads CLAUDE.md and memory files as always...]

Continuing from where I left off - I need to set up the PostgreSQL connection and create CRUD endpoints.

[Implements database connection...]

❌ I'm encountering an error with the async PostgreSQL connection. Instead of working around it, I'll follow the "Fix Don't Skip" policy.

Let me debug this properly...

[After fixing]

I'll document this fix in memory/fixes/2024-01-17-async-postgres.md:

# Fix: Async PostgreSQL Connection Error

## Symptoms
- asyncpg throwing "Event loop is closed" error
- Only happens in tests, not in actual API

## Root Cause
- Test fixtures were not properly handling async setup/teardown
- Database connection was being created outside async context

## Solution
- Used pytest-asyncio's async fixtures
- Properly managed connection lifecycle
- Added connection pooling

## Prevention
- Added integration test for connection pooling
- Documented pattern in memory/patterns/async-db-testing.md

## Files Changed
- tests/conftest.py
- src/database.py
```

## Key Takeaways

1. **Claude always starts by reading the memory system**
2. **Documentation is updated continuously, not just at session end**
3. **Questions are asked and documented when requirements are unclear**
4. **Problems are fixed and documented, not worked around**
5. **Each session builds seamlessly on the previous one**

This systematic approach ensures that Claude Code maintains perfect context and consistency across any number of development sessions.