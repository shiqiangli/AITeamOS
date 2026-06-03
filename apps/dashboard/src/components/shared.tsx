/**
 * AITeamOS Dashboard — Shared UI Components (file-first P0)
 */

import { type ReactNode, useId } from "react";
import {
  Brain,
  BookOpen,
  MessageSquare,
  Users,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "./ui/card";
import { Badge } from "./ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "./ui/table";
import { Button } from "./ui/button";
import { Skeleton } from "./ui/skeleton";
import { cn } from "@/lib/utils";

// ─── Panel ───────────────────────────────────────────────────────────────────

export function Panel({
  title,
  full,
  children,
}: {
  title?: string;
  full?: boolean;
  children: ReactNode;
}) {
  return (
    <Card className={full ? "col-span-full" : undefined}>
      {title && (
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
      )}
      <CardContent>{children}</CardContent>
    </Card>
  );
}

// ─── Status badge ────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  published: "bg-blue-100 text-blue-800",
  deprecated: "bg-gray-100 text-gray-600",
  draft: "bg-yellow-100 text-yellow-800",
  pending: "bg-orange-100 text-orange-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  running: "bg-cyan-100 text-cyan-800",
};

export function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status.toLowerCase()] ?? "bg-gray-100 text-gray-600";
  return <Badge variant="outline" className={`${color} border-0 capitalize`}>{status}</Badge>;
}

// ─── Key-Value list ──────────────────────────────────────────────────────────

export function KVList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="space-y-2 text-sm">
      {items.map(([label, value]) => (
        <div key={label} className="flex gap-2">
          <dt className="w-36 shrink-0 font-medium text-muted-foreground">{label}</dt>
          <dd className="text-foreground">{value ?? <span className="text-muted-foreground">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────────────

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <h3 className="text-lg font-semibold text-foreground mb-1">{title}</h3>
      {description && <p className="text-sm text-muted-foreground mb-4 max-w-sm">{description}</p>}
      {action}
    </div>
  );
}

// ─── Loading table ───────────────────────────────────────────────────────────

export function LoadingTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {Array.from({ length: cols }).map((_, i) => (
            <TableHead key={i}><Skeleton className="h-4 w-20" /></TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: rows }).map((_, r) => (
          <TableRow key={r}>
            {Array.from({ length: cols }).map((_, c) => (
              <TableCell key={c}><Skeleton className="h-4 w-full" /></TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ─── Section header ──────────────────────────────────────────────────────────

export function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {action}
    </div>
  );
}

// ─── Confirm dialog trigger ─────────────────────────────────────────────────

export function useConfirm() {
  const id = useId();
  return {
    confirmId: id,
    confirm: (message: string) => window.confirm(message),
  };
}

// ─── Router types & helpers ─────────────────────────────────────────────────

export interface RouteState {
  page: string;
  id: string | null;
}

export function parseHash(): RouteState {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts.length === 0) return { page: "chat", id: null };
  return {
    page: parts[0],
    id: parts.length > 1 ? decodeURIComponent(parts[1]) : null,
  };
}

export function navigateTo(page: string, id?: string | null): void {
  const path = id ? `#/${page}/${encodeURIComponent(id)}` : `#/${page}`;
  window.location.hash = path;
}

// ─── Status card ─────────────────────────────────────────────────────────────

export function Status({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "warn";
}) {
  const toneClass =
    tone === "ok"
      ? "text-green-600"
      : tone === "warn"
      ? "text-orange-500"
      : "text-foreground";
  return (
    <div className="rounded-lg border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-2xl font-bold ${toneClass}`}>{value}</p>
    </div>
  );
}

// ─── Loading state ──────────────────────────────────────────────────────────

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mb-3" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

// ─── Error state ─────────────────────────────────────────────────────────────

export function ErrorState({
  message,
  retry,
  onRetry,
}: {
  message: string;
  retry?: () => void;
  onRetry?: () => void;
}) {
  const handleRetry = onRetry ?? retry;
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <h3 className="text-lg font-semibold text-destructive mb-1">Error</h3>
      <p className="text-sm text-muted-foreground mb-4 max-w-sm">{message}</p>
      {handleRetry && (
        <Button variant="outline" onClick={handleRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

// ─── Nav items ───────────────────────────────────────────────────────────────

export interface NavItem {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "chat", label: "Chat", icon: MessageSquare },
  { key: "members", label: "Members", icon: Users },
  { key: "skills", label: "Skills", icon: BookOpen },
  { key: "memory", label: "Memory", icon: Brain },
];
