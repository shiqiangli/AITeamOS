# Tests

Unit and integration tests for AITeamOS.

## Running

```bash
# All tests
pytest tests/

# With coverage
pytest tests/ --cov=packages --cov=services

# Integration tests only
pytest tests/integration/

# Single test file
pytest tests/test_knowledge_domain.py
```

## Structure

| File | Coverage |
|------|----------|
| `test_knowledge_*` | Knowledge bounded context |
| `test_capability_*` | Capability bounded context |
| `test_workforce_*` | Workforce bounded context |
| `test_execution_*` | Execution bounded context |
| `test_validation_*` | Validation bounded context |
| `test_governance_*` | Governance bounded context |
| `test_shared_kernel.py` | Shared kernel utilities |
| `integration/` | Cross-context E2E tests |

## Conventions

- Use in-memory repositories (mock DB)
- LLM calls return deterministic mock results
- No external service dependencies
- All tests must pass for Stage completion
