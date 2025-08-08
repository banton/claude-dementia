#!/bin/bash
# Weekly memory maintenance

echo "=== Weekly Memory Maintenance ==="
DATE=$(date +%Y-%m-%d)

# Archive files older than 7 days
echo "Archiving old files..."
mkdir -p memory/archive/$DATE
find memory/active -name "*.md" -mtime +7 -exec mv {} memory/archive/$DATE/ \; 2>/dev/null

# Compress archives
if [ "$(ls -A memory/archive/$DATE 2>/dev/null)" ]; then
    tar -czf memory/archive/$DATE.tar.gz -C memory/archive $DATE
    rm -rf memory/archive/$DATE
    echo "✓ Archived old files to memory/archive/$DATE.tar.gz"
else
    rmdir memory/archive/$DATE 2>/dev/null
fi

# Re-run analysis to refresh
if [ -f scripts/memory-assistant.py ]; then
    python3 scripts/memory-assistant.py patterns
fi

echo "✓ Weekly maintenance complete"
