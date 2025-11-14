# AI-Trader Developer Guide

## Table of Contents
1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Running Tests](#running-tests)
4. [Debugging](#debugging)
5. [Code Quality](#code-quality)
6. [Performance Optimization](#performance-optimization)
7. [Common Issues](#common-issues)
8. [Contributing](#contributing)

---

## Development Setup

### Prerequisites
- Python 3.9 or higher
- pip package manager
- Git
- API keys for:
  - OpenAI (or other LLM providers)
  - Alpha Vantage (for stock data)
  - Jina AI (for market search)

### Initial Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd AI-Trader
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

   Required variables:
   ```
   OPENAI_API_KEY=your_key_here
   ALPHAVANTAGE_API_KEY=your_key_here
   JINA_API_KEY=your_key_here

   # Optional
   LOG_LEVEL=INFO
   LOG_TO_FILE=false
   ```

5. **Verify installation:**
   ```bash
   python -c "import langchain, fastmcp; print('Setup successful!')"
   ```

---

## Project Structure

```
AI-Trader/
├── agent/                    # AI Agent Core
│   └── base_agent/
│       └── base_agent.py     # Main trading agent logic
│
├── agent_tools/              # MCP Tool Services
│   ├── tool_trade.py         # Buy/sell operations
│   ├── tool_get_price_local.py  # Price data retrieval
│   ├── tool_jina_search.py   # Market info search
│   └── tool_math.py          # Math operations
│
├── tools/                    # Utility Modules
│   ├── general_tools.py      # Config utilities
│   ├── price_tools.py        # Price data processing
│   ├── result_tools.py       # Performance metrics
│   ├── logging_config.py     # Logging setup
│   └── price_cache.py        # Price data caching
│
├── prompts/                  # AI Prompts
│   └── agent_prompt.py
│
├── configs/                  # Configuration
│   └── default_config.json
│
├── data/                     # Data Storage
│   ├── merged.jsonl          # Consolidated price data
│   ├── daily_prices_*.json   # Individual stock files
│   └── agent_data/           # Agent trading records
│
├── tests/                    # Test Suite
│   ├── conftest.py           # Test fixtures
│   ├── test_validation.py    # Validation tests
│   ├── test_price_tools.py   # Price tools tests
│   └── test_logging_config.py # Logging tests
│
├── docs/                     # Frontend Dashboard
│   └── index.html
│
├── main.py                   # Entry point
├── requirements.txt          # Dependencies
├── pytest.ini                # Pytest configuration
├── mypy.ini                  # Type checking config
└── .gitignore                # Git ignore rules
```

---

## Running Tests

### Run All Tests
```bash
pytest
```

### Run with Coverage
```bash
pytest --cov=. --cov-report=html
# Open htmlcov/index.html to view coverage report
```

### Run Specific Test Files
```bash
pytest tests/test_validation.py
pytest tests/test_price_tools.py -v
```

### Run Tests by Marker
```bash
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m "not slow"    # Skip slow tests
```

### Run Tests in Parallel
```bash
pip install pytest-xdist
pytest -n auto
```

---

## Debugging

### Enable Debug Logging
Set environment variable:
```bash
export LOG_LEVEL=DEBUG
python main.py
```

Or in `.env`:
```
LOG_LEVEL=DEBUG
LOG_TO_FILE=true
```

Logs will be saved to `logs/ai_trader_YYYYMMDD.log`

### Debugging Trading Logic

1. **Check position history:**
   ```bash
   cat data/agent_data/{model-name}/position/position.jsonl | jq .
   ```

2. **Verify price data:**
   ```python
   from tools.price_tools import get_open_prices
   prices = get_open_prices("2025-10-28", ["AAPL", "MSFT"])
   print(prices)
   ```

3. **Test trade validation:**
   ```python
   from agent_tools.tool_trade import validate_trade_inputs
   result = validate_trade_inputs("AAPL", 10, "buy")
   print(result)  # Should be None for valid inputs
   ```

### Debugging Look-Ahead Bias

The system includes anti-look-ahead validation. To test:

```python
from tools.price_tools import validate_no_look_ahead

# Set TODAY_DATE environment variable
os.environ["TODAY_DATE"] = "2025-10-28"

# This should raise ValueError
validate_no_look_ahead("2025-10-29", "test")
```

### Common Debugging Commands

```bash
# Check if MCP services are running
ps aux | grep mcp

# View real-time logs
tail -f logs/ai_trader_*.log

# Validate configuration
python -c "from tools.general_tools import get_config_value; print(get_config_value('TODAY_DATE'))"

# Test price cache
python -c "from tools.price_cache import get_global_cache; cache = get_global_cache(); print(cache.get_stats())"
```

---

## Code Quality

### Linting with flake8
```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --max-complexity=10 --max-line-length=127 --statistics
```

### Code Formatting with black
```bash
# Check formatting
black --check .

# Auto-format code
black .
```

### Import Sorting with isort
```bash
# Check import order
isort --check-only --diff .

# Fix import order
isort .
```

### Type Checking with mypy
```bash
mypy --install-types --non-interactive .
```

### Run All Quality Checks
```bash
./scripts/quality_check.sh  # If you create this script
```

Or manually:
```bash
black . && isort . && flake8 . && mypy . && pytest
```

---

## Performance Optimization

### Use Price Cache

Instead of scanning merged.jsonl repeatedly:

**Before (slow):**
```python
from tools.price_tools import get_open_prices

for date in dates:
    prices = get_open_prices(date, symbols)  # O(n) scan each time
```

**After (fast):**
```python
from tools.price_cache import get_global_cache

cache = get_global_cache()  # Load once
for date in dates:
    prices = {
        f"{sym}_price": cache.get_price(sym, date)
        for sym in symbols
    }  # O(1) lookup
```

### Cache Statistics

```python
from tools.price_cache import get_global_cache

cache = get_global_cache()
stats = cache.get_stats()
print(f"Loaded {stats['symbols_count']} symbols")
print(f"Total entries: {stats['total_price_entries']}")
```

### Profiling

```bash
# Profile main.py
python -m cProfile -o profile.stats main.py

# View profile
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumtime'); p.print_stats(20)"
```

---

## Common Issues

### Issue: "SIGNATURE environment variable is not set"

**Solution:**
```bash
export SIGNATURE=gpt-5
# Or set in .runtime_env.json
```

### Issue: "Look-ahead bias detected"

**Cause:** Trying to access future price data.

**Solution:** Ensure `TODAY_DATE` is set correctly and not requesting data from future dates.

### Issue: "Insufficient cash" errors in tests

**Cause:** Position file not initialized properly.

**Solution:**
```bash
# Reset position for test model
rm -rf data/agent_data/test-model/
python tools/price_tools.py  # Reinitialize
```

### Issue: Tests failing with import errors

**Solution:**
```bash
# Ensure project root is in PYTHONPATH
export PYTHONPATH=$PWD:$PYTHONPATH
pytest
```

### Issue: MCP services not starting

**Solution:**
```bash
# Check ports are available
lsof -i :8000-8003

# Kill existing processes
pkill -f "mcp"

# Restart services
python agent_tools/start_mcp_services.py
```

---

## Contributing

### Before Submitting a PR

1. **Run all tests:**
   ```bash
   pytest
   ```

2. **Check code quality:**
   ```bash
   black --check .
   flake8 .
   mypy .
   ```

3. **Update tests:** Add tests for new features

4. **Update documentation:** Update README or this guide if needed

### Commit Message Format

```
type(scope): subject

body (optional)

footer (optional)
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `test`: Adding tests
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `chore`: Maintenance

Example:
```
feat(validation): add input validation for trade amounts

- Validate amount > 0
- Validate symbol in NASDAQ 100
- Add comprehensive error messages

Closes #123
```

### Pull Request Checklist

- [ ] Tests pass locally
- [ ] Code follows style guide (black, flake8)
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] No secrets or API keys committed
- [ ] Branch is up to date with main

---

## Additional Resources

- [LangChain Documentation](https://python.langchain.com/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Pytest Documentation](https://docs.pytest.org/)
- [Project README](README.md)
- [Configuration Guide](configs/README.md)

---

## Getting Help

- **Issues:** Open a GitHub issue
- **Questions:** Check existing issues or open a discussion
- **Security:** Report security issues privately to maintainers

---

**Last Updated:** 2025-11-13
