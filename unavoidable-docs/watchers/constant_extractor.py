#!/usr/bin/env python3
"""
Constant Extractor for Unavoidable Documentation System
Detects hardcoded values that should be documented constants
"""

import re
import ast
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor

class ConstantPattern:
    """Pattern definitions for detecting different types of constants"""
    
    # URL patterns
    URL_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>https?://[^\s"\']+)(?P=quote)',
        re.IGNORECASE
    )
    
    # Localhost/port patterns
    LOCALHOST_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>(?:localhost|127\.0\.0\.1):\d{1,5})(?P=quote)',
        re.IGNORECASE
    )
    
    # Standalone port patterns
    PORT_PATTERN = re.compile(
        r'(?:PORT|port|Port)\s*[=:]\s*(?P<value>\d{4,5})',
        re.IGNORECASE
    )
    
    # API endpoint patterns
    API_ENDPOINT_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>/api/[^\s"\']+)(?P=quote)'
    )
    
    # Environment variable patterns
    ENV_VAR_PATTERN = re.compile(
        r'(?:process\.env\.|os\.environ\[?|ENV\[?)["\']?(?P<value>[A-Z_][A-Z0-9_]*)'
    )
    
    # API key patterns
    API_KEY_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>(?:sk_|pk_|api_|key_|token_)[a-zA-Z0-9]{10,})(?P=quote)'
    )
    
    # Database URL patterns
    DB_URL_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>(?:mongodb|postgres|postgresql|mysql|redis|sqlite)://[^\s"\']+)(?P=quote)',
        re.IGNORECASE
    )
    
    # IP address patterns
    IP_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?P=quote)'
    )
    
    # Timeout/interval patterns
    TIMEOUT_PATTERN = re.compile(
        r'(?:timeout|interval|delay|duration)\s*[=:]\s*(?P<value>\d+)',
        re.IGNORECASE
    )
    
    # Limit/threshold patterns
    LIMIT_PATTERN = re.compile(
        r'(?:limit|max|min|threshold|count)\s*[=:]\s*(?P<value>\d+)',
        re.IGNORECASE
    )
    
    # File path patterns
    FILE_PATH_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>(?:/|\\|\.\.?/|[A-Za-z]:)[^\s"\']+\.[a-z]{2,4})(?P=quote)'
    )
    
    # AWS/Cloud resource patterns
    AWS_PATTERN = re.compile(
        r'(?P<quote>["\'])(?P<value>arn:aws:[^\s"\']+|s3://[^\s"\']+|[a-z]{2}-[a-z]+-\d{1}:[^\s"\']+)(?P=quote)'
    )
    
    # Hardcoded credentials (CRITICAL)
    CREDENTIAL_PATTERN = re.compile(
        r'(?:password|passwd|pwd|secret|token)\s*[=:]\s*(?P<quote>["\'])(?P<value>[^\s"\']{6,})(?P=quote)',
        re.IGNORECASE
    )

