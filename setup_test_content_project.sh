#!/bin/bash
# Setup test content production project for Claude Dementia testing

set -e

TEST_DIR="/tmp/content-test"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🚀 Setting up test content project at $TEST_DIR"

# Create directory structure
echo "📁 Creating directory structure..."
mkdir -p "$TEST_DIR"/{posts/{published,drafts,archive},templates,style-guides}

# Create sample markdown files
echo "📝 Creating sample markdown files..."

cat > "$TEST_DIR/posts/published/ml-basics-guide.md" << 'EOF'
---
id: 1
title: Complete Guide to Machine Learning Basics
slug: ml-basics-guide
category: Technology
tags: machine-learning,ai,tutorial
author: Sarah Chen
---

# Complete Guide to Machine Learning Basics

Machine learning is transforming how we build software. This guide covers the fundamentals.

## What is Machine Learning?

ML enables computers to learn from data without explicit programming...

## Key Concepts

1. **Supervised Learning**: Training with labeled data
2. **Unsupervised Learning**: Finding patterns in unlabeled data
3. **Reinforcement Learning**: Learning through trial and error

## Getting Started

Here's a simple example in Python...
EOF

cat > "$TEST_DIR/posts/published/python-tips-data-science.md" << 'EOF'
---
id: 2
title: 10 Python Tips for Data Scientists
slug: python-tips-data-science
category: Technology
tags: python,data-science,tips
author: Mike Johnson
---

# 10 Python Tips for Data Scientists

Boost your data science workflow with these practical Python tips.

## 1. Use List Comprehensions

List comprehensions are faster and more readable...

## 2. Leverage Pandas Efficiently

Avoid loops when working with DataFrames...
EOF

cat > "$TEST_DIR/posts/drafts/react-patterns-2024.md" << 'EOF'
---
id: 11
title: Advanced React Patterns 2024
slug: react-patterns-2024
category: Technology
tags: react,javascript,patterns
author: Sarah Chen
status: draft
---

# Advanced React Patterns 2024

Modern React development requires understanding advanced patterns.

## Custom Hooks

Create reusable logic with custom hooks...

## Composition vs Inheritance

React favors composition over inheritance...

[DRAFT: Need to add more examples]
EOF

cat > "$TEST_DIR/posts/drafts/kubernetes-production-guide.md" << 'EOF'
---
id: 12
title: Kubernetes Production Guide
slug: kubernetes-production-guide
category: Technology
tags: kubernetes,devops,production
author: Alex Rivera
status: draft
---

# Kubernetes Production Guide

Running Kubernetes in production requires careful planning.

## High Availability Setup

Configure control plane redundancy...

## Monitoring and Observability

Implement comprehensive monitoring...

[DRAFT: Add security section]
EOF

cat > "$TEST_DIR/posts/archive/javascript-es5.md" << 'EOF'
---
id: 17
title: JavaScript ES5 Guide
slug: javascript-es5
category: Technology
tags: javascript,legacy
author: Mike Johnson
status: archived
---

# JavaScript ES5 Guide

**Note**: This content is outdated. See ES6+ guides instead.

## ES5 Features

var, function expressions, prototype chains...
EOF

# Create style guide
cat > "$TEST_DIR/style-guides/content-style-guide.md" << 'EOF'
# Content Style Guide

## Voice and Tone
- ALWAYS write in active voice
- NEVER use jargon without explanation
- Be conversational but professional
- Show don't tell with examples

## Structure
- MUST include actionable takeaways
- Keep paragraphs under 4 sentences
- Use headers (H2/H3) for scanability
- Target: 8th grade reading level

## Quality Standards
- Minimum 1000 words for guides
- Include code examples where relevant
- Link to 2-3 related internal posts
- Add 1-2 authoritative external sources

## SEO Requirements
- Title: 60 chars max, include primary keyword
- Meta description: 155 chars, compelling CTA
- Use keyword in first paragraph
- Include semantic keywords naturally
EOF

# Create templates
cat > "$TEST_DIR/templates/how-to-template.md" << 'EOF'
# [How to {Accomplish Task}]

## Introduction
[State the problem and what readers will learn]

## Prerequisites
- Requirement 1
- Requirement 2

## Step 1: [Action]
[Detailed instructions with code examples]

## Step 2: [Action]
[More instructions]

## Troubleshooting
[Common issues and solutions]

## Conclusion
[Summary and next steps]

## Related Resources
- [Internal link 1]
- [Internal link 2]
- [External resource]
EOF

cat > "$TEST_DIR/templates/listicle-template.md" << 'EOF'
# [Number] [Things] for [Audience]

## Introduction
[Hook: Why this list matters]

## 1. [Item Title]
[Brief explanation, example, benefit]

## 2. [Item Title]
[Brief explanation, example, benefit]

[... continue for all items ...]

## Conclusion
[Summary and call to action]
EOF

# Create database with sample data
echo "🗄️  Creating SQLite database..."
sqlite3 "$TEST_DIR/content.db" < "$SCRIPT_DIR/create_test_content_db.sql" 2>&1 | grep -E "(===|count|message)"

# Copy .env file if it exists
if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "🔑 Copying .env file..."
    cp "$SCRIPT_DIR/.env" "$TEST_DIR/.env"
fi

# Create quick reference
cat > "$TEST_DIR/README.md" << 'EOF'
# Content Production Test Project

Test environment for Claude Dementia MCP tools.

## Structure

- `posts/published/` - Published content (high/medium/low performers)
- `posts/drafts/` - Draft content (ready to publish, orphaned)
- `posts/archive/` - Archived/outdated content
- `templates/` - Content templates
- `style-guides/` - Writing guidelines
- `content.db` - SQLite database with 27 posts

## Database Schema

```sql
posts (id, title, slug, content, status, category, tags,
       word_count, published_at, updated_at, author,
       seo_score, engagement_score)
```

## Quick Start

1. Start Claude Code in this directory
2. Run: `dementia:wake_up`
3. Follow TEST_PROMPT_CONTENT_PRODUCTION.md

## Test Queries

```bash
# View database summary
sqlite3 content.db "SELECT * FROM content_summary;"

# Find low performers
sqlite3 content.db "SELECT title, engagement_score FROM posts
                    WHERE status='published' AND engagement_score < 0.3;"

# Find high-potential drafts
sqlite3 content.db "SELECT title, word_count FROM posts
                    WHERE status='draft' AND word_count > 1500;"
```

## Features to Test

- ✅ Context locking (style guides, templates)
- ✅ Project scanning and tagging
- ✅ Semantic search (similar posts)
- ✅ LLM analysis (quality assessment)
- ✅ Database queries (performance analysis)
- ✅ Session handover (sleep/wake_up)
EOF

echo ""
echo "✅ Test environment created successfully!"
echo ""
echo "📂 Location: $TEST_DIR"
echo "📊 Database: $TEST_DIR/content.db"
echo "📝 Sample posts: 27 posts across published/draft/archived"
echo ""
echo "🚀 Next steps:"
echo "  1. cd $TEST_DIR"
echo "  2. Start Claude Code"
echo "  3. Run: dementia:wake_up"
echo "  4. Follow: $SCRIPT_DIR/TEST_PROMPT_CONTENT_PRODUCTION.md"
echo ""
echo "💡 Quick database check:"
echo "   sqlite3 $TEST_DIR/content.db 'SELECT COUNT(*) as total FROM posts;'"
echo ""
