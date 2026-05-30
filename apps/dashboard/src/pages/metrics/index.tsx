/**
 * AITeamOS Dashboard — Metrics & System Health Page (PRD §3.8)
 */

import { useEffect, useState, useCallback } from "react";
import { Panel, Status, Definition, LoadingState, ErrorState } from "../../components/shared";
import { Button } from "../../components/ui/button";
import {
  fetchValueMetrics,
  fetchSystemHealth,
  fetchMemoryHealth,
  type ValueMetricsResponse,
  type SystemHealthResponse,
  type MemoryHealthResponse,
} from "../../api/client";

export function MetricsPage() {
  const [metrics, setMetrics] = useState<ValueMetricsResponse | null>(null);
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [memoryHealth, setMemoryHealth] = useState<MemoryHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [m, h, mh] = await Promise.all([
        fetchValueMetrics(),
        fetchSystemHealth(),
        fetchMemoryHealth(),
      ]);
      setMetrics(m);
      setHealth(h);
      setMemoryHealth(mh);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  if (loading && !metrics) {
    return <LoadingState />;
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      {error && <ErrorState message={error} />}

      {/* Global Summary */}
      {metrics && (
        <Panel title="System Overview">
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-4">
            <Status label="Memories" value={metrics.memory_total} />
            <Status label="Active" value={metrics.memory_active} tone="ok" />
            <Status label="Candidates" value={metrics.memory_candidates} tone={metrics.memory_candidates > 0 ? "warn" : undefined} />
            <Status label="Skills" value={metrics.skill_count} />
            <Status label="Members" value={metrics.member_count} />
            <Status label="Tasks" value={metrics.task_count} />
            <Status label="Recalls" value={metrics.recall_count} />
            <Status label="Active Rate" value={`${(metrics.memory_active_rate * 100).toFixed(1)}%`} tone={metrics.memory_active_rate > 0.5 ? "ok" : "warn"} />
          </div>
        </Panel>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* System Health */}
        <Panel title="System Health">
          {health ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Status
                  label="Database"
                  value={health.database}
                  tone={health.database === "connected" ? "ok" : "warn"}
                />
                <Status
                  label="Status"
                  value={health.status}
                  tone={health.status === "healthy" ? "ok" : "warn"}
                />
                <Status
                  label="First Pass Rate"
                  value={`${(health.task_first_pass_rate * 100).toFixed(1)}%`}
                  tone={health.task_first_pass_rate > 0.7 ? "ok" : "warn"}
                />
                <Status
                  label="Open Conflicts"
                  value={health.conflicts_open}
                  tone={health.conflicts_open > 0 ? "warn" : "ok"}
                />
              </div>
              <Definition label="Total Memories" value={health.memory_total} />
              <Definition label="Pending Reviews" value={health.reviews_pending} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No system health data</p>
          )}
        </Panel>

        {/* Memory Health */}
        <Panel title="Memory Health">
          {memoryHealth ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Status label="Active" value={memoryHealth.active} tone="ok" />
                <Status label="Candidate" value={memoryHealth.candidate} tone={memoryHealth.candidate > 0 ? "warn" : undefined} />
                <Status label="Needs Verify" value={memoryHealth.needs_verify} tone={memoryHealth.needs_verify > 0 ? "warn" : "ok"} />
                <Status label="Deprecated" value={memoryHealth.deprecated} />
              </div>
              <Definition label="Total Memories" value={memoryHealth.total} />
              <Definition label="Candidate Ratio" value={`${(memoryHealth.candidate_ratio * 100).toFixed(1)}%`} />
              <Definition label="Deprecated Ratio" value={`${(memoryHealth.deprecated_ratio * 100).toFixed(1)}%`} />
              <Definition label="Needs Verify Ratio" value={`${(memoryHealth.needs_verify_ratio * 100).toFixed(1)}%`} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No memory health data</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
