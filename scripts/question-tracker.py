#!/usr/bin/env python3
"""
Question tracker - Monitors and reminds about unanswered questions.
Helps ensure important clarifications don't get lost.
"""
import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class QuestionTracker:
    def __init__(self):
        self.memory_path = Path("memory/questions")
        self.status_file = Path("memory/questions/.status.json")
        self.questions = []
        
    def scan_questions(self):
        """Scan all question files and extract status."""
        if not self.memory_path.exists():
            print("No questions directory found")
            return
        
        for question_file in self.memory_path.glob("*.md"):
            if question_file.name.startswith('.'):
                continue
                
            question_data = self._parse_question_file(question_file)
            if question_data:
                self.questions.append(question_data)
    
    def _parse_question_file(self, filepath: Path) -> Optional[Dict]:
        """Parse a question file and extract metadata."""
        try:
            content = filepath.read_text()
            
            # Extract status
            status_match = re.search(r'## Status: \[?([^\]]+)\]?', content)
            status = status_match.group(1) if status_match else 'UNKNOWN'
            
            # Extract question summary
            question_match = re.search(r'# Question: ([^\n]+)', content)
            question = question_match.group(1) if question_match else filepath.stem
            
            # Extract date from filename
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', filepath.name)
            date_str = date_match.group(1) if date_match else None
            
            # Calculate age
            if date_str:
                question_date = datetime.strptime(date_str, '%Y-%m-%d')
                age_days = (datetime.now() - question_date).days
            else:
                age_days = -1
            
            # Check if answered
            has_answer = 'Answer (When Received)' in content and '**Answer:**' in content
            
            return {
                'file': str(filepath),
                'question': question,
                'status': status,
                'date': date_str,
                'age_days': age_days,
                'has_answer': has_answer
            }
            
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None
    
    def generate_report(self) -> str:
        """Generate a question status report."""
        report = f"""# Question Tracker Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Summary
- **Total Questions**: {len(self.questions)}
- **Open Questions**: {sum(1 for q in self.questions if q['status'] == 'OPEN')}
- **Answered**: {sum(1 for q in self.questions if q['status'] == 'ANSWERED')}
- **Blocked**: {sum(1 for q in self.questions if q['status'] == 'BLOCKED')}

"""
        
        # Group by status
        open_questions = [q for q in self.questions if q['status'] == 'OPEN']
        blocked_questions = [q for q in self.questions if q['status'] == 'BLOCKED']
        old_questions = [q for q in open_questions if q['age_days'] > 7]
        
        if old_questions:
            report += "## ⚠️ Old Unanswered Questions (>7 days)\n"
            for q in sorted(old_questions, key=lambda x: x['age_days'], reverse=True):
                report += f"- **{q['age_days']} days old**: {q['question']}\n"
                report += f"  - File: `{q['file']}`\n"
        
        if open_questions:
            report += "\n## 📋 Open Questions\n"
            for q in sorted(open_questions, key=lambda x: x['age_days'], reverse=True):
                age_str = f"{q['age_days']} days old" if q['age_days'] >= 0 else "Unknown age"
                report += f"- {q['question']} ({age_str})\n"
        
        if blocked_questions:
            report += "\n## 🚧 Blocked Questions\n"
            for q in blocked_questions:
                report += f"- {q['question']}\n"
                report += f"  - May be unblocked now - check if situation changed\n"
        
        # Recommendations
        report += "\n## 💡 Recommendations\n"
        if old_questions:
            report += f"1. **Address old questions**: You have {len(old_questions)} questions older than a week\n"
        
        if len(open_questions) > 5:
            report += f"2. **Question backlog**: {len(open_questions)} open questions may slow development\n"
        
        report += "3. **Next actions**:\n"
        report += "   - Review old questions - they may no longer be relevant\n"
        report += "   - Check if blocked questions can be unblocked\n"
        report += "   - Consider batching similar questions together\n"
        
        return report
    
    def check_code_for_questions(self, files: List[Path]) -> List[Dict]:
        """Scan code files for potential questions in comments."""
        question_patterns = [
            r'# TODO:?\s*[Aa]sk',
            r'# QUESTION:',
            r'# Q:',
            r'# \?\?\?',
            r'# [Nn]eed clarification',
            r'# [Nn]ot sure',
            r'# [Ss]hould this',
            r'# [Ww]hat if',
            r'# [Hh]ow should'
        ]
        
        potential_questions = []
        
        for filepath in files:
            if not filepath.exists() or filepath.suffix not in ['.py', '.js', '.ts', '.md']:
                continue
                
            try:
                content = filepath.read_text()
                for i, line in enumerate(content.split('\n'), 1):
                    for pattern in question_patterns:
                        if re.search(pattern, line):
                            potential_questions.append({
                                'file': str(filepath),
                                'line': i,
                                'text': line.strip()
                            })
            except Exception as e:
                print(f"Error scanning {filepath}: {e}")
        
        return potential_questions
    
    def save_status(self):
        """Save question tracking status."""
        status_data = {
            'last_scan': datetime.now().isoformat(),
            'total_questions': len(self.questions),
            'open_count': sum(1 for q in self.questions if q['status'] == 'OPEN'),
            'oldest_open_days': max((q['age_days'] for q in self.questions 
                                   if q['status'] == 'OPEN' and q['age_days'] >= 0), 
                                  default=0)
        }
        
        self.memory_path.mkdir(parents=True, exist_ok=True)
        with open(self.status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

def main():
    """Main entry point."""
    tracker = QuestionTracker()
    
    print("Scanning questions in memory...")
    tracker.scan_questions()
    
    # Check recent code files for potential questions
    from subprocess import run
    result = run(
        ["git", "ls-files", "*.py", "*.js", "*.ts", "*.md"],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        files = [Path(f) for f in result.stdout.strip().split('\n') if f]
        print(f"\nScanning {len(files)} code files for potential questions...")
        potential = tracker.check_code_for_questions(files)
        
        if potential:
            print(f"\n⚠️ Found {len(potential)} potential questions in code:")
            for pq in potential[:5]:  # Show first 5
                print(f"  {pq['file']}:{pq['line']} - {pq['text'][:60]}...")
            if len(potential) > 5:
                print(f"  ... and {len(potential) - 5} more")
    
    # Generate report
    report = tracker.generate_report()
    
    # Save report
    report_file = Path("memory/questions/status-report.md")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(report)
    
    print(f"\nQuestion report saved to {report_file}")
    
    # Save status
    tracker.save_status()
    
    # Print summary
    if tracker.questions:
        open_count = sum(1 for q in tracker.questions if q['status'] == 'OPEN')
        old_count = sum(1 for q in tracker.questions 
                       if q['status'] == 'OPEN' and q['age_days'] > 7)
        
        if open_count > 0:
            print(f"\n📋 You have {open_count} open questions")
            if old_count > 0:
                print(f"⚠️  {old_count} of them are older than a week!")

if __name__ == "__main__":
    main()
