/**
 * AITeamOS Dashboard — App Shell (file-first P0)
 */

import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { parseHash, navigateTo, NAV_ITEMS, type RouteState } from "../components/shared";
import { Toaster } from "../components/ui/toaster";
import { Button } from "../components/ui/button";
import { cn } from "@/lib/utils";
import { ChatPage } from "../pages/chat";
import { AssetsPage } from "../pages/assets";
import { EmployeesPage } from "../pages/employees";
import { SettingsPage } from "../pages/settings";
import { TicketsPage } from "../pages/tickets";

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
    case "tickets":
      return <TicketsPage selectedSection={route.id} />;
    case "employees":
      return <EmployeesPage selectedId={route.id} />;
    case "assets":
      return <AssetsPage selectedArea={route.id} selectedDetail={route.detail} />;
    case "skills":
      return <AssetsPage selectedArea="skills" selectedDetail={route.id} />;
    case "knowledge":
      return <AssetsPage selectedArea="knowledge" selectedDetail={route.id} />;
    case "memory":
      return <AssetsPage selectedArea="knowledge" selectedDetail="memories" />;
    case "capabilities":
      return <AssetsPage selectedArea="capabilities" />;
    case "settings":
      return <SettingsPage selectedSection={route.id} />;
    default:
      return <NotFoundPage />;
  }
}

export function App() {
  const [route, setRoute] = useState<RouteState>(parseHash);
  const [navOpen, setNavOpen] = useState(true);

  useEffect(() => {
    function onHashChange() {
      setRoute(parseHash());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navPage = ["skills", "knowledge", "memory", "capabilities"].includes(route.page) ? "assets" : route.page;

  return (
    <div className="h-screen bg-background">
      <div className="flex h-full min-w-0">
        {/* Sidebar */}
        <aside className={cn(
          "relative flex h-full shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200",
          navOpen ? "w-44" : "w-14",
        )}>
          {/* Brand */}
          <div className={cn(
            "flex min-h-16 items-center border-b py-3",
            navOpen ? "gap-2 px-2.5" : "justify-center px-2",
          )}>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
              AI
            </div>
            {navOpen && (
              <div className="min-w-0 flex-1">
                <h1 className="truncate font-semibold text-sidebar-foreground">AITeamOS</h1>
                <p className="truncate text-xs text-muted-foreground">Team OS</p>
              </div>
            )}
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="absolute right-[-0.75rem] top-5 z-20 h-6 w-6 rounded-md bg-background p-0 shadow-sm"
            onClick={() => setNavOpen((open) => !open)}
            title={navOpen ? "Collapse navigation" : "Expand navigation"}
          >
            {navOpen ? <PanelLeftClose className="h-3.5 w-3.5" /> : <PanelLeftOpen className="h-3.5 w-3.5" />}
          </Button>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 overflow-y-auto p-2">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = navPage === item.key;
              return (
                <div key={item.key}>
                  <button
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center rounded-md text-sm font-medium transition-colors",
                      "hover:bg-accent hover:text-accent-foreground",
                      navOpen ? "gap-2 px-2 py-2" : "justify-center px-0 py-2",
                      isActive
                        ? "bg-accent text-accent-foreground border-l-2 border-primary"
                        : "text-muted-foreground"
                    )}
                    onClick={() => navigateTo(item.key, item.children?.[0]?.key)}
                    title={item.label}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {navOpen && <span className="truncate">{item.label}</span>}
                  </button>
                  {navOpen && item.children && isActive && (
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
                            <span className="block truncate">{child.label}</span>
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
          <div className={cn("border-t py-3 text-xs text-muted-foreground", navOpen ? "px-3" : "px-2 text-center")}>
            v1.0.0
          </div>
        </aside>

        {/* Main content */}
        <main className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
          {/* Page content */}
          <div className="flex-1 overflow-auto p-6">
            <PageBody route={route} />
          </div>
        </main>
      </div>

      {/* Toast notifications */}
      <Toaster />
    </div>
  );
}
