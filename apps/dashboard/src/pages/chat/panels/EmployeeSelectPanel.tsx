import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import type { ChatEmployeeSummary } from "../../../api/chat";
import { cn } from "@/lib/utils";

export function EmployeeSelectPanel({
  className,
  employees,
  selectedEmployee,
  onSelect,
}: {
  className?: string;
  employees: ChatEmployeeSummary[];
  selectedEmployee: ChatEmployeeSummary | null;
  onSelect: (employeeId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return employees;
    const q = query.toLowerCase();
    return employees.filter(
      (employee) => (
        employee.display_name.toLowerCase().includes(q)
        || employee.id.toLowerCase().includes(q)
        || employee.role.toLowerCase().includes(q)
      ),
    );
  }, [employees, query]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const initial = selectedEmployee?.display_name.charAt(0) ?? "?";

  return (
    <div ref={ref} className={cn("relative", className ?? "px-3 py-2 border-b")}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex h-full min-h-9 w-full items-center gap-2 rounded-md px-2 text-sm transition-colors hover:bg-muted"
      >
        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
          {initial}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <div className="truncate text-xs font-medium">{selectedEmployee?.display_name ?? "Select employee"}</div>
        </div>
        <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-2 right-2 top-full z-50 mt-1 rounded-md border bg-popover shadow-md">
          <div className="flex items-center gap-2 border-b px-2 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search employees..."
              className="h-6 w-full bg-transparent text-xs outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="max-h-48 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted-foreground">No employees found.</p>
            ) : (
              filtered.map((employee) => {
                const isActive = employee.id === selectedEmployee?.id;
                return (
                  <button
                    key={employee.id}
                    type="button"
                    onClick={() => {
                      onSelect(employee.id);
                      setOpen(false);
                      setQuery("");
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-1.5 text-sm transition-colors",
                      isActive ? "bg-primary/10 text-foreground font-medium" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <div className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                      isActive ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                    )}>
                      {employee.display_name.charAt(0)}
                    </div>
                    <div className="min-w-0 flex-1 text-left">
                      <span className="block truncate">{employee.display_name}</span>
                    </div>
                    <span className="shrink-0 text-[10px] text-muted-foreground">{employee.role}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
