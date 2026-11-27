# Precision interface

The production interface adapts the approved [Isolate Precision prototype](https://www.magicpatterns.com/os/4upamUiV84RMVkE7P4KfhA?file=psftLYjjCXRKVWAzxyMrZP) to the existing Flask pages. It does not ship the prototype's simulated identities, sessions, commands, approvals or role selector.

`dashboard.css` is the Tailwind source; run `npm ci --ignore-scripts` and `npm run build` to reproduce the checked-in CSS and local Lucide sprite. The application needs neither Node nor a CDN at runtime.

## Shared production surfaces

| Journeys | Implementation |
| --- | --- |
| Navigation, themes, profile, service status | `shared/isolate_web.py`, `shared/static/precision-theme.js` |
| Overview and audit stream | `shared/isolate_dashboard_ui.py`, `shared/static/dashboard-overview.js` |
| Resource catalogue and administration | `shared/isolate_workspace_ui.py`, `shared/static/workspace-catalog.*` |
| Terminal tabs, splits, paste guard, replay and bookmarks | `shared/isolate_terminal_ui.py`, `shared/static/terminal-workspace.*`, `shared/static/terminal-replay.js` |
| Access requests, grants, packages, inventory, jobs, sessions, GitOps, users and delivery status | Existing routes in `shared/isolate_web.py` and `shared/isolate_self_service.py` |
| Session approvals | `shared/isolate_session_approval_web.py` |
| Access explanation, policy impact | `shared/isolate_explain_api.py` |
| Access reviews and offboarding | `shared/isolate_governance_api.py` |
| Campaign planning, canaries and per-host output | `shared/isolate_campaign_api.py` |
| Correlated evidence | `shared/isolate_investigation_api.py` |
| Database, Kubernetes and web-application connections | `shared/isolate_workspace_api.py`, `shared/isolate_application_api.py` |

The shared shell and presentation tokens cover all these routes. Navigation retains the server's permission and feature checks, including on catalogue, terminal and replay pages. The built assets use the existing forms and APIs; mutation confirmation, CSRF, version checks and access decisions remain server-side.

## Appearance and localization

The header offers Light, Dark and System. The preference is browser-local under `isolate-theme`; System is the default and follows OS appearance changes. The synchronous local bootstrap resolves the palette before the stylesheet is painted. Restricted storage falls back to a working in-memory preference. Terminal dark/light preferences remain independent and retain their existing backend validation.

The existing EN/RU session preference and form hints apply to production screens. User-entered data, command output, identifiers and policy values are not translated.

## Verification

- `python -m unittest discover -s tests -v`
- `node tests/js/precision-theme.test.mjs`
- `node tests/js/terminal-workspace.test.mjs`
- `python tests/integration/ui/ui_integration.py --output ui-verification`
- `python tests/integration/ui/web_apps_integration.py --output ui-verification`

The main browser integration exercises real isolated SSH connections and records, access explanations, policy impact, reviews and campaigns, plus theme persistence, OS changes, blocked storage, responsive navigation and menu filtering. It does not substitute for an authenticated smoke test against the deployment's external identity provider.
