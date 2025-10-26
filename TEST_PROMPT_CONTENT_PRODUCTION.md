# Content Production Project - Test Prompt for Claude Dementia

## Project Context

You are helping manage a large content production project with the following structure:

```
content-project/
├── posts/               # 2,000+ markdown files
│   ├── published/
│   ├── drafts/
│   └── archive/
├── templates/           # Content templates
├── style-guides/        # Writing guidelines
├── content.db          # SQLite database with post metadata
└── .env                # Voyage AI + OpenRouter keys configured
```

**Database Schema** (`content.db`):
```sql
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    title TEXT,
    slug TEXT,
    content TEXT,
    status TEXT,  -- 'draft', 'published', 'archived'
    category TEXT,
    tags TEXT,    -- comma-separated
    word_count INTEGER,
    published_at TEXT,
    updated_at TEXT,
    author TEXT,
    seo_score INTEGER,
    engagement_score REAL
);
```

## Your Mission

Help analyze, organize, and improve this content library using Claude Dementia's memory and AI tools.

## Task Sequence

### Phase 1: Initial Setup and Discovery

1. **Wake up and load context**
   - Use `dementia:wake_up` to start session
   - Review any existing locked contexts
   - Check project status

2. **Lock critical content guidelines**
   - Create lock for "Content Style Guide" with priority `always_check`:
     ```
     ALWAYS write in active voice
     NEVER use jargon without explanation
     MUST include actionable takeaways
     Keep paragraphs under 4 sentences
     Target: 8th grade reading level
     ```

   - Create lock for "SEO Requirements" with priority `important`:
     ```
     Title: 60 chars max, include primary keyword
     Meta: 155 chars, compelling CTA
     Headers: Use H2/H3 hierarchy, keyword-rich
     Links: 2-3 internal, 1-2 authoritative external
     Images: Alt text required, descriptive filenames
     ```

   - Create lock for "Content Templates" with priority `reference`:
     ```
     How-To: Problem → Solution → Steps → Example → Conclusion
     Listicle: Hook → Items (3-10) → Brief explanations → CTA
     Guide: Overview → Sections → Deep-dive → Resources → Next steps
     ```

3. **Scan and analyze the content directory**
   - Use `dementia:project_update` to scan all markdown files
   - Let it tag files automatically based on content analysis
   - Review the tagging results

### Phase 2: Database Analysis

4. **Analyze the posts database**
   ```python
   # Example queries to run:

   # Find low-performing content (engagement < 0.3)
   SELECT id, title, category, engagement_score, published_at
   FROM posts
   WHERE status = 'published' AND engagement_score < 0.3
   ORDER BY engagement_score ASC
   LIMIT 20;

   # Find orphaned drafts (not updated in 90+ days)
   SELECT id, title, updated_at, author
   FROM posts
   WHERE status = 'draft'
   AND date(updated_at) < date('now', '-90 days');

   # Category distribution
   SELECT category, COUNT(*) as count,
          AVG(engagement_score) as avg_engagement,
          AVG(seo_score) as avg_seo
   FROM posts
   WHERE status = 'published'
   GROUP BY category
   ORDER BY count DESC;

   # Find high-potential drafts (word_count > 800, recent)
   SELECT id, title, word_count, updated_at, author
   FROM posts
   WHERE status = 'draft'
   AND word_count > 800
   AND date(updated_at) > date('now', '-30 days');
   ```

5. **Create analysis report and lock findings**
   - Summarize database insights using LLM service
   - Lock key findings as "Content Audit Results" (priority: `important`)
   - Track progress with `dementia:memory_update`

### Phase 3: Semantic Analysis

6. **Find content gaps and duplicates**
   - Use Voyage AI embeddings to find similar posts:
     ```python
     # Pseudo-code concept:
     # 1. Get embeddings for all published posts
     # 2. Find clusters of similar content (cosine similarity > 0.85)
     # 3. Identify topics with no coverage (orphan keywords)
     # 4. Find cannibalization risks (multiple posts on same topic)
     ```

