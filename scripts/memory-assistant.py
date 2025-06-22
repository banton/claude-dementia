#!/usr/bin/env python3
"""
Claude Memory Assistant - Orchestrates all memory tools.
A simple command-line interface to all memory subagents.
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class MemoryAssistant:
    def __init__(self):
        self.scripts_dir = Path(__file__).parent
        self.tools = {
            'session': self.scripts_dir / 'session-logger.py',
            'patterns': self.scripts_dir / 'pattern-detector.py',
            'questions': self.scripts_dir / 'question-tracker.py',
            'search': self.scripts_dir / 'memory-search.py'
        }
        
    def run_tool(self, tool_name: str, args: list = None):
        """Run a specific tool."""
        if tool_name not in self.tools:
            print(f"Unknown tool: {tool_name}")
            return False
            
        tool_path = self.tools[tool_name]
        if not tool_path.exists():
            print(f"Tool not found: {tool_path}")
            return False
            
        cmd = [sys.executable, str(tool_path)]
        if args:
            cmd.extend(args)
            
        try:
            result = subprocess.run(cmd, capture_output=False)
            return result.returncode == 0
        except Exception as e:
            print(f"Error running {tool_name}: {e}")
            return False
    
    def session_end(self):
        """Run end-of-session routine."""
        print("🏁 Running end-of-session routine...\n")
        
        # 1. Generate session summary
        print("📝 Generating session summary from git activity...")
        self.run_tool('session')
        
        # 2. Detect new patterns
        print("\n🔍 Detecting code patterns...")
        self.run_tool('patterns')
        
        # 3. Check questions
        print("\n❓ Checking question status...")
        self.run_tool('questions')
        
        # 4. Rebuild search index
        print("\n🔎 Updating search index...")
        self.run_tool('search', ['--rebuild', 'dummy'])
        
        print("\n✅ Session end routine complete!")
        print("\n📋 Don't forget to:")
        print("1. Edit memory/current-session.md with session details")
        print("2. Review any new patterns detected")
        print("3. Check if any old questions can be answered")
        
    def session_start(self):
        """Run start-of-session routine."""
        print("🚀 Running start-of-session routine...\n")
        
        # 1. Check question status
        print("❓ Checking for unanswered questions...")
        self.run_tool('questions')
        
        # 2. Show recent session summary
        session_file = Path("memory/current-session.md")
        if session_file.exists():
            print("\n📝 Last session summary:")
            print("-" * 50)
            # Show first 20 lines
            with open(session_file, 'r') as f:
                lines = f.readlines()[:20]
                print(''.join(lines))
            if len(lines) == 20:
                print("... (truncated)")
            print("-" * 50)
        
        print("\n✅ Ready to start coding!")
        
    def quick_search(self, query: str):
        """Quick search through memory."""
        self.run_tool('search', [query])
        
    def show_help(self):
        """Show help information."""
        print("""
Claude Memory Assistant - Manage your external memory

Commands:
  start         - Run start-of-session routine
  end           - Run end-of-session routine  
  search QUERY  - Search through memory files
  patterns      - Detect patterns in recent code
  questions     - Check question status
  help          - Show this help

Examples:
  ./memory-assistant.py start
  ./memory-assistant.py search "error handling"
  ./memory-assistant.py end

Git Hook Setup:
  # Add to .git/hooks/post-commit:
  #!/bin/bash
  python scripts/memory-assistant.py patterns

  # Add to .git/hooks/pre-push:
  #!/bin/bash
  python scripts/memory-assistant.py questions
""")

def main():
    """Main entry point."""
    assistant = MemoryAssistant()
    
    if len(sys.argv) < 2:
        assistant.show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'help' or command == '--help':
        assistant.show_help()
    elif command == 'start':
        assistant.session_start()
    elif command == 'end':
        assistant.session_end()
    elif command == 'search' and len(sys.argv) > 2:
        query = ' '.join(sys.argv[2:])
        assistant.quick_search(query)
    elif command == 'patterns':
        assistant.run_tool('patterns')
    elif command == 'questions':
        assistant.run_tool('questions')
    else:
        print(f"Unknown command: {command}")
        assistant.show_help()

if __name__ == "__main__":
    main()
