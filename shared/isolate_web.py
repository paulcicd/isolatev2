#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight Isolate admin dashboard."""

import html
import datetime
import json
import os
import re
import secrets
import time
import urllib.parse

from isolate import get_grant_record, list_grant_records, load_grants, load_project_sets, redis_client, update_grant_record
from isolate_audit import prepare_and_dispatch
from isolate_access import AccessDenied, approve_access_request, deny_access_request, get_access_request, is_access_admin, list_access_requests, parse_duration, repeat_access_request, revoke_access_request, set_notification_status
from isolate_announcements import AnnouncementError, create_announcement, delete_announcement, list_announcements
from isolate_build import get_build_info
from isolate_config import load_config
from isolate_history import list_user_profiles, read_history, user_activity_summary
from isolate_health import run_health_checks
from isolate_identity import normalize_claims
from isolate_inventory import HostValidationError, bulk_update_hosts, create_host, get_host, list_hosts, update_host
from isolate_connectivity import ConnectivityError, check_host, get_last_check, save_check
from isolate_exports import ExportError, flatten_access_matrix, render_export
from isolate_dashboard_data import (
    DashboardDataError,
    build_access_matrix,
    collect_alerts,
    filter_jobs,
    fleet_progress,
    preview_grant_change,
    update_alert_state,
)
from isolate_jobs import JobError, create_runbook_fleet, get_job, list_jobs, read_job_output, request_job_cancel, retry_job
from isolate_notifications import NotificationError, notify_access_event
from isolate_packages import (
    AccessPackageError,
    assign_package,
    create_package,
    get_assignment,
    get_package,
    list_assignments,
    list_package_revisions,
    list_packages,
    preview_package_update,
    rollback_package,
    unassign_package,
    update_package,
)
from isolate_replay import find_session, parse_raw_replay
from isolate_policy import PolicyDenied, resolve_grant
from isolate_policy_bundle import PolicyBundleError, apply_bundle, blast_radius, export_bundle, plan_bundle, validate_bundle
from isolate_gitops import GitOpsError, git_policy_status, list_policy_snapshots, rollback_policy, save_policy_snapshot, sync_git_policy
from isolate_runbooks import BUILTIN_RUNBOOKS, list_runbooks
from isolate_sessions import SessionControlError, get_session, list_active_sessions, list_session_records, request_session_termination
from isolate_service_discovery import get_discovery_history
from isolate_self_service import add_history_recording_links, history_page, read_web_history, register_self_service
from isolate_permissions import has_permission, filter_projects, is_platform_admin, role_names
from isolate_session_approval_web import register_session_approval_routes


_DASHBOARD_STARTED_AT = time.time()

from isolate_ui_locale import localize_template as _ui, message as _message


def is_dashboard_admin(identity, config):
    return is_platform_admin(identity, config)


def is_self_service_user(identity, config):
    dashboard = config.get("dashboard", {})
    groups = dashboard.get("self_service_groups") or []
    return bool(identity.get("username") and dashboard.get("self_service_enabled", True)
                and (not groups or set(identity.get("groups") or []) & set(groups)))


def _secret_key(config):
    path = config.get("dashboard", {}).get("secret_key_file")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as secret_f:
            return secret_f.read().strip()
    return os.environ.get("ISOLATE_DASHBOARD_SECRET", "dev-only-change-me")


def _build_info(config):
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            cached = current_app.extensions.get("isolate_build_info")
            if cached:
                result = dict(cached)
                result["uptime_seconds"] = max(0, int(time.time() - _DASHBOARD_STARTED_AT))
                return result
    except (ImportError, RuntimeError):
        pass
    return get_build_info(config, _DASHBOARD_STARTED_AT)


_DASHBOARD_CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6fa;
  --surface: #ffffff;
  --surface-muted: #eef1f7;
  --sidebar: #111622;
  --sidebar-hover: #1c2433;
  --sidebar-active: #252f44;
  --sidebar-line: #293246;
  --sidebar-text: #d8deeb;
  --sidebar-muted: #8f9bb3;
  --text: #192131;
  --muted: #68748a;
  --line: #dbe1ec;
  --accent: #4967d5;
  --accent-strong: #334fb7;
  --accent-soft: #edf0ff;
  --info: #3274c8;
  --info-soft: #eaf2fc;
  --positive: #286ea8;
  --positive-soft: #e8f3fb;
  --amber: #94600c;
  --amber-soft: #fff3d6;
  --red: #ae3f51;
  --red-soft: #fcebef;
  --topbar: rgba(255, 255, 255, 0.96);
  --table-head: #f7f8fb;
  --table-hover: #f7f9fd;
  --input: #ffffff;
  --terminal: #111722;
  --terminal-text: #dce4f3;
  --shadow: 0 1px 2px rgba(23, 31, 48, 0.05), 0 8px 24px rgba(23, 31, 48, 0.05);
}

html[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0c1018;
  --surface: #151b27;
  --surface-muted: #1d2534;
  --sidebar: #080c13;
  --sidebar-hover: #171e2b;
  --sidebar-active: #222c40;
  --sidebar-line: #252d3d;
  --sidebar-text: #d7ddea;
  --sidebar-muted: #8894aa;
  --text: #e8ecf5;
  --muted: #98a4b9;
  --line: #2a3447;
  --accent: #8ea2ff;
  --accent-strong: #adbbff;
  --accent-soft: #252d4a;
  --info: #7eb2f3;
  --info-soft: #1b2b42;
  --positive: #72a9df;
  --positive-soft: #1a2b3d;
  --amber: #e1b45e;
  --amber-soft: #382d1a;
  --red: #ee91a0;
  --red-soft: #3a2028;
  --topbar: rgba(21, 27, 39, 0.96);
  --table-head: #19212e;
  --table-hover: #1a2230;
  --input: #111722;
  --terminal: #080c12;
  --terminal-text: #dce4f3;
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.24), 0 10px 28px rgba(0, 0, 0, 0.18);
}

* { box-sizing: border-box; }
html { min-width: 320px; background: var(--bg); }
body {
  margin: 0;
  color: var(--text);
  background: var(--bg);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
  letter-spacing: 0;
}

a { color: var(--accent); text-decoration: none; }
a:hover { color: var(--accent-strong); text-decoration: underline; }

.app-shell { min-height: 100vh; }
.sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 20;
  display: flex;
  width: 236px;
  flex-direction: column;
  overflow-y: auto;
  color: var(--sidebar-text);
  background: var(--sidebar);
  border-right: 1px solid var(--sidebar-line);
}
.brand {
  display: flex;
  min-height: 76px;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  color: #ffffff;
  border-bottom: 1px solid var(--sidebar-line);
}
.brand:hover { color: #ffffff; text-decoration: none; }
.brand-mark {
  display: grid;
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  place-items: center;
  color: #ffffff;
  background: var(--accent);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 800;
}
.brand-copy { display: flex; flex-direction: column; font-size: 16px; font-weight: 720; line-height: 1.2; }
.brand-copy small { margin-top: 3px; color: var(--sidebar-muted); font-size: 11px; font-weight: 600; text-transform: uppercase; }

.primary-nav { flex: 1; padding: 14px 10px; }
.nav-section + .nav-section { margin-top: 18px; }
.nav-label {
  display: block;
  padding: 0 10px 6px;
  color: var(--sidebar-muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}
.nav-link {
  display: flex;
  min-height: 36px;
  align-items: center;
  margin: 2px 0;
  padding: 8px 10px;
  color: var(--sidebar-text);
  border-left: 3px solid transparent;
  border-radius: 4px;
  font-weight: 560;
}
.nav-link:hover { color: #ffffff; background: var(--sidebar-hover); text-decoration: none; }
.nav-link.active { color: #ffffff; background: var(--sidebar-active); border-left-color: var(--accent); }

.user-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  color: #eef1ff;
  background: #303a55;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 750;
}

.main { min-height: 100vh; margin-left: 236px; }
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 28px;
  background: var(--topbar);
  border-bottom: 1px solid var(--line);
}
.topbar-title { font-size: 14px; font-weight: 700; }
.topbar-kicker { display: block; color: var(--muted); font-size: 11px; font-weight: 650; text-transform: uppercase; }
.runtime-state { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; font-weight: 600; }
.status-dot { width: 8px; height: 8px; background: var(--accent); border-radius: 50%; box-shadow: 0 0 0 3px var(--accent-soft); }

.content { width: 100%; max-width: 1600px; margin: 0 auto; padding: 28px; }
h1 { margin: 0 0 22px; font-size: 28px; line-height: 1.2; font-weight: 730; }
h2 { margin: 34px 0 12px; font-size: 18px; line-height: 1.3; font-weight: 700; }
h3 { margin: 24px 0 10px; font-size: 15px; font-weight: 700; }
p { margin: 10px 0; }
.page-lead { max-width: 720px; margin: -12px 0 22px; color: var(--muted); }
.muted { color: var(--muted); }

.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.metric {
  position: relative;
  min-height: 112px;
  padding: 20px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  box-shadow: var(--shadow);
}
.metric::before { position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--accent); content: ""; }
.metric:nth-child(2)::before { background: var(--amber); }
.metric:nth-child(3)::before { background: var(--info); }
.metric strong { display: block; margin-bottom: 4px; font-size: 30px; line-height: 1; font-variant-numeric: tabular-nums; }
.metric .muted { font-size: 13px; font-weight: 600; }
.metric-link { display: inline-block; margin-top: 13px; font-size: 12px; font-weight: 700; }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 18px; margin-top: 34px; }
.section-heading h2 { margin: 0; }
.empty-state { margin-top: 12px; padding: 28px; color: var(--muted); text-align: center; background: var(--surface); border: 1px dashed var(--line); border-radius: 6px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin: 0 0 14px; }
.toolbar form { flex: 1; }
.panel { margin-top: 14px; padding: 18px; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; box-shadow: var(--shadow); }
.panel h2, .panel h3 { margin-top: 0; }
.summary-list { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }
.summary-item { padding: 12px; background: var(--surface-muted); border-radius: 5px; }
.summary-item strong { display: block; font-size: 20px; font-variant-numeric: tabular-nums; }
.progress { width: 150px; height: 8px; overflow: hidden; background: var(--surface-muted); border-radius: 4px; }
.progress > span { display: block; height: 100%; background: var(--accent); }
.matrix-wrap { overflow: auto; border: 1px solid var(--line); border-radius: 6px; box-shadow: var(--shadow); }
.matrix { width: max-content; min-width: 100%; }
.matrix th:first-child, .matrix td:first-child { position: sticky; left: 0; z-index: 2; background: var(--table-head); }
.matrix-cell { min-width: 154px; max-width: 220px; white-space: normal; }
.matrix-cell strong { display: block; margin-bottom: 3px; }
.matrix-allowed { background: var(--positive-soft); }
.matrix-partial, .matrix-mixed { background: var(--amber-soft); }
.matrix-denied { color: var(--muted); background: var(--surface-muted); }
.severity-critical { color: var(--red); background: var(--red-soft); }
.severity-high { color: var(--red); background: var(--red-soft); }
.severity-medium { color: var(--amber); background: var(--amber-soft); }
.severity-low { color: var(--info); background: var(--info-soft); }
.button-secondary { color: var(--accent); background: var(--surface); }
.button-secondary:hover { color: #ffffff; }
.button-danger { color: var(--red); background: var(--surface); border-color: var(--red); }
.button-danger:hover { color: #ffffff; background: var(--red); border-color: var(--red); }
.key-value { display: grid; grid-template-columns: minmax(130px, 190px) minmax(0, 1fr); gap: 7px 16px; }
.key-value dt { color: var(--muted); font-weight: 650; }
.key-value dd { margin: 0; overflow-wrap: anywhere; }

.table-wrap {
  width: 100%;
  margin-top: 14px;
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  box-shadow: var(--shadow);
}
table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; }
th, td { padding: 10px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); font-size: 13px; }
th {
  color: var(--muted);
  background: var(--table-head);
  font-size: 11px;
  font-weight: 750;
  text-transform: uppercase;
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: var(--table-hover); }
td { white-space: nowrap; }
td.cell-server-services, td.cell-server-note, td.cell-privileged-access-hint, td.cell-command {
  min-width: 170px;
  max-width: 280px;
  overflow-wrap: anywhere;
  white-space: normal;
}
td.cell-connection-id { max-width: 220px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }

.badge { display: inline-flex; min-height: 23px; align-items: center; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 750; white-space: nowrap; }
.badge-active, .badge-approved, .badge-allowed, .badge-success { color: var(--positive); background: var(--positive-soft); }
.badge-pending, .badge-vip, .badge-warning { color: var(--amber); background: var(--amber-soft); }
.badge-denied, .badge-failed, .badge-error { color: var(--red); background: var(--red-soft); }
.badge-completed { color: var(--info); background: var(--info-soft); }

