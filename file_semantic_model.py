#!/usr/bin/env python3
"""
File Semantic Model - Core Implementation

Provides intelligent file system analysis with:
- Efficient change detection (mtime + size + hash)
- Smart hashing (full for small files, partial for large)
- File type detection and classification
- Semantic analysis (imports, exports, dependencies)
- Standard file recognition and warnings
"""

import os
import hashlib
import time
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime


# ============================================================================
# CHANGE DETECTION - Three-stage: mtime → size → hash
# ============================================================================

def compute_file_hash(file_path: str, file_size: int) -> Tuple[str, str]:
    """
    Compute file hash using smart strategy based on file size.

    Returns: (hash_value, hash_method)
    """
    if file_size > 1_000_000:  # >1MB - use partial hash
        return partial_hash(file_path, file_size), 'partial'
    else:  # <=1MB - use full hash
        return full_hash(file_path), 'full'


def full_hash(file_path: str) -> str:
    """Full MD5 hash of entire file (for small files)"""
    md5 = hashlib.md5()

    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return ''


def partial_hash(file_path: str, file_size: int) -> str:
    """
    Partial hash: first 64KB + last 64KB + file size.
    Fast for large files, detects 99.9% of changes.
    """
    md5 = hashlib.md5()

    try:
        with open(file_path, 'rb') as f:
            # First 64KB
            md5.update(f.read(65536))

            # Last 64KB (if file large enough)
            if file_size > 131072:
                f.seek(-65536, 2)  # Seek to 64KB from end
                md5.update(f.read(65536))

            # Include file size in hash
            md5.update(str(file_size).encode())

        return md5.hexdigest()
    except Exception:
        return ''


def detect_file_change(file_path: str, stored_metadata: Optional[Dict]) -> Tuple[bool, str, str]:
    """
    Three-stage change detection: mtime → size → hash

    Returns: (changed: bool, hash: str, hash_method: str)
    """
    try:
        stat = os.stat(file_path)
        current_mtime = stat.st_mtime
        current_size = stat.st_size
    except Exception:
        return False, '', 'none'

    # Stage 1: mtime unchanged = definitely not changed
    if stored_metadata and current_mtime == stored_metadata.get('modified_time'):
        return False, stored_metadata.get('content_hash', ''), stored_metadata.get('hash_method', 'full')

    # Stage 2: size changed = definitely changed (skip hash check)
    if stored_metadata and current_size != stored_metadata.get('file_size'):
        new_hash, hash_method = compute_file_hash(file_path, current_size)
        return True, new_hash, hash_method

    # Stage 3: mtime changed but size same = check hash
    new_hash, hash_method = compute_file_hash(file_path, current_size)

    if stored_metadata and new_hash == stored_metadata.get('content_hash'):
        return False, new_hash, hash_method  # Touched but not changed

    return True, new_hash, hash_method  # Content actually changed


# ============================================================================
# FILE TYPE DETECTION
# ============================================================================

