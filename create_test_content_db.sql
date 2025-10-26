-- Create test content database for dementia testing
-- Run with: sqlite3 content.db < create_test_content_db.sql

-- Create posts table
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    content TEXT,
    status TEXT CHECK(status IN ('draft', 'published', 'archived')),
    category TEXT,
    tags TEXT,
    word_count INTEGER,
    published_at TEXT,
    updated_at TEXT,
    author TEXT,
    seo_score INTEGER CHECK(seo_score BETWEEN 0 AND 100),
    engagement_score REAL CHECK(engagement_score BETWEEN 0.0 AND 1.0)
);

-- Insert sample published posts (high performers)
INSERT INTO posts VALUES
(1, 'Complete Guide to Machine Learning Basics', 'ml-basics-guide', 'Comprehensive introduction to ML concepts...', 'published', 'Technology', 'machine-learning,ai,tutorial', 2500, '2024-01-15', '2024-01-15', 'Sarah Chen', 85, 0.82),
(2, '10 Python Tips for Data Scientists', 'python-tips-data-science', 'Practical Python tips...', 'published', 'Technology', 'python,data-science,tips', 1800, '2024-02-01', '2024-02-01', 'Mike Johnson', 78, 0.75),
(3, 'How to Build REST APIs in 2024', 'rest-api-guide-2024', 'Modern API development...', 'published', 'Technology', 'api,rest,backend', 3200, '2024-02-15', '2024-02-15', 'Sarah Chen', 82, 0.79);

-- Insert more published posts (medium performers)
INSERT INTO posts VALUES
(4, 'Understanding Docker Containers', 'docker-containers-intro', 'Docker basics...', 'published', 'Technology', 'docker,devops,containers', 2100, '2024-01-20', '2024-01-20', 'Alex Rivera', 72, 0.58),
(5, 'Git Workflow Best Practices', 'git-workflow-best-practices', 'Git branching strategies...', 'published', 'Technology', 'git,version-control,workflow', 1600, '2024-03-01', '2024-03-01', 'Mike Johnson', 68, 0.52),
(6, 'Introduction to TypeScript', 'typescript-introduction', 'TypeScript fundamentals...', 'published', 'Technology', 'typescript,javascript,programming', 1900, '2024-03-10', '2024-03-10', 'Sarah Chen', 75, 0.61),
(7, 'CSS Grid Layout Tutorial', 'css-grid-tutorial', 'Master CSS Grid...', 'published', 'Technology', 'css,frontend,design', 1400, '2024-02-20', '2024-02-20', 'Emma Davis', 70, 0.55);

-- Insert published posts (low performers - needs improvement)
INSERT INTO posts VALUES
(8, 'Web Security Basics', 'web-security-basics', 'Security overview...', 'published', 'Technology', 'security,web', 900, '2024-01-05', '2024-01-05', 'Mike Johnson', 45, 0.22),
(9, 'Database Design Tips', 'database-design-tips', 'DB design...', 'published', 'Technology', 'database,sql', 750, '2023-11-15', '2023-11-15', 'Alex Rivera', 38, 0.18),
(10, 'Cloud Computing Overview', 'cloud-computing-overview', 'Cloud intro...', 'published', 'Technology', 'cloud,aws', 650, '2023-10-20', '2023-10-20', 'Sarah Chen', 42, 0.25);

-- Insert high-potential drafts (ready to publish)
INSERT INTO posts VALUES
(11, 'Advanced React Patterns 2024', 'react-patterns-2024', 'Deep dive into React patterns...', 'draft', 'Technology', 'react,javascript,patterns', 2800, NULL, '2024-10-15', 'Sarah Chen', 88, NULL),
(12, 'Kubernetes Production Guide', 'kubernetes-production-guide', 'Production-ready K8s setup...', 'draft', 'Technology', 'kubernetes,devops,production', 3500, NULL, '2024-10-18', 'Alex Rivera', 82, NULL),
(13, 'AI Ethics in Practice', 'ai-ethics-practice', 'Practical AI ethics...', 'draft', 'Technology', 'ai,ethics,responsibility', 2200, NULL, '2024-10-20', 'Emma Davis', 79, NULL);

