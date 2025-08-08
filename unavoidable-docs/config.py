"""
Configuration for Unavoidable Documentation System
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# Database Configuration
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'unavoidable_docs'),
    'user': os.getenv('DB_USER', 'unavoidable_docs_user'),
    'password': os.getenv('DB_PASSWORD', 'docs_pass_123')
}

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
    f"{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"
)

# File Monitoring Configuration
WATCH_DIRECTORIES = os.getenv('WATCH_DIRECTORIES', '.').split(',')
IGNORE_PATTERNS = [
    '*.pyc', '__pycache__', '.git', '.gitignore', 
    'node_modules', '.env', '*.log', '.DS_Store',
    'venv', 'env', '*.sqlite', '*.db',
    '.pytest_cache', '.coverage', 'htmlcov',
    'dist', 'build', '*.egg-info'
]

# Documentation Enforcement Levels
ENFORCEMENT_LEVELS = {
    'low': {
        'hours_before_warning': 4,
        'hours_before_blocking': 24,
        'blocks': []
    },
    'medium': {
        'hours_before_warning': 2,
        'hours_before_blocking': 12,
        'blocks': ['commit', 'push']
    },
    'high': {
        'hours_before_warning': 1,
        'hours_before_blocking': 4,
        'blocks': ['commit', 'push', 'build']
    },
    'critical': {
        'hours_before_warning': 0,
        'hours_before_blocking': 0,
        'blocks': ['all']
    }
}

# Current enforcement level
ENFORCEMENT_LEVEL = os.getenv('ENFORCEMENT_LEVEL', 'medium')

# Constant Detection Patterns
CONSTANT_PATTERNS = {
    'url': r'https?://[^\s\"\']+',
    'localhost': r'localhost:\d+',
    'port': r'(?:PORT|port)\s*[=:]\s*\d+',
    'api_endpoint': r'/api/[^\s\"\']+',
    'env_var': r'(?:process\.env\.|os\.getenv\(|os\.environ\[)[\'"]([A-Z_]+)',
    'api_key': r'(?:sk_|pk_|api_|key_)[a-zA-Z0-9]+',
    'database_url': r'(?:mongodb|postgres|postgresql|mysql|redis)://[^\s\"\']+',
    'timeout': r'(?:timeout|TIMEOUT)\s*[=:]\s*\d+',
    'limit': r'(?:limit|LIMIT|max|MAX)\s*[=:]\s*\d+',
    'ip_address': r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
    'version': r'(?:version|VERSION)\s*[=:]\s*[\'"]?[\d\.]+',
    'path': r'(?:path|PATH)\s*[=:]\s*[\'\"][^\s\"\']+[\'\"]',
}

# File types to monitor
MONITORED_EXTENSIONS = [
    '.py', '.js', '.ts', '.jsx', '.tsx',
    '.java', '.go', '.rs', '.rb', '.php',
    '.c', '.cpp', '.h', '.hpp', '.cs',
    '.swift', '.kt', '.scala', '.r',
    '.sql', '.sh', '.yml', '.yaml', '.json',
    '.env', '.config', '.conf', '.ini'
]

# Documentation templates
DOCUMENTATION_TEMPLATES = {
    'function': '''
    """
    {function_name}
    
    Purpose: [Brief description of what this function does]
    
    Args:
        {parameters}
    
    Returns:
        {return_type}: [Description of return value]
    
    Raises:
        [Any exceptions that might be raised]
    
    Example:
        {example}
    """
    ''',
    
    'constant': '''
    # {constant_name}: {constant_type}
    # Purpose: {purpose}
    # Used in: {usage_locations}
    # Example: {example_value}
    ''',
    
    'file': '''
    """
    File: {file_path}
    Purpose: {purpose}
    
    This file contains:
    {contents_summary}
    
    Dependencies:
    {dependencies}
    
    Exports:
    {exports}
    """
    '''
}

# Quality thresholds
QUALITY_THRESHOLDS = {
    'minimum_completeness': 80,  # Minimum % documentation completeness
    'maximum_debt_age_hours': 24,  # Maximum age for any debt item
    'maximum_critical_debt': 0,  # Maximum number of critical debt items
    'minimum_quality_score': 70  # Minimum documentation quality score
}

# Session configuration
SESSION_CONFIG = {
    'auto_start': True,  # Automatically start session on first operation
    'auto_end_after_minutes': 30,  # Auto-end session after inactivity
    'track_all_operations': True,  # Track all file operations
    'enforce_documentation_mode': True  # Force documentation when debt is high
}

# Reporting configuration
REPORTING_CONFIG = {
    'daily_report_time': '09:00',  # Time to generate daily report
    'weekly_report_day': 'monday',  # Day to generate weekly report
    'send_email_reports': False,  # Whether to email reports
    'dashboard_port': 8080,  # Port for web dashboard
    'metrics_retention_days': 90  # How long to keep metrics
}

# Integration settings
INTEGRATION_CONFIG = {
    'update_claude_md': True,  # Update CLAUDE.md memory system
    'update_project_map': True,  # Update PROJECT_MAP.md
    'update_constants_registry': True,  # Update constants registry
    'git_hooks_enabled': True,  # Enable git pre-commit hooks
    'mcp_wrapper_enabled': True  # Enable MCP tool wrapping
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'unavoidable_docs.log',
    'max_bytes': 10485760,  # 10MB
    'backup_count': 5
}