FILE_TYPE_MAP = {
    # Programming languages
    '.py': ('python', 'python'),
    '.js': ('javascript', 'javascript'),
    '.ts': ('typescript', 'typescript'),
    '.jsx': ('javascript_react', 'javascript'),
    '.tsx': ('typescript_react', 'typescript'),
    '.java': ('java', 'java'),
    '.go': ('go', 'go'),
    '.rs': ('rust', 'rust'),
    '.cpp': ('cpp', 'cpp'),
    '.c': ('c', 'c'),
    '.h': ('c_header', 'c'),
    '.rb': ('ruby', 'ruby'),
    '.php': ('php', 'php'),
    '.cs': ('csharp', 'csharp'),
    '.swift': ('swift', 'swift'),
    '.kt': ('kotlin', 'kotlin'),

    # Markup/data
    '.md': ('markdown', 'markdown'),
    '.html': ('html', 'html'),
    '.htm': ('html', 'html'),
    '.css': ('stylesheet', 'css'),
    '.scss': ('stylesheet', 'scss'),
    '.sass': ('stylesheet', 'sass'),
    '.less': ('stylesheet', 'less'),
    '.json': ('json_data', 'json'),
    '.yaml': ('yaml_config', 'yaml'),
    '.yml': ('yaml_config', 'yaml'),
    '.xml': ('xml_data', 'xml'),
    '.toml': ('toml_config', 'toml'),

    # Config files
    '.env': ('environment_config', None),
    '.conf': ('config', None),
    '.ini': ('config', None),
    '.cfg': ('config', None'),

    # Documentation
    '.txt': ('text', None),
    '.rst': ('restructured_text', 'rst'),
    '.pdf': ('pdf_document', None),

    # Shell scripts
    '.sh': ('shell_script', 'shell'),
    '.bash': ('shell_script', 'shell'),
    '.zsh': ('shell_script', 'shell'),

    # Build/package
    'Dockerfile': ('container_config', 'dockerfile'),
    'Makefile': ('build_config', 'makefile'),
}

STANDARD_FILES = {
    '.env': 'environment_config',
    '.env.local': 'environment_config',
    '.env.development': 'environment_config',
    '.env.production': 'environment_config',
    '.env.test': 'environment_config',
    'package.json': 'package_manifest',
    'package-lock.json': 'package_lock',
    'yarn.lock': 'yarn_lock',
    'requirements.txt': 'python_dependencies',
    'Pipfile': 'python_dependencies',
    'Pipfile.lock': 'python_lock',
    'poetry.lock': 'poetry_lock',
    'pyproject.toml': 'python_project',
    'Cargo.toml': 'rust_manifest',
    'Cargo.lock': 'rust_lock',
    'go.mod': 'go_module',
    'go.sum': 'go_dependencies',
    'docker-compose.yml': 'container_orchestration',
    'docker-compose.yaml': 'container_orchestration',
    'Dockerfile': 'container_config',
    '.dockerignore': 'docker_ignore',
    '.gitignore': 'vcs_config',
    '.gitattributes': 'vcs_config',
    'README.md': 'documentation',
    'README': 'documentation',
    'LICENSE': 'license',
    'LICENSE.md': 'license',
    'CHANGELOG.md': 'changelog',
    'setup.py': 'python_setup',
    'tsconfig.json': 'typescript_config',
    '.eslintrc': 'eslint_config',
    '.eslintrc.js': 'eslint_config',
    '.prettierrc': 'prettier_config',
}


def detect_file_type(file_path: str) -> Tuple[Optional[str], Optional[str], bool, Optional[str]]:
    """
    Detect file type and language.

    Returns: (file_type, language, is_standard, standard_type)
    """
    path = Path(file_path)
    file_name = path.name
    ext = path.suffix.lower()

    # Check if standard file
    if file_name in STANDARD_FILES:
        std_type = STANDARD_FILES[file_name]
        # Determine file_type and language from extension
        if ext in FILE_TYPE_MAP:
            file_type, language = FILE_TYPE_MAP[ext]
        else:
            file_type = std_type
            language = None
        return file_type, language, True, std_type

    # Check by extension
    if ext in FILE_TYPE_MAP:
        file_type, language = FILE_TYPE_MAP[ext]
        return file_type, language, False, None

    # Check special cases by filename
    if file_name in FILE_TYPE_MAP:
        file_type, language = FILE_TYPE_MAP[file_name]
        return file_type, language, False, None

    # Default: unknown
    return 'unknown', None, False, None


# ============================================================================
# STANDARD FILE WARNINGS
# ============================================================================

def check_standard_file_warnings(file_path: str, file_type: str, standard_type: Optional[str], project_root: str) -> List[str]:
    """Generate warnings for standard files"""
    warnings = []

    if not standard_type:
        return warnings

    file_name = os.path.basename(file_path)

    # .env file warnings
    if standard_type == 'environment_config':
        # Check if .env is in .gitignore
        gitignore_path = os.path.join(project_root, '.gitignore')
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                gitignore_content = f.read()
                if '.env' not in gitignore_content:
                    warnings.append('.env not in .gitignore - may expose secrets')
        else:
            warnings.append('No .gitignore found - .env may be committed')

        # Check for secrets in .env
        try:
            with open(file_path, 'r') as f:
                content = f.read().upper()
                secret_keywords = ['PASSWORD', 'SECRET', 'TOKEN', 'KEY', 'API_KEY', 'PRIVATE']
                if any(keyword in content for keyword in secret_keywords):
                    warnings.append('Contains potential secrets (PASSWORD, SECRET, TOKEN, KEY)')
        except:
            pass

    # package.json warnings
    elif standard_type == 'package_manifest':
        # Check if package-lock.json exists
        lock_file = os.path.join(os.path.dirname(file_path), 'package-lock.json')
        if not os.path.exists(lock_file):
            warnings.append('No package-lock.json found - dependencies not locked')

    # requirements.txt warnings
    elif standard_type == 'python_dependencies':
        # Check if versions are pinned
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                unpinned = [line for line in lines if '==' not in line and '>=' not in line]
                if unpinned:
                    warnings.append(f'{len(unpinned)} unpinned dependencies (recommend pinning versions)')
        except:
            pass

    # Dockerfile warnings
    elif standard_type == 'container_config':
        dockerignore_path = os.path.join(os.path.dirname(file_path), '.dockerignore')
        if not os.path.exists(dockerignore_path):
            warnings.append('No .dockerignore found - image may be larger than necessary')

    return warnings


# ============================================================================
# SEMANTIC ANALYSIS - Extract imports, exports, dependencies
# ============================================================================

def analyze_python_file(file_path: str, content: str) -> Dict[str, Any]:
    """Extract semantic information from Python file"""

    imports = []
    exports = []

    # Extract imports (simple regex, fast)
    import_patterns = [
        r'^import\s+([\w\.]+)',
        r'^from\s+([\w\.]+)\s+import',
    ]

    for pattern in import_patterns:
        matches = re.findall(pattern, content, re.MULTILINE)
        imports.extend(matches)

    # Extract functions and classes (exports)
    function_pattern = r'^def\s+(\w+)'
    class_pattern = r'^class\s+(\w+)'

    functions = re.findall(function_pattern, content, re.MULTILINE)
    classes = re.findall(class_pattern, content, re.MULTILINE)

    exports = functions + classes

    # Count components
    contains = {
        'classes': len(classes),
        'functions': len(functions),
        'lines': content.count('\n')
    }

    return {
        'imports': list(set(imports))[:20],  # Limit to 20
        'exports': exports[:20],
        'contains': contains
    }


def analyze_javascript_file(file_path: str, content: str) -> Dict[str, Any]:
    """Extract semantic information from JavaScript/TypeScript file"""

    imports = []
    exports = []

    # Extract imports
    import_patterns = [
        r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]",
        r"require\(['\"]([^'\"]+)['\"]\)",
    ]

    for pattern in import_patterns:
        matches = re.findall(pattern, content)
        imports.extend(matches)

    # Extract exports (simplified)
    export_patterns = [
        r'export\s+(?:default\s+)?(?:function|class)\s+(\w+)',
        r'export\s+const\s+(\w+)',
        r'module\.exports\s*=\s*(\w+)',
    ]

    for pattern in export_patterns:
        matches = re.findall(pattern, content)
        exports.extend(matches)

    # Count components
    function_count = len(re.findall(r'function\s+\w+', content))
    class_count = len(re.findall(r'class\s+\w+', content))

    contains = {
        'functions': function_count,
        'classes': class_count,
        'lines': content.count('\n')
    }

    return {
        'imports': list(set(imports))[:20],
        'exports': exports[:20],
        'contains': contains
    }


