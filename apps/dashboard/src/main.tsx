import { createRoot } from "react-dom/client";
import "./styles.css";
import { App } from "./state/App";

export { App };

export function mountDashboard(rootElement: HTMLElement) {
  const root = createRoot(rootElement);
  root.render(<App />);
  return root;
}

const rootElement = typeof document !== "undefined" ? document.getElementById("root") : null;

if (rootElement) {
  mountDashboard(rootElement);
}