input, select, textarea, button { min-height: 36px; margin: 2px; font: inherit; letter-spacing: 0; }
input, select, textarea {
  max-width: 100%;
  padding: 7px 10px;
  color: var(--text);
  background: var(--input);
  border: 1px solid var(--line);
  border-radius: 4px;
}
input::placeholder, textarea::placeholder { color: var(--muted); }
input:focus, select:focus, textarea:focus, button:focus-visible, a:focus-visible {
  outline: 3px solid rgba(73, 103, 213, 0.22);
  outline-offset: 1px;
  border-color: var(--accent);
}
button {
  padding: 7px 13px;
  color: #ffffff;
  background: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 4px;
  cursor: pointer;
  font-weight: 680;
}
button:hover { background: var(--accent-strong); border-color: var(--accent-strong); }
button:disabled { cursor: not-allowed; opacity: 0.55; }
form { margin: 10px 0 18px; }
form.inline { display: inline-flex; flex-wrap: wrap; gap: 5px; align-items: center; margin: 0; }
form:not(.inline) { max-width: 1180px; padding: 18px; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
form p { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
label { color: var(--text); font-size: 13px; font-weight: 600; }
label input[type="checkbox"] { min-height: auto; accent-color: var(--accent); }
form[action*="/terminate"] button { color: var(--red); background: var(--surface); border-color: var(--red); }
form[action*="/terminate"] button:hover { color: #ffffff; background: var(--red); border-color: var(--red); }

.notice { padding: 12px 14px; margin: 0 0 20px; color: var(--info); background: var(--info-soft); border: 1px solid var(--line); border-left: 4px solid var(--info); border-radius: 5px; }
.notice.error { color: var(--red); background: var(--red-soft); border-left-color: var(--red); }
.notice.warning { color: var(--amber); background: var(--amber-soft); border-left-color: var(--amber); }
.notice.info, .notice.success { color: var(--positive); background: var(--positive-soft); border-left-color: var(--positive); }

pre { max-width: 100%; padding: 16px; overflow: auto; color: var(--terminal-text); background: var(--terminal); border: 1px solid var(--line); border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.92em; }
.terminal { border: 1px solid var(--line); border-radius: 6px; box-shadow: var(--shadow); }

.topbar-actions { display: flex; align-items: center; gap: 12px; }
.theme-switch, .locale-switch {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(54px, 1fr));
  padding: 3px;
  background: var(--surface-muted);
  border: 1px solid var(--line);
  border-radius: 6px;
}
.theme-switch button, .locale-switch a {
  display: grid;
  min-height: 28px;
  margin: 0;
  padding: 3px 9px;
  place-items: center;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 650;
}
.theme-switch button:hover, .locale-switch a:hover { color: var(--text); background: var(--surface); text-decoration: none; }
.theme-switch button[aria-pressed="true"], .locale-switch a.active { color: var(--text); background: var(--surface); box-shadow: 0 1px 3px rgba(20, 28, 45, 0.16); }
.locale-switch { grid-template-columns: repeat(2, 38px); }
.locale-switch a { min-width: 38px; font-size: 11px; font-weight: 720; }
.page-help {
  max-width: 900px;
  margin: -10px 0 22px;
  color: var(--muted);
  border-bottom: 1px solid var(--line);
}
.page-help summary { width: max-content; padding: 6px 0 9px; color: var(--accent); cursor: pointer; font-size: 12px; font-weight: 700; }
.page-help p { max-width: 820px; margin: 0 0 14px; }
.package-rule-example { font-size: 12px; }

@media (max-width: 1050px) {
  .sidebar { width: 208px; }
  .main { margin-left: 208px; }
  .content { padding: 22px; }
  .summary-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .sidebar { position: static; width: 100%; max-height: none; }
  .brand { min-height: 62px; }
  .primary-nav { display: flex; gap: 6px; overflow-x: auto; padding: 8px 10px; }
  .nav-section { display: flex; gap: 4px; margin: 0 !important; }
  .nav-label { display: none; }
  .nav-link { min-height: 34px; flex: 0 0 auto; padding: 7px 9px; border-left: 0; border-bottom: 2px solid transparent; }
  .nav-link.active { border-bottom-color: var(--accent); }
  .main { margin-left: 0; }
  .topbar { position: static; min-height: 54px; padding: 0 16px; }
  .runtime-state { display: none; }
  .topbar-actions { gap: 8px; }
  .content { padding: 20px 16px; }
  .grid { grid-template-columns: 1fr; }
  .summary-list { grid-template-columns: 1fr 1fr; }
  .key-value { grid-template-columns: 1fr; gap: 2px; }
  .key-value dd { margin-bottom: 8px; }
  h1 { font-size: 24px; }
  form:not(.inline) { padding: 14px; }
  .locale-switch { display: none; }
}
"""


_SHELL_I18N = {
    "en": {
        "operations": "Operations", "summary": "Summary", "jobs": "Jobs & runbooks", "alerts": "Alert center",
        "active_sessions": "Active sessions", "history": "History", "inventory": "Inventory", "announcements": "Announcements",
        "access_control": "Access control", "requests": "Requests", "grants": "Grants", "packages": "Access packages",
        "matrix": "Access matrix", "simulator": "Policy simulator", "platform": "Platform", "gitops": "GitOps",
        "users": "Users", "notifications": "Notifications", "documentation": "Documentation", "sign_out": "Sign out",
        "bastion_control": "Bastion control", "operations_console": "Operations console", "secured": "Secured by Keycloak",
        "day": "Light", "night": "Dark", "system": "System", "about": "About this page", "primary_nav": "Primary navigation",
        "theme": "Color theme", "language": "Language",
    },
    "ru": {
        "operations": "Операции", "summary": "Обзор", "jobs": "Задания и регламенты", "alerts": "События и предупреждения",
        "active_sessions": "Активные сессии", "history": "История", "inventory": "Инвентарь", "announcements": "Объявления",
        "access_control": "Управление доступом", "requests": "Заявки на доступ", "grants": "Правила доступа", "packages": "Пакеты доступа",
        "matrix": "Матрица доступа", "simulator": "Проверка доступа", "platform": "Платформа", "gitops": "GitOps",
        "users": "Пользователи", "notifications": "Уведомления", "documentation": "Документация", "sign_out": "Выйти",
        "bastion_control": "Управление бастионом", "operations_console": "Консоль управления", "secured": "Вход через Keycloak",
        "day": "Светлая", "night": "Тёмная", "system": "Как в системе", "about": "Об этой странице", "primary_nav": "Основная навигация",
        "theme": "Цветовая тема", "language": "Язык",
    },
}


_PAGE_HELP = {
    "Isolate Dashboard": {
        "en": "Operational overview of active sessions, pending access requests, recent connections, jobs, and security alerts.",
        "ru": "Активные сессии, заявки на доступ, недавние подключения, задания и события, требующие внимания.",
    },
    "Jobs & Runbooks": {
        "en": "Run approved operational procedures across one host or a fleet, then monitor progress, output, retries, and cancellations.",
        "ru": "Запускайте разрешённые регламенты, следите за выполнением на каждом сервере и открывайте вывод команд.",
    },
    "Alert Center": {
        "en": "Review session risks, failed jobs, and notification delivery failures; acknowledge or resolve findings with an audit trail.",
        "ru": "Разбирайте подозрительные подключения и ошибки заданий или доставки уведомлений. Решения сохраняются в журнале аудита.",
    },
    "Access Matrix": {
        "en": "Inspect effective user and group access by project, identify conflicting grants, and preview the blast radius of changes.",
        "ru": "Проверьте, к каким проектам есть доступ у пользователя или группы и на кого повлияет изменение правила.",
    },
    "Active Sessions": {
        "en": "See current SSH connections, their duration and target identity, and terminate a session when an incident requires it.",
        "ru": "Узнайте, кто сейчас подключён по SSH, под какой учётной записью и как долго. Отсюда можно завершить сессию.",
    },
    "History": {
        "en": "Search audited SSH connections by user, project, host ID, host name, or target address and open their session details.",
        "ru": "Найдите подключение по пользователю, проекту, имени, адресу или ID сервера и откройте карточку сессии.",
    },
    "Access Requests": {
        "en": "Review temporary access requests, comments, tickets, notification status, and approve or deny break-glass grants.",
        "ru": "Проверьте срок и причину, по которой нужен временный доступ, затем примите решение по заявке.",
    },
    "Inventory": {
        "en": "Browse bastion-managed hosts, service metadata, VIP markers, and privileged access guidance. Host changes are audited.",
        "ru": "Найдите сервер, проверьте его сервисы и условия привилегированного доступа. Изменения попадают в журнал аудита.",
    },
    "Announcements": {
        "en": "Publish time-limited operational notices globally or for a project or host. Notices appear in terminal search and before connection.",
        "ru": "Опубликуйте сообщение для всех, проекта или сервера. Пользователи увидят его в результатах поиска и перед подключением.",
    },
    "Session Details": {
        "en": "Inspect one connection's identity, policy decision, commands, timestamps, exit status, raw log, and replay artifacts.",
        "ru": "Проверьте, кто подключался, по какому правилу и чем завершилась сессия. Здесь доступны журнал и запись терминала.",
    },
    "Live Session": {
        "en": "Follow newly written terminal output for an active connection. This observational view is not Web SSH.",
        "ru": "Следите за выводом терминала, пока идёт сессия. Ввод команд отключён.",
    },
    "Session Replay": {
        "en": "Replay the recorded terminal stream with seek, speed, ANSI rendering, and raw or JSON downloads.",
        "ru": "Откройте запись терминала, перемотайте её на нужное место или скачайте исходный журнал либо JSON.",
    },
    "Policy Simulator": {
        "en": "Explain which grant applies to an identity, project, and host before changing production access.",
        "ru": "Проверьте, какое правило разрешит или запретит действие для выбранного пользователя, проекта и сервера.",
    },
    "Policy GitOps": {
        "en": "Validate, compare, apply, and roll back optional Git-managed grants and project sets while tracking Redis drift.",
        "ru": "Сравните правила и наборы проектов из Git с действующей конфигурацией в Redis перед применением или откатом.",
    },
    "Users": {
        "en": "Inspect identities observed in audit data together with effective grants, active sessions, and connection history.",
        "ru": "Найдите пользователя в журнале аудита и проверьте его доступ, активные сессии и историю подключений.",
    },
    "User Details": {
        "en": "Review one user's observed groups, access rules, active sessions, and historical activity.",
        "ru": "Проверяйте группы, правила доступа, активные сессии и историю выбранного пользователя.",
    },
    "Notifications": {
        "en": "Check recent webhook, Telegram, and email delivery outcomes for access and session events.",
        "ru": "Узнайте, дошли ли уведомления о заявках и подключениях через вебхуки, Telegram или электронную почту.",
    },
    "Grants": {
        "en": "Manage low-level RBAC grants and project sets. Package-managed grants are changed through Access Packages.",
        "ru": "Настройте отдельные правила доступа и наборы проектов. Правила из пакета редактируются в самом пакете.",
    },
    "Access Packages": {
        "en": "Create reusable access profiles, preview revisions, and assign them to Keycloak users, groups, or roles.",
        "ru": "Соберите правила в пакет, проверьте изменения и назначьте пакет пользователю, группе или роли.",
    },
    "Documentation": {
        "en": "A practical guide to identity, inventory, policies, packages, temporary access, sessions, jobs, backup, and updates.",
        "ru": "Руководство по подключению, управлению доступом, аудиту и обслуживанию бастиона.",
    },
}


_FIELD_HELP = {
    "en": {
        "q": "Free-text filter for the current table.", "status": "Lifecycle or execution state to display.",
        "user": "Verified Keycloak username.", "group": "Exact Keycloak group claim.", "role": "Exact signed token role.",
        "name": "Human-readable object or subject name.", "description": "Short administrator-facing purpose and scope.",
        "project": "Exact Isolate project name.", "groups": "Comma-separated Keycloak groups used by the simulator.",
        "roles": "Comma-separated signed token roles used by the simulator.",
        "host": "Optional server ID restriction.", "remote_user": "Unix account used on the target host.",
        "sudo_mode": "Whether and how the remote session elevates privileges.", "allowed_actions": "Comma-separated capabilities such as ssh, runbook, command, operate.",
        "ttl": "Assignment lifetime, for example 2h or 7d.", "ticket": "Incident or change ticket associated with the action.",
        "reason": "Operational justification stored in audit data.", "comment": "Immutable decision or review note.",
        "selector_type": "Choose an exact project, glob, or named project set.", "selector_value": "Value for the selected project selector.",
        "access_json": "JSON list of package access rules; every rule needs one selector and a remote user.",
        "default_ttl": "Default lifetime used when assignment does not specify one.", "max_ttl": "Maximum assignment lifetime allowed by this package.",
        "permanent_allowed": "Allow assignments without an expiration time.", "approval_required": "Mark this package as requiring an administrator assignment decision.",
        "admin_groups": "Comma-separated Keycloak groups allowed to assign this package.", "ticket_required": "Require a ticket for every assignment.",
        "minimum_approvals": "Required approvers; values above one block direct assignment until a multi-approval workflow is configured.",
        "package": "Package ID or exact package name.", "subject": "Identity type receiving the package: user, group, or role.",
        "revision": "Immutable package revision used for rollback.", "permanent": "Create an assignment without expiration when the package permits it.",
        "ip": "Target IPv4/IPv6 address or validated hostname.", "port": "Target SSH port.",
        "services": "Free-form searchable service inventory.", "note": "Short operational note shown in inventory.",
        "maintenance_reason": "Reason shown while new connections are paused.", "maintenance_until": "Unix timestamp when maintenance expires; empty means no deadline.",
        "severity": "Visual priority of an operational announcement.",
        "policy_action": "Capability evaluated by the production policy resolver.", "confirm": "Explicitly acknowledge this audited mutation.",
    },
    "ru": {
        "q": "Введите часть названия, имени или идентификатора из таблицы.",
        "status": "Показывать записи в выбранном состоянии.",
        "user": "Имя пользователя, которое Isolate получает при входе.",
        "group": "Укажите группу ровно так, как она указана в токене входа.",
        "role": "Укажите роль ровно так, как она указана в подписанном токене.",
        "name": "Выберите короткое имя, по которому запись легко найти.",
        "description": "Укажите, для чего нужна эта настройка и где она действует.",
        "project": "Введите имя проекта так, как оно записано в каталоге.",
        "groups": "Введите через запятую группы, с которыми нужно проверить доступ.",
        "roles": "Введите через запятую роли, с которыми нужно проверить доступ.",
        "host": "Укажите ID сервера, чтобы ограничить правило этим сервером.",
        "remote_user": "Имя учётной записи Unix на целевом сервере.",
        "sudo_mode": "Определяет, может ли пользователь повышать привилегии через sudo.",
        "allowed_actions": "Перечислите разрешённые действия через запятую. Например, ssh, runbook, command, operate.",
        "ttl": "Сколько действует назначение. Например, 2h — два часа, 7d — семь дней.",
        "ticket": "Номер задачи, инцидента или заявки на изменение, с которой связано действие.",
        "reason": "Объясните, зачем нужно действие. Причина попадёт в журнал аудита.",
        "comment": "Поясните решение. Комментарий сохранится в журнале.",
        "selector_type": "Выберите один проект, шаблон имени или набор проектов.",
        "selector_value": "Имя проекта, шаблон или имя набора по выбранному типу.",
        "access_json": "Список правил в JSON. Для каждого укажите условие выбора проектов и учётную запись на сервере.",
        "default_ttl": "Срок доступа, если не указать его при назначении.",
        "max_ttl": "Самый долгий срок, на который можно назначить этот пакет.",
        "permanent_allowed": "Разрешить назначение пакета без даты окончания.",
        "approval_required": "Запрашивать решение администратора перед назначением.",
        "admin_groups": "Перечислите через запятую группы Keycloak, которым разрешено назначать пакет.",
        "ticket_required": "Требовать номер заявки при каждом назначении пакета.",
        "minimum_approvals": "При двух и более согласующих потребуется настроить процесс согласования. Напрямую назначить пакет нельзя.",
        "package": "Введите ID или точное имя пакета доступа.",
        "subject": "Укажите, кому назначается пакет — пользователю, группе или роли.",
        "revision": "Выберите сохранённую версию пакета, которую хотите вернуть.",
        "permanent": "Назначить без даты окончания, если это разрешено настройками пакета.",
        "ip": "IP-адрес (IPv4 или IPv6) либо DNS-имя целевого сервера.",
        "port": "Порт, на котором целевой сервер принимает подключения SSH.",
        "services": "Перечислите сервисы, по которым этот сервер можно будет найти в каталоге.",
        "note": "Короткая заметка, которую увидят пользователи в каталоге серверов.",
        "maintenance_reason": "Эту причину увидят пользователи, когда новые подключения приостановлены.",
        "maintenance_until": "Время окончания работ в формате Unix timestamp. Пустое поле оставляет ограничение без срока.",
        "severity": "Уровень важности объявления. По нему определяется оформление.",
        "policy_action": "Выберите действие, для которого нужно проверить доступ.",
        "confirm": "Подтвердите действие. Оно будет записано в журнал аудита.",
    },
}


def _dashboard_locale(config=None):
    locale = str((config or {}).get("dashboard", {}).get("default_locale") or "en").lower()
    try:
        from flask import current_app, has_request_context, request, session
        if has_request_context():
            if config is None:
                locale = current_app.config.get("ISOLATE_DEFAULT_LOCALE", locale)
            requested = str(request.args.get("lang") or "").lower()
            if requested in _SHELL_I18N:
                session["dashboard_locale"] = requested
            locale = session.get("dashboard_locale") or locale
    except (ImportError, RuntimeError):
        pass
    return locale if locale in _SHELL_I18N else "en"


def _locale_url(locale):
    try:
        from flask import has_request_context, request
        if has_request_context():
            values = request.args.to_dict(flat=False)
            values["lang"] = [locale]
            return request.path + "?" + urllib.parse.urlencode(values, doseq=True)
    except (ImportError, RuntimeError):
        pass
    return "?lang={}".format(locale)


def _page_help(title, locale):
    if title == "Isolate Dashboard":
        return ""
    descriptions = _PAGE_HELP.get(str(title))
    if not descriptions and str(title).startswith("Job "):
        descriptions = {
            "en": "Inspect per-host state, output, errors, cancellation status, and retries for this job.",
            "ru": "Проверьте ход задания на каждом сервере, вывод команд и ошибки.",
        }
    if not descriptions:
        return ""
    return '<details class="page-help"><summary>{}</summary><p>{}</p></details>'.format(
        html.escape(_SHELL_I18N[locale]["about"]), html.escape(descriptions.get(locale) or descriptions["en"])
    )


def _html(title, body, config=None, notice=None):
    from isolate_navigation_ui import render_navigation
    from isolate_profile_ui import portal_role_label
    from isolate_ui_icons import icon
    from isolate_ui_locale import localize_html, translate
    locale = _dashboard_locale(config)
    body = localize_html(body, locale, fallback_hints=_FIELD_HELP[locale])
    words = dict(_SHELL_I18N[locale])
    from isolate_oidc import identity_provider_config
    display_provider = identity_provider_config(config or {})
    if display_provider.get("provider") == "oidc":
        words["secured"] = ("Вход через " if locale == "ru" else "Sign-in with ") + str(display_provider.get("display_name") or "OpenID Connect")
    build = _build_info(config)
    refresh = ""
    refresh_seconds = int((config or {}).get("dashboard", {}).get("refresh_seconds") or 0)
    if refresh_seconds > 0 and title in ("Isolate Dashboard", "Active Sessions", "Access Requests"):
        refresh = '<meta http-equiv="refresh" content="{}">'.format(refresh_seconds)
    notice_html = ""
    if notice:
        level = notice.get("level", "info")
        text = str(notice.get("text", ""))
        caption = translate(text, locale)
        if locale == "ru" and level == "error" and caption == text and not re.search(r"[А-ЯЁа-яё]", text):
            notice_body = (
                '<p>Действие не выполнено. Проверьте данные и права доступа.</p>'
                '<details><summary>Технические сведения</summary><p>{}</p></details>'
            ).format(html.escape(text))
        else:
            notice_body = html.escape(caption)
        notice_html = '<div class="notice {}">{}</div>'.format(
            html.escape(level), notice_body,
        )
    username = "Administrator"
    identity, path = {}, ""
    try:
        from flask import has_request_context, request, session
        if has_request_context():
            path = request.path
            if isinstance(session.get("identity"), dict):
                identity = session["identity"]
                username = str(identity.get("username") or username)
    except (ImportError, RuntimeError):
        pass
    initials = "".join(part[:1] for part in username.replace(".", " ").split()[:2]).upper() or "AD"
    admin_groups = (config or {}).get("dashboard", {}).get("admin_groups") or (config or {}).get("history", {}).get("admin_groups") or []
    matched_groups = sorted(set(identity.get("groups") or []) & set(admin_groups))
    labels = ("Роль в панели", "Группы доступа", "Группы OIDC", "Роли Keycloak") if locale == "ru" else ("Dashboard role", "Access groups", "OIDC groups", "Keycloak roles")
    if display_provider.get("provider") == "oidc":
        labels = labels[:3] + (("Роли OIDC" if locale == "ru" else "OIDC roles"),)
    admin_view = is_dashboard_admin(identity, config or {})
    portal_roles = role_names(identity, config or {})
    roles = ", ".join(portal_role_label(role, locale) for role in portal_roles)
    role_label = ("Администратор" if locale == "ru" else "Admin") if admin_view else (
        roles or ("Пользователь" if locale == "ru" else "User"))
    identity_details = '<div class="sidebar-claims"><p>{}: {}</p>{}</div>'.format(
        labels[0], html.escape(role_label),
        "".join('<p><strong>{}</strong>: {}</p>'.format(html.escape(label), html.escape(", ".join(values) or "—")) for label, values in zip(labels[1:], (matched_groups, identity.get("groups") or [], identity.get("roles") or []))),
    )
    rail_buttons, navigation_groups = render_navigation(config or {}, identity, locale, words,
                                                       admin=admin_view, roles=portal_roles, path=path)
    search_label = "Поиск ресурсов" if locale == "ru" else "Search resources"
    profile_label = "Профиль пользователя" if locale == "ru" else "User profile"
    shell_script = """
(function () {
  const menu = document.querySelector('[data-sidebar-toggle]');
  const sidebar = document.querySelector('.sidebar');
  const search = document.querySelector('#global-search');
  const popovers = document.querySelectorAll('[data-shell-popover]');
  document.addEventListener('pointerdown', function (event) {
    popovers.forEach(function (popover) {
      if (popover.open && !popover.contains(event.target)) popover.open = false;
    });
  });
  popovers.forEach(function (popover) {
    popover.addEventListener('toggle', function () {
      if (!popover.open) return;
      popovers.forEach(function (other) { if (other !== popover) other.open = false; });
    });
    popover.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || !popover.open) return;
      event.preventDefault();
      event.stopPropagation();
      popover.open = false;
      popover.querySelector('summary').focus({preventScroll: true});
    });
  });
  if (menu && sidebar) {
    menu.addEventListener('click', function () {
      const open = sidebar.dataset.open !== 'true';
      sidebar.dataset.open = String(open);
      menu.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        sidebar.dataset.open = 'false';
        menu.setAttribute('aria-expanded', 'false');
      }
    });
  }
  document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' &&
        !document.querySelector('#workspace-query')) {
      event.preventDefault();
      if (search) search.focus();
    }
  });
  const state = document.querySelector('[data-bastion-state]');
  if (state) {
    fetch('/health', {credentials:'same-origin', cache:'no-store'})
      .then(function (response) { return response.json(); })
      .then(function (health) {
        state.textContent = health.ok ? state.dataset.healthy : state.dataset.degraded;
        state.dataset.state = health.ok ? 'healthy' : 'degraded';
      })
      .catch(function () { state.textContent = state.dataset.unknown; state.dataset.state = 'unknown'; });
  }
})();
"""
    rendered = """<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" type="image/svg+xml" href="/static/favicon.svg">{refresh}<title>{title}</title>
