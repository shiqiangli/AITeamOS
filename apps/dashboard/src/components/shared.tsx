/**
 * AITeamOS Dashboard — Shared UI Components
 *
 * Rewritten with Tailwind CSS + shadcn/ui primitives.
 * Same public API as before.
 */

import { type ReactNode, useId } from "react";
import {
  LayoutDashboard,
  Brain,
  Bot,
  Wrench,
  Users,
  Building2,
  FolderKanban,
  ListTodo,
  BarChart3,
  Zap,
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

export function Status({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "warn";
}) {
  const variant = tone === "ok" ? "success" : tone === "warn" ? "warning" : "secondary";
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-muted-foreground">{label}</span>
      <Badge variant={variant}>{value}</Badge>
    </div>
  );
}

// ─── Definition (label + value) ──────────────────────────────────────────────

export function Definition({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground uppercase tracking-wide">
        {label}
      </span>
      <span className="text-sm font-medium">{value ?? "—"}</span>
    </div>
  );
}

// ─── Data Table ──────────────────────────────────────────────────────────────

export interface Column<T> {
  key: string;
  label?: string;
  render?: (row: T) => ReactNode;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function DataTable<T extends Record<string, any>>({
  data,
  columns,
  selectedId,
  onSelect,
}: {
  data: T[];
  columns: Column<T>[];
  selectedId?: string;
  onSelect?: (row: T) => void;
}) {
  if (data.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No records
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          {columns.map((col) => (
            <TableHead key={col.key}>{col.label ?? col.key}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((row, idx) => {
          const id = String(row["id"] ?? idx);
          const isSelected = id === selectedId;
          return (
            <TableRow
              key={id}
              className={cn(
                "cursor-pointer transition-colors",
                isSelected && "bg-muted"
              )}
              onClick={() => onSelect?.(row)}
            >
              {columns.map((col) => (
                <TableCell key={col.key}>
                  {col.render
                    ? col.render(row)
                    : formatCellValue(row[col.key])}
                </TableCell>
              ))}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// ─── Loading / Error states ──────────────────────────────────────────────────

export function LoadingState() {
  return (
    <Card>
      <CardContent className="py-6 space-y-3">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-5/6" />
      </CardContent>
    </Card>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-destructive">
      <CardContent className="py-6 space-y-3">
        <p className="text-sm text-destructive">{message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Form helpers ────────────────────────────────────────────────────────────

export function FormField({
  label,
  children,
  wide,
}: {
  label: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5", wide && "col-span-full")}>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

// ─── ComboInput (select + free text) ─────────────────────────────────────────

export interface ComboOption {
  value: string;
  label: string;
}

export function ComboInput({
  value,
  onChange,
  options,
  placeholder,
  className,
}: {
  value: string;
  onChange: (val: string) => void;
  options: ComboOption[];
  placeholder?: string;
  className?: string;
}) {
  const listId = useId();
  return (
    <>
      <input
        list={listId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={cn(
          "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      />
      <datalist id={listId}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </datalist>
    </>
  );
}

// ─── Hash-based Router ───────────────────────────────────────────────────────

export interface RouteState {
  page: string;
  id: string | null;
}

export function parseHash(): RouteState {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts.length === 0) return { page: "home", id: null };
  return {
    page: parts[0],
    id: parts.length > 1 ? decodeURIComponent(parts[1]) : null,
  };
}

export function navigateTo(page: string, id?: string | null): void {
  const path = id ? `#/${page}/${encodeURIComponent(id)}` : `#/${page}`;
  window.location.hash = path;
}

// ─── Nav items ───────────────────────────────────────────────────────────────

export interface NavItem {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "home", label: "Home", icon: LayoutDashboard },
  { key: "memories", label: "Memories", icon: Brain },
  { key: "skills", label: "Skills", icon: Wrench },
  { key: "agents", label: "API", icon: Bot },
  { key: "members", label: "Members", icon: Users },
  { key: "departments", label: "Departments", icon: Building2 },
  { key: "projects", label: "Projects", icon: FolderKanban },
  { key: "tasks", label: "Tasks", icon: ListTodo },
  { key: "jobs", label: "Jobs", icon: Zap },
  { key: "metrics", label: "Metrics", icon: BarChart3 },
];
