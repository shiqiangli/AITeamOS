# Connector Reference Templates

Connector examples are package templates, not product catalog entries. They show
how an external package can expose an `aiteamos.connectors` entry point, ship a
`ConnectorAdapter`, and include hermetic fixtures that `workspace validate` can
run without provider credentials or network calls.

- `slack-notification/`: minimal chat notification adapter template.