<script src="/static/precision-theme.js"></script><script src="/static/precision-navigation.js" defer></script>
<style>{css}</style><link rel="stylesheet" href="/static/dashboard.css"><link rel="stylesheet" href="/static/admin-ui.css">
<link rel="stylesheet" href="/static/access-admin.css"><link rel="stylesheet" href="/static/field-help.css"></head><body class="precision-app font-sans">
<a class="skip-link sr-only focus:not-sr-only" href="#main-content">{skip_label}</a>
<div class="app-shell">
  <aside class="sidebar" id="sidebar-navigation">
    <a class="brand" href="/" aria-label="Isolate dashboard">
      <span class="brand-mark">{brand_icon}</span>
      <span class="brand-copy">isolate<span class="brand-slash"> /</span><small>{bastion_control}</small></span>
    </a>
    <div class="sidebar-navigation">
      <div class="nav-rail" role="group" aria-label="{section_navigation_label}" hidden>{rail_buttons}</div>
      <div class="nav-pages">
        <div class="nav-search"><label class="sr-only" for="navigation-search">{navigation_search_label}</label>{search_icon}<input id="navigation-search" type="search" placeholder="{navigation_search_label}" autocomplete="off"></div>
        <nav class="primary-nav" aria-label="{primary_nav}">
          {navigation_groups}
          <p class="nav-no-results" data-nav-no-results role="status" hidden>{navigation_no_results}</p>
        </nav>
      </div>
    </div>
    <div class="sidebar-footer">
      <details class="sidebar-build" data-shell-popover>
        <summary class="sidebar-build-trigger" aria-label="{build_label}">{build_icon}</summary>
        <div class="sidebar-popover topbar-popover-panel">
          <div class="sidebar-popover-heading"><strong>{build_label}</strong><span>v{version}</span></div>
          <dl class="sidebar-build-details">
            <div><dt>{revision_label}</dt><dd>{revision}</dd></div>
            <div><dt>{schema_label}</dt><dd>{schema}</dd></div>
            <div><dt>Python</dt><dd>{python}</dd></div>
          </dl>
        </div>
      </details>
      <details class="sidebar-account" data-shell-popover>
        <summary class="sidebar-account-trigger" aria-label="{account_menu_label}">
          <span class="user-avatar">{initials}</span>
          <span class="sidebar-account-copy"><strong>{username}</strong><span>{role_label}</span></span>{profile_icon}
        </summary>
        <div class="sidebar-popover topbar-popover-panel">
          <div class="sidebar-popover-heading"><strong>{username}</strong></div>
          {identity_details}
          <a href="/me/profile">{profile_settings_icon}<span>{profile_label}</span></a>
          <a href="/logout">{logout_icon}<span>{sign_out}</span></a>
        </div>
      </details>
    </div>
  </aside>
  <nav class="nav-flyout" aria-labelledby="nav-flyout-title" hidden>
    <h2 class="nav-flyout-title" id="nav-flyout-title"></h2><div class="nav-flyout-links"></div>
  </nav>
  <main class="main">
    <header class="topbar">
      <button class="mobile-nav-button" type="button" data-sidebar-toggle aria-controls="sidebar-navigation" aria-expanded="false" aria-label="{menu_label}">{menu_icon}</button>
      <div class="topbar-heading"><span class="topbar-kicker">Isolate / {bastion_control}</span><span class="topbar-title">{page_title}</span></div>
      <form class="global-search" role="search" method="get" action="{search_route}">{search_icon}<label class="sr-only" for="global-search">{search_label}</label><input id="global-search" type="search" name="q" placeholder="{search_label}" autocomplete="off"><kbd>⌘ K</kbd></form>
      <div class="topbar-actions">
        <div class="runtime-state"><span class="status-dot"></span><span data-bastion-state data-healthy="{healthy_label}" data-degraded="{degraded_label}" data-unknown="{unknown_label}">{unknown_label}</span></div>
        <div class="locale-switch" aria-label="{language}"><a class="{en_active}" href="{en_url}" lang="en">EN</a><a class="{ru_active}" href="{ru_url}" lang="ru">RU</a></div>
        <details class="topbar-popover theme-switch" id="theme-preference" data-shell-popover>
          <summary class="topbar-popover-trigger" title="{theme}"><span class="sr-only">{theme}</span>{theme_icon}<span class="theme-label" data-theme-label>{system}</span>{profile_icon}</summary>
          <div class="topbar-popover-panel" role="group" aria-label="{theme}">
            <button type="button" data-theme-choice="light" aria-pressed="false"><span data-theme-name>{day}</span>{check_icon}</button>
            <button type="button" data-theme-choice="dark" aria-pressed="false"><span data-theme-name>{night}</span>{check_icon}</button>
            <button type="button" data-theme-choice="system" aria-pressed="true" title="{theme_hint}"><span data-theme-name>{system}</span>{check_icon}</button>
          </div>
        </details>
        <a class="header-help" href="/docs" aria-label="{documentation}" title="{documentation}">{help_icon}</a>
        <details class="topbar-popover header-profile" data-shell-popover>
          <summary class="topbar-popover-trigger" aria-label="{account_menu_label}"><span class="user-avatar">{initials}</span><span class="profile-label">{username}</span>{profile_icon}</summary>
          <div class="topbar-popover-panel">
            <div class="topbar-account-name">{username}</div>
            <a href="/me/profile">{profile_settings_icon}<span>{profile_label}</span></a>
            <a href="/logout">{logout_icon}<span>{sign_out}</span></a>
          </div>
        </details>
      </div>
    </header>
    <div class="content" id="main-content" tabindex="-1">{notice}{page_help}{body}</div>
    <footer class="precision-footer"><span>isolate / precision</span><span>{secured}</span></footer>
  </main>
</div>
<script>{shell_script}</script><script src="/static/admin-dialog.js" defer></script><script src="/static/field-help.js" defer></script>
</body></html>""".format(
        locale=locale,
        rail_buttons=rail_buttons,
        navigation_groups=navigation_groups,
        section_navigation_label="Разделы" if locale == "ru" else "Sections",
        navigation_no_results="Разделы не найдены" if locale == "ru" else "No matching pages",
        refresh=refresh,
        title=html.escape(translate(str(title), locale)),
        page_title=html.escape(translate(str(title), locale)),
        css=_DASHBOARD_CSS,
        initials=html.escape(initials),
        username=html.escape(username),
        role_label=html.escape(role_label),
        identity_details=identity_details,
        build_label="О сборке" if locale == "ru" else "Build information",
        revision_label="Ревизия" if locale == "ru" else "Revision",
        schema_label="Схема" if locale == "ru" else "Schema",
        build_icon=icon("info"),
        version=html.escape(str(build.get("version") or "unknown")),
        revision=html.escape(str(build.get("revision_short") or "unknown")),
        schema=html.escape(str(build.get("schema_version") or "n/a")),
        python=html.escape(str(build.get("python") or "unknown")),
        notice=notice_html,
        page_help=_page_help(title, locale),
        body=body,
        shell_script=shell_script,
        search_label=search_label,
        search_route="/workspace" if (config or {}).get("api", {}).get("enabled") else "/inventory",
        profile_label=profile_label,
        account_menu_label="Меню учётной записи" if locale == "ru" else "Account menu",
        navigation_search_label="Найти раздел…" if locale == "ru" else "Find a section…",
        theme_hint="В режиме «Как в системе» тема меняется вместе с настройками устройства." if locale == "ru" else "Your choice is saved. System mode follows your device appearance.",
        brand_icon=icon("shield-check"), search_icon=icon("search"), menu_icon=icon("menu"),
        profile_icon=icon("chevron-down"), help_icon=icon("book-open"),
        theme_icon=icon("sliders-horizontal"), check_icon=icon("check", "theme-check"),
        profile_settings_icon=icon("settings-2"), logout_icon=icon("log-out"),
        menu_label="Открыть навигацию" if locale == "ru" else "Open navigation",
        skip_label="Перейти к содержимому" if locale == "ru" else "Skip to content",
        healthy_label="Исправен" if locale == "ru" else "Healthy",
        degraded_label="Требует внимания" if locale == "ru" else "Degraded",
        unknown_label="Проверка состояния" if locale == "ru" else "Checking status",
        en_active="active" if locale == "en" else "",
        ru_active="active" if locale == "ru" else "",
        en_url=html.escape(_locale_url("en"), quote=True),
        ru_url=html.escape(_locale_url("ru"), quote=True),
        **{key: html.escape(str(value)) for key, value in words.items()}
    )
    return rendered


def _table(rows, columns):
    from isolate_ui_locale import message
    locale = _dashboard_locale()
    header = "".join("<th scope=\"col\">{}</th>".format(html.escape(str(label))) for key, label in columns)
    body = ""
    for row in rows:
        cells = []
        for key, _ in columns:
            value = row.get(key) or ""
            safe_html = key in (
                "raw", "project_link", "history", "details", "replay", "live", "control",
                "user_link", "package_link", "edit", "actions", "progress", "source_link", "severity_badge",
            )
            rendered = str(value) if safe_html else html.escape(str(value))
            normalized = str(value).strip().lower()
            if not safe_html and key == "server_vip_marker" and rendered:
                rendered = '<span class="badge badge-vip">{}</span>'.format(rendered)
            elif not safe_html and key == "status" and rendered:
                badge_class = "badge-{}".format("".join(ch for ch in normalized if ch.isalnum() or ch == "-") or "status")
                rendered = '<span class="badge {}">{}</span>'.format(badge_class, html.escape(message("Open" if value == "open" and locale == "ru" else str(value), locale)))
            elif not safe_html and key == "result" and rendered:
                if normalized in ("allowed", "ok", "success") or normalized.startswith("exit=0"):
                    badge_class = "badge-success"
                elif "denied" in normalized or "failed" in normalized or (normalized.startswith("exit=") and normalized != "exit=0"):
                    badge_class = "badge-error"
                else:
                    badge_class = "badge-completed"
                rendered = '<span class="badge {}">{}</span>'.format(badge_class, html.escape(message(str(value), locale)))
            cell_class = "cell-{}".format(str(key).replace("_", "-"))
            cells.append('<td class="{}">{}</td>'.format(cell_class, rendered))
        body += "<tr>{}</tr>".format("".join(cells))
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(header, body)


def _split_values(value):
    return [item.strip() for item in str(value or "").replace("\n", ",").split(",") if item.strip()]


def _optional_bool(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ValueError("boolean field must be true or false")


def _format_ts(value):
    if not value:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(value)))
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _format_access_time(value):
    if value in (None, ""):
        return ""
    return datetime.datetime.fromtimestamp(int(value), datetime.timezone.utc).isoformat()


def _parse_json_object(value, field_name="JSON parameters"):
    try:
        result = json.loads(value or "{}")
    except (TypeError, ValueError) as exc:
        raise ValueError("{} are invalid: {}".format(field_name, exc)) from exc
    if not isinstance(result, dict):
        raise ValueError("{} must be a JSON object".format(field_name))
    return result


def _parse_json_list(value, field_name="JSON value"):
    try:
        result = json.loads(value or "[]")
    except (TypeError, ValueError) as exc:
        raise ValueError("{} is invalid: {}".format(field_name, exc)) from exc
    if not isinstance(result, list):
        raise ValueError("{} must be a JSON list".format(field_name))
    return result


def _package_form_payload(form, current=None):
    current = current or {}
    lifecycle = current.get("lifecycle") or {}
    approval = current.get("approval") or {}
    return {
        "name": str(form.get("name") or current.get("name") or "").strip(),
        "description": str(form.get("description") or "").strip(),
        "status": str(form.get("status") or current.get("status") or "enabled"),
        "access": _parse_json_list(form.get("access_json"), "package access JSON"),
        "lifecycle": {
            "default_ttl": str(form.get("default_ttl") or "").strip() or None,
            "max_ttl": str(form.get("max_ttl") or "").strip() or None,
            "permanent_allowed": form.get("permanent_allowed") == "true",
        },
        "approval": {
            "required": form.get("approval_required") == "true",
            "admin_groups": _split_values(form.get("admin_groups")),
            "ticket_required": form.get("ticket_required") == "true",
            "minimum_approvals": int(form.get("minimum_approvals") or approval.get("minimum_approvals") or 1),
        },
    }



def _host_form_values(form, partial=False):
    mapping = {
        "project": "project_name",
        "name": "server_name",
        "ip": "server_ip",
        "port": "server_port",
        "user": "server_user",
        "services": "server_services",
        "note": "server_note",
        "privileged_provider": "privileged_access_provider",
        "privileged_url": "privileged_access_url",
        "privileged_hint": "privileged_access_hint",
        "proxy_id": "proxy_id",
        "maintenance_until": "maintenance_until",
        "maintenance_reason": "maintenance_reason",
        "tags": "tags",
        "owner": "resource_owner",
        "environment": "environment",
    }
    result = {}
    for source, target in mapping.items():
        value = form.get(source)
        if value not in (None, "") or (not partial and source in form):
            result[target] = value
    for source, target in (("vip", "server_vip"), ("nosudo", "server_nosudo"), ("maintenance", "maintenance_enabled")):
        value = _optional_bool(form.get(source))
        if value is not None:
            result[target] = value
    if form.get("clear_tags") == "true":
        result["tags"] = {}
    return result


def create_app(config=None):
    from authlib.integrations.base_client import OAuthError
    from authlib.integrations.flask_client import OAuth
    from flask import Flask, Response, abort, g, jsonify, redirect, render_template_string, request, send_file, session, url_for
    from joserfc.errors import JoseError
    from requests.exceptions import RequestException
    from werkzeug.exceptions import HTTPException

    from isolate_oidc import identity_provider_config, normalize_identity_claims, read_client_secret
    from isolate_identity import IdentityError
    from isolate_connection_auth import ConnectionDenied
    config = config or load_config()
    provider = identity_provider_config(config)
    config["keycloak"] = provider
    generic_oidc = provider.get("provider") == "oidc"
    app = Flask(__name__)
    app.secret_key = _secret_key(config)
    app.config["ISOLATE_DEFAULT_LOCALE"] = str(config.get("dashboard", {}).get("default_locale") or "en").lower()
    app.config["MAX_CONTENT_LENGTH"] = int(config.get("dashboard", {}).get("max_request_bytes", 1048576))
    app.extensions["isolate_build_info"] = get_build_info(config, _DASHBOARD_STARTED_AT)
    from isolate_error_ui import render_error_page
    from isolate_recordings import RecordingError

    def russian_error_page(title, detail, *, diagnostic=""):
        diagnostics = (
            f'<details><summary>Технические сведения</summary><p>{html.escape(diagnostic)}</p></details>'
            if diagnostic else ""
        )
        return (
            '<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<title>{title}</title><h1>{title}</h1><p>{detail}</p><p>ID запроса: {request_id}</p>{diagnostics}</html>'
        ).format(
            title=html.escape(title), detail=html.escape(detail), request_id=g.request_id, diagnostics=diagnostics,
        )

    def is_browser_page():
        return (not request.path.startswith(("/api/", "/export/", "/raw/"))
                and request.path != "/me/history/export"
                and not request.path.endswith((".json", ".txt")))

    def browser_error_response(error):
        response = error.get_response()
        response.set_data(render_error_page(error.code, _dashboard_locale(config), g.request_id))
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        if error.code == 400 and is_browser_page():
            return browser_error_response(error)
        browser_errors = {
            400: ("Проверьте данные", "Проверьте заполненные поля и повторите действие."),
            401: ("Требуется вход", "Войдите в Isolate и повторите действие."),
            403: ("Доступ запрещён", "Проверьте условия доступа или обратитесь к администратору."),
            404: ("Страница не найдена", "Проверьте адрес или вернитесь в каталог ресурсов."),
            409: ("Не удалось выполнить действие", "Обновите страницу и проверьте текущее состояние."),
            413: ("Слишком большой запрос", "Сократите объём данных и повторите действие."),
        }
        if (error.code not in browser_errors or request.path.startswith("/api/") or request.path.endswith(".json")
                or _dashboard_locale(config) != "ru"):
            return error
        title, detail = browser_errors[error.code]
        description = str(error.description or "") if error.description != type(error).description else ""
        if re.search(r"[А-ЯЁа-яё]", description):
            detail, description = description, ""
        response = error.get_response()
        response.set_data(russian_error_page(title, detail, diagnostic=description))
        return response

    @app.errorhandler(RecordingError)
    def recording_unavailable(error):
        if not request.path.startswith("/api/") and _dashboard_locale(config) == "ru":
            return russian_error_page("Запись пока недоступна", "Isolate не смог проверить целостность записи."), 503
        return '<h1>Recording temporarily unavailable</h1><p>Evidence could not be verified. Request ID: {}</p>'.format(g.request_id), 503
    oauth = OAuth(app)

    @app.before_request
    def assign_request_id():
        g.request_id = secrets.token_hex(16)

    @app.after_request
    def attach_request_id(response):
        response.headers["X-Request-ID"] = g.request_id
        if request.path.startswith(("/api/", "/docs", "/me/profile", "/me/terminal", "/raw/", "/replay/", "/workspace", "/ssh/authorize")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Dashboard request failed: request_id=%s method=%s path=%s", g.request_id, request.method, request.path)
        if is_browser_page():
            return browser_error_response(error)
        if not request.path.startswith("/api/") and _dashboard_locale(config) == "ru":
            return russian_error_page("Ошибка на стороне Isolate", "Если ошибка повторится, сообщите ID запроса администратору."), 500
        return '<h1>Internal Server Error</h1><p>Request ID: {}</p>'.format(g.request_id), 500

    issuer = (config.get("keycloak", {}).get("issuer") or "").rstrip("/")
    oauth.register(
        name="keycloak",
        client_id=config.get("keycloak", {}).get("client_id"),
        client_secret=read_client_secret(provider),
        server_metadata_url=issuer + "/.well-known/openid-configuration",
        client_kwargs={
            "scope": " ".join(config.get("keycloak", {}).get("scopes") or ["openid", "profile", "email"]),
            "code_challenge_method": "S256",
            "verify": provider.get("ca_file") or provider.get("ca_bundle") or provider.get("tls_verify", True),
            "default_timeout": (
                float(config.get("keycloak", {}).get("http_connect_timeout", 2)),
                float(config.get("keycloak", {}).get("http_read_timeout", 3)),
            ),
        },
    )

    def current_identity():
        identity = session.get("identity")
        if not identity:
            return None
        if identity.get("exp") and int(identity["exp"]) <= int(time.time()):
            session.clear()
            return None
        if (identity.get("raw_claims") or {}).get("iss") not in (None, provider.get("issuer")):
            session.clear()
            return None
        if provider.get("issuer"):
            from isolate_identity_binding import ensure_provider_binding
            try:
                ensure_provider_binding(config, redis_client(config))
            except (IdentityError, ConnectionDenied):
                session.clear()
                return None
        if generic_oidc:
            from isolate_runtime import Runtime
            try:
                identity = Runtime(config, redis=redis_client(config)).authenticate(browser_token() or "")
                session["identity"] = identity
                return identity
            except (IdentityError, ConnectionDenied):
                session.clear()
                return None
        from isolate_governance import check_governance_access
        try:
            check_governance_access(redis_client(config), identity)
        except IdentityError:
            session.clear()
            return None
        security = config.get("identity_security", {})
        if any(security.get(name, {}).get("enabled") for name in ("backchannel_logout", "introspection", "membership")):
            from isolate_identity_security import refresh_identity
            try:
                identity = refresh_identity(redis_client(config), config, identity, token=browser_token())
                session["identity"] = identity
            except IdentityError:
                session.clear()
                return None
        return identity

    def browser_token():
        key = session.get("runtime_session")
        if not key:
            return None
        value = redis_client(config).get("isolate_browser_" + key)
        if not value:
            return None
        record = json.loads(value)
        if record.get("sub") != (session.get("identity") or {}).get("keycloak_sub"):
            return None
        return record.get("token")

    def delegation_options():
        if not config.get("identity_security", {}).get("delegation", {}).get("enabled"):
            return {}
        return {"token": browser_token()}

    def require_admin():
        identity = current_identity()
        if identity is None:
            return redirect(url_for("login"))
        if not is_dashboard_admin(identity, config):
            abort(403)
        return identity

    def require_permission(permission, project=None):
        identity = current_identity()
        if identity is None:
            return redirect(url_for("login"))
        if not has_permission(identity, config, permission, project):
            abort(403)
        return identity

    def require_object_permission(identity, permission, project):
        if not is_dashboard_admin(identity, config) and (not project or not has_permission(identity, config, permission, project)):
            abort(404)

    def scoped_host(redis, server_id, identity, permission="inventory.read"):
        host = get_host(redis, server_id)
        if host is None:
            abort(404)
        require_object_permission(identity, permission, host.get("project_name"))
        return host

    def inventory_authorizer(identity):
        from isolate_permissions import authorize_inventory_change
        return lambda current, proposed: authorize_inventory_change(identity, config, current, proposed)

    def disable_protected_inventory_fields(body):
        fields = "ip|port|user|nosudo|vip|proxy_id|privileged_provider|privileged_url|privileged_hint"
        return re.sub(r'(<(?:input|select)\b[^>]*\bname="(?:' + fields + r')")', r'\1 disabled', body)

    def scoped_session(connection_id, identity):
        details = find_session(config["logging"]["base_path"], connection_id, archive_config=config,
            authorize_archive=lambda metadata: require_object_permission(identity, "audit.read", metadata.get("project")))
        if details is None:
            abort(404)
        require_object_permission(identity, "audit.read", (details.get("summary") or {}).get("project"))
        return details

    def raw_log_missing_message():
        if _dashboard_locale(config) == "ru":
            return "Для этой сессии нет сохранённого вывода терминала."
        return "No terminal output was recorded for this session."

    def replay_session(connection_id):
        identity = current_identity()
        if identity is None:
            return None, redirect("/login")
        def authorize(metadata):
            owned = (metadata.get("keycloak_sub") == identity.get("keycloak_sub") if metadata.get("keycloak_sub")
                     else metadata.get("username") == identity.get("username"))
            if not owned and not (metadata.get("project") and has_permission(identity, config, "audit.read", metadata["project"])):
                abort(404)
            return True
        details = find_session(config["logging"]["base_path"], connection_id, archive_config=config,
            authorize_archive=authorize)
        if details is None:
            abort(404)
        authorize(details.get("summary") or {})
        return identity, details

    def load_replay(details):
        return parse_raw_replay(
            details.get("raw_log_path"), max_bytes=int(config.get("replay", {}).get("max_bytes", 10485760))
        )

    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    from isolate_api import register_api_routes
    register_api_routes(app, config, lambda cfg: redis_client(cfg), current_identity, csrf_token, browser_token)
    from isolate_ssh_browser import register_ssh_browser_routes
    register_ssh_browser_routes(app, config, lambda cfg: redis_client(cfg), current_identity, csrf_token, browser_token)
    from isolate_workspace_ui import register_workspace_routes
    register_workspace_routes(app, config, current_identity, csrf_token)

    def validate_csrf():
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token")
        if not expected or not supplied or not secrets.compare_digest(str(supplied), str(expected)):
            abort(403)

    def require_mutation_confirmation():
        if config.get("dashboard", {}).get("require_mutation_confirmation", True):
            if request.form.get("confirm") != "true":
                raise ValueError("explicit confirmation is required")

    def require_manual_policy_edit():
        if config.get("policy_as_code", {}).get("enforce_git", False):
            raise ValueError("manual policy editing is disabled because enforced GitOps is active")

    def audit_admin(action, admin, outcome, details=None):
        record = {
            "event": "dashboard_user_action" if (details or {}).get("self_service") else "dashboard_admin_action",
            "ts": time.time(),
            "action": action,
            "username": admin.get("username"),
            "keycloak_sub": admin.get("keycloak_sub"),
            "outcome": outcome,
            "source": "isolate-dashboard",
        }
        record.update(details or {})
        prepare_and_dispatch(record, config.get("logging", {}))

    def notify_dashboard(redis, event_name, record, admin, extra=None):
        try:
            result = notify_access_event(config, event_name, record, actor=admin, extra=extra)
        except NotificationError as exc:
            set_notification_status(redis, record.get("id"), {"ok": False, "errors": [str(exc)], "sent": []})
            return {"level": "error", "text": "Action completed, but notification failed: {}".format(exc)}
        set_notification_status(redis, record.get("id"), {"ok": not bool(result.get("errors")), "errors": result.get("errors") or [], "sent": result.get("sent") or []})
        if result.get("errors"):
            return {"level": "warning", "text": "Action completed with notification warning: {}".format("; ".join(result["errors"]))}
        return None

    @app.route("/health")
    def health():
        result = run_health_checks(config)
        public_result = {
            "ok": result["ok"],
            "status": result["status"],
            "checks": {name: {"ok": bool(check.get("ok"))} for name, check in result["checks"].items()},
        }
        response = jsonify(public_result)
        response.status_code = 200 if result["ok"] else 503
        return response

    def status_filter_links(current):
        statuses = [("all", None), ("pending", "pending"), ("approved", "approved"), ("denied", "denied"), ("cancelled", "cancelled"), ("revoked", "revoked")]
        links = []
        for label, value in statuses:
            href = "/access" if value is None else "/access?status={}".format(value)
            text = "<strong>{}</strong>".format(label) if current == value else html.escape(label)
            links.append('<a href="{}">{}</a>'.format(href, text))
        return " ".join(links)

    def access_table(rows, token, access_cfg, identity):
        default_ttl = html.escape(str(access_cfg.get("default_ttl", "2h")))
        header = (
            "<th>id</th><th>status</th><th>user</th><th>project</th><th>host</th><th>ticket</th>"
            "<th>remote_user</th><th>sudo</th><th>reason</th><th>decision</th><th>start (UTC)</th><th>requested end (UTC)</th><th>expires (UTC)</th><th>grant</th><th>comments</th><th>notify</th><th>actions</th>"
        )
        body = ""
        for row in rows:
            revoke_form = ""
            cells = [
                html.escape(str(row.get("id") or "")),
                html.escape(str(row.get("status") or "")),
                html.escape(str(row.get("requester") or "")),
                html.escape(str(row.get("project") or "")),
                html.escape(str(row.get("host") or "")),
                html.escape(str(row.get("ticket") or "")),
                html.escape(str(row.get("remote_user") or "")),
                html.escape(str(row.get("sudo_mode") or "")),
                html.escape(str(row.get("reason") or "")),
                html.escape(str(row.get("decision_reason") or "")),
                html.escape(_format_access_time(row.get("starts_at"))),
                html.escape(_format_access_time(row.get("ends_at"))),
                html.escape(_format_access_time(row.get("expires_at"))),
                html.escape(str(row.get("grant_id") or "")),
                html.escape("; ".join("{}: {}".format(c.get("username") or "", c.get("text") or "") for c in row.get("comments") or [])),
                html.escape(str((row.get("notification_status") or {}).get("ok", ""))),
            ]
            actions = ""
            if row.get("status") == "pending":
                request_id = html.escape(str(row.get("id") or ""))
                remote_user = html.escape(str(row.get("remote_user") or ""))
                sudo_mode = html.escape(str(row.get("sudo_mode") or ""))
                actions = """
