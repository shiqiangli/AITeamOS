import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, MessageSquare, Users } from "lucide-react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  ErrorState,
  LoadingState,
  Status,
  navigateTo,
} from "../../components/shared";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { listChatMembers, type ChatMemberSummary } from "../../api/chat";
import { cn } from "@/lib/utils";

export function MembersPage({ selectedId }: { selectedId: string | null }) {
  const [members, setMembers] = useState<ChatMemberSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setMembers(await listChatMembers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load members");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const selectedMember = useMemo(() => {
    return members.find((member) => member.id === selectedId) ?? members[0] ?? null;
  }, [members, selectedId]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={loadMembers} />;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="rounded-md border bg-background">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">Members</h3>
          </div>
          <Button type="button" variant="outline" onClick={() => navigateTo("chat")}>
            <MessageSquare className="h-4 w-4" />
            Ask in Chat
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Runtime</TableHead>
              <TableHead className="text-right">Skills</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {members.map((member) => {
              const active = selectedMember?.id === member.id;
              return (
                <TableRow
                  key={member.id}
                  className={cn("cursor-pointer", active && "bg-muted/60")}
                  onClick={() => navigateTo("members", member.id)}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Bot className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <div className="font-medium">{member.display_name}</div>
                        <div className="text-xs text-muted-foreground">{member.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{member.role}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{member.runtime_mode}</Badge>
                  </TableCell>
                  <TableCell className="text-right">{member.skills.length}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </section>

      <aside className="space-y-4">
        {selectedMember ? (
          <>
            <section className="rounded-md border bg-background p-4">
              <div className="mb-3 flex items-center gap-2">
                <Bot className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">{selectedMember.display_name}</h3>
              </div>
              <div className="space-y-3">
                <Status label="Role" value={selectedMember.role} />
                <Status label="Runtime" value={selectedMember.runtime_mode} />
                <Status label="Skills" value={selectedMember.skills.length} />
              </div>
            </section>

            <section className="rounded-md border bg-background p-4">
              <h3 className="mb-3 text-sm font-semibold">Summary</h3>
              <p className="text-sm leading-6 text-muted-foreground">
                {selectedMember.summary || "No summary configured."}
              </p>
            </section>

            <section className="rounded-md border bg-background p-4">
              <h3 className="mb-3 text-sm font-semibold">Skills</h3>
              {selectedMember.skills.length ? (
                <div className="flex flex-wrap gap-2">
                  {selectedMember.skills.map((skill) => (
                    <Badge key={skill} variant="secondary">
                      {skill}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No skills assigned.</p>
              )}
            </section>
          </>
        ) : (
          <section className="rounded-md border bg-background p-4">
            <p className="text-sm text-muted-foreground">No members configured.</p>
          </section>
        )}
      </aside>
    </div>
  );
}

