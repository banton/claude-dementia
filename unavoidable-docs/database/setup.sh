#!/bin/bash

# Database setup script for Unavoidable Documentation System
# This script creates the database and runs the schema

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== UNAVOIDABLE DOCS DATABASE SETUP ===${NC}"

# Default values
DB_NAME=${DB_NAME:-"unavoidable_docs"}
DB_USER=${DB_USER:-"unavoidable_docs_user"}
DB_PASSWORD=${DB_PASSWORD:-"docs_pass_123"}
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}

# Check if PostgreSQL is running
if ! pg_isready -h $DB_HOST -p $DB_PORT > /dev/null 2>&1; then
    echo -e "${RED}Error: PostgreSQL is not running on $DB_HOST:$DB_PORT${NC}"
    echo "Please start PostgreSQL first"
    exit 1
fi

echo -e "${GREEN}✓ PostgreSQL is running${NC}"

# Create database if it doesn't exist
echo "Creating database '$DB_NAME' if it doesn't exist..."
psql -h $DB_HOST -p $DB_PORT -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
psql -h $DB_HOST -p $DB_PORT -U postgres -c "CREATE DATABASE $DB_NAME"

echo -e "${GREEN}✓ Database '$DB_NAME' ready${NC}"

# Create user if it doesn't exist
echo "Creating user '$DB_USER' if it doesn't exist..."
psql -h $DB_HOST -p $DB_PORT -U postgres -tc "SELECT 1 FROM pg_user WHERE usename = '$DB_USER'" | grep -q 1 || \
psql -h $DB_HOST -p $DB_PORT -U postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD'"

echo -e "${GREEN}✓ User '$DB_USER' ready${NC}"

# Grant privileges
echo "Granting privileges..."
psql -h $DB_HOST -p $DB_PORT -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER"

echo -e "${GREEN}✓ Privileges granted${NC}"

# Run schema
echo "Running schema..."
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f schema.sql

echo -e "${GREEN}✓ Schema created${NC}"

# Create .env file if it doesn't exist
if [ ! -f "../.env" ]; then
    echo "Creating .env file..."
    cat > ../.env << EOF
# Database Configuration
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT

# Connection string
DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME
EOF
    echo -e "${GREEN}✓ .env file created${NC}"
else
    echo -e "${YELLOW}! .env file already exists, skipping${NC}"
fi

echo -e "${GREEN}=== DATABASE SETUP COMPLETE ===${NC}"
echo ""
echo "Database connection details:"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"