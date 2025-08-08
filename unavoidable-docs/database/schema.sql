-- UNAVOIDABLE DOCUMENTATION SYSTEM
-- PostgreSQL Database Schema
-- This schema tracks every file, constant, and function to ensure 100% documentation

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main table tracking documentation status of every file
CREATE TABLE file_documentation_status (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_hash VARCHAR(64), -- SHA256 hash to detect changes
    status VARCHAR(20) NOT NULL DEFAULT 'undocumented' 
        CHECK (status IN ('undocumented', 'documented', 'outdated', 'ignored')),
    
    -- Timestamps
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_modified TIMESTAMP NOT NULL DEFAULT NOW(),
    last_documented TIMESTAMP,
    
    -- Documentation metrics
    doc_completeness INTEGER DEFAULT 0 
        CHECK (doc_completeness >= 0 AND doc_completeness <= 100),
    has_constants BOOLEAN DEFAULT FALSE,
    constants_documented INTEGER DEFAULT 0,
    total_constants INTEGER DEFAULT 0,
    has_functions BOOLEAN DEFAULT FALSE,
    functions_documented INTEGER DEFAULT 0,
    total_functions INTEGER DEFAULT 0,
    
    -- Debt tracking
    debt_level VARCHAR(10) DEFAULT 'low'
        CHECK (debt_level IN ('critical', 'high', 'medium', 'low')),
    debt_age_hours INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (NOW() - COALESCE(last_documented, first_seen)))/3600
    ) STORED,
    times_skipped INTEGER DEFAULT 0,
    
    -- File metadata
    file_type VARCHAR(20),
    file_size INTEGER,
    line_count INTEGER,
    complexity_score INTEGER,
    
    -- Tracking
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_file_status ON file_documentation_status(status);
CREATE INDEX idx_debt_level ON file_documentation_status(debt_level);
CREATE INDEX idx_file_path ON file_documentation_status(file_path);

-- Documentation debt entries for specific undocumented items
CREATE TABLE documentation_debt (
    id SERIAL PRIMARY KEY,
    debt_id UUID DEFAULT uuid_generate_v4(),
    file_id INTEGER REFERENCES file_documentation_status(id) ON DELETE CASCADE,
    
    -- Debt details
    debt_type VARCHAR(30) NOT NULL
        CHECK (debt_type IN (
            'new_file', 'new_function', 'new_constant', 
            'modified_logic', 'new_endpoint', 'new_dependency',
            'new_class', 'new_method', 'new_variable',
            'config_change', 'schema_change'
        )),
    item_name TEXT, -- Name of function/constant/etc
    description TEXT NOT NULL,
    
    -- Priority and blocking
    priority VARCHAR(10) DEFAULT 'low'
        CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    created_at TIMESTAMP DEFAULT NOW(),
    escalated_at TIMESTAMP,
    is_blocking BOOLEAN DEFAULT FALSE,
    blocks_operations TEXT[], -- Array of operations this blocks
    
    -- Assignment and resolution
    assigned_session VARCHAR(100),
    resolution_attempts INTEGER DEFAULT 0,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(100),
    resolution_notes TEXT,
    
    -- Detection metadata
    auto_detected BOOLEAN DEFAULT TRUE,
    detection_confidence DECIMAL(3,2) DEFAULT 1.0,
    line_number INTEGER,
    context TEXT, -- Surrounding code context
    
    -- Escalation tracking
    hours_old INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (NOW() - created_at))/3600
    ) STORED
);

-- Create indexes for debt queries
CREATE INDEX idx_debt_priority ON documentation_debt(priority);
CREATE INDEX idx_debt_blocking ON documentation_debt(is_blocking);
CREATE INDEX idx_debt_type ON documentation_debt(debt_type);
CREATE INDEX idx_debt_unresolved ON documentation_debt(resolved_at) WHERE resolved_at IS NULL;