-- Insert orphaned drafts (old, abandoned)
INSERT INTO posts VALUES
(14, 'GraphQL Basics', 'graphql-basics', 'GraphQL introduction...', 'draft', 'Technology', 'graphql,api', 450, NULL, '2024-06-10', 'Mike Johnson', 35, NULL),
(15, 'Vue.js Components', 'vue-components', 'Vue component guide...', 'draft', 'Technology', 'vue,javascript', 380, NULL, '2024-05-22', 'Emma Davis', 28, NULL),
(16, 'MongoDB Queries', 'mongodb-queries', 'NoSQL query guide...', 'draft', 'Technology', 'mongodb,nosql,database', 520, NULL, '2024-04-15', 'Alex Rivera', 31, NULL);

-- Insert archived posts (old, outdated)
INSERT INTO posts VALUES
(17, 'JavaScript ES5 Guide', 'javascript-es5', 'ES5 features...', 'archived', 'Technology', 'javascript,legacy', 1200, '2020-03-10', '2020-03-10', 'Mike Johnson', 55, 0.42),
(18, 'AngularJS Tutorial', 'angularjs-tutorial', 'AngularJS 1.x...', 'archived', 'Technology', 'angularjs,javascript', 1800, '2019-08-15', '2019-08-15', 'Sarah Chen', 48, 0.38);

-- Insert more diverse content
INSERT INTO posts VALUES
(19, 'Remote Work Productivity Tips', 'remote-work-productivity', 'Stay productive remotely...', 'published', 'Productivity', 'remote-work,productivity,tips', 1500, '2024-03-15', '2024-03-15', 'Emma Davis', 76, 0.68),
(20, 'Time Management for Developers', 'time-management-developers', 'Developer time management...', 'published', 'Productivity', 'time-management,productivity', 1700, '2024-03-20', '2024-03-20', 'Mike Johnson', 73, 0.64),
(21, 'Career Growth in Tech', 'career-growth-tech', 'Advance your tech career...', 'published', 'Career', 'career,growth,tech', 2100, '2024-02-28', '2024-02-28', 'Sarah Chen', 80, 0.71),
(22, 'Interview Prep for Software Engineers', 'interview-prep-software', 'Ace your tech interviews...', 'published', 'Career', 'interview,career,preparation', 2400, '2024-03-05', '2024-03-05', 'Alex Rivera', 84, 0.77);

-- Insert drafts in various categories
INSERT INTO posts VALUES
(23, 'Microservices Architecture Guide', 'microservices-architecture', 'Complete microservices guide...', 'draft', 'Technology', 'microservices,architecture,backend', 3100, NULL, '2024-10-22', 'Alex Rivera', 85, NULL),
(24, 'Building Team Culture', 'building-team-culture', 'Foster great team culture...', 'draft', 'Leadership', 'team,culture,leadership', 1900, NULL, '2024-10-19', 'Emma Davis', 71, NULL),
(25, 'Personal Branding for Developers', 'personal-branding-devs', 'Build your developer brand...', 'draft', 'Career', 'branding,career,marketing', 1600, NULL, '2024-10-21', 'Sarah Chen', 68, NULL);

-- Insert some duplicate-risk content
INSERT INTO posts VALUES
(26, 'Python Best Practices', 'python-best-practices', 'Python coding standards...', 'published', 'Technology', 'python,best-practices,code-quality', 1850, '2024-03-12', '2024-03-12', 'Mike Johnson', 74, 0.59),
(27, 'Clean Python Code', 'clean-python-code', 'Writing clean Python...', 'draft', 'Technology', 'python,clean-code,best-practices', 1920, NULL, '2024-10-17', 'Mike Johnson', 72, NULL);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category);
CREATE INDEX IF NOT EXISTS idx_posts_engagement ON posts(engagement_score);
CREATE INDEX IF NOT EXISTS idx_posts_updated ON posts(updated_at);
CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author);

-- Create summary view
CREATE VIEW IF NOT EXISTS content_summary AS
SELECT
    status,
    category,
    COUNT(*) as post_count,
    AVG(word_count) as avg_words,
    AVG(seo_score) as avg_seo,
    AVG(engagement_score) as avg_engagement
FROM posts
GROUP BY status, category;

-- Display summary
SELECT '=== Content Database Summary ===' as info;
SELECT status, COUNT(*) as count FROM posts GROUP BY status;
SELECT '=== Category Distribution ===' as info;
SELECT category, COUNT(*) as count FROM posts GROUP BY category ORDER BY count DESC;
SELECT '=== Ready for Testing ===' as info;
SELECT 'Database created with ' || COUNT(*) || ' posts' as message FROM posts;
