from __future__ import annotations

from pathlib import Path
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import (
    TRACE_COMPONENTS,
    is_valid_traceparent,
    new_trace_context,
    run_trace_context,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / ".aiteamos"
PARENT_TRACEPARENT = "00-11111111111111111111111111111111-2222222222222222-01"


class ObservabilityTracingTest(unittest.TestCase):
    def test_http_middleware_propagates_w3c_trace_context(self) -> None:
        response = TestClient(create_app(WORKSPACE)).get(
            "/health",
            headers={"traceparent": PARENT_TRACEPARENT},
        )

        self.assertEqual(response.status_code, 200)
        response_traceparent = response.headers["traceparent"]
        self.assertTrue(is_valid_traceparent(response_traceparent))
        self.assertTrue(response_traceparent.startswith("00-11111111111111111111111111111111-"))
        self.assertNotEqual(response_traceparent.split("-")[2], "2222222222222222")
        self.assertEqual(response.headers["x-aiteamos-trace-id"], "11111111111111111111111111111111")

    def test_run_trace_projection_spans_required_components_and_attributes(self) -> None:
        response = TestClient(create_app(WORKSPACE)).get(
            "/runs/RUN-0001/trace-context",
            headers={"traceparent": PARENT_TRACEPARENT},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["traceparent"], response.headers["traceparent"])
        self.assertEqual(payload["traceId"], "11111111111111111111111111111111")
        self.assertEqual(payload["components"], list(TRACE_COMPONENTS))
        self.assertEqual([span["component"] for span in payload["spans"]], list(TRACE_COMPONENTS))
        self.assertEqual(payload["requiredAttributes"], ["runId", "taskId", "memberId"])
        self.assertEqual(payload["attributes"]["runId"], "RUN-0001")
        self.assertEqual(payload["attributes"]["taskId"], "TASK-20260520T101022277")
        self.assertEqual(payload["attributes"]["memberId"], "architect")
        self.assertEqual(payload["spans"][1]["parentSpanId"], "2222222222222222")
        self.assertEqual(payload["spans"][2]["parentSpanId"], payload["spans"][1]["spanId"])
        self.assertEqual(payload["spans"][3]["parentSpanId"], payload["spans"][2]["spanId"])
        self.assertEqual(payload["spans"][4]["parentSpanId"], payload["spans"][2]["spanId"])

    def test_workspace_trace_helpers_reject_invalid_traceparent(self) -> None:
        self.assertFalse(is_valid_traceparent("not-a-traceparent"))
        context = new_trace_context("not-a-traceparent")
        self.assertTrue(is_valid_traceparent(context["traceparent"]))
        self.assertIsNone(context["parentSpanId"])

        projection = run_trace_context(WORKSPACE, "RUN-0001", parent_traceparent=PARENT_TRACEPARENT)
        self.assertEqual(projection["traceId"], "11111111111111111111111111111111")
        self.assertEqual(projection["attributes"]["runId"], "RUN-0001")


if __name__ == "__main__":
    unittest.main()