def analyze_file_semantics(file_path: str, file_type: str, language: Optional[str]) -> Dict[str, Any]:
    """Analyze file semantics based on file type"""

    result = {
        'imports': [],
        'exports': [],
        'dependencies': [],
        'contains': {}
    }

    # Skip binary files and very large files
    try:
        file_size = os.path.getsize(file_path)
        if file_size > 1_000_000:  # Skip files >1MB for semantic analysis
            return result

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return result

    # Analyze based on language
    if language == 'python':
        analysis = analyze_python_file(file_path, content)
        result.update(analysis)

    elif language in ['javascript', 'typescript']:
        analysis = analyze_javascript_file(file_path, content)
        result.update(analysis)

    # Add more languages here as needed

    return result


# ============================================================================
# FILESYSTEM WALKING - Respect .gitignore
# ============================================================================

def should_ignore_path(path: str, gitignore_patterns: Set[str]) -> bool:
    """Check if path should be ignored based on .gitignore patterns"""

    # Always ignore these
    always_ignore = {
        '.git', '__pycache__', 'node_modules', 'venv', 'env',
        '.venv', 'dist', 'build', '.next', '.cache', 'target',
        '.pytest_cache', '.mypy_cache', 'coverage', '.DS_Store'
    }

    path_parts = Path(path).parts
    if any(part in always_ignore for part in path_parts):
        return True

    # Check gitignore patterns (simplified)
    basename = os.path.basename(path)
    for pattern in gitignore_patterns:
        if pattern in path or pattern in basename:
            return True

    return False


