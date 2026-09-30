#!/bin/bash
# Setup script for first-time developers
# Usage: ./scripts/setup.sh

set -e

echo "🚀 Setting up Agentic AI Database Migration Platform"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check prerequisites
echo "${BLUE}📋 Checking prerequisites...${NC}"

# Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.11+${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"

# Poetry
if ! command -v poetry &> /dev/null; then
    echo -e "${YELLOW}⚠ Poetry not found. Installing...${NC}"
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "${GREEN}✓ Poetry $(poetry --version | awk '{print $3}') found${NC}"

# Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker Desktop${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker $(docker --version | awk '{print $3}') found${NC}"

# Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose $(docker-compose --version | awk '{print $3}') found${NC}"

echo ""
echo "${BLUE}🔧 Installing Python dependencies...${NC}"
poetry install --no-interaction

echo ""
echo "${BLUE}🐳 Starting Docker services...${NC}"
docker-compose up -d

echo ""
echo "${BLUE}⏳ Waiting for services to become healthy...${NC}"
echo "  (This may take 30-60 seconds, Oracle may take 5-10 minutes)"
echo ""

# Function to check if service is healthy
check_health() {
    local service=$1
    local max_attempts=60
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose ps $service | grep -q "healthy\|up"; then
            return 0
        fi
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    return 1
}

# Check PostgreSQL metadata
echo -n "  Waiting for PostgreSQL metadata..."
if check_health "postgres-metadata"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${YELLOW}⚠ Taking longer than expected${NC}"
fi

# Check PostgreSQL sample
echo -n "  Waiting for PostgreSQL sample..."
if check_health "postgres-sample"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${YELLOW}⚠ Taking longer than expected${NC}"
fi

# Check MySQL
echo -n "  Waiting for MySQL sample..."
if check_health "mysql-sample"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${YELLOW}⚠ Taking longer than expected${NC}"
fi

# Oracle may take longer
echo ""
echo -n "  Waiting for Oracle sample (this may take 5-10 minutes)..."
if check_health "oracle-sample"; then
    echo -e " ${GREEN}✓${NC}"
else
    echo -e " ${YELLOW}⚠ Still initializing (check back later with: docker-compose logs oracle-sample)${NC}"
fi

echo ""
echo "${BLUE}🔐 Setting up environment file...${NC}"
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "Creating .env from .env.example"
        cp .env.example .env
        echo -e "${YELLOW}⚠ Please edit .env with your AWS credentials${NC}"
    fi
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

echo ""
echo "${BLUE}🪝 Setting up pre-commit hooks...${NC}"
pre-commit install
echo -e "${GREEN}✓ Pre-commit hooks installed${NC}"

echo ""
echo "${BLUE}🧪 Running basic tests...${NC}"
if poetry run pytest tests/unit/ -v --tb=short 2>&1 | head -20; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
else
    echo -e "${YELLOW}⚠ Some tests may be failing (check full output)${NC}"
fi

echo ""
echo "========================"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo "========================"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your AWS credentials (if needed)"
echo "  2. Test database connections:"
echo "     poetry run python scripts/test_connections.py"
echo "  3. Start the API:"
echo "     cd apps/api-fastapi && poetry run uvicorn main:app --reload"
echo "  4. In another terminal, start the UI:"
echo "     cd apps/ui-streamlit && poetry run streamlit run app.py"
echo ""
echo "For more information, see:"
echo "  - README.md (quick start)"
echo "  - DEVELOPMENT.md (detailed guide)"
echo ""
