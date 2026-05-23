# Examples

`examples/` is reserved for protocol test fixtures. These workspaces are used by
schema, loader, API, dashboard, and browser replay regression tests. They are not
product examples and must not be shown in product-facing workspace catalogs.

The canonical self-hosting example is the repository-root `.aiteamos/` workspace.

## Fixtures

- `protocol-fixture/`: protocol regression fixture for a neutral compiler-shaped
  workspace. Tests may continue to reference `examples/protocol-fixture/.aiteamos`
  directly so fixture paths stay stable.

## Connector Templates

- `connectors/slack-notification/`: reference third-party connector package
  template. It is tested as protocol guidance and is not a product-facing
  workspace catalog entry.