class ConstantExtractor:
    """Extracts potential constants from source code files"""
    
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.conn = None
        self.patterns = {
            'url': (ConstantPattern.URL_PATTERN, 0.9),
            'localhost': (ConstantPattern.LOCALHOST_PATTERN, 0.95),
            'port': (ConstantPattern.PORT_PATTERN, 0.85),
            'api_endpoint': (ConstantPattern.API_ENDPOINT_PATTERN, 0.9),
            'env_var': (ConstantPattern.ENV_VAR_PATTERN, 0.8),
            'api_key': (ConstantPattern.API_KEY_PATTERN, 0.95),
            'database_url': (ConstantPattern.DB_URL_PATTERN, 0.95),
            'ip_address': (ConstantPattern.IP_PATTERN, 0.7),
            'timeout': (ConstantPattern.TIMEOUT_PATTERN, 0.75),
            'limit': (ConstantPattern.LIMIT_PATTERN, 0.7),
            'file_path': (ConstantPattern.FILE_PATH_PATTERN, 0.6),
            'aws_resource': (ConstantPattern.AWS_PATTERN, 0.9),
            'credential': (ConstantPattern.CREDENTIAL_PATTERN, 1.0)
        }
        self.connect()
    
    def connect(self):
        """Connect to database"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 5432),
                database=self.db_config.get('database', 'unavoidable_docs'),
                user=self.db_config.get('user', 'unavoidable_docs_user'),
                password=self.db_config.get('password', '')
            )
            self.conn.autocommit = True
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
    
    def extract_constants_from_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract all potential constants from a file"""
        constants = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Process each pattern
            for const_type, (pattern, base_confidence) in self.patterns.items():
                for match in pattern.finditer(content):
                    value = match.group('value')
                    
                    # Skip if too short (except for ports)
                    if len(value) < 3 and const_type != 'port':
                        continue
                    
                    # Find line number
                    line_num = content[:match.start()].count('\n') + 1
                    
                    # Get context (2 lines before and after)
                    context_start = max(0, line_num - 3)
                    context_end = min(len(lines), line_num + 2)
                    context_lines = lines[context_start:context_end]
                    
                    # Calculate confidence based on context
                    confidence = self.calculate_confidence(
                        value, const_type, base_confidence, context_lines
                    )
                    
                    # Generate probable name
                    probable_name = self.generate_constant_name(value, const_type)
                    
                    # Determine purpose from context
                    probable_purpose = self.infer_purpose(value, const_type, context_lines)
                    
                    constants.append({
                        'file_path': file_path,
                        'constant_value': value,
                        'constant_type': const_type,
                        'line_number': line_num,
                        'confidence_score': confidence,
                        'probable_name': probable_name,
                        'probable_purpose': probable_purpose,
                        'context_before': '\n'.join(context_lines[:2]) if line_num > 1 else '',
                        'context_after': '\n'.join(context_lines[-2:]) if line_num < len(lines) else ''
                    })
        
        except Exception as e:
            print(f"Error extracting from {file_path}: {e}")
        
        # For Python files, also use AST parsing
        if file_path.endswith('.py'):
            constants.extend(self.extract_python_constants(file_path))
        
        return constants
    
    def extract_python_constants(self, file_path: str) -> List[Dict[str, Any]]:
        """Extract constants from Python files using AST"""
        constants = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            for node in ast.walk(tree):
                # Module-level assignments that look like constants
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id.isupper():
                            # This looks like a constant
                            value = self.extract_ast_value(node.value)
                            if value:
                                constants.append({
                                    'file_path': file_path,
                                    'constant_value': str(value),
                                    'constant_type': self.infer_type_from_value(value),
                                    'line_number': node.lineno,
                                    'confidence_score': 0.9,
                                    'probable_name': target.id,
                                    'probable_purpose': f"Constant {target.id}",
                                    'context_before': '',
                                    'context_after': ''
                                })
        except:
            pass  # AST parsing failed, skip
        
        return constants
    
    def extract_ast_value(self, node) -> Optional[Any]:
        """Extract value from AST node"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.List):
            return [self.extract_ast_value(elt) for elt in node.elts]
        elif isinstance(node, ast.Dict):
            return {
                self.extract_ast_value(k): self.extract_ast_value(v)
                for k, v in zip(node.keys, node.values)
            }
        return None
    
    def calculate_confidence(self, value: str, const_type: str, 
                            base_confidence: float, context: List[str]) -> float:
        """Calculate confidence score based on value and context"""
        confidence = base_confidence
        
        # Increase confidence for certain patterns
        if const_type == 'credential' and any(word in str(context).lower() 
                                             for word in ['secret', 'password', 'token']):
            confidence = min(1.0, confidence + 0.1)
        
        if const_type == 'port' and 1024 <= int(value) <= 65535:
            confidence = min(1.0, confidence + 0.1)
        
        if const_type == 'api_endpoint' and value.startswith('/api/v'):
            confidence = min(1.0, confidence + 0.05)
        
        # Decrease confidence for common false positives
        if const_type == 'ip_address' and value in ['0.0.0.0', '127.0.0.1', '255.255.255.255']:
            confidence = max(0.3, confidence - 0.3)
        
        if const_type == 'limit' and int(value) in [0, 1, 10, 100]:
            confidence = max(0.5, confidence - 0.2)
        
        return confidence
    
    def generate_constant_name(self, value: str, const_type: str) -> str:
        """Generate a probable constant name based on value and type"""
        # Type-specific prefixes
        prefixes = {
            'url': 'API_URL',
            'localhost': 'LOCAL_HOST',
            'port': 'PORT',
            'api_endpoint': 'ENDPOINT',
            'env_var': 'ENV',
            'api_key': 'API_KEY',
            'database_url': 'DATABASE_URL',
            'ip_address': 'IP_ADDRESS',
            'timeout': 'TIMEOUT',
            'limit': 'MAX_LIMIT',
            'file_path': 'FILE_PATH',
            'aws_resource': 'AWS_RESOURCE',
            'credential': 'SECRET'
        }
        
        prefix = prefixes.get(const_type, 'CONSTANT')
        
        # Clean value for name generation
        if const_type == 'api_endpoint':
            # Convert /api/users/profile to USERS_PROFILE
            clean = value.replace('/api/', '').replace('/', '_').upper()
            return f"{prefix}_{clean}"
        elif const_type == 'url':
            # Extract domain from URL
            import re
            domain_match = re.search(r'://([^/]+)', value)
            if domain_match:
                domain = domain_match.group(1).replace('.', '_').upper()
                return f"{prefix}_{domain}"
        elif const_type == 'port':
            return f"{prefix}_{value}"
        
        return prefix
    
    def infer_purpose(self, value: str, const_type: str, context: List[str]) -> str:
        """Infer the purpose of a constant from its context"""
        context_str = ' '.join(context).lower()
        
        # Type-specific purpose inference
        if const_type == 'url':
            if 'api' in context_str:
                return "API endpoint URL"
            elif 'webhook' in context_str:
                return "Webhook URL"
            elif 'cdn' in context_str:
                return "CDN resource URL"
            return "External service URL"
        
        elif const_type == 'port':
            if 'server' in context_str:
                return f"Server port number"
            elif 'database' in context_str or 'db' in context_str:
                return f"Database port number"
            return f"Service port number"
        
        elif const_type == 'api_endpoint':
            # Try to infer from endpoint path
            if 'auth' in value or 'login' in value:
                return "Authentication endpoint"
            elif 'user' in value:
                return "User management endpoint"
            elif 'payment' in value:
                return "Payment processing endpoint"
            return "API endpoint path"
        
        elif const_type == 'timeout':
            if 'request' in context_str:
                return "Request timeout in milliseconds"
            elif 'session' in context_str:
                return "Session timeout duration"
            return "Timeout duration"
        
        elif const_type == 'credential':
            return "⚠️ HARDCODED CREDENTIAL - SECURITY RISK"
        
        return f"{const_type.replace('_', ' ').title()} constant"
    
    def infer_type_from_value(self, value: Any) -> str:
        """Infer constant type from its value"""
        if isinstance(value, str):
            if value.startswith(('http://', 'https://')):
                return 'url'
            elif value.startswith('/'):
                return 'api_endpoint'
            elif '@' in value:
                return 'email'
        elif isinstance(value, int):
            if 1024 <= value <= 65535:
                return 'port'
            elif value > 1000:
                return 'timeout'
            else:
                return 'limit'
        return 'unknown'
    
    def save_constants_to_db(self, file_path: str, constants: List[Dict[str, Any]]):
        """Save extracted constants to database"""
        if not self.conn or not constants:
            return
        
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get or create file entry
            cur.execute(
                "SELECT id FROM file_documentation_status WHERE file_path = %s",
                (file_path,)
            )
            result = cur.fetchone()
            
            if not result:
                # Create file entry
                cur.execute("""
                    INSERT INTO file_documentation_status (file_path, status)
                    VALUES (%s, 'undocumented')
                    RETURNING id
                """, (file_path,))
                file_id = cur.fetchone()['id']
            else:
                file_id = result['id']
            
            # Update file to indicate it has constants
            cur.execute("""
                UPDATE file_documentation_status
                SET has_constants = TRUE, total_constants = %s
                WHERE id = %s
            """, (len(constants), file_id))
            
            # Insert constants
            for const in constants:
                # Check if constant already exists
                cur.execute("""
                    SELECT id FROM undocumented_constants
                    WHERE file_id = %s AND constant_value = %s AND line_number = %s
                """, (file_id, const['constant_value'], const['line_number']))
                
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO undocumented_constants
                        (file_id, constant_value, constant_type, line_number,
                         confidence_score, probable_name, probable_purpose,
                         context_before, context_after)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        file_id, const['constant_value'], const['constant_type'],
                        const['line_number'], const['confidence_score'],
                        const['probable_name'], const['probable_purpose'],
                        const['context_before'], const['context_after']
                    ))
                    
                    # Create documentation debt for high-confidence constants
                    if const['confidence_score'] >= 0.8:
                        priority = 'critical' if const['constant_type'] == 'credential' else 'medium'
                        cur.execute("""
                            INSERT INTO documentation_debt
                            (file_id, debt_type, item_name, description, priority, line_number)
                            VALUES (%s, 'new_constant', %s, %s, %s, %s)
                        """, (
                            file_id, const['probable_name'],
                            f"Undocumented {const['constant_type']}: {const['constant_value'][:50]}",
                            priority, const['line_number']
                        ))

def scan_file(file_path: str, db_config: dict) -> int:
    """Scan a single file for constants"""
    extractor = ConstantExtractor(db_config)
    constants = extractor.extract_constants_from_file(file_path)
    
    if constants:
        print(f"\n📋 Found {len(constants)} potential constants in {file_path}:")
        for const in constants:
            confidence_emoji = "🔴" if const['confidence_score'] >= 0.9 else "🟡" if const['confidence_score'] >= 0.7 else "⚪"
            print(f"   {confidence_emoji} Line {const['line_number']}: {const['constant_type']} = {const['constant_value'][:50]}...")
            print(f"      Suggested name: {const['probable_name']}")
            print(f"      Purpose: {const['probable_purpose']}")
            print(f"      Confidence: {const['confidence_score']:.0%}")
        
        extractor.save_constants_to_db(file_path, constants)
    
    return len(constants)

def scan_directory(directory: str, db_config: dict):
    """Scan entire directory for constants"""
    print(f"🔍 Scanning directory for undocumented constants: {directory}")
    
    total_files = 0
    total_constants = 0
    critical_constants = []
    
    for path in Path(directory).rglob('*'):
        if path.is_file() and path.suffix in ['.py', '.js', '.ts', '.java', '.go', '.rb', '.php']:
            total_files += 1
            count = scan_file(str(path), db_config)
            total_constants += count
            
            if count > 0:
                # Check for critical constants (credentials)
                extractor = ConstantExtractor(db_config)
                constants = extractor.extract_constants_from_file(str(path))
                for const in constants:
                    if const['constant_type'] == 'credential':
                        critical_constants.append((str(path), const))
    
    print(f"\n{'='*60}")
    print(f"📊 CONSTANT EXTRACTION SUMMARY")
    print(f"{'='*60}")
    print(f"Files scanned: {total_files}")
    print(f"Constants found: {total_constants}")
    
    if critical_constants:
        print(f"\n⚠️  CRITICAL: Found {len(critical_constants)} hardcoded credentials!")
        for file_path, const in critical_constants:
            print(f"   🔴 {file_path}:{const['line_number']} - {const['constant_value'][:20]}...")
    
    print(f"{'='*60}")

if __name__ == "__main__":
    import sys
    
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'unavoidable_docs',
        'user': 'unavoidable_docs_user',
        'password': ''
    }
    
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if Path(path).is_file():
            scan_file(path, db_config)
        else:
            scan_directory(path, db_config)
    else:
        scan_directory('.', db_config)