<form class="inline" method="post">
  <input type="hidden" name="csrf_token" value="{token}">
  <input type="hidden" name="id" value="{request_id}">
  <input type="hidden" name="action" value="approve">
  <input name="ttl" value="{default_ttl}" size="5" title="TTL">
  <input name="starts_at" value="{starts_at}" placeholder="start: ISO time +timezone" size="25">
  <input name="remote_user" value="{remote_user}" placeholder="remote_user" size="10">
  <input name="sudo_mode" value="{sudo_mode}" placeholder="sudo_mode" size="8">
  <input name="comment" placeholder="comment" size="12">
  <label><input type="checkbox" name="confirm" value="true" required> confirm</label>
  <button type="submit">Approve</button>
</form>
<form class="inline" method="post">
  <input type="hidden" name="csrf_token" value="{token}">
  <input type="hidden" name="id" value="{request_id}">
  <input type="hidden" name="action" value="deny">
  <input name="reason" placeholder="reason" size="12">
  <input name="comment" placeholder="comment" size="12">
  <label><input type="checkbox" name="confirm" value="true" required> confirm</label>
  <button type="submit">Deny</button>
</form>""".format(
                    token=html.escape(token),
                    request_id=request_id,
                    default_ttl=default_ttl,
                    remote_user=remote_user,
                    sudo_mode=sudo_mode,
                    starts_at=html.escape(_format_access_time(row.get("starts_at")), quote=True),
                )
            else:
                request_id = html.escape(str(row.get("id") or ""))
                actions = """
<form class="inline" method="post">
  <input type="hidden" name="csrf_token" value="{token}">
  <input type="hidden" name="id" value="{request_id}">
  <input type="hidden" name="action" value="repeat">
  <input name="reason" placeholder="reason" size="14">
  <input name="ticket" placeholder="ticket" size="10">
  <button type="submit">Request again</button>
</form>""".format(token=html.escape(token), request_id=request_id)
                if row.get("status") == "approved":
                    revoke_form = '<form class="inline" method="post"><input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="id" value="{}"><input type="hidden" name="action" value="revoke"><input name="reason" placeholder="revocation reason"><label><input type="checkbox" name="confirm" value="true" required> confirm</label><button>Revoke access</button></form>'.format(html.escape(token), request_id)
                    actions += revoke_form
            if not has_permission(identity, config, "access.approve", row.get("project") or ""):
                actions = ""
            elif not is_dashboard_admin(identity, config) and row.get("status") != "pending":
                actions = revoke_form
            body += "<tr>{}<td>{}</td></tr>".format("".join("<td>{}</td>".format(cell) for cell in cells), actions)
        return "<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(header, body)

    @app.route("/login")
    def login():
        _dashboard_locale(config)
        redirect_uri = config.get("dashboard", {}).get("public_url", "").rstrip("/") + url_for("callback")
        try:
            options = {}
            if generic_oidc:
                from isolate_oidc_web import configure_browser_provider
                configure_browser_provider(oauth.keycloak, provider)
            if request.args.get("step_up") == "true":
                step_up = config.get("identity_security", {}).get("step_up", {})
                if step_up.get("enabled"):
                    options = {"acr_values": " ".join(step_up.get("acr_values") or []),
                               "max_age": int(step_up.get("max_age_seconds", 300)), "prompt": "login"}
            return oauth.keycloak.authorize_redirect(redirect_uri, **options)
        except (RequestException, IdentityError) as exc:
            return identity_provider_unavailable(exc)

    def identity_provider_unavailable(error):
        app.logger.warning("OIDC provider unavailable: request_id=%s error_type=%s", g.request_id, type(error).__name__)
        if _dashboard_locale(config) == "ru":
            return russian_error_page("Служба входа временно недоступна",
                                      "Попробуйте войти ещё раз через несколько секунд."), 503, {"Retry-After": "10"}
        return '<h1>Sign-in temporarily unavailable</h1><p>Please retry sign-in shortly.</p><p>Request ID: {}</p>'.format(g.request_id), 503, {"Retry-After": "10"}

    @app.route("/auth/callback")
    def callback():
        locale = _dashboard_locale(config)
        russian = locale == "ru"
        try:
            if generic_oidc:
                from isolate_oidc_web import configure_browser_provider
                configure_browser_provider(oauth.keycloak, provider)
            token = oauth.keycloak.authorize_access_token()
        except (RequestException, IdentityError) as exc:
            return identity_provider_unavailable(exc)
        except (OAuthError, JoseError) as exc:
            error_code = str(getattr(exc, "error", "") or "unknown")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", error_code):
                error_code = "unknown"
            app.logger.warning("OIDC sign-in rejected: request_id=%s error_type=%s error_code=%s", g.request_id, type(exc).__name__, error_code)
            abort(401, description="Не удалось подтвердить вход. Откройте страницу входа и попробуйте ещё раз."
                  if russian else "Sign-in could not be verified. Please start a new sign-in.")
        claims = token.get("userinfo") or {}
        if not isinstance(claims, dict) or not claims:
            abort(401, description="Служба входа не передала подтверждённые сведения об учётной записи."
                  if russian else "Keycloak did not return verified OIDC claims")
        if generic_oidc:
            from isolate_identity import verify_jwt_claims
            from isolate_identity_binding import ensure_provider_binding
            try:
                if not token.get("id_token"):
                    raise IdentityError("OIDC sign-in requires a verified ID token")
                verified = verify_jwt_claims(token["id_token"], dict(provider, expected_audience=provider.get("client_id"), token_kind="id_token"))
                if verified.get("sub") != claims.get("sub"):
                    raise IdentityError("OIDC browser subject mismatch")
                from isolate_runtime import Runtime
                selected = token.get(provider.get("token_kind", "id_token"))
                identity = Runtime(config, redis=redis_client(config)).authenticate(selected or "")
                if identity.get("oidc_sub") != verified.get("sub"):
                    raise IdentityError("OIDC access token and ID token subjects differ")
            except (IdentityError, ConnectionDenied):
                abort(401, description="Не удалось проверить вход через OIDC. Обратитесь к администратору Isolate."
                      if russian else "OIDC sign-in could not be verified or the provider is not bound")
        else:
            identity = normalize_claims(claims)
            from isolate_identity_binding import ensure_provider_binding
            try:
                ensure_provider_binding(config, redis_client(config))
            except IdentityError:
                abort(401, description="Служба входа не соответствует настройкам этого бастиона. Обратитесь к администратору."
                      if russian else "Identity provider binding does not match this installation")
        from isolate_governance import check_governance_access
        try:
            check_governance_access(redis_client(config), identity)
        except IdentityError:
            abort(403, description="Вход в Isolate для этой учётной записи приостановлен. Обратитесь к администратору."
                  if russian else 'Access lifecycle policy prevents sign-in')
        if not is_dashboard_admin(identity, config) and not is_self_service_user(identity, config) and not role_names(identity, config):
            if russian:
                abort(403, description="Для этой учётной записи нет доступа к порталу Isolate. Обратитесь к администратору.")
            abort(403)
        return_to = session.get("return_to")
        session.clear()
        session["dashboard_locale"] = locale
        session["identity"] = identity
        from isolate_investigations import identity_session_reference
        audit_admin('login', identity, 'success', {'event': 'identity_login',
            'identity_session_sha256': identity_session_reference(identity)})
        # Flask cookies are signed, not encrypted. Keep bearer credentials only
        # in the private server-side store, keyed by an opaque session handle.
        if generic_oidc or config.get("api", {}).get("enabled") or any(config.get("identity_security", {}).get(name, {}).get("enabled") for name in ("introspection", "delegation")):
            kind = config.get("keycloak", {}).get("token_kind", "id_token")
            bearer_token = token.get(kind)
            if bearer_token and identity.get("exp"):
                handle = secrets.token_urlsafe(32)
                redis_client(config).set("isolate_browser_" + handle, json.dumps({"token": bearer_token, "sub": identity.get("keycloak_sub")}),
                                        ex=max(1, int(identity["exp"]) - int(time.time())))
                session["runtime_session"] = handle
        if isinstance(return_to, str) and re.fullmatch(r"(?:/me/terminal(?:/[0-9]{1,20})?(?:\?view=window)?|/ssh/authorize\?code=[A-Z2-7-]{12,14}|/workspace(?:/admin)?)", return_to):
            return redirect(return_to)
        if config.get("api", {}).get("enabled") and config.get("dashboard", {}).get("workspace_enabled", True):
            return redirect("/workspace")
        return redirect(url_for("index") if is_dashboard_admin(identity, config) else "/me")

    @app.route("/logout")
    def logout():
        locale = _dashboard_locale(config)
        identity = session.get('identity')
        if isinstance(identity, dict):
            from isolate_investigations import identity_session_reference
            audit_admin('logout', identity, 'closed', {'event': 'identity_logout',
                'identity_session_sha256': identity_session_reference(identity)})
        handle = session.get("runtime_session")
        if handle:
            redis_client(config).delete("isolate_browser_" + handle)
        session.clear()
        session["dashboard_locale"] = locale
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        identity = current_identity()
        if identity and not is_dashboard_admin(identity, config) and (is_self_service_user(identity, config) or role_names(identity, config)):
            return redirect("/me")
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        from isolate_dashboard_ui import render_overview
        body = render_overview(config, redis, csrf_token(), admin)
        page_config = dict(config, dashboard=dict(config.get("dashboard", {}), refresh_seconds=0))
        return _html("Isolate Dashboard", body, config=page_config)

    @app.get("/dashboard/overview-fragment")
    def dashboard_overview_fragment():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        from isolate_dashboard_ui import render_overview_fragment
        response = Response(render_overview_fragment(config, redis_client(config), csrf_token(), admin),
                            mimetype="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/settings")
    def platform_settings():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        from isolate_dashboard_ui import render_settings
        return _html("Settings", render_settings(config), config=config)

    @app.route("/jobs", methods=["GET", "POST"])
    def jobs_console():
        from isolate_jobs import _runbook_submission_plan
        from isolate_jobs_ui import render_jobs_page, runbook_parameters
        from isolate_workspace_ui import campaign_navigation_allowed
        from isolate_workflow_ui import workflow_value

        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        locale = _dashboard_locale(config)
        runbook_cfg = config.get("runbooks", {}) or {}
        definitions = {item["id"]: item for item in list_runbooks(config, store=redis)}
        available = {}
        if runbook_cfg.get("enabled"):
            for item in definitions.values():
                class_cfg = runbook_cfg.get(item["class"], {}) or {}
                if item["class"] == "operational" and not class_cfg.get("enabled"):
                    continue
                if set(admin.get("groups") or []) & set(class_cfg.get("allowed_groups") or []):
                    available[item["id"]] = item
        can_stage = campaign_navigation_allowed(admin, config)
        view = request.args.get("view", "runs")
        if view not in ("runs", "runbooks", "campaigns") or (view == "campaigns" and not can_stage):
            view = "runs"
        selected = available.get(request.args.get("runbook")) if view == "runbooks" else None
        notice = None
        review = None
        max_timeout = int((config.get("command_execution") or {}).get("max_timeout", 900))
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            try:
                if action != "preview_runbook":
                    require_mutation_confirmation()
                if action in ("queue_runbook", "preview_runbook"):
                    previewing = action == "preview_runbook"
                    runbook_id = request.form.get("runbook_id")
                    selected = available.get(runbook_id)
                    if previewing:
                        view = "runbooks"
                        if selected is None:
                            raise JobError("this runbook is not available for your groups")
                    parameters = runbook_parameters(request.form, _parse_json_object)
                    timeout = request.form.get("timeout") or None
                    timeout = int(timeout) if timeout else None
                    host_ids = _split_values(request.form.get("host_ids"))
                    project_selector = request.form.get("project") or None
                    tag_selector = request.form.get("tags") or None
                    if host_ids and (project_selector or tag_selector):
                        raise JobError("use host IDs or project/tags selectors, not both")
                    if not host_ids:
                        if not (project_selector or tag_selector):
                            raise JobError("an explicit host, project, or tag selector is required")
                        host_ids = [host["server_id"] for host in list_hosts(redis, project=project_selector, tags=tag_selector)]
                    if previewing:
                        rendered, planned, _ = _runbook_submission_plan(
                            redis, config, admin, runbook_id, host_ids, parameters=parameters, timeout=timeout,
                            **delegation_options(),
                        )
                        timeout = timeout or int(rendered["runbook"]["default_timeout"])
                        if not 1 <= timeout <= max_timeout:
                            raise JobError("timeout is outside the configured range")
                        review = rendered["runbook"], rendered["parameters"], timeout, planned, rendered["command"]
                    else:
                        definition_sha256 = request.form.get("definition_sha256") or None
                        if runbook_id not in BUILTIN_RUNBOOKS and not definition_sha256:
                            raise JobError("Сначала проверьте план запуска регламента." if locale == "ru"
                                           else "Review the custom runbook plan before queueing it.")
                        result = create_runbook_fleet(
                            redis, config, admin, runbook_id, host_ids, parameters=parameters,
                            timeout=timeout, confirmed=True, definition_sha256=definition_sha256,
                            **delegation_options(),
                        )
                        audit_admin("runbook_fleet_queue", admin, "success", {
                            "fleet_id": result["fleet_id"], "job_count": result["count"],
                        })
                        notice = {"level": "success", "text": _message("Queued fleet {} with {} job(s).", locale).format(
                            result["fleet_id"], result["count"])}
                        view = "runs"
                elif action == "retry_fleet":
                    fleet_id = str(request.form.get("fleet_id") or "")
                    summary = next((row for row in fleet_progress(list_jobs(redis, limit=10000)) if row["fleet_id"] == fleet_id), None)
                    if summary is None:
                        raise JobError("fleet was not found")
                    retried = [retry_job(redis, config, job_id, admin, **delegation_options()) for job_id in summary["failed_job_ids"]]
                    if not retried:
                        raise JobError("fleet has no failed hosts to retry")
                    audit_admin("job_fleet_retry", admin, "success", {"fleet_id": fleet_id, "job_count": len(retried)})
                    notice = {"level": "success", "text": _message("Retried {} failed host(s) in fleet {}.", locale).format(len(retried), fleet_id)}
                else:
                    raise JobError("unknown jobs action")
            except (JobError, HostValidationError, ValueError) as exc:
                audit_admin("jobs_action", admin, "denied", {"error": str(exc)})
                notice = {"level": "error", "text": str(exc)}
                if action == "queue_runbook" and selected:
                    view = "runbooks"

        all_jobs = list_jobs(redis, limit=10000)
        rows = filter_jobs(
            all_jobs,
            status=request.args.get("status") or None,
            user=request.args.get("user") or None,
            project=request.args.get("project") or None,
            host=request.args.get("host") or None,
            job_type=request.args.get("type") or None,
        )
        query = request.args.get("q", "").strip().casefold()
        if query:
            titles = {identifier: (item["title"], workflow_value(config, item["title"])) for identifier, item in definitions.items()}
            rows = [job for job in rows if any(query in str(value or "").casefold() for value in (
                job.get("id"), job.get("runbook_id"), job.get("project"), *titles.get(job.get("runbook_id"), ()),
            ))]
        from collections import Counter
        body = render_jobs_page(
            locale=locale, view=view, jobs=rows[:int(config.get("dashboard", {}).get("jobs_max_results") or 250)],
            fleets=fleet_progress(all_jobs) if view == "runs" else [], counts=Counter(job.get("status") for job in all_jobs),
            runbooks=definitions, available=list(available.values()), selected=selected, review=review,
            args=request.args, values=request.form, token=csrf_token(), max_timeout=max_timeout,
            can_stage=can_stage, format_time=_format_ts,
        )
        return _html("Jobs & Runbooks", body, config=config, notice=notice)

    @app.route("/job/<job_id>")
    def job_details(job_id):
        from isolate_jobs_ui import render_job_details

        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        job = get_job(redis_client(config), job_id)
        if job is None:
            abort(404)
        execution = config.get("command_execution") or {}
        output = read_job_output(
            job, max_bytes=int(execution.get("max_return_bytes", 262144)),
            jobs_path=execution.get("jobs_path", "/opt/auth/jobs"), job_id=job_id,
        )
        locale = _dashboard_locale(config)
        explanation = ""
        investigation = ""
        if config.get("api", {}).get("enabled"):
            from isolate_explain_api import explanation_panel
            explanation = explanation_panel(job.get("host_id"), "ssh", action=job.get("policy_action") or "command",
                                            russian=locale == "ru")
            if config.get("audit_index", {}).get("enabled"):
                investigation = _ui('<p><a href="/investigations?kind=job&amp;id={}">Follow related evidence</a></p>', locale).format(
                    html.escape(urllib.parse.quote(job_id, safe=""), quote=True))
        body = render_job_details(job, output, locale=locale, token=csrf_token(), format_time=_format_ts,
                                  explanation=explanation, investigation=investigation)
        return _html("Job {}".format(job_id), body, config=config)

    @app.route("/job/<job_id>/cancel", methods=["POST"])
    def job_cancel(job_id):
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        validate_csrf()
        try:
            require_mutation_confirmation()
            record = request_job_cancel(redis_client(config), job_id, admin)
            if record is None:
                abort(404)
            audit_admin("job_cancel", admin, "success", {"job_id": job_id})
        except (JobError, ValueError) as exc:
            audit_admin("job_cancel", admin, "denied", {"job_id": job_id, "error": str(exc)})
            abort(409, description=str(exc))
        return redirect(url_for("job_details", job_id=job_id))

    @app.route("/job/<job_id>/retry", methods=["POST"])
    def job_retry(job_id):
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        validate_csrf()
        try:
            require_mutation_confirmation()
            record = retry_job(redis_client(config), config, job_id, admin, **delegation_options())
            audit_admin("job_retry", admin, "success", {"job_id": record["id"], "retry_of": job_id})
        except (JobError, ValueError) as exc:
            audit_admin("job_retry", admin, "denied", {"job_id": job_id, "error": str(exc)})
            abort(409, description=str(exc))
        return redirect(url_for("job_details", job_id=record["id"]))

    @app.route("/alerts", methods=["GET", "POST"])
    def alert_center():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            try:
                require_mutation_confirmation()
                alert_id = request.form.get("alert_id")
                known = {row["id"] for row in collect_alerts(redis, config)}
                if alert_id not in known:
                    raise DashboardDataError("alert was not found")
                state = update_alert_state(
                    redis, alert_id, admin, request.form.get("action"), comment=request.form.get("comment") or None
                )
                audit_admin("alert_{}".format(request.form.get("action")), admin, "success", {
                    "alert_id": alert_id, "status": state.get("status"),
                })
                notice = {"level": "success", "text": "Alert state updated."}
            except (DashboardDataError, ValueError) as exc:
                audit_admin("alert_action", admin, "denied", {"error": str(exc)})
                notice = {"level": "error", "text": str(exc)}
        rows = collect_alerts(
            redis,
            config,
            status=request.args.get("status") or None,
            kind=request.args.get("kind") or None,
            user=request.args.get("user") or None,
            project=request.args.get("project") or None,
        )
        all_rows = collect_alerts(redis, config)
        counts = {name: sum(1 for row in all_rows if row.get("status") == name) for name in ("open", "acknowledged", "resolved")}
        body = _ui("""<h1>Alert Center</h1><p class="page-lead">Session risk, failed jobs, and notification delivery failures in one operational queue.</p>
