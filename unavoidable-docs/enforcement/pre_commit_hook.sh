#!/bin/bash

# UNAVOIDABLE DOCUMENTATION SYSTEM - PRE-COMMIT HOOK
# This hook BLOCKS commits when documentation debt exists
# Install by copying to .git/hooks/pre-commit

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Database configuration (can be overridden by environment variables)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-unavoidable_docs}"
DB_USER="${DB_USER:-unavoidable_docs_user}"
DB_PASSWORD="${DB_PASSWORD:-}"

# PostgreSQL connection string
export PGPASSWORD="$DB_PASSWORD"
PSQL="psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -t -A"

echo -e "${BOLD}🚨 UNAVOIDABLE DOCUMENTATION SYSTEM - COMMIT CHECK${NC}"
echo "=================================================="

# Function to check database connectivity
check_database() {
    if ! $PSQL -c "SELECT 1" >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Warning: Could not connect to documentation database${NC}"
        echo "Documentation enforcement is temporarily disabled."
        echo "Please ensure the documentation system is running."
        exit 0  # Allow commit but warn
    fi
}

# Function to get documentation debt summary
get_debt_summary() {
    $PSQL -c "
        SELECT 
            COUNT(*) FILTER (WHERE priority = 'critical') as critical,
            COUNT(*) FILTER (WHERE priority = 'high') as high,
            COUNT(*) FILTER (WHERE priority = 'medium') as medium,
            COUNT(*) FILTER (WHERE priority = 'low') as low,
            COUNT(*) FILTER (WHERE hours_old > 24) as overdue,
            COUNT(*) as total
        FROM documentation_debt
        WHERE resolved_at IS NULL
    " | tr '|' ' '
}

# Function to get critical debt items
get_critical_items() {
    $PSQL -c "
        SELECT 
            dd.debt_type || '|' ||
            fds.file_path || '|' ||
            COALESCE(dd.item_name, '') || '|' ||
            dd.hours_old || '|' ||
            dd.priority
        FROM documentation_debt dd
        JOIN file_documentation_status fds ON dd.file_id = fds.id
        WHERE dd.resolved_at IS NULL
        AND (dd.priority = 'critical' OR dd.hours_old > 24 OR dd.is_blocking = TRUE)
        ORDER BY 
            CASE dd.priority 
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            dd.hours_old DESC
        LIMIT 10
    "
}

# Function to get undocumented constants
get_undocumented_constants() {
    $PSQL -c "
        SELECT COUNT(*)
        FROM undocumented_constants
        WHERE documented_at IS NULL
        AND confidence_score >= 0.8
    "
}

