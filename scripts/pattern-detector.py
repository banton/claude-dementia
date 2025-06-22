#!/usr/bin/env python3
"""
Pattern detector - Automatically identifies and documents code patterns.
Analyzes recent changes to find reusable patterns.
"""
import ast
import re
import json
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

class PatternDetector:
    def __init__(self):
        self.patterns = {
            'error_handling': [],
            'validation': [],
            'api_endpoints': [],
            'test_patterns': [],
            'database_queries': [],
            'logging': [],
            'authentication': []
        }
        
    def analyze_python_file(self, filepath):
        """Analyze a Python file for patterns."""
        try:
            with open(filepath, 'r') as f:
                content = f.read()
                tree = ast.parse(content)
                
            # Detect error handling patterns
            self._detect_error_handling(tree, filepath)
            
            # Detect validation patterns
            self._detect_validation(tree, filepath)
            
            # Detect API endpoint patterns
            self._detect_api_patterns(content, filepath)
            
            # Detect test patterns
            if 'test' in str(filepath).lower():
                self._detect_test_patterns(tree, filepath)
                
        except Exception as e:
            print(f"Error analyzing {filepath}: {e}")
    
    def _detect_error_handling(self, tree, filepath):
        """Detect try-except patterns."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                pattern = {
                    'file': str(filepath),
                    'line': node.lineno,
                    'type': 'try-except',
                    'exceptions': []
                }
                
                for handler in node.handlers:
                    if handler.type:
                        if isinstance(handler.type, ast.Name):
                            pattern['exceptions'].append(handler.type.id)
                        elif isinstance(handler.type, ast.Tuple):
                            pattern['exceptions'].extend(
                                [e.id for e in handler.type.elts if isinstance(e, ast.Name)]
                            )
                
                if pattern['exceptions']:
                    self.patterns['error_handling'].append(pattern)
    
    def _detect_validation(self, tree, filepath):
        """Detect validation patterns."""
        for node in ast.walk(tree):
            # Look for Pydantic validators
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and 'validator' in decorator.id:
                        self.patterns['validation'].append({
                            'file': str(filepath),
                            'line': node.lineno,
                            'function': node.name,
                            'type': 'pydantic_validator'
                        })
                    
                # Look for validation in function names
                if any(word in node.name.lower() for word in ['validate', 'check', 'verify']):
                    self.patterns['validation'].append({
                        'file': str(filepath),
                        'line': node.lineno,
                        'function': node.name,
                        'type': 'validation_function'
                    })
    
    def _detect_api_patterns(self, content, filepath):
        """Detect API endpoint patterns."""
        # FastAPI/Flask style decorators
        api_patterns = [
            r'@(app|router)\.(get|post|put|delete|patch)\(["\']([^"\']+)["\']\)',
            r'@(app|bp)\.route\(["\']([^"\']+)["\']\)'
        ]
        
        for pattern in api_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                self.patterns['api_endpoints'].append({
                    'file': str(filepath),
                    'method': match.group(2) if match.lastindex >= 2 else 'route',
                    'endpoint': match.group(3) if match.lastindex >= 3 else match.group(2),
                    'type': 'api_endpoint'
                })
    
    def _detect_test_patterns(self, tree, filepath):
        """Detect test patterns."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('test_'):
                    # Check for common test patterns
                    has_arrange = False
                    has_act = False
                    has_assert = False
                    
                    for child in ast.walk(node):
                        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Str):
                            comment = child.value.s.lower()
                            if 'arrange' in comment:
                                has_arrange = True
                            elif 'act' in comment:
                                has_act = True
                            elif 'assert' in comment:
                                has_assert = True
                    
                    self.patterns['test_patterns'].append({
                        'file': str(filepath),
                        'line': node.lineno,
                        'function': node.name,
                        'has_aaa': has_arrange and has_act and has_assert,
                        'type': 'test_function'
                    })
    
    def generate_pattern_report(self):
        """Generate a report of detected patterns."""
        report = f"""# Detected Code Patterns - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Summary
"""
        total_patterns = sum(len(patterns) for patterns in self.patterns.values())
        report += f"- **Total Patterns Found**: {total_patterns}\n"
        
        for category, patterns in self.patterns.items():
            if patterns:
                report += f"- **{category.replace('_', ' ').title()}**: {len(patterns)} patterns\n"
        
        # Detail sections
        if self.patterns['error_handling']:
            report += "\n## Error Handling Patterns\n"
            exception_counts = Counter()
            for pattern in self.patterns['error_handling']:
                for exc in pattern['exceptions']:
                    exception_counts[exc] += 1
            
            report += "### Most Common Exceptions\n"
            for exc, count in exception_counts.most_common(5):
                report += f"- `{exc}`: {count} occurrences\n"
        
        if self.patterns['api_endpoints']:
            report += "\n## API Endpoint Patterns\n"
            method_counts = Counter(p['method'] for p in self.patterns['api_endpoints'])
            report += "### HTTP Methods Used\n"
            for method, count in method_counts.items():
                report += f"- `{method.upper()}`: {count} endpoints\n"
        
        if self.patterns['validation']:
            report += "\n## Validation Patterns\n"
            validation_types = Counter(p['type'] for p in self.patterns['validation'])
            for vtype, count in validation_types.items():
                report += f"- **{vtype}**: {count} occurrences\n"
        
        if self.patterns['test_patterns']:
            report += "\n## Test Patterns\n"
            aaa_count = sum(1 for p in self.patterns['test_patterns'] if p['has_aaa'])
            total_tests = len(self.patterns['test_patterns'])
            report += f"- Tests following AAA pattern: {aaa_count}/{total_tests}\n"
        
        report += "\n## Recommendations\n"
        report += "Based on the patterns detected:\n"
        
        # Generate recommendations
        if exception_counts:
            most_common_exc = exception_counts.most_common(1)[0][0]
            report += f"1. Consider creating a centralized error handler for `{most_common_exc}`\n"
        
        if self.patterns['api_endpoints']:
            report += "2. Document common API patterns in `memory/patterns/api-patterns.md`\n"
        
        if self.patterns['validation']:
            report += "3. Extract validation logic into reusable validators\n"
        
        return report
    
    def save_patterns_to_memory(self, report):
        """Save the pattern report to memory."""
        memory_dir = Path("memory/patterns")
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y-%m-%d')
        pattern_file = memory_dir / f"detected-patterns-{timestamp}.md"
        
        with open(pattern_file, 'w') as f:
            f.write(report)
        
        print(f"Pattern report saved to {pattern_file}")
        
        # Also save raw patterns as JSON for future analysis
        json_file = memory_dir / f"patterns-{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(self.patterns, f, indent=2, default=str)

def main():
    """Main entry point."""
    detector = PatternDetector()
    
    # Find all Python files modified recently
    from subprocess import run
    result = run(
        ["git", "diff", "--name-only", "--diff-filter=AM", "HEAD~10", "HEAD", "*.py"],
        capture_output=True, text=True
    )
    
    if result.returncode != 0:
        # If no git, analyze all Python files in current directory
        files = list(Path(".").rglob("*.py"))
    else:
        files = [Path(f) for f in result.stdout.strip().split('\n') if f]
    
    if not files:
        print("No Python files to analyze")
        return
    
    print(f"Analyzing {len(files)} Python files for patterns...")
    
    for filepath in files:
        if filepath.exists():
            detector.analyze_python_file(filepath)
    
    # Generate and save report
    report = detector.generate_pattern_report()
    detector.save_patterns_to_memory(report)
    
    # Print summary
    print("\nPattern Detection Summary:")
    for category, patterns in detector.patterns.items():
        if patterns:
            print(f"- {category}: {len(patterns)} patterns found")

if __name__ == "__main__":
    main()
