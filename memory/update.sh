#!/bin/bash
# Quick memory update script

SUMMARY="$1"
if [ -z "$SUMMARY" ]; then
    echo "Usage: ./update.sh 'Summary of changes'"
    exit 1
fi

DATE=$(date +"%Y-%m-%d %H:%M")
echo "" >> memory/active/status.md
echo "### Update: $DATE" >> memory/active/status.md
echo "- $SUMMARY" >> memory/active/status.md

# Run compression check
./memory/compress.sh

echo "✓ Memory updated"
