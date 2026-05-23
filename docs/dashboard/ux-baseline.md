# Dashboard UX Baseline

Status: Accepted
Architecture Reference: `docs/architecture.md#12-dashboard-design`

This baseline defines the minimum UX contract for the AITEAMOS Dashboard. It keeps the dashboard usable as the primary review and operations surface while preserving `.aiteamos/` as the durable source of truth.

## Keyboard Access

- Every durable action must be reachable through native `button`, `a`, `input`, `select`, or `textarea` elements.
- Navigation, table row actions, review decisions, assisted ingest, permission review, connector operations, and ProductUser administration must remain operable with keyboard tab order alone.
- Disabled actions must use real `disabled` controls when the action is blocked by readiness, review, permission, or lifecycle gates.
- URL state must preserve focused records for reload and shared links so keyboard users can return to the same task, run, memory item, review, skill, permission request, automation, connector delivery, project, employee, and workspace view.

## Contrast

- Body text, panel text, table text, muted labels, status badges, buttons, and danger states must meet WCAG AA contrast for normal-size text.
- The primary action color is blue, recommended actions are green, warnings are amber, and destructive actions are red. These meanings must not be expressed by color alone; labels, disabled state, or adjacent status text must carry the same meaning.
- Generated screenshots or browser audits should target Lighthouse accessibility score `>= 95` for the dashboard shell and core review pages.

## Focus Ring

- Focus indication must be visible without relying on browser defaults hidden by custom button or input styles.
- The shared focus ring is `2px` solid gold with an offset, applied through `:focus-visible` to buttons, links, form controls, and selectable table rows.
- Focus must remain visible in light and dark themes, including on sidebar navigation, table action buttons, and JSON/text editors.

## Empty States

- Empty sections must render stable panels or tables without layout jumps.
- Empty task, run, review, memory, permission, automation, connector, and product-user views must explain that no source manifests or derived projection rows are currently available.
- Empty states must not offer hidden mutation shortcuts; durable changes must still go through explicit task/run/review/memory/product-user/permission controls.

## Error States

- API failures must surface as visible text in the dashboard shell or the affected panel.
- Field-level validation errors must use `.error-text` and remain adjacent to the invalid draft or action.
- Secret values must never be echoed in error text, diagnostics, logs, dashboard URL state, or exported bundles.

## Loading States

- Initial workspace loading must display a stable panel instead of a blank page.
- Long projection refreshes should preserve existing data until the next derived view arrives.
- Loading labels must not resize toolbars, sidebars, or fixed control surfaces.

## Light And Dark Themes

- The default light theme uses a neutral work-surface palette with restrained blue, green, amber, and red accents.
- The dark theme is activated through `prefers-color-scheme: dark` and must preserve contrast, focus rings, and disabled-action legibility.
- Theme support must not change manifest data, API routing, URL state, or ProductUser session behavior.

## Internationalization

- User-facing dashboard shell copy, first-level navigation, shared panel titles, status labels, table headings, empty states, and accessible shell labels must resolve through `apps/dashboard/src/i18n.ts`.
- English is the default locale, and Chinese is the required second locale for the current baseline.
- The language switch is a browser-local UI preference; it must not store credentials, mutate `.aiteamos/` source manifests, or change URL auth state.

## Desktop And Tablet Breakpoints

- The dashboard shell supports desktop widths with sidebar navigation and dense projection panels.
- At widths `<= 900px`, the shell collapses to a single-column layout, sidebar navigation becomes a two-column grid, and two-column panels/forms collapse to one column.
- The minimum supported viewport width is `320px`; content must wrap or scroll within panels instead of overflowing the page.

## Verification

- Static documentation tests must keep this baseline linked from the dashboard README.
- Static i18n tests must keep the bilingual strings table linked to the dashboard shell.
- Dashboard CSS tests must assert the shared focus ring, dark theme media query, and tablet breakpoint.
- TypeScript checking must pass for the generated React/Vite dashboard.