<div class="summary-list"><div class="summary-item"><strong>{open}</strong><span class="muted">Open</span></div><div class="summary-item"><strong>{acknowledged}</strong><span class="muted">acknowledged</span></div><div class="summary-item"><strong>{resolved}</strong><span class="muted">resolved</span></div><div class="summary-item"><strong>{total}</strong><span class="muted">total</span></div></div>
<form class="inline" method="get"><select name="status"><option value="">all statuses</option><option value="open">Open</option><option>acknowledged</option><option>resolved</option></select><select name="kind"><option value="">all kinds</option><option value="long_session">long session</option><option value="vip_session">VIP</option><option value="privileged_session">privileged</option><option value="unusual_source_ip">unusual source</option><option value="failed_job">failed job</option><option value="notification_delivery_failed">notification failure</option></select><input name="user" value="{user}" placeholder="user"><input name="project" value="{project}" placeholder="project"><button>Filter</button></form>""", _dashboard_locale(config)).format(
            total=len(all_rows), user=html.escape(request.args.get("user", "")), project=html.escape(request.args.get("project", "")), **counts
        )
        alert_rows = []
        for alert in rows:
            row = dict(alert)
            row["created"] = _format_ts(alert.get("created_at"))
            row["severity_badge"] = _ui('<span class="badge severity-{}">{}</span>', _dashboard_locale(config)).format(
                html.escape(str(alert.get("severity") or "medium")), html.escape(str(alert.get("severity") or "medium"))
            )
            row["message"] = alert.get("details")
            if alert.get("source_type") == "session":
                row["source_link"] = _ui('<a href="/session/{}">session</a>', _dashboard_locale(config)).format(html.escape(str(alert.get("source_id"))))
            elif alert.get("source_type") == "job":
                row["source_link"] = _ui('<a href="/job/{}">job {}</a>', _dashboard_locale(config)).format(html.escape(str(alert.get("source_id"))), html.escape(str(alert.get("source_id"))))
            else:
                row["source_link"] = _ui('<a href="/access?id={}">request {}</a>', _dashboard_locale(config)).format(html.escape(str(alert.get("source_id"))), html.escape(str(alert.get("source_id"))))
            buttons = []
            if alert.get("status") == "open":
                buttons.append(_ui('<button name="action" value="acknowledge" class="button-secondary">Acknowledge</button>', _dashboard_locale(config)))
            if alert.get("status") != "resolved":
                buttons.append(_ui('<button name="action" value="resolve">Resolve</button>', _dashboard_locale(config)))
            else:
                buttons.append(_ui('<button name="action" value="reopen" class="button-secondary">Reopen</button>', _dashboard_locale(config)))
            buttons.append(_ui('<button name="action" value="comment" class="button-secondary">Comment</button>', _dashboard_locale(config)))
            row["control"] = _ui('<form class="inline" method="post"><input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="alert_id" value="{}"><input name="comment" placeholder="optional comment">{}<label><input type="checkbox" name="confirm" value="true" required> confirm</label></form>', _dashboard_locale(config)).format(
                html.escape(csrf_token()), html.escape(alert["id"]), "".join(buttons)
            )
            row["comments_count"] = len(alert.get("comments") or [])
            alert_rows.append(row)
        body += _table(alert_rows, [
            ("created", "created"), ("severity_badge", "severity"), ("status", "status"), ("title", "alert"),
            ("username", "user"), ("project", "project"), ("host_id", "host"), ("message", "details"),
            ("source_link", "source"), ("comments_count", "comments"), ("control", "actions"),
        ]) if alert_rows else _ui('<div class="empty-state">No alerts match the selected filters.</div>', _dashboard_locale(config))
        return _html("Alert Center", body, config=config, notice=notice)

    @app.route("/policy/matrix", methods=["GET", "POST"])
    def access_matrix():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        grants = load_grants(redis)
        project_sets = load_project_sets(redis)
        hosts = list_hosts(redis)
        defaults = {**config.get("policy", {}), **config.get("ssh", {})}
        matrix = build_access_matrix(grants, project_sets, hosts, defaults=defaults)
        preview = None
        notice = None
        if request.method == "POST":
            validate_csrf()
            try:
                selector_type = request.form.get("selector_type")
                if selector_type not in ("project", "project_set", "project_glob"):
                    raise DashboardDataError("invalid selector type")
                candidate = {
                    "subject": request.form.get("subject"), "name": request.form.get("name"),
                    "replace_grant_id": request.form.get("replace_grant_id") or None,
                    selector_type: request.form.get("selector_value"),
                    "host": request.form.get("host") or None,
                    "remote_user": request.form.get("remote_user") or None,
                    "sudo_mode": request.form.get("sudo_mode") or "none",
                    "allowed_actions": _split_values(request.form.get("allowed_actions") or "ssh"),
                }
                preview = preview_grant_change(grants, project_sets, hosts, candidate, defaults=defaults)
            except (DashboardDataError, ValueError) as exc:
                notice = {"level": "error", "text": str(exc)}
        from isolate_access_admin_ui import render_access_matrix
        body = render_access_matrix(matrix, request.args, csrf_token(), _dashboard_locale(config),
                                    preview=preview, submitted=request.form if request.method == "POST" else None)
        return _html("Access Matrix", body, config=config, notice=notice)

    @app.route("/sessions/active")
    def active_sessions():
        admin = require_permission("sessions.read")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        rows = filter_projects(list_active_sessions(redis), admin, config, "sessions.read")
        token = csrf_token()
        termination_enabled = is_dashboard_admin(admin, config) and config.get("session_control", {}).get("terminate_enabled", False)
        for row in rows:
            if not row.get("server_name") and row.get("host_id"):
                host_record = get_host(redis, row.get("host_id"))
                if host_record is not None and has_permission(admin, config, "inventory.read", host_record.get("project_name") or ""):
                    row["server_name"] = host_record.get("server_name")
            row["started"] = _format_ts(row.get("started_at"))
            connection_id = html.escape(str(row.get("connection_id") or ""))
            username = str(row.get("username") or "")
            row["user_link"] = (_ui('<a href="/user/{}">{}</a>', _dashboard_locale(config)).format(urllib.parse.quote(username, safe=""), html.escape(username))
                                if is_dashboard_admin(admin, config) else html.escape(username))
            row["live"] = _ui('<a href="/session/{}/live">live</a>', _dashboard_locale(config)).format(connection_id)
            if termination_enabled:
                row["control"] = _ui("""
<form class="inline" method="post" action="/sessions/{connection_id}/terminate">
  <input type="hidden" name="csrf_token" value="{token}">
  <input type="hidden" name="confirm" value="true">
  <input name="reason" placeholder="reason" size="12">
  <button type="submit">Terminate</button>
</form>""", _dashboard_locale(config)).format(connection_id=connection_id, token=html.escape(token))
        return _html("Active Sessions", _ui("<h1>Active Sessions</h1>", _dashboard_locale(config)) + _table(rows, [
            ("started", "started"), ("duration_seconds", "duration_s"), ("user_link", "user"),
            ("project", "project"), ("host_id", "host"), ("server_name", "host name"), ("target_host", "target"),
            ("remote_user", "remote_user"), ("connection_id", "connection_id"), ("live", "view"), ("control", "control")
        ]), config=config)

    @app.route("/sessions/<connection_id>/terminate", methods=["POST"])
    def terminate_session(connection_id):
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        validate_csrf()
        if not config.get("session_control", {}).get("terminate_enabled", False):
            abort(403)
        try:
            require_mutation_confirmation()
            record = request_session_termination(
                redis_client(config), connection_id, admin, reason=request.form.get("reason") or None
            )
            audit_admin("session_terminate", admin, "requested", {"connection_id": connection_id})
        except (SessionControlError, ValueError) as exc:
            audit_admin("session_terminate", admin, "denied", {"connection_id": connection_id})
            return _html("Session Control", _ui("<h1>Session Control</h1>", _dashboard_locale(config)), config=config, notice={"level": "error", "text": str(exc)}), 409
        return redirect(url_for("active_sessions"))

    @app.route("/history")
    def history():
        from isolate_history import HistoryFilterError

        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        locale = _dashboard_locale(config)
        title = "Журнал сессий" if locale == "ru" else "Session Logs"
        try:
            rows = read_web_history(config, redis_client(config), admin, request.args)
        except RecordingError:
            raise
        except HistoryFilterError as exc:
            body = history_page(request.args, locale, title, error=exc)
            return _html("History", body, config=config), 400
        except ValueError as exc:
            abort(400, description=str(exc))
        add_history_recording_links(rows, config, locale)
        for row in rows:
            connection_id = row.get("connection_id") or row.get("session_id")
            username = str(row.get("username") or "")
            row["user_link"] = _ui('<a href="/user/{}">{}</a>', _dashboard_locale(config)).format(urllib.parse.quote(username, safe=""), html.escape(username))
            host_name = row.get("server_name") or row.get("target") or row.get("host_id") or "—"
            host_meta = " · ".join(str(value) for value in (row.get("host_id"), row.get("target"), row.get("remote_user"))
                                   if value and str(value) != str(host_name))
            host_label = "<strong>{}</strong>".format(html.escape(str(host_name)))
            if connection_id:
                host_label = '<a href="{}">{}</a>'.format(
                    html.escape(url_for("session_details", connection_id=connection_id)), host_label)
            row["details"] = host_label + '<span class="admin-meta font-mono">{}</span>'.format(html.escape(host_meta))
        results = _table(rows, [
            ("time", "time"), ("user_link", "user"), ("details", "host"), ("project", "project"),
            ("result", "result"), ("replay", "Recording"),
        ])
        return _html("History", history_page(request.args, locale, title, results=results, count=len(rows)), config=config)

    @app.route("/export/<kind>")
    def export_data(kind):
        admin = require_permission("inventory.read" if kind == "inventory" else "audit.read") if kind in ("inventory", "history") else require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        output_format = request.args.get("format", "csv")
        if kind == "inventory":
            try:
                rows = list_hosts(redis, project=request.args.get("project"), query=request.args.get("q"), tags=request.args.get("tags") or None)
                rows = filter_projects(rows, admin, config, "inventory.read", project_field="project_name")
            except HostValidationError as exc:
                abort(400, description=str(exc))
        elif kind == "grants":
            rows = list_grant_records(redis, project=request.args.get("project"))
        elif kind == "users":
            rows = list_user_profiles(config["logging"]["base_path"], archive_config=config)
        elif kind == "history":
            try:
                rows = read_web_history(config, redis, admin, request.args)
            except RecordingError:
                raise
            except ValueError as exc:
                abort(400, description=str(exc))
        elif kind == "access-matrix":
            matrix = build_access_matrix(
                load_grants(redis), load_project_sets(redis), list_hosts(redis),
                defaults={**config.get("policy", {}), **config.get("ssh", {})},
            )
            rows = flatten_access_matrix(matrix)
        else:
            abort(404)
        try:
            content, mimetype = render_export(rows, output_format)
        except ExportError:
            abort(400)
        response = Response(content, mimetype=mimetype)
        response.headers["Content-Disposition"] = "attachment; filename=isolate-{}.{}".format(kind, output_format)
        return response

    @app.route("/access", methods=["GET", "POST"])
    def access():
        admin = require_permission("access.read")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            request_id = request.form.get("id")
            target_request = get_access_request(redis, request_id)
            if target_request is None:
                abort(404)
            require_object_permission(admin, "access.approve" if action in ("approve", "deny", "revoke") else "access.read", target_request.get("project"))
            try:
                if not is_dashboard_admin(admin, config):
                    require_mutation_confirmation()
                if action == "approve":
                    ttl = parse_duration(request.form.get("ttl"), default=config.get("access", {}).get("default_ttl", "2h"))
                    max_ttl = parse_duration(config.get("access", {}).get("max_ttl", "24h"))
                    remote_user = request.form.get("remote_user") or None
                    sudo_mode = request.form.get("sudo_mode") or None
                    record, grant = approve_access_request(
                        redis,
                        request_id,
                        admin,
                        ttl,
                        remote_user=remote_user,
                        sudo_mode=sudo_mode,
                        max_ttl=max_ttl,
                        comment=request.form.get("comment") or None,
                        starts_at=request.form.get("starts_at") or None,
                        config=config,
                    )
                    notice = notify_dashboard(redis, "access_request_approved", record, admin, extra={"grant": grant})
                    notice = notice or {"level": "info", "text": "Access request approved"}
                elif action == "deny":
                    record = deny_access_request(redis, request_id, admin, reason=request.form.get("reason"), comment=request.form.get("comment") or None, config=config)
                    notice = notify_dashboard(redis, "access_request_denied", record, admin)
                    notice = notice or {"level": "info", "text": "Access request denied"}
                elif action == "repeat":
                    if not is_dashboard_admin(admin, config):
                        abort(403)
                    record = repeat_access_request(redis, request_id, admin, reason=request.form.get("reason") or None, ticket=request.form.get("ticket") or None, config=config,
                                                   admin_groups=config.get("dashboard", {}).get("admin_groups") or config.get("history", {}).get("admin_groups") or [])
                    notice = notify_dashboard(redis, "access_request_created", record, admin)
                    notice = notice or {"level": "info", "text": "Access request repeated"}
                elif action == "revoke":
                    require_mutation_confirmation()
                    record = revoke_access_request(redis, request_id, admin,
                        admin_groups=config.get("dashboard", {}).get("admin_groups") or config.get("history", {}).get("admin_groups") or [],
                        reason=request.form.get("reason") or None, config=config)
                    if record is None:
                        raise ValueError("access request was not found")
                    audit_admin("access_request_revoke", admin, "applied", {"access_request_id": request_id})
                    notice = notify_dashboard(redis, "access_request_revoked", record, admin) or {"level": "info", "text": "Access revoked"}
                else:
                    raise ValueError("unknown access action")
            except (AccessDenied, ValueError) as exc:
                notice = {"level": "error", "text": str(exc)}
        status = request.args.get("status")
        if status == "all":
            status = None
        rows = list_access_requests(
            redis,
            status=status,
            user=request.args.get("user") or None,
            project=request.args.get("project") or None,
            ticket=request.args.get("ticket") or None,
        )
        rows = filter_projects(rows, admin, config, "access.read")
        body = _ui("""