-- Table for tracking undocumented constants
CREATE TABLE undocumented_constants (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_documentation_status(id) ON DELETE CASCADE,
    
    -- Constant details
    constant_value TEXT NOT NULL,
    constant_type VARCHAR(30), -- 'url', 'port', 'api_endpoint', 'env_var', 'ip', etc
    probable_name VARCHAR(100), -- Suggested variable name
    
    -- Location in code
    line_number INTEGER NOT NULL,
    column_start INTEGER,
    column_end INTEGER,
    
    -- Detection confidence
    confidence_score DECIMAL(3,2) DEFAULT 0.5
        CHECK (confidence_score >= 0 AND confidence_score <= 1),
    
    -- Context and purpose
    probable_purpose TEXT,
    usage_context TEXT, -- How it's being used
    context_before TEXT, -- Code before the constant
    context_after TEXT, -- Code after the constant
    
    -- Documentation status
    detected_at TIMESTAMP DEFAULT NOW(),
    documented_at TIMESTAMP,
    documentation TEXT,
    documented_by VARCHAR(100),
    
    -- Validation
    is_valid_constant BOOLEAN DEFAULT TRUE,
    false_positive BOOLEAN DEFAULT FALSE,
    ignore_reason TEXT
);

-- Create indexes for constant queries
CREATE INDEX idx_const_undocumented ON undocumented_constants(documented_at) WHERE documented_at IS NULL;
CREATE INDEX idx_const_type ON undocumented_constants(constant_type);
CREATE INDEX idx_const_file ON undocumented_constants(file_id);

-- Table for tracking undocumented functions
CREATE TABLE undocumented_functions (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_documentation_status(id) ON DELETE CASCADE,
    
    -- Function details
    function_name TEXT NOT NULL,
    function_type VARCHAR(30), -- 'function', 'method', 'constructor', 'async', 'generator'
    class_name TEXT, -- If it's a method
    
    -- Signature
    parameters TEXT[], -- Array of parameter names
    parameter_types TEXT[], -- Array of parameter types if known
    return_type TEXT,
    is_exported BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT TRUE,
    
    -- Location
    line_start INTEGER NOT NULL,
    line_end INTEGER,
    
    -- Complexity
    cyclomatic_complexity INTEGER,
    lines_of_code INTEGER,
    
    -- Documentation status
    detected_at TIMESTAMP DEFAULT NOW(),
    documented_at TIMESTAMP,
    documentation TEXT,
    documented_by VARCHAR(100),
    
    -- Quality
    has_jsdoc BOOLEAN DEFAULT FALSE,
    has_comments BOOLEAN DEFAULT FALSE,
    needs_update BOOLEAN DEFAULT FALSE
);

-- Create indexes for function queries
CREATE INDEX idx_func_undocumented ON undocumented_functions(documented_at) WHERE documented_at IS NULL;
CREATE INDEX idx_func_file ON undocumented_functions(file_id);
CREATE INDEX idx_func_exported ON undocumented_functions(is_exported);

-- Session tracking for documentation work
CREATE TABLE documentation_sessions (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Timing
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    duration_minutes INTEGER GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (COALESCE(ended_at, NOW()) - started_at))/60
    ) STORED,
    
    -- Debt metrics
    debt_at_start INTEGER DEFAULT 0,
    debt_created INTEGER DEFAULT 0,
    debt_resolved INTEGER DEFAULT 0,
    debt_at_end INTEGER,
    net_debt INTEGER GENERATED ALWAYS AS (debt_created - debt_resolved) STORED,
    
    -- Documentation work
    files_documented INTEGER DEFAULT 0,
    constants_documented INTEGER DEFAULT 0,
    functions_documented INTEGER DEFAULT 0,
    items_documented JSON, -- Detailed list of documented items
    
    -- Quality metrics
    quality_score INTEGER,
    documentation_quality JSON, -- Detailed quality metrics
    time_spent_minutes INTEGER,
    
    -- Session type
    forced_documentation BOOLEAN DEFAULT FALSE,
    documentation_sprint BOOLEAN DEFAULT FALSE,
    session_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    
    -- User/system
    user_name VARCHAR(100),
    system_version VARCHAR(20)
);

-- Create indexes for session queries
CREATE INDEX idx_session_date ON documentation_sessions(started_at);
CREATE INDEX idx_session_user ON documentation_sessions(user_name);
CREATE INDEX idx_session_blocked ON documentation_sessions(session_blocked);

