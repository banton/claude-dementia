#!/bin/bash
# Memory compression script - maintains 10k token budget

count_tokens() {
    echo $(cat "$1" 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
}

compress_file() {
    local file=$1
    local target_tokens=$2
    local current_tokens=$(count_tokens "$file")
    
    if [ $current_tokens -gt $target_tokens ]; then
        echo "Compressing $file from $current_tokens to ~$target_tokens tokens..."
        # Keep most important content (assuming it's at the top)
        head -n $(($target_tokens / 10)) "$file" > "$file.tmp"
        mv "$file.tmp" "$file"
    fi
}

echo "=== Memory Compression Check ==="

# Token budgets
ACTIVE_BUDGET=1500   # Per file in active
REFERENCE_BUDGET=1000 # Per file in reference

# Compress active files
for file in memory/active/*.md; do
    [ -f "$file" ] && compress_file "$file" $ACTIVE_BUDGET
done

# Compress reference files
for file in memory/reference/*.md; do
    [ -f "$file" ] && compress_file "$file" $REFERENCE_BUDGET
done

# Report totals
active_total=$(find memory/active -name "*.md" -exec cat {} + 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
reference_total=$(find memory/reference -name "*.md" -exec cat {} + 2>/dev/null | wc -w | awk '{print int($1 * 1.3)}')
total=$((active_total + reference_total))

echo ""
echo "Token Usage Report:"
echo "- Active: $active_total tokens"
echo "- Reference: $reference_total tokens" 
echo "- Total: $total tokens (target: 10,000)"
echo ""

if [ $total -gt 10000 ]; then
    echo "⚠️  WARNING: Over budget by $((total - 10000)) tokens"
else
    echo "✓ SUCCESS: Under budget by $((10000 - total)) tokens"
fi