# Function to check files being committed for documentation
check_staged_files() {
    local undocumented_count=0
    
    # Get list of staged files
    staged_files=$(git diff --cached --name-only --diff-filter=ACM)
    
    for file in $staged_files; do
        # Skip non-code files
        if [[ ! "$file" =~ \.(py|js|ts|jsx|tsx|java|go|rs|cpp|c|h|rb|php|sql)$ ]]; then
            continue
        fi
        
        # Check if file is documented in database
        doc_status=$($PSQL -c "
            SELECT status
            FROM file_documentation_status
            WHERE file_path = '$PWD/$file'
        " 2>/dev/null)
        
        if [ "$doc_status" = "undocumented" ] || [ "$doc_status" = "outdated" ]; then
            echo -e "${YELLOW}📄 $file - ${RED}$doc_status${NC}"
            ((undocumented_count++))
        fi
    done
    
    return $undocumented_count
}

# Main enforcement logic
main() {
    # Check database connectivity
    check_database
    
    # Get debt summary
    read critical high medium low overdue total <<< $(get_debt_summary)
    
    echo -e "\n${BOLD}📊 Documentation Debt Summary${NC}"
    echo "--------------------------------"
    
    if [ "$total" -eq 0 ]; then
        echo -e "${GREEN}✅ No documentation debt! Commit allowed.${NC}"
        exit 0
    fi
    
    # Display debt summary
    echo -e "Total debt items: ${BOLD}$total${NC}"
    if [ "$critical" -gt 0 ]; then
        echo -e "  ${RED}● Critical: $critical${NC}"
    fi
    if [ "$high" -gt 0 ]; then
        echo -e "  ${YELLOW}● High: $high${NC}"
    fi
    if [ "$medium" -gt 0 ]; then
        echo -e "  ${CYAN}● Medium: $medium${NC}"
    fi
    if [ "$low" -gt 0 ]; then
        echo -e "  ● Low: $low${NC}"
    fi
    if [ "$overdue" -gt 0 ]; then
        echo -e "  ${RED}⏰ Overdue (>24h): $overdue${NC}"
    fi
    
    # Check for undocumented constants
    const_count=$(get_undocumented_constants)
    if [ "$const_count" -gt 0 ]; then
        echo -e "  ${YELLOW}🔤 Undocumented constants: $const_count${NC}"
    fi
    
    # Check staged files
    echo -e "\n${BOLD}📝 Checking staged files...${NC}"
    check_staged_files
    undocumented_staged=$?
    
    if [ $undocumented_staged -gt 0 ]; then
        echo -e "${RED}Found $undocumented_staged undocumented/outdated files in commit${NC}"
    fi
    
    # Enforcement decision
    echo -e "\n${BOLD}🔒 Enforcement Decision${NC}"
    echo "--------------------------------"
    
    # CRITICAL: Block if any critical debt or overdue items
    if [ "$critical" -gt 0 ] || [ "$overdue" -gt 0 ]; then
        echo -e "${RED}${BOLD}❌ COMMIT BLOCKED: Critical documentation debt exists${NC}"
        echo -e "\n${BOLD}Critical items that MUST be documented:${NC}"
        
        # Show critical items
        get_critical_items | while IFS='|' read -r debt_type file_path item_name hours_old priority; do
            echo -e "${RED}  • ${debt_type} in ${file_path##*/}${NC}"
            if [ -n "$item_name" ]; then
                echo -e "    Item: ${item_name}"
            fi
            echo -e "    Age: ${hours_old} hours | Priority: ${priority}"
        done
        
        echo -e "\n${BOLD}To resolve this:${NC}"
        echo "1. Run: ./unavoidable-docs/tools/resolve_debt.py"
        echo "2. Or use Claude Code: 'Please resolve all critical documentation debt'"
        echo "3. Document all critical items listed above"
        echo ""
        echo -e "${YELLOW}Alternative: Use --no-verify to skip (NOT RECOMMENDED)${NC}"
        
        # Create enforcement block entry
        $PSQL -c "
            INSERT INTO enforcement_blocks 
            (operation_type, operation_details, debt_count, critical_debt_count, oldest_debt_hours)
            VALUES ('commit', 'Pre-commit hook blocked due to critical debt', $total, $critical, 
                    (SELECT MAX(hours_old) FROM documentation_debt WHERE resolved_at IS NULL))
        " >/dev/null 2>&1
        
        exit 1
    fi
    
    # HIGH: Strong warning but allow with confirmation
    if [ "$high" -gt 0 ] || [ $undocumented_staged -gt 0 ]; then
        echo -e "${YELLOW}⚠️  WARNING: High priority documentation debt exists${NC}"
        echo -e "High priority items: $high"
        echo -e "Undocumented files in commit: $undocumented_staged"
        echo ""
        echo -e "${BOLD}It is STRONGLY recommended to document before committing.${NC}"
        echo ""
        
        # Interactive prompt (if terminal is available)
        if [ -t 0 ]; then
            read -p "Do you want to proceed anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${GREEN}Good choice! Please document before committing.${NC}"
                exit 1
            else
                echo -e "${YELLOW}Proceeding with undocumented code (not recommended)${NC}"
                
                # Log the skip
                $PSQL -c "
                    UPDATE documentation_debt
                    SET resolution_attempts = resolution_attempts + 1
                    WHERE resolved_at IS NULL AND priority = 'high'
                " >/dev/null 2>&1
            fi
        else
            echo -e "${YELLOW}Non-interactive mode: allowing commit with warnings${NC}"
        fi
    fi
    
    # MEDIUM/LOW: Information only
    if [ "$medium" -gt 0 ] || [ "$low" -gt 0 ]; then
        echo -e "${CYAN}ℹ️  Info: You have $medium medium and $low low priority documentation items${NC}"
        echo "Consider documenting these soon to maintain code quality."
    fi
    
    echo -e "\n${GREEN}✅ Commit allowed${NC}"
}

# Function to install the hook
install_hook() {
    HOOK_PATH=".git/hooks/pre-commit"
    
    if [ ! -d ".git" ]; then
        echo -e "${RED}Error: Not in a git repository${NC}"
        exit 1
    fi
    
    # Backup existing hook if present
    if [ -f "$HOOK_PATH" ]; then
        cp "$HOOK_PATH" "${HOOK_PATH}.backup"
        echo -e "${YELLOW}Backed up existing hook to ${HOOK_PATH}.backup${NC}"
    fi
    
    # Copy this script to hooks directory
    cp "$0" "$HOOK_PATH"
    chmod +x "$HOOK_PATH"
    
    echo -e "${GREEN}✅ Pre-commit hook installed successfully!${NC}"
    echo "The hook will now enforce documentation on every commit."
}

# Check if being run with --install flag
if [ "$1" = "--install" ]; then
    install_hook
    exit 0
fi

# Run main enforcement
main