# Slack Notification Connector Template

This template is a minimal third-party connector package. It demonstrates the
contract required by FG-10:

- expose a package descriptor through `[project.entry-points."aiteamos.connectors"]`;
- implement a `ConnectorAdapter`;
- ship at least one signed sample webhook fixture with an expected normalized
  summary;
- keep secrets out of fixture results, logs, manifests, and dashboard payloads.

Installable shape:

```toml
[project.entry-points."aiteamos.connectors"]
slack_notification = "aiteamos_slack_notification_connector:connector_package"
```

The sample fixture uses fake Slack-style headers and payload fields. It is
hermetic and never calls Slack.