-- Enforcement rules and blocks
CREATE TABLE enforcement_blocks (
    id SERIAL PRIMARY KEY,
    block_id UUID DEFAULT uuid_generate_v4(),
    
    -- What was blocked
    operation_type VARCHAR(50) NOT NULL, -- 'commit', 'push', 'build', 'test', 'deploy', etc
    operation_details TEXT,
    blocked_at TIMESTAMP DEFAULT NOW(),
    
    -- Why it was blocked
    debt_count INTEGER NOT NULL,
    critical_debt_count INTEGER DEFAULT 0,
    oldest_debt_hours INTEGER,
    blocking_items JSON, -- List of specific items blocking
    
    -- Resolution
    resolved_at TIMESTAMP,
    resolution_method VARCHAR(50), -- 'documented', 'overridden', 'expired'
    
    -- Session info
    session_id VARCHAR(100),
    user_name VARCHAR(100)
);

-- Create indexes for enforcement queries
CREATE INDEX idx_block_operation ON enforcement_blocks(operation_type);
CREATE INDEX idx_block_session ON enforcement_blocks(session_id);
CREATE INDEX idx_block_unresolved ON enforcement_blocks(resolved_at) WHERE resolved_at IS NULL;

-- Documentation quality metrics
CREATE TABLE documentation_quality (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES file_documentation_status(id) ON DELETE CASCADE,
    
    -- Quality scores (0-100)
    completeness_score INTEGER DEFAULT 0,
    clarity_score INTEGER DEFAULT 0,
    accuracy_score INTEGER DEFAULT 0,
    freshness_score INTEGER DEFAULT 0,
    overall_score INTEGER GENERATED ALWAYS AS (
        (completeness_score + clarity_score + accuracy_score + freshness_score) / 4
    ) STORED,
    
    -- Specific checks
    has_file_header BOOLEAN DEFAULT FALSE,
    has_function_docs BOOLEAN DEFAULT FALSE,
    has_constant_docs BOOLEAN DEFAULT FALSE,
    has_type_annotations BOOLEAN DEFAULT FALSE,
    has_examples BOOLEAN DEFAULT FALSE,
    has_error_handling_docs BOOLEAN DEFAULT FALSE,
    
    -- Issues found
    quality_issues JSON,
    improvement_suggestions JSON,
    
    -- Tracking
    last_evaluated TIMESTAMP DEFAULT NOW(),
    evaluated_by VARCHAR(100)
);

-- Create indexes for quality queries
CREATE INDEX idx_quality_score ON documentation_quality(overall_score);
CREATE INDEX idx_quality_file ON documentation_quality(file_id);

-- Audit log for all documentation changes
CREATE TABLE documentation_audit_log (
    id SERIAL PRIMARY KEY,
    event_id UUID DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    event_timestamp TIMESTAMP DEFAULT NOW(),
    
    -- What changed
    entity_type VARCHAR(50), -- 'file', 'constant', 'function', etc
    entity_id INTEGER,
    old_value JSON,
    new_value JSON,
    
    -- Who/what made the change
    changed_by VARCHAR(100),
    session_id VARCHAR(100),
    auto_generated BOOLEAN DEFAULT FALSE,
    
    -- Additional context
    context JSON
);

-- Create indexes for audit queries
CREATE INDEX idx_audit_timestamp ON documentation_audit_log(event_timestamp);
CREATE INDEX idx_audit_type ON documentation_audit_log(event_type);
CREATE INDEX idx_audit_entity ON documentation_audit_log(entity_type, entity_id);

-- Views for common queries

-- Current documentation status overview
CREATE VIEW documentation_overview AS
SELECT 
    COUNT(*) as total_files,
    COUNT(CASE WHEN status = 'documented' THEN 1 END) as documented_files,
    COUNT(CASE WHEN status = 'undocumented' THEN 1 END) as undocumented_files,
    COUNT(CASE WHEN status = 'outdated' THEN 1 END) as outdated_files,
    AVG(doc_completeness) as avg_completeness,
    COUNT(CASE WHEN debt_level = 'critical' THEN 1 END) as critical_debt_files,
    COUNT(CASE WHEN debt_level = 'high' THEN 1 END) as high_debt_files
