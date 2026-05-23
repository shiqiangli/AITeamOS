# Protocol Fixture

This directory is a protocol test fixture for AITEAMOS. It models a small
protocol-shaped workspace with digital, human, hybrid, and service TeamMembers
working through assignments, tasks, runs, reviews, memory promotion, handoff,
automation, permissions, and Git activity.

The embedded `.aiteamos` directory is intentionally safe to track. It contains only
synthetic compiler examples and no private workspace data. It is retained for
schema, loader, API, dashboard, and browser replay regression tests; it is not a
product example and should not appear in product-facing workspace catalogs.

Useful checks:

```bash
./aiteamos workspace validate --workspace examples/protocol-fixture/.aiteamos
PYTHONPATH=examples/protocol-fixture python -m unittest discover examples/protocol-fixture/tests -q
PYTHONPATH=packages/schema:packages/workspace:services/api:. python -m unittest tests.test_example_workspace -q
```
