/**
 * AITeamOS Dashboard — App Shell
 *
 * Tailwind CSS layout with sidebar navigation and icons.
 */

import { useEffect, useState } from "react";
import { parseHash, navigateTo, NAV_ITEMS, type RouteState } from "../components/shared";
import { Toaster } from "../components/ui/toaster";
import { cn } from "@/lib/utils";
import { HomePage } from "../pages/home";
import { MemoryPage } from "../pages/memory";
import { SkillPage } from "../pages/skills";
import { MemberPage } from "../pages/members";
import { DepartmentPage } from "../pages/manager";
import { ProjectPage } from "../pages/projects";
import { TaskPage } from "../pages/tasks";
import { ReviewPage } from "../pages/reviews";
import { MetricsPage } from "../pages/metrics";

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <h2 className="text-2xl font-semibold text-foreground mb-2">Page not found</h2>
      <p className="text-muted-foreground mb-4">The page you are looking for does not exist.</p>
      <button
        className="text-primary underline"
        onClick={() => navigateTo("home")}
      >
        Go to Home
      </button>
    </div>
  );
}

function PageBody({ route }: { route: RouteState }) {
  switch (route.page) {
    case "home":
      return <HomePage />;
    case "memories":
      return <MemoryPage selectedId={route.id} />;
    case "skills":
      return <SkillPage selectedId={route.id} />;
    case "members":
      return <MemberPage selectedId={route.id} />;
    case "departments":
      return <DepartmentPage selectedId={route.id} />;
    case "projects":
      return <ProjectPage selectedId={route.id} />;
    case "tasks":
      return <TaskPage selectedId={route.id} />;
    case "reviews":
      return <ReviewPage selectedId={route.id} />;
    case "metrics":
      return <MetricsPage />;
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

  const currentPage = NAV_ITEMS.find((n) => n.key === route.page);

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
              <button
                key={item.key}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  "hover:bg-accent hover:text-accent-foreground",
                  isActive
                    ? "bg-accent text-accent-foreground border-l-2 border-primary"
                    : "text-muted-foreground"
                )}
                onClick={() => navigateTo(item.key)}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
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
            {currentPage?.label ?? "Home"}
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
