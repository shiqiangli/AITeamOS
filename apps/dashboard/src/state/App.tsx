/**
 * AITeamOS Dashboard — App Shell (file-first P0)
 */

import { useEffect, useState } from "react";
import { parseHash, navigateTo, NAV_ITEMS, type RouteState } from "../components/shared";
import { Toaster } from "../components/ui/toaster";
import { cn } from "@/lib/utils";
import { ChatPage } from "../pages/chat";
import { KnowledgePage } from "../pages/knowledge";
import { MembersPage } from "../pages/members";
import { SettingsPage } from "../pages/settings";
import { SkillsPage } from "../pages/skills";
import { WorkPage } from "../pages/work";

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <h2 className="text-2xl font-semibold text-foreground mb-2">Page not found</h2>
      <p className="text-muted-foreground mb-4">The page you are looking for does not exist.</p>
      <button
        className="text-primary underline"
        onClick={() => navigateTo("chat")}
      >
        Go to Chat
      </button>
    </div>
  );
}

function PageBody({ route }: { route: RouteState }) {
  switch (route.page) {
    case "chat":
      return <ChatPage />;
    case "work":
      return <WorkPage selectedSection={route.id} />;
    case "members":
      return <MembersPage selectedId={route.id} />;
    case "skills":
      return <SkillsPage selectedId={route.id} />;
    case "knowledge":
      return <KnowledgePage selectedSection={route.id} />;
    case "memory":
      return <KnowledgePage selectedSection="memories" />;
    case "settings":
      return <SettingsPage selectedSection={route.id} />;
    default:
      return <NotFoundPage />;
  }
}

export function App() {
  const [route, setRoute] = useState<RouteState>(parseHash);

  useEffect(() => {
    function onHashChange() {
      setRoute(parseHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const currentPage = NAV_ITEMS.find((n) => n.key === (route.page === "memory" ? "knowledge" : route.page));

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r bg-sidebar">
        {/* Brand */}
        <div className="flex items-center gap-3 border-b px-6 py-5">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-lg">
            AI
          </div>
          <div>
            <h1 className="font-semibold text-sidebar-foreground">AITeamOS</h1>
            <p className="text-xs text-muted-foreground">Team OS</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 p-4">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = route.page === item.key;
            return (
              <div key={item.key}>
                <button
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    "hover:bg-accent hover:text-accent-foreground",
                    isActive
                      ? "bg-accent text-accent-foreground border-l-2 border-primary"
                      : "text-muted-foreground"
                  )}
                  onClick={() => navigateTo(item.key, item.children?.[0]?.key)}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
                {item.children && isActive && (
                  <div className="mt-1 space-y-1 pl-7">
                    {item.children.map((child) => {
                      const childActive = route.id === child.key || (!route.id && child.key === item.children?.[0]?.key);
                      return (
                        <button
                          key={child.key}
                          className={cn(
                            "w-full rounded-md px-3 py-1.5 text-left text-xs transition-colors",
                            childActive
                              ? "bg-background text-foreground"
                              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                          )}
                          onClick={() => navigateTo(item.key, child.key)}
                        >
                          {child.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Version */}
        <div className="border-t px-6 py-3 text-xs text-muted-foreground">
          v1.0.0
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {/* Top bar */}
        <header className="border-b bg-card px-8 py-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wide">
            Dashboard
          </p>
          <h2 className="text-2xl font-semibold text-foreground">
            {currentPage?.label ?? "Not Found"}
          </h2>
        </header>

        {/* Page content */}
        <div className="p-8">
          <PageBody route={route} />
        </div>
      </main>

      {/* Toast notifications */}
      <Toaster />
    </div>
  );
}
