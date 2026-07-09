import { Bot } from "lucide-react";
import { Badge } from "../../../components/ui/badge";
import type { CapabilityRecord } from "../../../api/capabilities";
import type { ChatEmployeeSummary } from "../../../api/chat";

function capabilityVariant(capability: CapabilityRecord): "success" | "warning" | "secondary" | "outline" {
  if (!capability.configured) return "outline";
  if (capability.status === "ready") return "success";
  if (capability.status === "planned") return "warning";
  return "secondary";
}

export function CurrentEmployeePanel({
  capabilities,
  employee,
  threadCount,
}: {
  capabilities: CapabilityRecord[];
  employee: ChatEmployeeSummary | null;
  threadCount: number;
}) {
  if (!employee) return null;
  return (
    <section className="border-b p-3">
      <div className="mb-2 flex items-center gap-1.5">
        <Bot className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold">Current Employee</h3>
      </div>
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground">Role</span>
          <span className="truncate text-right font-medium">{employee.role}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-muted-foreground">Threads</span>
          <span>{threadCount}</span>
        </div>
        {capabilities.length > 0 && (
          <div>
            <div className="mb-1 mt-2 text-[10px] uppercase text-muted-foreground">Capabilities</div>
            <div className="flex flex-wrap gap-1">
              {capabilities.slice(0, 8).map((capability) => (
                <Badge
                  key={capability.id}
                  variant={capabilityVariant(capability)}
                  className="max-w-full px-1.5 text-[10px]"
                  title={capability.description || capability.id}
                >
                  <span className="truncate">{capability.name}</span>
                </Badge>
              ))}
              {capabilities.length > 8 && (
                <Badge variant="outline" className="px-1.5 text-[10px]">+{capabilities.length - 8}</Badge>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