<h1>Access Requests</h1>
<form method="get">
  <input name="user" value="{user}" placeholder="user">
  <input name="project" value="{project}" placeholder="project">
  <input name="ticket" value="{ticket}" placeholder="ticket">
  <button type="submit">Filter</button>
</form>
<p>{links}</p>{table}
""", _dashboard_locale(config)).format(
            user=html.escape(request.args.get("user") or ""),
            project=html.escape(request.args.get("project") or ""),
            ticket=html.escape(request.args.get("ticket") or ""),
            links=status_filter_links(status),
            table=access_table(rows, csrf_token(), config.get("access", {}), admin),
        )
        return _html("Access Requests", body, config=config, notice=notice)

    @app.route("/inventory", methods=["GET", "POST"])
    def inventory():
        from isolate_inventory_ui import inventory_page

        admin = require_permission("inventory.read")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            if not has_permission(admin, config, "inventory.write"):
                abort(403)
            try:
                require_mutation_confirmation()
                if action == "add":
                    if not is_dashboard_admin(admin, config):
                        abort(403)
                    host = create_host(redis, _host_form_values(request.form), updated_by=admin.get("username"))
                    notice = {"level": "info", "text": _message("Host {} added", _dashboard_locale(config)).format(host.get("server_id"))}
                    audit_admin("host_add", admin, "applied", {"host_id": host.get("server_id")})
                elif action == "bulk_update":
                    host_ids = list(dict.fromkeys(
                        _split_values(request.form.get("host_ids")) + request.form.getlist("selected_host_id")
                    ))
                    if not host_ids or len(host_ids) > 200:
                        raise ValueError("between 1 and 200 host ids are required")
                    updates = _host_form_values(request.form, partial=True)
                    if not updates:
                        raise ValueError("at least one bulk update field is required")
                    for server_id in host_ids:
                        scoped_host(redis, server_id, admin, "inventory.write")
                    bulk_update_hosts(redis, host_ids, updates, updated_by=admin.get("username"), authorize=inventory_authorizer(admin))
                    changed = [str(host_id) for host_id in host_ids]
                    notice = {"level": "info", "text": _message("Updated hosts: {}", _dashboard_locale(config)).format(", ".join(changed))}
                    audit_admin("host_bulk_update", admin, "applied", {"host_ids": changed, "count": len(changed)})
                elif action == "connectivity_check":
                    host = scoped_host(redis, request.form.get("host_id"), admin, "inventory.write")
                    if not is_dashboard_admin(admin, config):
                        abort(403)
                    result = check_host(host, config, timeout=config.get("connectivity", {}).get("default_timeout", 3))
                    save_check(redis, result, ttl=config.get("connectivity", {}).get("result_ttl", 3600))
                    notice = {"level": "info" if result.get("ok") else "warning", "text": "Host {}: {}".format(host.get("server_id"), "reachable" if result.get("ok") else result.get("error"))}
                    audit_admin("host_connectivity_check", admin, "completed", {"host_id": host.get("server_id"), "ok": result.get("ok")})
                else:
                    raise ValueError("unknown inventory action")
            except (ConnectivityError, HostValidationError, ValueError) as exc:
                audit_admin("inventory_mutation", admin, "denied", {"action": action})
                notice = {"level": "error", "text": str(exc)}
        project = request.args.get("project") or None
        query = request.args.get("q") or None
        try:
            rows = list_hosts(redis, project=project, query=query, tags=request.args.get("tags") or None)
            rows = filter_projects(rows, admin, config, "inventory.read", project_field="project_name")
        except HostValidationError as exc:
            abort(400, description=str(exc))
        is_admin = is_dashboard_admin(admin, config)
        for row in rows:
            project_name = row.get("project_name") or ""
            last_check = get_last_check(redis, row.get("server_id"))
            row["connectivity"] = "unknown" if not last_check else ("reachable" if last_check.get("ok") else "failed")
            row["can_write"] = has_permission(admin, config, "inventory.write", project_name)
            row["can_audit"] = has_permission(admin, config, "audit.read", project_name)
        posted = request.form if notice and notice["level"] == "error" else None
        body = inventory_page(rows, request.args, _dashboard_locale(config), csrf_token(),
                              is_admin=is_admin, can_write=has_permission(admin, config, "inventory.write"), posted=posted)
        return _html("Inventory", body, config=config, notice=notice)

    @app.route("/inventory/<server_id>/edit", methods=["GET", "POST"])
    def inventory_edit(server_id):
        admin = require_permission("inventory.write")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        scoped_host(redis, server_id, admin, "inventory.write")
        notice = None
        if request.method == "POST":
            validate_csrf()
            try:
                require_mutation_confirmation()
                host = update_host(
                    redis,
                    server_id,
                    _host_form_values(request.form),
                    updated_by=admin.get("username"),
                    expected_revision=request.form.get("revision") or None,
                    authorize=inventory_authorizer(admin),
                )
                if host is None:
                    abort(404)
                audit_admin("host_update", admin, "applied", {"host_id": server_id})
                notice = {"level": "info", "text": "Host updated"}
            except (HostValidationError, ValueError) as exc:
                audit_admin("host_update", admin, "denied", {"host_id": server_id})
                notice = {"level": "error", "text": str(exc)}
        host = scoped_host(redis, server_id, admin, "inventory.write")
        body = _ui("""
<section class="admin-page admin-inventory">
<header class="admin-heading"><div><h1>Edit Host {server_id}</h1><p>{name}</p></div>
<a class="admin-button" href="/inventory">Inventory</a></header>
<form class="admin-panel" method="post">
<input type="hidden" name="csrf_token" value="{csrf}">
<input type="hidden" name="revision" value="{revision}">
<fieldset><legend>Connection</legend><div class="admin-fields">
  <label>Project <input name="project" value="{project}" required></label>
  <label>Name <input name="name" value="{name}" required></label>
  <label>IP <input name="ip" value="{ip}" required></label>
  <label>Port <input name="port" value="{port}" type="number" min="1" max="65535" required></label>
  <label>User <input name="user" value="{user}" required></label>
</div></fieldset>
<fieldset><legend>Host metadata</legend><div class="admin-fields">
  <label>Services <input name="services" value="{services}"></label>
  <label>Tags <input name="tags" value="{tags}" placeholder="env=prod,owner=payments"></label>
  <label>Owner <input name="owner" value="{owner}"></label>
  <label>Environment <input name="environment" value="{environment}"></label>
  <label>Note <input name="note" value="{note}"></label>
</div></fieldset>
<details class="admin-disclosure"><summary>Maintenance</summary><div class="admin-fields">
  <label>Maintenance <select name="maintenance"><option value="false">false</option><option value="true" {maintenance_selected}>true</option></select></label>
  <label>Until <input name="maintenance_until" value="{maintenance_until}"></label>
  <label>Reason <input name="maintenance_reason" value="{maintenance_reason}"></label>
</div></details>
<details class="admin-disclosure"><summary>Privileged access and proxy</summary><div class="admin-fields">
  <label>VIP <select name="vip"><option value="false">false</option><option value="true" {vip_selected}>true</option></select></label>
  <label>No sudo <select name="nosudo"><option value="false">false</option><option value="true" {nosudo_selected}>true</option></select></label>
  <label>Provider <input name="privileged_provider" value="{provider}"></label>
  <label>URL <input name="privileged_url" value="{provider_url}"></label>
  <label>Privileged hint <input name="privileged_hint" value="{provider_hint}"></label>
  <label>Proxy ID <input name="proxy_id" value="{proxy_id}"></label>
</div></details>
<div class="admin-toolbar inventory-edit-submit">
  <label><input type="checkbox" name="confirm" value="true" required> confirm update</label>
  <button class="admin-primary" type="submit">Save</button>
</div></form></section>
""", _dashboard_locale(config)).format(
            server_id=html.escape(str(server_id)), csrf=html.escape(csrf_token()), revision=html.escape(str(host.get("_revision") or "")),
            project=html.escape(str(host.get("project_name") or "")), name=html.escape(str(host.get("server_name") or "")),
            ip=html.escape(str(host.get("server_ip") or "")), port=html.escape(str(host.get("server_port") or 22)),
            user=html.escape(str(host.get("server_user") or "")), services=html.escape(str(host.get("server_services") or "")),
            tags=html.escape(str(host.get("tags_display") or ""), quote=True),
            owner=html.escape(str(host.get("resource_owner") or ""), quote=True), environment=html.escape(str(host.get("environment") or ""), quote=True),
            note=html.escape(str(host.get("server_note") or "")), vip_selected="selected" if host.get("server_vip") else "",
            nosudo_selected="selected" if host.get("server_nosudo") else "", provider=html.escape(str(host.get("privileged_access_provider") or "")),
            provider_url=html.escape(str(host.get("privileged_access_url") or "")), provider_hint=html.escape(str(host.get("privileged_access_hint") or "")),
            proxy_id=html.escape(str(host.get("proxy_id") or "")),
            maintenance_selected="selected" if host.get("maintenance_enabled") else "",
            maintenance_until=html.escape(str(host.get("maintenance_until") or "")),
            maintenance_reason=html.escape(str(host.get("maintenance_reason") or "")),
        )
        if not is_dashboard_admin(admin, config):
            body = disable_protected_inventory_fields(body)
        return _html("Edit Host", body, config=config, notice=notice)

    @app.route("/announcements", methods=["GET", "POST"])
    def announcements():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            try:
                require_mutation_confirmation()
                if action == "add":
                    active_count = len(list_announcements(redis, active_only=True))
                    maximum = int(config.get("announcements", {}).get("max_active", 100))
                    if active_count >= maximum:
                        raise AnnouncementError("active announcement limit reached")
                    ttl = parse_duration(request.form.get("ttl")) if request.form.get("ttl") else None
                    record = create_announcement(
                        redis, request.form.get("text"), admin.get("username"),
                        project=request.form.get("project") or None, host=request.form.get("host") or None,
                        severity=request.form.get("severity") or "info",
                        expires_at=int(time.time()) + ttl if ttl else None,
                    )
                    audit_admin("announcement_add", admin, "applied", {"announcement_id": record.get("id")})
                    notice = {"level": "info", "text": "Announcement published"}
                elif action == "remove":
                    result = delete_announcement(redis, request.form.get("id"))
                    audit_admin("announcement_remove", admin, "applied", {"announcement_id": result.get("id")})
                    notice = {"level": "info", "text": "Announcement removed"}
                else:
                    raise AnnouncementError("unknown announcement action")
            except (AnnouncementError, ValueError) as exc:
                audit_admin("announcement_mutation", admin, "denied", {"action": action})
                notice = {"level": "error", "text": str(exc)}
        rows = list_announcements(
            redis, project=request.args.get("project") or None, host=request.args.get("host") or None,
            active_only=request.args.get("active") == "1",
        )
        token = html.escape(csrf_token())
        for row in rows:
            row["scope"] = "host:{}".format(row.get("host")) if row.get("host") else ("project:{}".format(row.get("project")) if row.get("project") else "global")
            row["status"] = "active" if not row.get("expires_at") or int(row.get("expires_at")) > int(time.time()) else "expired"
            row["actions"] = _ui('<form method="post" class="inline"><input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="action" value="remove"><input type="hidden" name="id" value="{}"><input type="hidden" name="confirm" value="true"><button type="submit">Remove</button></form>', _dashboard_locale(config)).format(token, html.escape(str(row.get("id") or "")))
        body = _ui("""
<h1>Announcements</h1>
<form method="post" class="inline">
  <input type="hidden" name="csrf_token" value="{token}"><input type="hidden" name="action" value="add">
  <input name="text" placeholder="Operational notice" size="50" required>
  <input name="project" placeholder="project"><input name="host" placeholder="host id">
  <select name="severity"><option value="info">info</option><option value="warning">warning</option><option value="critical">critical</option></select>
  <input name="ttl" placeholder="2h" size="6"><label><input type="checkbox" name="confirm" value="true" required> confirm</label>
  <button type="submit">Publish</button>
</form>
<p><a href="/announcements?active=1">Active only</a> &middot; <a href="/announcements">All</a></p>
""", _dashboard_locale(config)).format(token=token)
        body += _table(rows, [
            ("id", "id"), ("status", "status"), ("severity", "severity"), ("scope", "scope"),
            ("text", "text"), ("created_by", "author"), ("expires_at", "expires"), ("actions", "actions"),
        ])
        return _html("Announcements", body, config=config, notice=notice)

    @app.route("/session/<connection_id>")
    def session_details(connection_id):
        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        details = scoped_session(connection_id, admin)
        summary = details.get("summary") or {}
        if not summary.get("server_name") and summary.get("host_id"):
            try:
                host_record = get_host(redis_client(config), summary.get("host_id"))
            except Exception:
                host_record = None
            if host_record is not None and has_permission(admin, config, "inventory.read", host_record.get("project_name") or ""):
                summary["server_name"] = host_record.get("server_name")
        text_link = ""
        raw_link = ""
        replay_link = ""
        replay_json_link = ""
        live_link = ""
        try:
            active_record = get_session(redis_client(config), connection_id)
        except Exception:
            active_record = None
        if active_record and active_record.get("status") == "active":
            live_link = _ui('<a href="/session/{}/live">live</a>', _dashboard_locale(config)).format(html.escape(str(connection_id)))
        if details.get("raw_log_path"):
            if summary.get("project"):
                text_link = _ui('<a href="{}">Session text</a>', _dashboard_locale(config)).format(
                    html.escape(url_for("replay", connection_id=connection_id, view="text"))
                )
            raw_link = _ui('<a href="/raw/{}/{}">raw transcript</a>', _dashboard_locale(config)).format(
                html.escape(str(summary.get("username") or "")),
                html.escape(str(connection_id)),
            )
            replay_link = _ui('<a href="/replay/{}">replay</a>', _dashboard_locale(config)).format(html.escape(str(connection_id)))
            replay_json_link = _ui('<a href="/replay/{}.json">replay.json</a>', _dashboard_locale(config)).format(html.escape(str(connection_id)))
        summary_rows = [
            {"key": key, "value": summary.get(key)}
            for key in ("time", "username", "project", "host_id", "server_name", "target", "remote_user", "result", "connection_id", "session_id")
        ]
        event_rows = []
        command_rows = []
        for event in details.get("events") or []:
            if event.get("event") == "command":
                command_rows.append(
                    {
                        "time": _format_ts(event.get("ts")),
                        "cwd": event.get("cwd"),
                        "command": event.get("command"),
                        "exit_code": event.get("exit_code"),
                        "shell": event.get("shell"),
                    }
                )
                continue
            event_rows.append(
                {
                    "time": _format_ts(event.get("ts")),
                    "event": event.get("event"),
                    "project": event.get("project"),
                    "host_id": event.get("host_id"),
                    "remote_user": event.get("remote_user"),
                    "exit_code": event.get("exit_code"),
                }
            )
        body = _ui("<h1>Session Details</h1>", _dashboard_locale(config))
        events_link = '<a href="{}">events.json</a>'.format(
            html.escape(url_for("session_events_json", connection_id=connection_id))
        )
        links = (text_link, replay_link, live_link, raw_link, replay_json_link, events_link)
        body += "<p>{}</p>".format(" &middot; ".join(link for link in links if link))
        if not details.get("raw_log_path") and not live_link:
            body += "<p>{}</p>".format(html.escape(raw_log_missing_message()))
        body += _ui("<h2>Summary</h2>", _dashboard_locale(config)) + _table(summary_rows, [("key", "field"), ("value", "value")])
        if command_rows:
            body += _ui("<h2>Commands</h2>", _dashboard_locale(config)) + _table(command_rows, [
                ("time", "time"), ("cwd", "cwd"), ("command", "command"), ("exit_code", "exit"), ("shell", "shell")
            ])
        body += _ui("<h2>Timeline</h2>", _dashboard_locale(config)) + _table(event_rows, [
            ("time", "time"), ("event", "event"), ("project", "project"), ("host_id", "host"),
            ("remote_user", "remote_user"), ("exit_code", "exit")
        ])
        return _html("Session Details", body, config=config)

    @app.route("/session/<connection_id>/events.json")
    def session_events_json(connection_id):
        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        details = scoped_session(connection_id, admin)
        return app.response_class(
            response=json.dumps(details.get("events") or [], indent=2, sort_keys=True),
            status=200,
            mimetype="application/json",
        )

    @app.route("/session/<connection_id>/live.json")
    def session_live_json(connection_id):
        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        active = get_session(redis, connection_id)
        details = find_session(config["logging"]["base_path"], connection_id, archive_config=config,
            authorize_archive=lambda metadata: require_object_permission(admin, "audit.read", metadata.get("project")))
        if details is None and active is None:
            abort(404)
        if details is not None:
            require_object_permission(admin, "audit.read", (details.get("summary") or {}).get("project"))
        if active is not None:
            require_object_permission(admin, "audit.read", active.get("project"))
        raw_path = (details or {}).get("raw_log_path")
        replay_data = parse_raw_replay(
            raw_path,
            max_bytes=int(config.get("session_control", {}).get("live_tail_bytes", 262144)),
            tail=True,
        )
        return jsonify({
            "active": bool(active and active.get("status") == "active"),
            "session": active or {},
            "duration": replay_data.get("duration"),
            "chunks": replay_data.get("chunks") or [],
            "plain": replay_data.get("plain") or "",
            "readable": replay_data.get("readable") or "",
            "error": replay_data.get("error"),
        })

    @app.route("/session/<connection_id>/live")
    def session_live(connection_id):
        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        scoped_session(connection_id, admin)
        connection_id_safe = html.escape(str(connection_id))
        locale = _dashboard_locale(config)
        live_status = {
            "loading": "Читаем вывод…" if locale == "ru" else "Loading…",
            "unavailable": "Вывод пока недоступен" if locale == "ru" else "Output unavailable",
            "active": "Сессия идёт" if locale == "ru" else "Session active",
            "completed": "Сессия завершена" if locale == "ru" else "Session ended",
        }
        body = _ui("""