7. **Recommend content improvements**
   - Use OpenRouter LLM to analyze low-performing posts
   - Generate rewrite suggestions
   - Identify posts needing updates (outdated info, broken links)
   - Tag posts with quality assessment using `dementia:tag_path`

### Phase 4: Content Production Workflow

8. **Create content production system**
   - Tag posts by: `status:published`, `quality:high/medium/low`, `domain:topic`
   - Use `dementia:search_by_tags` to find related content
   - Check locked contexts before writing to ensure compliance
   - Update memory with production decisions

9. **Generate content calendar**
   - Analyze seasonal trends in published_at dates
   - Identify content gaps by category
   - Recommend posting schedule
   - Lock calendar as "Q1 2025 Content Plan" (priority: `important`)

### Phase 5: Continuous Improvement

10. **Set up monitoring dashboard**
    - Use `dementia:file_insights` to assess project health
    - Track: quality distribution, coverage gaps, production velocity
    - Create weekly summary using `dementia:context_dashboard`

11. **End session with handover**
    - Use `dementia:sleep` to create comprehensive handover package
    - Should include:
      - Locked contexts (style guide, SEO rules, templates)
      - Content audit findings
      - Semantic analysis results
      - Production recommendations
      - Tagged file inventory
      - Next session priorities

## Success Criteria

Your solution should demonstrate:

✅ **Memory Management**:
- 3-5 locked contexts with appropriate priorities
- Regular memory updates tracking progress
- Clean handover package for next session

✅ **AI Integration**:
- Voyage AI: Embeddings for 100+ posts, similarity analysis
- OpenRouter: Content summarization, quality assessment, recommendations
- Token tracking: Monitor costs throughout

✅ **Project Intelligence**:
- Comprehensive file tagging (status, quality, domain, topic)
- Searchable content inventory
- Automated insights and recommendations

✅ **Database Analysis**:
- Identify low performers, orphaned drafts, high-potential content
- Category/tag distribution analysis
- Trend identification

✅ **Content Quality**:
- Compliance checking against locked style guide
- SEO optimization recommendations
- Duplicate/gap identification

## Test Queries to Try

After setup, test these searches:

```bash
# Find all high-quality guides
dementia:search_by_tags "quality:high AND domain:guide"

# Find drafts needing attention
dementia:search_by_tags "status:draft AND quality:needs-work"

# Get insights on specific file
dementia:file_insights "posts/published/how-to-machine-learning.md"

# Check what contexts are relevant before writing
dementia:check_contexts "I'm writing a technical how-to guide about APIs"
```

## Expected Output

At the end, you should provide:

1. **Executive Summary**:
   - Content inventory overview (counts by status/quality)
   - Key findings (top performers, gaps, risks)
   - Cost analysis (tokens used, API costs)

2. **Locked Contexts**:
   - List all locked contexts with versions
   - Show how they're used in workflow

3. **Tagged File Inventory**:
   - Sample of tagged files showing semantic tags
   - Search examples demonstrating discoverability

4. **Recommendations**:
   - Top 10 posts to improve
   - Top 5 content gaps to fill
   - Automated workflow suggestions

5. **Handover Package**:
   - Complete sleep() output showing session summary
   - Next session priorities
   - Audit trail of decisions made

## Notes for Testing

- This exercises ALL major dementia features
- Tests both cloud APIs (Voyage AI + OpenRouter)
- Realistic scenario for content operations
- Demonstrates value of persistent memory across sessions
- Shows cost tracking for production use

## Quick Start Command

```bash
# Set up test environment
mkdir -p /tmp/content-test/{posts/{published,drafts,archive},templates,style-guides}

# Create sample database
sqlite3 /tmp/content-test/content.db < create_test_data.sql

# Start Claude Code in test directory
cd /tmp/content-test

# Begin with: "dementia:wake_up"
```

---

**Ready to test?** Start with `dementia:wake_up` and work through the phases!
