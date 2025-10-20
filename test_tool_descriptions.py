#!/usr/bin/env python3
"""
Test that tool descriptions are enhanced with detailed usage instructions

Verifies:
1. Descriptions are 200+ words (not 20 words)
2. Include "When to use" sections
3. Include "Best practices" sections
4. Include example workflows
5. Include performance notes (for RLM-optimized tools)
"""

import sys
import re
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import claude_mcp_hybrid as mcp_module


def count_words(text: str) -> int:
    """Count words in text"""
    return len(re.findall(r'\b\w+\b', text))


def test_tool_description_quality():
    """Test that key tool descriptions are enhanced"""
    print("\n🧪 Test: Tool description quality")

    # Tools that should have enhanced descriptions
    enhanced_tools = [
        'lock_context',
        'recall_context',
        'check_contexts',
    ]

    all_passed = True

    for tool_name in enhanced_tools:
        print(f"\n   Testing: {tool_name}")

        # Get the function
        func = getattr(mcp_module, tool_name, None)
        if func is None:
            print(f"   ❌ Tool '{tool_name}' not found")
            all_passed = False
            continue

        docstring = func.__doc__
        if not docstring:
            print(f"   ❌ No docstring for '{tool_name}'")
            all_passed = False
            continue

        # Test 1: Word count (should be 200+ words)
        word_count = count_words(docstring)
        if word_count < 200:
            print(f"   ❌ Too short: {word_count} words (expected 200+)")
            all_passed = False
        else:
            print(f"   ✅ Length: {word_count} words")

        # Test 2: Has "When to use" section
        if "when to use" not in docstring.lower():
            print(f"   ❌ Missing 'When to use' section")
            all_passed = False
        else:
            print(f"   ✅ Has 'When to use' section")

        # Test 3: Has "Best practices" section
        if "best practices" not in docstring.lower():
            print(f"   ❌ Missing 'Best practices' section")
            all_passed = False
        else:
            print(f"   ✅ Has 'Best practices' section")

        # Test 4: Has examples
        if "example" not in docstring.lower():
            print(f"   ❌ Missing examples")
            all_passed = False
        else:
            print(f"   ✅ Has examples")

        # Test 5: Has performance note (for RLM-optimized tools)
        if tool_name in ['check_contexts', 'recall_context']:
            if "rlm" not in docstring.lower() and "60-80%" not in docstring:
                print(f"   ⚠️  Missing RLM performance note")
                # Don't fail, just warn
            else:
                print(f"   ✅ Has RLM performance note")

    return all_passed


def test_description_structure():
    """Test that descriptions follow the pattern"""
    print("\n🧪 Test: Description structure")

    # Check lock_context as example
    func = getattr(mcp_module, 'lock_context')
    docstring = func.__doc__

    required_sections = [
        "When to use",
        "What this",
        "Priority levels",
        "Best practices",
        "Example",
        "Returns",
    ]

    all_found = True
    for section in required_sections:
        if section.lower() not in docstring.lower():
            print(f"   ❌ Missing section: '{section}'")
            all_found = False
        else:
            print(f"   ✅ Found section: '{section}'")

    return all_found


def test_actionable_language():
    """Test that descriptions use actionable, directive language"""
    print("\n🧪 Test: Actionable language")

    func = getattr(mcp_module, 'check_contexts')
    docstring = func.__doc__

    # Should have imperative/directive phrases
    directive_patterns = [
        r'\bcheck before\b',
        r'\buse after\b',
        r'\bdon\'t\b',
        r'\bdo check\b',
        r'\bmust\b',
        r'\bshould\b',
    ]

    found_count = 0
    for pattern in directive_patterns:
        if re.search(pattern, docstring, re.IGNORECASE):
            found_count += 1

    if found_count >= 3:
        print(f"   ✅ Has actionable language ({found_count} directive phrases)")
        return True
    else:
        print(f"   ❌ Lacks actionable language ({found_count} directive phrases, expected 3+)")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Tool Description Quality Test")
    print("=" * 60)

    tests = [
        ("Description Quality", test_tool_description_quality),
        ("Description Structure", test_description_structure),
        ("Actionable Language", test_actionable_language),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