<h1>Live Session</h1>
<p><a href="/session/{connection_id}">details</a> <span id="state" role="status">{loading}</span>
  <label><input type="checkbox" id="readableToggle"> Readable text</label></p>
<link rel="stylesheet" href="/static/vendor/xterm/xterm.css">
<div id="terminal" style="background:#111;padding:12px;height:70vh;"></div>
<pre id="readable" style="display:none;max-height:70vh;overflow:auto;"></pre>
<script type="module">
import {{ Terminal }} from "/static/vendor/xterm/xterm.mjs";
const terminal = new Terminal({{rows: 50, cols: 180, scrollback: 5000, disableStdin: true, convertEol: false, theme: {{background: "#111111"}}}});
terminal.open(document.getElementById("terminal"));
const terminalElement = document.getElementById("terminal");
const readableElement = document.getElementById("readable");
const status = document.getElementById("state");
const messages = {messages};
document.getElementById("readableToggle").onchange = (event) => {{
  terminalElement.style.display = event.target.checked ? "none" : "block";
  readableElement.style.display = event.target.checked ? "block" : "none";
}};
async function refreshLive() {{
  const response = await fetch("/session/{connection_id}/live.json", {{cache: "no-store"}});
  if (!response.ok) {{ status.textContent = messages.unavailable; return; }}
  const data = await response.json();
  terminal.reset();
  terminal.write((data.chunks || []).map(chunk => chunk.data).join("") || data.plain || "");
  readableElement.textContent = data.readable || data.plain || "";
  const label = data.active ? messages.active : messages.completed;
  if (status.textContent !== label) status.textContent = label;
  if (data.active) setTimeout(refreshLive, 2000);
}}
refreshLive();
</script>
""", locale).format(connection_id=connection_id_safe, loading=html.escape(live_status["loading"]),
                   messages=json.dumps(live_status, ensure_ascii=False))
        return _html("Live Session", body, config=config)

    @app.route("/replay/<connection_id>.json")
    def replay_json(connection_id):
        identity, details = replay_session(connection_id)
        if identity is None:
            return details
        replay = load_replay(details)
        return app.response_class(
            response=json.dumps(replay, indent=2, sort_keys=True),
            status=200,
            mimetype="application/json",
        )

    @app.route("/replay/<connection_id>.txt")
    def replay_text(connection_id):
        identity, details = replay_session(connection_id)
        if identity is None:
            return details
        recording = load_replay(details)
        if recording.get("error") and not recording["plain"]:
            abort(404, description=raw_log_missing_message())
        content = recording["readable"]
        if recording.get("truncated"):
            note = _message("Showing the beginning of the recording due to the size limit.", _dashboard_locale(config))
            content += "\n\n[" + note + "]\n"
        return app.response_class(response=content, mimetype="text/plain")

    @app.route("/replay/<connection_id>")
    def replay(connection_id):
        identity, details = replay_session(connection_id)
        if identity is None:
            return details
        if config.get("api", {}).get("enabled"):
            from isolate_terminal_ui import render_replay_workspace
            body = render_replay_workspace(connection_id, csrf_token(), _dashboard_locale(config),
                default_speed=config.get("replay", {}).get("default_speed", 1))
            return _html("Session Replay", body, config=dict(config,
                dashboard=dict(config.get("dashboard", {}), refresh_seconds=0)))
        replay_data = load_replay(details)
        readable = html.escape(replay_data["readable"])
        locale = _dashboard_locale(config)
        if request.args.get("view") == "text":
            body = _ui("""
<h1>Session text</h1>
<p><a href="{player}">Session Replay</a> &middot; <a href="{text}" download>Download TXT</a></p>
""", locale).format(
                player=html.escape(url_for("replay", connection_id=connection_id)),
                text=html.escape(url_for("replay_text", connection_id=connection_id)),
            )
            if replay_data.get("error") and not replay_data["plain"]:
                body += "<p>{}</p>".format(html.escape(raw_log_missing_message()))
            if replay_data.get("truncated"):
                body += _ui('<p class="notice warning">Showing the beginning of the recording due to the size limit.</p>', locale)
            body += "<pre>{}</pre>".format(readable)
            return _html("Session text", body, config=config)
        error = replay_data.get("error")
        default_speed = html.escape(str(config.get("replay", {}).get("default_speed", 1)))
        body = _ui("""
<h1>Session Replay</h1>
<p><a href="/session/{connection_id}">details</a> <a href="/replay/{connection_id}.json" download>replay.json</a></p>
<p>
  <button id="play">Play</button>
  <button id="pause">Pause</button>
  <button id="reset">Reset</button>
  <select id="speed"><option value="0.5">0.5x</option><option value="1">1x</option><option value="2">2x</option><option value="5">5x</option></select>
  <label><input type="checkbox" id="plainToggle"> Readable text</label>
  <span id="clock">0.00 / 0.00</span>
</p>
<input id="scrubber" type="range" min="0" max="0" step="0.01" value="0" style="width:100%;">
<link rel="stylesheet" href="/static/vendor/xterm/xterm.css">
<div id="terminal" class="terminal" style="background:#111;padding:12px;height:62vh;"></div>
<pre id="fallback" style="display:none;max-height:62vh;overflow:auto;">{readable}</pre>
<script type="module">
import {{ Terminal }} from "/static/vendor/xterm/xterm.mjs";
let chunks = [];
let timers = [];
let speed = {default_speed};
let cursor = 0;
let duration = 0;
const terminalElement = document.getElementById("terminal");
const fallback = document.getElementById("fallback");
const emulator = new Terminal({{rows: 40, cols: 160, scrollback: 10000, disableStdin: true, convertEol: false, theme: {{background: "#111111"}}}});
emulator.open(terminalElement);
const scrubber = document.getElementById("scrubber");
const clock = document.getElementById("clock");
document.getElementById("speed").value = String(speed);
function clearTimers() {{ timers.forEach(clearTimeout); timers = []; }}
function renderUntil(index) {{
  cursor = Math.max(0, Math.min(index, chunks.length));
  emulator.reset();
  emulator.write(chunks.slice(0, cursor).map(c => c.data).join(""));
  const t = chunks[cursor - 1] ? chunks[cursor - 1].t : 0;
  scrubber.value = t;
  clock.textContent = t.toFixed(2) + " / " + duration.toFixed(2);
}}
function play() {{
  clearTimers();
  speed = parseFloat(document.getElementById("speed").value || "1");
  const base = chunks[cursor] ? chunks[cursor].t : 0;
  for (let i = cursor; i < chunks.length; i++) {{
    timers.push(setTimeout(() => {{
      emulator.write(chunks[i].data);
      cursor = i + 1;
      scrubber.value = chunks[i].t;
      clock.textContent = chunks[i].t.toFixed(2) + " / " + duration.toFixed(2);
    }}, Math.max(0, (chunks[i].t - base) * 1000 / speed)));
  }}
}}
document.getElementById("play").onclick = play;
document.getElementById("pause").onclick = clearTimers;
document.getElementById("reset").onclick = () => {{ clearTimers(); renderUntil(0); }};
document.getElementById("plainToggle").onchange = (event) => {{
  clearTimers();
  terminalElement.style.display = event.target.checked ? "none" : "block";
  fallback.style.display = event.target.checked ? "block" : "none";
  if (!event.target.checked) renderUntil(cursor);
}};
scrubber.oninput = () => {{
  clearTimers();
  const t = parseFloat(scrubber.value || "0");
  let index = chunks.findIndex(c => c.t > t);
  if (index < 0) index = chunks.length;
  renderUntil(index);
}};
fetch("/replay/{connection_id}.json").then(r => r.json()).then(data => {{
  chunks = data.chunks || [];
  duration = data.duration || (chunks.length ? chunks[chunks.length - 1].t : 0);
  scrubber.max = duration;
  clock.textContent = "0.00 / " + duration.toFixed(2);
  if (!chunks.length) {{ terminalElement.style.display = "none"; fallback.style.display = "block"; }}
}});
</script>
""", _dashboard_locale(config)).format(connection_id=html.escape(str(connection_id)), readable=readable, default_speed=default_speed)
        if error:
            body = _ui('<div class="notice warning">{}</div>', _dashboard_locale(config)).format(html.escape(str(error))) + body
        return _html("Session Replay", body, config=config)

    @app.route("/policy/simulate", methods=["GET", "POST"])
    def policy_simulate():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        result = None
        values = request.form if request.method == "POST" else request.args
        if values.get("project") or values.get("host"):
            redis = redis_client(config)
            host_id = str(values.get("host") or "").strip() or None
            host = get_host(redis, host_id) if host_id else None
            project = str(values.get("project") or "").strip() or (host or {}).get("project_name")
            identity = {
                "username": str(values.get("user") or "policy-preview").strip(),
                "groups": _split_values(values.get("groups")),
                "roles": _split_values(values.get("roles")),
            }
            action = str(values.get("policy_action") or "ssh").strip()
            try:
                decision = resolve_grant(
                    identity, project=project, host=host, grants=load_grants(redis),
                    project_sets=load_project_sets(redis),
                    defaults={**config.get("policy", {}), **config.get("ssh", {})}, action=action,
                )
                result = {"allowed": True, "identity": identity, "project": project, "host": host, "action": action, "decision": decision}
            except PolicyDenied as exc:
                result = {"allowed": False, "identity": identity, "project": project, "host_id": host_id, "action": action, "reason": str(exc)}
        body = _ui("""
<h1>Policy Simulator</h1>
<form method="post" class="inline">
<input name="user" value="{user}" placeholder="username"><input name="groups" value="{groups}" placeholder="Group-A,Group-B">
<input name="roles" value="{roles}" placeholder="roles"><input name="project" value="{project}" placeholder="project">
<input name="host" value="{host}" placeholder="host id"><select name="policy_action"><option>ssh</option><option>runbook</option><option>operate</option><option>command</option></select>
<button type="submit">Simulate</button>
</form>
""", _dashboard_locale(config)).format(**{name: html.escape(str(values.get(name) or "")) for name in ("user", "groups", "roles", "project", "host")})
        if result is not None:
            decision = result.get("decision") or {}
            matched = decision.get("matched_rule") or {}
            summary = {
                "result": "ALLOWED" if result.get("allowed") else "DENIED",
                "reason": result.get("reason"),
                "grant_id": matched.get("id"),
                "remote_user": decision.get("remote_user"),
                "sudo_mode": decision.get("sudo_mode"),
                "allowed_actions": decision.get("allowed_actions"),
            }
            level = "info" if result.get("allowed") else "error"
            body += _ui('<div class="notice {}"><strong>{}</strong></div>', _dashboard_locale(config)).format(level, _message("allowed" if result.get("allowed") else "denied", _dashboard_locale(config)) if _dashboard_locale(config) == "ru" else summary["result"])
            body += _ui("<h2>Decision</h2><pre>{}</pre>", _dashboard_locale(config)).format(html.escape(json.dumps(summary, indent=2, sort_keys=True)))
            body += _ui("<details><summary>Full evaluation</summary><pre>{}</pre></details>", _dashboard_locale(config)).format(html.escape(json.dumps(result, indent=2, sort_keys=True)))
        return _html("Policy Simulator", body, config=config)

    @app.route("/policy/gitops", methods=["GET", "POST"])
    def policy_gitops():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        cfg = config.get("policy_as_code", {}) or {}
        notice = None
        status = None
        if request.method == "POST":
            validate_csrf()
            try:
                require_mutation_confirmation()
                action = request.form.get("action")
                if action == "sync":
                    status = sync_git_policy(config, redis, dry_run=False, confirmed=True)
                    audit_admin("policy_git_sync", admin, "applied", {"commit": status.get("commit")})
                    notice = {"level": "info", "text": "Approved Git policy synchronized"}
                elif action == "rollback":
                    revision = request.form.get("revision")
                    status = rollback_policy(config, redis, revision, confirmed=True)
                    audit_admin("policy_rollback", admin, "applied", {"revision": revision})
                    notice = {"level": "warning", "text": "Policy rolled back; pause the sync timer if Git still contains the newer revision"}
                else:
                    raise ValueError("unknown GitOps action")
            except (GitOpsError, PolicyBundleError, OSError, ValueError) as exc:
                notice = {"level": "error", "text": str(exc)}
        elif cfg.get("enabled") and request.args.get("refresh") == "1":
            try:
                status = git_policy_status(config, redis)
            except (GitOpsError, PolicyBundleError, OSError, ValueError) as exc:
                notice = {"level": "error", "text": str(exc)}
        revisions = list_policy_snapshots(config)
        body = _ui("<h1>Policy GitOps</h1><pre>{}</pre>", _dashboard_locale(config)).format(html.escape(json.dumps({
            "enabled": bool(cfg.get("enabled")), "enforce_git": bool(cfg.get("enforce_git")),
            "repository": cfg.get("repository"), "branch": cfg.get("branch"),
            "bundle": cfg.get("git_bundle_path"), "approval_required": True,
        }, indent=2, sort_keys=True)))
        body += _ui('<p><a href="/policy/gitops?refresh=1">Fetch status, drift and blast radius</a></p>', _dashboard_locale(config))
        if status is not None:
            body += _ui("<h2>Result</h2><pre>{}</pre>", _dashboard_locale(config)).format(html.escape(json.dumps(status, indent=2, sort_keys=True)))
        token = html.escape(csrf_token())
        if cfg.get("enabled"):
            body += _ui('<form method="post" class="inline"><input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="action" value="sync"><label><input type="checkbox" name="confirm" value="true" required> confirm</label><button>Sync approved revision</button></form>', _dashboard_locale(config)).format(token)
        body += _ui("<h2>Rollback revisions</h2>", _dashboard_locale(config)) + _table(revisions, [("revision_id", "revision"), ("created_at", "created"), ("source", "source")])
        body += _ui('<form method="post" class="inline"><input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="action" value="rollback"><input name="revision" placeholder="revision id" required><label><input type="checkbox" name="confirm" value="true" required> confirm</label><button>Rollback</button></form>', _dashboard_locale(config)).format(token)
        return _html("Policy GitOps", body, config=config, notice=notice)

    @app.route("/users")
    def users():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        profiles = list_user_profiles(config["logging"]["base_path"], archive_config=config)
        active_users = {row.get("username") for row in list_active_sessions(redis_client(config))}
        for profile in profiles:
            username = str(profile.get("username") or "")
            profile["user_link"] = _ui('<a href="/user/{}">{}</a>', _dashboard_locale(config)).format(urllib.parse.quote(username, safe=""), html.escape(username))
            profile["active"] = "yes" if username in active_users else ""
            profile["groups_display"] = ", ".join(profile.get("groups") or [])
            profile["last_seen_display"] = _format_ts(profile.get("last_seen"))
        export_links = _ui('<p><a href="/export/users?format=csv">Download CSV</a> &middot; <a href="/export/users?format=json">Download JSON</a></p>', _dashboard_locale(config))
        return _html("Users", _ui("<h1>Users</h1>", _dashboard_locale(config)) + export_links + _table(profiles, [
            ("user_link", "user"), ("groups_display", "groups"), ("last_seen_display", "last_seen"),
            ("connection_count", "connections"), ("active", "active"),
        ]), config=config)

    @app.route("/user/<username>")
    def user_details(username):
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        profiles = {row["username"]: row for row in list_user_profiles(config["logging"]["base_path"], archive_config=config)}
        profile = profiles.get(username, {"username": username, "groups": [], "roles": []})
        redis = redis_client(config)
        active = [row for row in list_active_sessions(redis) if row.get("username") == username]
        history_rows = read_history(
            config["logging"]["base_path"], admin, archive_config=config, user=username, limit=200,
            admin_groups=config.get("dashboard", {}).get("admin_groups") or [],
        )
        subjects = {("user", username)}
        subjects.update(("group", group) for group in profile.get("groups") or [])
        subjects.update(("role", role) for role in profile.get("roles") or [])
        grants = [row for row in list_grant_records(redis) if (row.get("subject"), row.get("name")) in subjects]
        activity = user_activity_summary(
            config["logging"]["base_path"], username, limit=20, active_sessions=active, archive_config=config, state_client=redis,
            grants=list_grant_records(redis), access_requests=list_access_requests(redis),
        )
        metrics = activity.get("metrics") or {}
        body = _ui("""