def load_gitignore_patterns(project_root: str) -> Set[str]:
    """Load patterns from .gitignore file"""
    patterns = set()

    gitignore_path = os.path.join(project_root, '.gitignore')
    if not os.path.exists(gitignore_path):
        return patterns

    try:
        with open(gitignore_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Remove trailing slashes and wildcards for simple matching
                    pattern = line.rstrip('/').replace('*', '')
                    if pattern:
                        patterns.add(pattern)
    except:
        pass

    return patterns


def walk_project_files(project_root: str, respect_gitignore: bool = True, max_files: int = 10000) -> List[str]:
    """
    Walk project directory and return list of files.

    Returns: List of absolute file paths
    """
    files = []

    gitignore_patterns = set()
    if respect_gitignore:
        gitignore_patterns = load_gitignore_patterns(project_root)

    try:
        for root, dirs, filenames in os.walk(project_root):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not should_ignore_path(os.path.join(root, d), gitignore_patterns)]

            for filename in filenames:
                file_path = os.path.join(root, filename)

                if should_ignore_path(file_path, gitignore_patterns):
                    continue

                files.append(file_path)

                if len(files) >= max_files:
                    return files
    except Exception:
        pass

    return files


# ============================================================================
# SEMANTIC CLUSTERING
# ============================================================================

def cluster_files_by_semantics(files_data: List[Dict]) -> Dict[str, List[str]]:
    """
    Group files into semantic clusters based on:
    - Directory structure
    - File naming patterns
    - Import/dependency relationships
    """
    clusters = {}

    for file_data in files_data:
        file_path = file_data['file_path']
        path_lower = file_path.lower()

        # Determine cluster(s) for this file
        file_clusters = set()

        # Cluster by directory
        parts = Path(file_path).parts
        if len(parts) > 1:
            dir_name = parts[-2] if len(parts) > 1 else ''
            if dir_name:
                file_clusters.add(dir_name)

        # Cluster by semantic patterns
        if any(keyword in path_lower for keyword in ['auth', 'login', 'user', 'account']):
            file_clusters.add('authentication')

        if any(keyword in path_lower for keyword in ['api', 'endpoint', 'route', 'handler']):
            file_clusters.add('api')

        if any(keyword in path_lower for keyword in ['database', 'db', 'model', 'schema', 'migration']):
            file_clusters.add('database')

        if any(keyword in path_lower for keyword in ['test', 'spec', '__test__']):
            file_clusters.add('tests')

        if any(keyword in path_lower for keyword in ['config', 'settings', 'env']):
            file_clusters.add('configuration')

        if any(keyword in path_lower for keyword in ['doc', 'readme', 'guide']):
            file_clusters.add('documentation')

        # Add to clusters
        if not file_clusters:
            file_clusters.add('misc')

        for cluster in file_clusters:
            if cluster not in clusters:
                clusters[cluster] = []
            clusters[cluster].append(file_path)

    return clusters