FROM file_documentation_status;

-- Critical debt items that need immediate attention
CREATE VIEW critical_debt_items AS
SELECT 
    dd.id,
    dd.debt_type,
    dd.item_name,
    dd.description,
    dd.hours_old,
    fds.file_path,
    dd.priority
FROM documentation_debt dd
JOIN file_documentation_status fds ON dd.file_id = fds.id
WHERE dd.resolved_at IS NULL 
AND (dd.priority = 'critical' OR dd.hours_old > 24 OR dd.is_blocking = TRUE)
ORDER BY dd.priority DESC, dd.hours_old DESC;

-- Session performance metrics
CREATE VIEW session_metrics AS
SELECT 
    session_id,
    started_at,
    duration_minutes,
    debt_resolved,
    debt_created,
    net_debt,
    CASE 
        WHEN debt_resolved > 0 THEN ROUND(debt_resolved::numeric / NULLIF(duration_minutes, 0) * 60, 2)
        ELSE 0 
    END as debt_resolved_per_hour,
    quality_score
FROM documentation_sessions
ORDER BY started_at DESC;

-- Functions for debt escalation

-- Function to escalate debt priority based on age
CREATE OR REPLACE FUNCTION escalate_debt_priority() RETURNS void AS $$
BEGIN
    -- Escalate to high after 12 hours
    UPDATE documentation_debt 
    SET priority = 'high', escalated_at = NOW()
    WHERE resolved_at IS NULL 
    AND hours_old > 12 
    AND priority = 'medium';
    
    -- Escalate to critical after 24 hours
    UPDATE documentation_debt 
    SET priority = 'critical', escalated_at = NOW(), is_blocking = TRUE
    WHERE resolved_at IS NULL 
    AND hours_old > 24 
    AND priority IN ('high', 'medium', 'low');
    
    -- Update file debt levels
    UPDATE file_documentation_status fds
    SET debt_level = (
        SELECT MAX(dd.priority::text)::varchar(10)
        FROM documentation_debt dd
        WHERE dd.file_id = fds.id AND dd.resolved_at IS NULL
    )
    WHERE EXISTS (
        SELECT 1 FROM documentation_debt dd 
        WHERE dd.file_id = fds.id AND dd.resolved_at IS NULL
    );
END;
$$ LANGUAGE plpgsql;

-- Trigger to update file status when debt is resolved
CREATE OR REPLACE FUNCTION update_file_status_on_debt_resolution() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.resolved_at IS NOT NULL AND OLD.resolved_at IS NULL THEN
        UPDATE file_documentation_status
        SET 
            last_documented = NOW(),
            updated_at = NOW()
        WHERE id = NEW.file_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER debt_resolution_trigger
AFTER UPDATE ON documentation_debt
FOR EACH ROW
EXECUTE FUNCTION update_file_status_on_debt_resolution();

-- Function to calculate documentation completeness
CREATE OR REPLACE FUNCTION calculate_doc_completeness(file_id INTEGER) RETURNS INTEGER AS $$
DECLARE
    completeness INTEGER;
    const_score INTEGER;
    func_score INTEGER;
BEGIN
    SELECT 
        CASE 
            WHEN total_constants > 0 THEN (constants_documented * 100 / total_constants)
            ELSE 100
        END,
        CASE 
            WHEN total_functions > 0 THEN (functions_documented * 100 / total_functions)
            ELSE 100
        END
    INTO const_score, func_score
    FROM file_documentation_status
    WHERE id = file_id;
    
    completeness := (const_score + func_score) / 2;
    
    UPDATE file_documentation_status 
    SET doc_completeness = completeness, updated_at = NOW()
    WHERE id = file_id;
    
    RETURN completeness;
END;
$$ LANGUAGE plpgsql;

-- Grant appropriate permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO unavoidable_docs_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO unavoidable_docs_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO unavoidable_docs_user;