<h1>User {username}</h1>
<div class="grid">
  <div class="metric"><strong>{connections}</strong><span class="muted">connections</span></div>
  <div class="metric"><strong>{active}</strong><span class="muted">active sessions</span></div>
  <div class="metric"><strong>{failures}</strong><span class="muted">recent failures</span></div>
  <div class="metric"><strong>{grants}</strong><span class="muted">grant candidates</span></div>
  <div class="metric"><strong>{requests}</strong><span class="muted">access requests</span></div>
</div>
<h2>Identity observed in audit</h2><pre>{profile}</pre>
<h2>Top projects</h2>{top_projects}
""", _dashboard_locale(config)).format(
            username=html.escape(username), connections=metrics.get("connections", 0), active=metrics.get("active_sessions", 0),
            failures=metrics.get("recent_failures", 0), grants=metrics.get("grant_candidates", 0), requests=metrics.get("access_requests", 0),
            profile=html.escape(json.dumps(profile, indent=2, sort_keys=True)),
            top_projects=_table(activity.get("top_projects") or [], [("project", "project"), ("connections", "connections")]),
        )
        body += _ui("<h2>Effective grant candidates</h2>", _dashboard_locale(config)) + _table(grants, [
            ("id", "id"), ("subject", "subject"), ("name", "name"), ("project", "project"),
            ("project_set", "project_set"), ("project_glob", "glob"), ("host", "host"),
            ("remote_user", "remote_user"), ("sudo_mode", "sudo"), ("allowed_actions", "actions"),
        ])
        body += _ui("<h2>Active sessions</h2>", _dashboard_locale(config)) + _table(active, [
            ("started_at", "started"), ("project", "project"), ("host_id", "host"), ("remote_user", "remote_user"),
        ])
        body += _ui("<h2>Recent sessions</h2>", _dashboard_locale(config)) + _table(history_rows, [
            ("time", "time"), ("project", "project"), ("host_id", "host"), ("target", "target"),
            ("remote_user", "remote_user"), ("result", "result"),
        ])
        body += _ui("<h2>Recent access requests</h2>", _dashboard_locale(config)) + _table(activity.get("access_requests") or [], [
            ("id", "id"), ("status", "status"), ("project", "project"), ("host", "host"),
            ("remote_user", "remote_user"), ("ticket", "ticket"), ("created_at", "created"),
        ])
        return _html("User Details", body, config=config)

    @app.route("/notifications")
    def notification_status():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        sinks = []
        for index, sink in enumerate(config.get("notifications", {}).get("sinks") or []):
            sinks.append({"index": index, "type": sink.get("type"), "configured": "yes"})
        deliveries = []
        for record in list_access_requests(redis_client(config)):
            status = record.get("notification_status") or {}
            deliveries.append({
                "request_id": record.get("id"), "status": record.get("status"), "requester": record.get("requester"),
                "ok": status.get("ok"), "sent": ", ".join(str(item.get("type")) for item in status.get("sent") or []),
                "errors": "; ".join(status.get("errors") or []), "updated_at": status.get("updated_at"),
            })
        session_deliveries = []
        for record in list_session_records(redis_client(config)):
            for delivery in record.get("alert_deliveries") or []:
                session_deliveries.append({
                    "connection_id": record.get("connection_id"), "alert": delivery.get("alert"),
                    "user": record.get("username"), "ok": delivery.get("ok"),
                    "sent": ", ".join(str(item.get("type")) for item in delivery.get("sent") or []),
                    "errors": "; ".join(delivery.get("errors") or []), "updated_at": delivery.get("ts"),
                })
        body = _ui("<h1>Notification Delivery</h1><h2>Configured sinks</h2>", _dashboard_locale(config)) + _table(sinks, [("index", "#"), ("type", "type"), ("configured", "configured")])
        body += _ui("<h2>Access request delivery status</h2>", _dashboard_locale(config)) + _table(deliveries, [
            ("request_id", "request"), ("status", "status"), ("requester", "requester"),
            ("ok", "ok"), ("sent", "sent"), ("errors", "errors"), ("updated_at", "updated"),
        ])
        body += _ui("<h2>Session alert delivery status</h2>", _dashboard_locale(config)) + _table(session_deliveries, [
            ("connection_id", "connection"), ("alert", "alert"), ("user", "user"),
            ("ok", "ok"), ("sent", "sent"), ("errors", "errors"), ("updated_at", "updated"),
        ])
        return _html("Notifications", body, config=config)

    @app.route("/packages", methods=["GET", "POST"])
    def packages():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            try:
                require_mutation_confirmation()
                require_manual_policy_edit()
                if not config.get("access_packages", {}).get("enabled", True):
                    raise AccessPackageError("access packages are disabled")
                if action == "create":
                    package = create_package(
                        redis, _package_form_payload(request.form), actor=admin.get("username"),
                        max_rules=config.get("access_packages", {}).get("max_rules", 50),
                    )
                    notice = {"level": "success", "text": _message("Access package created: {}", _dashboard_locale(config)).format(package["name"])}
                elif action == "assign":
                    package = get_package(redis, request.form.get("package"))
                    if package is None:
                        raise AccessPackageError("access package was not found")
                    allowed_admins = set((package.get("approval") or {}).get("admin_groups") or [])
                    if allowed_admins and not allowed_admins.intersection(admin.get("groups") or []):
                        raise AccessPackageError("your Keycloak groups cannot assign this package")
                    names = _split_values(request.form.get("name"))
                    maximum = int(config.get("access_packages", {}).get("max_assignments_per_operation") or 100)
                    if not names or len(names) > maximum:
                        raise AccessPackageError("provide between 1 and {} subject names".format(maximum))
                    for name in names:
                        assign_package(
                            redis, package["id"], request.form.get("subject"), name,
                            actor=admin.get("username"), ttl=str(request.form.get("ttl") or "").strip() or None,
                            permanent=request.form.get("permanent") == "true", ticket=request.form.get("ticket"),
                        )
                    notice = {"level": "success", "text": _message("Package assigned to {} subject(s)", _dashboard_locale(config)).format(len(names))}
                elif action == "unassign":
                    assignment, deleted = unassign_package(redis, request.form.get("id"), actor=admin.get("username"))
                    notice = {"level": "success", "text": _message("Assignment {} revoked; {} managed grant(s) removed", _dashboard_locale(config)).format(assignment["id"], deleted)}
                else:
                    raise AccessPackageError("unknown package action")
                audit_admin("package_{}".format(action), admin, "applied", {"package": request.form.get("package")})
            except (AccessPackageError, ValueError) as exc:
                audit_admin("package_{}".format(action or "mutation"), admin, "denied")
                notice = {"level": "error", "text": str(exc)}

        from isolate_access_admin_ui import render_packages
        body = render_packages(list_packages(redis), list_assignments(redis), request.args, csrf_token(),
                               _dashboard_locale(config), _format_ts,
                               read_only=(config.get("policy_as_code", {}).get("enforce_git", False)
                                          or not config.get("access_packages", {}).get("enabled", True)),
                               submitted=request.form if notice and notice["level"] == "error" else None)
        return _html("Access Packages", body, config=config, notice=notice)

    @app.route("/packages/<package_id>", methods=["GET", "POST"])
    def package_details(package_id):
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        package = get_package(redis, package_id)
        if package is None:
            abort(404)
        notice = None
        preview = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            try:
                if action == "preview":
                    payload = _package_form_payload(request.form, current=package)
                    preview = preview_package_update(
                        redis, package["id"], payload, actor=admin.get("username"),
                        max_rules=config.get("access_packages", {}).get("max_rules", 50),
                    )
                    notice = {"level": "info", "text": "Preview completed; no changes were applied"}
                elif action == "update":
                    require_mutation_confirmation()
                    require_manual_policy_edit()
                    payload = _package_form_payload(request.form, current=package)
                    package, _ = update_package(
                        redis, package["id"], payload, actor=admin.get("username"),
                        expected_revision=request.form.get("expected_revision"),
                        max_rules=config.get("access_packages", {}).get("max_rules", 50),
                    )
                    audit_admin("package_update", admin, "applied", {"package_id": package["id"], "revision": package["revision"]})
                    notice = {"level": "success", "text": "Package updated and assignments synchronized"}
                elif action == "rollback":
                    require_mutation_confirmation()
                    require_manual_policy_edit()
                    package, _ = rollback_package(
                        redis, package["id"], int(request.form.get("revision")), actor=admin.get("username"),
                        expected_revision=request.form.get("expected_revision"),
                    )
                    audit_admin("package_rollback", admin, "applied", {"package_id": package["id"], "revision": package["revision"]})
                    notice = {"level": "success", "text": _message("Package rollback created revision {}", _dashboard_locale(config)).format(package["revision"])}
                else:
                    raise AccessPackageError("unknown package action")
            except (AccessPackageError, ValueError) as exc:
                audit_admin("package_{}".format(action or "mutation"), admin, "denied", {"package_id": package_id})
                notice = {"level": "error", "text": str(exc)}
        from isolate_access_admin_ui import render_package_details
        body = render_package_details(package, list_package_revisions(redis, package["id"]), request.args,
                                      csrf_token(), _dashboard_locale(config), _format_ts, preview=preview,
                                      read_only=config.get("policy_as_code", {}).get("enforce_git", False),
                                      submitted=request.form if preview is not None or notice and notice["level"] == "error" else None)
        return _html("Access Packages", body, config=config, notice=notice)

    @app.get("/docs")
    def documentation():
        identity = current_identity()
        if identity is None:
            return redirect(url_for("login"))
        from isolate_docs_ui import render_docs
        build = _build_info(config) if is_dashboard_admin(identity, config) else None
        page = render_docs(_dashboard_locale(config), request.args.get("topic", ""),
                           request.args.get("q", ""), build=build)
        if page is None:
            abort(404)
        return page

    @app.get("/me/profile")
    def personal_profile():
        identity = current_identity()
        if identity is None:
            return redirect(url_for("login"))
        admin = is_dashboard_admin(identity, config)
        self_service = is_self_service_user(identity, config)
        if not (admin or self_service or role_names(identity, config)):
            abort(403)
        api_enabled = config.get("api", {}).get("enabled", False)
        catalog_enabled = api_enabled and config.get("dashboard", {}).get("workspace_enabled", True)
        can_browse = admin or self_service or has_permission(identity, config, "inventory.read")
        can_terminal = bool(api_enabled and config.get("gateway", {}).get("enabled") and browser_token())
        locale = _dashboard_locale(config)
        from isolate_profile_ui import render_profile
        body = render_profile(config, identity, locale, can_browse=can_browse, can_terminal=can_terminal,
                              catalog_url="/workspace" if catalog_enabled else "/me")
        return _html("Личный кабинет" if locale == "ru" else "My profile", body, config=config)

    @app.route("/grants", methods=["GET", "POST"])
    def grants():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        notice = None
        if request.method == "POST":
            validate_csrf()
            action = request.form.get("action")
            try:
                require_mutation_confirmation()
                require_manual_policy_edit()
                bundle = export_bundle(redis)
                if action == "grant_save":
                    grant_id = str(request.form.get("id") or "").strip() or None
                    selector_type = request.form.get("selector_type")
                    selector_value = str(request.form.get("selector_value") or "").strip()
                    if selector_type not in ("project", "project_glob", "project_set") or not selector_value:
                        raise ValueError("one project selector is required")
                    grant = {
                        "schema_version": 2,
                        "subject": request.form.get("subject"),
                        "name": str(request.form.get("name") or "").strip(),
                        selector_type: selector_value,
                        "host": str(request.form.get("host") or "").strip() or None,
                        "remote_user": str(request.form.get("remote_user") or "").strip(),
                        "sudo_mode": request.form.get("sudo_mode") or "none",
                        "allowed_actions": _split_values(request.form.get("allowed_actions")) or ["ssh"],
                    }
                    if grant_id:
                        grant["id"] = grant_id
                        replaced = False
                        for index, current in enumerate(bundle["grants"]):
                            if str(current.get("id")) == grant_id:
                                if current.get("managed_by") == "access_package":
                                    raise ValueError("grant {} is managed by access package {}; edit the package instead".format(
                                        grant_id, current.get("package_name") or current.get("package_id")
                                    ))
                                bundle["grants"][index] = grant
                                replaced = True
                                break
                        if not replaced:
                            raise ValueError("grant not found: {}".format(grant_id))
                    else:
                        bundle["grants"].append(grant)
                elif action == "grant_remove":
                    grant_id = str(request.form.get("id") or "").strip()
                    current = next((row for row in bundle["grants"] if str(row.get("id")) == grant_id), None)
                    if current and current.get("managed_by") == "access_package":
                        raise ValueError("grant {} is managed by access package {}; unassign it through Access Packages".format(
                            grant_id, current.get("package_name") or current.get("package_id")
                        ))
                    before = len(bundle["grants"])
                    bundle["grants"] = [row for row in bundle["grants"] if str(row.get("id")) != grant_id]
                    if len(bundle["grants"]) == before:
                        raise ValueError("grant not found: {}".format(grant_id))
                elif action == "grant_bulk_action":
                    grant_ids = set(_split_values(request.form.get("ids")))
                    selected_action = str(request.form.get("allowed_action") or "").strip()
                    mode = request.form.get("mode")
                    if not grant_ids or not selected_action or mode not in ("add", "remove"):
                        raise ValueError("grant ids, action, and mode are required")
                    matched = set()
                    for grant in bundle["grants"]:
                        if str(grant.get("id")) not in grant_ids:
                            continue
                        if grant.get("managed_by") == "access_package":
                            raise ValueError("bulk editing package-managed grants is not allowed")
                        matched.add(str(grant.get("id")))
                        actions = set(grant.get("allowed_actions") or ["ssh"])
                        if mode == "add":
                            actions.add(selected_action)
                        else:
                            actions.discard(selected_action)
                        grant["allowed_actions"] = sorted(actions)
                    if matched != grant_ids:
                        raise ValueError("one or more grant ids were not found")
                elif action == "project_set_save":
                    name = str(request.form.get("name") or "").strip()
                    if not name:
                        raise ValueError("project set name is required")
                    record = {
                        "schema_version": 2,
                        "name": name,
                        "projects": sorted(set(_split_values(request.form.get("projects")))),
                        "project_globs": sorted(set(_split_values(request.form.get("project_globs")))),
                    }
                    bundle["project_sets"] = [row for row in bundle["project_sets"] if row.get("name") != name]
                    bundle["project_sets"].append(record)
                elif action == "project_set_remove":
                    name = str(request.form.get("name") or "").strip()
                    bundle["project_sets"] = [row for row in bundle["project_sets"] if row.get("name") != name]
                elif action == "project_set_bulk_members":
                    names = set(_split_values(request.form.get("names")))
                    values = set(_split_values(request.form.get("values")))
                    member_type = request.form.get("member_type")
                    mode = request.form.get("mode")
                    if not names or not values or member_type not in ("projects", "project_globs") or mode not in ("add", "remove"):
                        raise ValueError("set names, values, member type, and mode are required")
                    matched = set()
                    for project_set in bundle["project_sets"]:
                        if project_set.get("name") not in names:
                            continue
                        matched.add(project_set["name"])
                        members = set(project_set.get(member_type) or [])
                        members = members | values if mode == "add" else members - values
                        project_set[member_type] = sorted(members)
                    if matched != names:
                        raise ValueError("one or more project sets were not found")
                else:
                    raise ValueError("unknown policy action")
                validation = validate_bundle(bundle)
                if not validation["valid"]:
                    raise PolicyBundleError("; ".join(validation["errors"]))
                changes = plan_bundle(redis, bundle, prune=True)
                save_policy_snapshot(config, redis, source="dashboard:{}".format(action))
                apply_bundle(redis, bundle, prune=True)
                audit_admin(action, admin, "applied", {"change_count": sum(len(rows) for rows in changes.values())})
                notice = {"level": "info", "text": "Policy updated"}
            except (ValueError, PolicyBundleError, OSError) as exc:
                audit_admin(action or "policy_mutation", admin, "denied")
                notice = {"level": "error", "text": str(exc)}
        from isolate_access_admin_ui import render_grants
        body = render_grants(list_grant_records(redis), list(load_project_sets(redis).values()), request.args,
                             csrf_token(), _dashboard_locale(config),
                             read_only=config.get("policy_as_code", {}).get("enforce_git", False),
                             submitted=request.form if notice and notice["level"] == "error" else None)
        return _html("Grants", body, config=config, notice=notice)

    @app.route("/raw/<user>/<connection_id>")
    def raw(user, connection_id):
        admin = require_permission("audit.read")
        if not isinstance(admin, dict):
            return admin
        details = scoped_session(connection_id, admin)
        summary = details.get("summary") or {}
        if str(summary.get("username") or "") != user:
            abort(404)
        path = details.get("raw_log_path")
        if path:
            try:
                return send_file(path, mimetype="text/plain")
            except (FileNotFoundError, IsADirectoryError):
                # Retention can remove a file between lookup and streaming.
                pass
        abort(404, description=raw_log_missing_message())

    @app.route("/inventory/<server_id>/services")
    def service_changes(server_id):
        admin = require_permission("inventory.read")
        if not isinstance(admin, dict):
            return admin
        redis = redis_client(config)
        host = scoped_host(redis, server_id, admin)
        rows = get_discovery_history(redis, server_id, limit=50)
        for row in rows:
            row["time"] = _format_ts(row.get("checked_at"))
            row["kind"] = "baseline" if row.get("baseline") else "change"
            for key in ("added", "removed", "services"):
                row[key] = ", ".join(row.get(key) or [])
        body = _ui('<h1>Service changes: {}</h1><p>Last 50 changes to running systemd units. Baseline establishes the initial state; failed scans do not create changes.</p>', _dashboard_locale(config)).format(html.escape(host.get("server_name") or str(server_id)))
        body += _table(rows, [("time", "time"), ("kind", "kind"), ("added", "appeared"), ("removed", "disappeared"), ("services", "running services")])
        return _html("Service changes", body, config=config)

    from isolate_runbook_admin_ui import register_runbook_admin
    register_runbook_admin(
        app, config, require_admin=require_admin, store_factory=lambda: redis_client(config),
        csrf_token=csrf_token, validate_csrf=validate_csrf, require_confirmation=require_mutation_confirmation,
        audit_admin=audit_admin,
        render_page=lambda title, body, notice=None: _html(title, body, config=config, notice=notice),
        locale=lambda: _dashboard_locale(config),
    )
    register_self_service(app, config, current_identity, csrf_token, validate_csrf, notify_dashboard, audit_admin)
    register_session_approval_routes(app, config, current_identity, csrf_token, validate_csrf, audit_admin)
    return app


def main():
    config = load_config()
    app = create_app(config)
    dashboard = config.get("dashboard", {})
    app.run(host=dashboard.get("listen_host", "127.0.0.1"), port=int(dashboard.get("listen_port", 8080)))


if __name__ == "__main__":
    main()
