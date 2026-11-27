"""Headless browser checks against the real Flask/API/WebSocket/SSH workspace.

Identity uses a synthetic locally signed JWT; real IdP login is covered by the
separate HTTPS Keycloak integration. Nothing contacts a deployed environment.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "shared"), str(ROOT / "tests")]

import asyncssh
from aiohttp import web
from werkzeug.serving import make_server, WSGIRequestHandler
from isolate_gateway import create_web_app
from isolate_runtime import Runtime
from isolate_state import SQLState, StateClient
from isolate_web import create_app
import test_runtime_api_index as fixtures


class Quiet(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass


def browser_checks(base, cookie, output, commands, connection_ids, store, audit_config):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright, expect
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="msedge" if os.name == "nt" else None)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        context.add_cookies([{"name": "session", "value": cookie, "url": base, "httpOnly": True, "sameSite": "Lax"}])
        page = context.new_page()
        page.emulate_media(color_scheme='light')
        page.on("pageerror", lambda error: (errors.append(str(error)), print("UI script error: " + str(error), flush=True)))
        page.on("console", lambda message: print("UI console: " + message.text, flush=True) if message.type in ("error", "warning") else None)
        page.on("dialog", lambda dialog: dialog.accept())
        def connection_response(response):
            if response.url.endswith("/api/v1/connections"):
                if response.status == 201:
                    connection_ids.append(response.json()["connection_id"])
                else:
                    print("Connection API failed: " + str(response.status) + " " + response.text(), flush=True)
            elif '/replay/' in response.url and response.url.endswith('.json'):
                data = response.json() if response.status == 200 else {}
                print("Replay response: status={}, error={}, chunks={}".format(response.status, data.get('error'), len(data.get('chunks', []))), flush=True)
        page.on("response", connection_response)
        # Synthetic records exercise the normal authorized overview and polling.
        from isolate_sessions import mark_session_start
        from isolate_audit_index import AuditIndex
        for identifier, user, name, address, protocol in (
                ('ui-overview-1', 'alex.morgan', 'payments-api-01', '10.24.8.12', 'ssh'),
                ('ui-overview-2', 'daria.volkova', 'analytics-db-02', '10.24.12.6', 'webssh'),
                ('ui-overview-3', 'sam.rivera', 'platform-build-01', '10.24.4.21', 'ssh')):
            mark_session_start(store, identifier, {'username':user,'server_name':name,
                'target_host':address,'host_id':'1','project':'payments','protocol':protocol,
                'started_at':int(time.time()) - 810})
        def choose_theme(target, theme):
            switch = target.locator('#theme-preference')
            switch.locator('summary').click()
            choice = switch.locator(f'[data-theme-choice="{theme}"]')
            expect(choice).to_be_visible()
            choice.click()
            expect(switch.locator('summary')).to_be_focused()
            expect(target.locator('html')).to_have_attribute('data-theme-preference', theme)

        page.goto(base + '/?lang=en')
        expect(page.locator('.overview-table tbody tr')).to_have_count(3)
        expect(page.locator('html')).to_have_attribute('data-theme-preference', 'system')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        expect(page.locator('#theme-preference [data-theme-choice="system"]')).to_have_attribute('aria-pressed', 'true')
        page.screenshot(path=str(output / 'overview-desktop-light-en.png'), full_page=True)
        delayed_page = context.new_page()
        pending_navigation = []
        pending_health = []
        delayed_page.route('**/static/precision-navigation.js', lambda route: pending_navigation.append(route))
        delayed_page.route('**/health', lambda route: pending_health.append(route))
        delayed_page.goto(base + '/?lang=en', wait_until='commit')
        expect(delayed_page.locator('#navigation-search')).to_be_visible()
        expect(delayed_page.locator('.nav-rail')).to_be_hidden()
        sidebar_search_before = delayed_page.locator('#navigation-search').bounding_box()
        top_search_before = delayed_page.locator('#global-search').bounding_box()
        pending_navigation.pop().continue_()
        expect(delayed_page.locator('.nav-rail')).to_be_visible()
        sidebar_search_after = delayed_page.locator('#navigation-search').bounding_box()
        assert abs(sidebar_search_before['x'] - sidebar_search_after['x']) <= 1
        assert abs(sidebar_search_before['width'] - sidebar_search_after['width']) <= 1
        pending_health.pop().fulfill(json={'ok': True})
        expect(delayed_page.locator('[data-bastion-state]')).to_have_text('Healthy')
        assert abs(top_search_before['x'] - delayed_page.locator('#global-search').bounding_box()['x']) <= 1
        delayed_page.close()
        # Explicit choices survive reloads and route changes; system mode tracks
        # device appearance without overriding a saved explicit choice.
        choose_theme(page, 'dark')
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        page.reload()
        expect(page.locator('#theme-preference [data-theme-choice="dark"]')).to_have_attribute('aria-pressed', 'true')
        page.goto(base + '/workspace?lang=en')
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        navigation = page.locator('.primary-nav')
        rail = page.locator('.nav-rail')
        workspace_trigger = rail.locator('[data-nav-trigger="workspace"]')
        platform_trigger = rail.locator('[data-nav-trigger="platform"]')
        flyout = page.locator('.nav-flyout')
        expect(workspace_trigger).to_have_attribute('aria-pressed', 'true')
        expect(navigation.locator('a[href="/workspace"]')).to_have_attribute('aria-current', 'page')
        expect(navigation.locator('a[href="/users"]')).to_be_hidden()
        platform_trigger.hover()
        users_link = flyout.locator('a[href="/users"]')
        expect(users_link).to_be_visible()
        expect(workspace_trigger).to_have_attribute('aria-pressed', 'true')
        expect(navigation.locator('a[href="/workspace"]')).to_be_visible()
        users_link.hover()
        expect(flyout).to_be_visible()
        page.screenshot(path=str(output / 'navigation-flyout-desktop.png'))
        page.locator('.topbar-heading').hover()
        expect(flyout).to_be_hidden()
        platform_trigger.focus()
        page.keyboard.press('ArrowRight')
        expect(flyout.locator('a').first).to_be_focused()
        page.keyboard.press('Escape')
        expect(flyout).to_be_hidden()
        expect(platform_trigger).to_be_focused()
        page.keyboard.press('Enter')
        expect(platform_trigger).to_have_attribute('aria-pressed', 'true')
        expect(navigation.locator('a[href="/users"]')).to_be_visible()
        workspace_trigger.click()
        nav_search = page.locator('#navigation-search')
        nav_search.fill('GitOps')
        expect(navigation.locator('a[href="/policy/gitops"]')).to_be_visible()
        expect(navigation.locator('a[href="/users"]')).to_be_hidden()
        nav_search.fill('')
        expect(workspace_trigger).to_have_attribute('aria-pressed', 'true')
        expect(navigation.locator('a[href="/workspace"]')).to_be_visible()
        expect(navigation.locator('a[href="/policy/gitops"]')).to_be_hidden()

        # The sidebar retains its own section position after switching, filtering,
        # navigating, reloading and returning through browser history.
        page.goto(base + '/jobs')
        page.set_viewport_size({'width': 1440, 'height': 320})
        operations_trigger = rail.locator('[data-nav-trigger="operations"]')
        expect(operations_trigger).to_have_attribute('aria-pressed', 'true')
        announcement_link = navigation.locator('a[href="/announcements"]')
        announcement_link.scroll_into_view_if_needed()
        scroll_position = navigation.evaluate('nav => nav.scrollTop')
        assert scroll_position > 0, 'sidebar fixture did not scroll'
        platform_trigger.click()
        operations_trigger.click()
        assert navigation.evaluate('nav => nav.scrollTop') == scroll_position
        nav_search.fill('GitOps')
        nav_search.fill('')
        assert navigation.evaluate('nav => nav.scrollTop') == scroll_position
        announcement_link.click()
        expect(page).to_have_url(base + '/announcements')
        assert navigation.evaluate('nav => nav.scrollTop') == scroll_position
        page.reload()
        assert navigation.evaluate('nav => nav.scrollTop') == scroll_position
        page.go_back()
        assert navigation.evaluate('nav => nav.scrollTop') == scroll_position
        page.set_viewport_size({'width': 1440, 'height': 1000})
        choose_theme(page, 'light')
        page.emulate_media(color_scheme='dark')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        choose_theme(page, 'system')
        expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
        page.emulate_media(color_scheme='light')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        page.reload()
        expect(page.locator('#theme-preference [data-theme-choice="system"]')).to_have_attribute('aria-pressed', 'true')
        page.screenshot(path=str(output / 'catalog-desktop-light.png'), full_page=True)
        # A blocked storage API must leave controls usable and following the OS.
        restricted = browser.new_context(viewport={'width':1440, 'height':1000}, color_scheme='light')
        restricted.add_cookies(context.cookies())
        restricted.add_init_script("""
          for (const key of ['localStorage', 'sessionStorage']) {
            Object.defineProperty(window, key, {get() { throw new DOMException('Storage disabled', 'SecurityError'); }});
          }
        """)
        restricted_page = restricted.new_page()
        restricted_errors = []
        restricted_page.on('pageerror', lambda error: restricted_errors.append(str(error)))
        restricted_page.goto(base + '/?lang=en')
        expect(restricted_page.locator('html')).to_have_attribute('data-theme', 'light')
        choose_theme(restricted_page, 'dark')
        expect(restricted_page.locator('html')).to_have_attribute('data-theme', 'dark')
        restricted_page.locator('.nav-rail [data-nav-trigger="platform"]').click()
        expect(restricted_page.locator('.primary-nav a[href="/users"]')).to_be_visible()
        assert not restricted_errors, restricted_errors
        restricted.close()
        without_scripts = browser.new_context(java_script_enabled=False, viewport={'width':1440, 'height':1000})
        without_scripts.add_cookies(context.cookies())
        fallback = without_scripts.new_page()
        fallback.goto(base + '/workspace?lang=en')
        expect(fallback.locator('.nav-rail')).to_be_hidden()
        expect(fallback.locator('.primary-nav a[href="/users"]')).to_be_visible()
        without_scripts.close()
        choose_theme(page, 'dark')
        page.goto(base + '/?lang=en')
        expect(page.get_by_role('link', name='Access rules', exact=True)).to_be_visible()
        expect(page.locator('.global-search')).to_be_visible()
        page.screenshot(path=str(output / 'overview-desktop-en.png'), full_page=True)
        audit_stream = page.locator('.overview-audit-stream')
        audit_state = """stream => {
          const top = stream.getBoundingClientRect().top + stream.clientTop;
          const row = [...stream.querySelectorAll('[data-audit-event]')]
            .find(event => event.getBoundingClientRect().bottom > top);
          return [row.dataset.auditEvent, Math.round(row.getBoundingClientRect().top - top)];
        }"""
        audit_stream.evaluate('stream => stream.scrollTop = 110')
        assert audit_stream.evaluate('stream => stream.scrollTop') > 0
        visible_event = audit_stream.evaluate(audit_state)
        AuditIndex(audit_config).ingest({'event_id': 'overview-refresh-check', 'event': 'access_request_created',
                                       'ts': time.time(), 'username': 'alex.morgan', 'project': 'payments', 'host_id': '1'})
        page.locator('[data-overview-refresh]').click()
        expect(audit_stream.locator('.overview-audit-code').first).to_have_text('access_request_created')
        assert audit_stream.evaluate(audit_state) == visible_event
        sidebar_before = page.locator('.sidebar-navigation').bounding_box()
        content_before = page.locator('.main').bounding_box()
        build_info = page.locator('.sidebar-build')
        sidebar_account = page.locator('.sidebar-account')
        build_info.locator('summary').click()
        expect(build_info.locator('.sidebar-popover')).to_be_visible()
        expect(build_info.locator('dt', has_text='Python')).to_be_visible()
        assert page.locator('.sidebar-navigation').bounding_box() == sidebar_before
        assert page.locator('.main').bounding_box() == content_before
        sidebar_account.locator('summary').click()
        expect(build_info.locator('.sidebar-popover')).to_be_hidden()
        expect(sidebar_account.get_by_role('link', name='User profile')).to_be_visible()
        assert page.locator('.sidebar-navigation').bounding_box() == sidebar_before
        assert page.locator('.main').bounding_box() == content_before
        page.screenshot(path=str(output / 'sidebar-account-dark.png'), animations='disabled')
        page.keyboard.press('Escape')
        expect(sidebar_account.locator('.sidebar-popover')).to_be_hidden()
        page.locator('[data-overview-terminate]').first.click()
        dialog = page.locator('#overview-terminate-dialog')
        expect(dialog).to_be_visible()
        expect(dialog.locator('[name=reason]')).to_have_attribute('aria-describedby', __import__('re').compile('overview-reason-help'))
        help_button = dialog.get_by_role('button', name='Field help')
        help_popup = dialog.locator('#field-help-overview-reason-help')
        expect(help_popup).to_be_hidden()
        help_button.hover()
        expect(help_popup).to_be_visible()
        page.screenshot(path=str(output / 'field-help.png'), animations='disabled')
        help_button.focus()
        page.keyboard.press('Escape')
        expect(help_popup).to_be_hidden()
        expect(dialog).to_be_visible()
        help_button.click()
        expect(help_popup).to_be_visible()
        help_button.click()
        expect(help_popup).to_be_hidden()
        page.locator('[data-overview-dialog-close]').click()
        account = page.locator('.header-profile')
        account_trigger = account.locator('summary')
        account_trigger.focus()
        page.keyboard.press('Enter')
        expect(page).to_have_url(base + '/?lang=en')
        expect(account.get_by_role('link', name='Sign out')).to_be_visible()
        page.keyboard.press('Escape')
        expect(account.get_by_role('link', name='Sign out')).to_be_hidden()
        expect(account_trigger).to_be_focused()
        account_trigger.click()
        page.locator('.overview-heading').click()
        expect(account.get_by_role('link', name='Sign out')).to_be_hidden()
        account_trigger.click()
        page.screenshot(path=str(output / 'account-menu-dark.png'), full_page=True)
        account.get_by_role('link', name='User profile').click()
        expect(page).to_have_url(base + '/me/profile')
        expect(page.locator('h1')).to_have_text('My profile')
        page.locator('#profile-theme').select_option('light')
        expect(page.locator('#theme-preference [data-theme-choice="light"]')).to_have_attribute('aria-pressed', 'true')
        page.locator('#profile-theme').select_option('dark')
        page.screenshot(path=str(output / 'profile-desktop-en.png'), full_page=True)
        page.locator('.header-help').click()
        expect(page).to_have_url(base + '/docs')
        expect(page.locator('h1')).to_have_text('Isolate Documentation')
        page.screenshot(path=str(output / 'docs-desktop-en.png'), full_page=True)
        query = page.locator('form[role=search] input[name=q]')
        query.fill('GitOps')
        query.press('Enter')
        expect(page).to_have_url(__import__('re').compile(r'/docs\?.*q=GitOps'))
        expect(page.locator('main a[href*="topic=gitops"]').first).to_be_visible()
        page.goto(base + '/docs?topic=automation&lang=en')
        diagram = page.locator('.docs-diagram[data-workflow="automation"]')
        expect(diagram.locator('.docs-diagram-steps > li')).to_have_count(3)
        expect(diagram.locator('.docs-diagram-branches > li')).to_have_count(3)
        expect(diagram.locator('[data-branch="pass"]')).to_be_visible()
        expect(diagram.locator('[data-branch="stop"]')).to_be_visible()
        expect(diagram.locator('[data-branch="wait"]')).to_be_visible()
        diagram.screenshot(path=str(output / 'docs-canary-en-dark.png'))
        page.goto(base + '/docs?topic=automation&lang=ru')
        page.locator('[data-theme-select]').select_option('light')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        expect(diagram).to_contain_text('пробн')
        diagram.screenshot(path=str(output / 'docs-canary-ru-light.png'))
        page.set_viewport_size({'width': 390, 'height': 844})
        page.emulate_media(reduced_motion='reduce')
        expect(diagram.locator('[data-branch="wait"]')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile workflow overflow'
        diagram.screenshot(path=str(output / 'docs-canary-ru-mobile.png'))
        page.emulate_media(reduced_motion='no-preference')
        page.locator('[data-theme-select]').select_option('dark')
        page.goto(base + '/docs?topic=resources&lang=ru')
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile docs overflow'
        page.screenshot(path=str(output / 'docs-mobile-ru.png'), full_page=True)
        page.get_by_text('Разделы справки', exact=True).click()
        expect(page.locator('details[open] a[href*="topic=packages"]')).to_be_visible()
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(base + '/?lang=ru')
        expect(page.locator('.overview-heading h1')).to_have_text('Обзор операций')
        page.screenshot(path=str(output / 'overview-desktop-ru.png'), full_page=True)
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'mobile overview overflows'
        assert page.locator('.sidebar').evaluate('element => element.getBoundingClientRect().right <= 0'), 'closed mobile sidebar covers content'
        page.locator('[data-sidebar-toggle]').click()
        expect(page.locator('.sidebar')).to_have_attribute('data-open','true')
        page.keyboard.press('Escape')
        expect(page.locator('.sidebar')).to_have_attribute('data-open','false')
        assert page.locator('.sidebar').evaluate('element => element.getBoundingClientRect().right <= 0'), 'sidebar remains over content after closing'
        touch = browser.new_context(viewport={'width':390, 'height':844}, has_touch=True, device_scale_factor=1)
        touch.add_cookies(context.cookies())
        touch_page = touch.new_page()
        touch_page.goto(base + '/?lang=ru')
        touch_page.locator('[data-sidebar-toggle]').tap()
        touch_platform = touch_page.locator('.nav-rail [data-nav-trigger="platform"]')
        touch_platform.tap()
        expect(touch_platform).to_have_attribute('aria-pressed', 'true')
        expect(touch_page.locator('.nav-flyout')).to_be_hidden()
        touch_page.locator('.primary-nav a[href="/users"]').tap()
        expect(touch_page).to_have_url(base + '/users')
        touch.close()
        expect(page.locator('.locale-switch')).to_be_visible()
        switch = page.locator('#theme-preference')
        expect(switch.locator('summary')).to_be_visible()
        switch.locator('summary').click()
        options = switch.locator('.topbar-popover-panel')
        expect(options).to_be_visible()
        assert options.evaluate("panel => panel.getBoundingClientRect().left >= 0 && panel.getBoundingClientRect().right <= innerWidth")
        page.screenshot(path=str(output / 'theme-menu-mobile-dark.png'), full_page=True)
        page.keyboard.press('Escape')
        expect(options).to_be_hidden()
        choose_theme(page, 'light')
        expect(page.locator('html')).to_have_attribute('data-theme', 'light')
        page.screenshot(path=str(output / 'overview-mobile-light-ru.png'), full_page=True)
        choose_theme(page, 'dark')
        page.screenshot(path=str(output / 'overview-mobile-ru.png'), full_page=True)
        page.set_viewport_size({'width':1440,'height':1000})
        for identifier in ('ui-overview-1','ui-overview-2','ui-overview-3'):
            store.delete('active_session_' + identifier)
        page.goto(base + "/workspace?lang=ru")
        expect(page.locator(".workspace-resource")).to_have_count(9)
        page.keyboard.press("Control+k")
        expect(page.locator("#workspace-query")).to_be_focused()
        page.locator("#workspace-query").fill("payments")
        expect(page.locator(".workspace-resource")).to_have_count(3)
        page.locator("#workspace-query").fill("")
        expect(page.locator(".workspace-resource")).to_have_count(9)
        page.locator("[data-resource-favorite]").first.click()
        page.locator('[data-workspace-view="favorites"]').click()
        expect(page.locator(".workspace-resource")).to_have_count(1)
        page.locator('[data-workspace-view="all"]').click()
        expect(page.locator(".workspace-resource")).to_have_count(9)
        page.screenshot(path=str(output / "catalog-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "catalog-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "mobile catalogue overflows"
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(base + "/workspace/admin?lang=ru")
        expect(page.locator(".workspace-admin-card").first).to_be_visible()
        page.screenshot(path=str(output / "administration.png"), full_page=True)
        page.goto(base + "/me/terminal/1?lang=ru")
        expect(workspace_trigger).to_have_attribute('aria-pressed', 'true')
        expect(navigation.locator('a[href="/me/terminal"]')).to_have_attribute('aria-current', 'page')
        expect(navigation.locator('a[href="/grants"]')).to_have_count(1)
        expect(navigation.locator('a[href="/users"]')).to_have_count(1)
        try:
            expect(page.locator('.tw-pane[data-state="connected"]')).to_have_count(1, timeout=10000)
        except Exception:
            print("Terminal states: " + str(page.locator('.tw-pane-status').all_text_contents()), flush=True)
            page.screenshot(path=str(output / "terminal-error.png"), full_page=True)
            raise

        def expect_terminal_fit(target=page):
            measure_terminals = """() => [...document.querySelectorAll('.tw-pane-grid:not([hidden]) .tw-emulator')]
              .map(emulator => {
                const screen = emulator.querySelector('.xterm-screen');
                const scrollbar = emulator.querySelector('.xterm-scrollable-element > .scrollbar.vertical');
                const style = getComputedStyle(emulator);
                const width = emulator.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
                              - (scrollbar?.offsetWidth || 0);
                const height = emulator.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
                return { width, height, screenWidth: screen?.offsetWidth, screenHeight: screen?.offsetHeight,
                         rows: screen?.querySelector('.xterm-rows')?.children.length };
              })"""
            try:
                target.wait_for_function(f"""() => {{
                    const sizes = ({measure_terminals})();
                    return sizes.length && sizes.every(({{width, height, screenWidth, screenHeight, rows}}) =>
                      rows && screenWidth > 0 && screenWidth <= width + 1 &&
                      screenHeight > 0 && screenHeight <= height + 1 &&
                      height - screenHeight < screenHeight / rows + 2);
                }}""", timeout=5000)
            except PlaywrightTimeout:
                print("Current terminal dimensions:", target.evaluate(measure_terminals), flush=True)
                raise

        expect_terminal_fit()
        first_pane = page.locator('.tw-pane').first
        terminal = first_pane.locator(".xterm-helper-textarea")
        prompt = first_pane.locator('.xterm-rows > div').last
        expect(prompt).to_contain_text('isolate-test$')
        terminal.press("w")
        terminal.type("hoami")
        expect(prompt).to_contain_text('isolate-test$ whoami')
        page.screenshot(path=str(output / "terminal-live-typing.png"), full_page=True)
        expect(prompt).to_be_in_viewport(ratio=0.95)
        assert 'whoami' not in commands, 'command executed before Enter'

        fullscreen = page.locator('[data-action="fullscreen"]')
        existing_connections = list(connection_ids)
        fullscreen.click()
        expect(fullscreen).to_have_attribute('aria-pressed', 'true')
        assert page.evaluate("""() => {
          const workspace = document.getElementById('terminal-workspace');
          return document.fullscreenElement === workspace || workspace.classList.contains('tw-fullscreen');
        }"""), 'fullscreen did not expand the live workspace'
        expect_terminal_fit()
        expect(prompt).to_contain_text('isolate-test$ whoami')
        fullscreen.click()
        expect(fullscreen).to_have_attribute('aria-pressed', 'false')
        expect_terminal_fit()
        expect(prompt).to_contain_text('isolate-test$ whoami')
        expect(first_pane).to_have_attribute('data-state', 'connected')
        assert existing_connections == connection_ids and 'whoami' not in commands

        terminal.press("Enter")
        page.wait_for_function("document.querySelector('.tw-pane[data-state=connected]') !== null")
        page.locator('[data-action="search"]').click()
        page.locator("#tw-search-input").fill("support")
        expect(page.locator("#tw-search-count")).not_to_have_text("Нет совпадений")
        page.locator('[data-action="hide-search"]').click()

        with context.expect_page() as opened:
            page.locator('a[data-action="open-window"]').click()
        popup = opened.value
        popup.on('pageerror', lambda error: errors.append(str(error)))
        try:
            expect(popup.locator('#terminal-workspace[data-presentation="window"]')).to_be_visible()
            assert popup.evaluate("""() => window.opener === null && location.pathname === '/me/terminal/1' &&
                new URLSearchParams(location.search).get('view') === 'window'""")
            expect(popup.locator('.topbar, .sidebar')).to_have_count(0)
            expect(popup.locator('.tw-pane[data-state="connected"]')).to_have_count(1)
            expect(popup.locator('.xterm-rows > div').last).to_contain_text('isolate-test$')
            popup_fullscreen = popup.locator('[data-action="fullscreen"]')
            popup_fullscreen.click()
            expect(popup_fullscreen).to_have_attribute('aria-pressed', 'true')
            popup_fullscreen.click()
            expect(popup_fullscreen).to_have_attribute('aria-pressed', 'false')
            popup.set_viewport_size({"width": 390, "height": 620})
            expect_terminal_fit(popup)
            assert popup.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'standalone terminal overflows'
        finally:
            popup.close()
        expect(first_pane).to_have_attribute('data-state', 'connected')
        assert existing_connections == connection_ids, 'opening a new window reconnected the original terminal'

        page.locator('[data-action="split-columns"]').click()
        page.locator(".tw-resource-choice").first.click()
        expect(page.locator('.tw-pane[data-state="connected"]')).to_have_count(2)
        expect_terminal_fit()
        page.set_viewport_size({"width": 390, "height": 844})
        expect_terminal_fit()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile terminal overflows"
        page.evaluate("Object.defineProperty(document, 'fullscreenEnabled', {value: false, configurable: true})")
        fullscreen.click()
        expect(page.locator('#terminal-workspace.tw-fullscreen')).to_be_visible()
        assert page.evaluate("document.querySelector('#terminal-workspace').getBoundingClientRect().height <= innerHeight + 1")
        expect_terminal_fit()
        fullscreen.click()
        page.evaluate("delete document.fullscreenEnabled")
        page.screenshot(path=str(output / "terminal-split-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        expect_terminal_fit()
        before = len(commands)
        page.locator(".xterm-helper-textarea").first.evaluate(r"""element => {
          const data = new DataTransfer(); data.setData('text/plain', 'first-command\nsecond-command\n');
          element.dispatchEvent(new ClipboardEvent('paste', {clipboardData:data, bubbles:true, cancelable:true}));
        }""")
        expect(page.locator("#tw-paste-dialog")).to_be_visible()
        assert len(commands) == before, "paste reached SSH before confirmation"
        page.screenshot(path=str(output / "paste-confirmation.png"), full_page=True)
        page.locator('#tw-paste-dialog button[value="confirm"]').click()
        page.locator('[data-action="settings"]').click()
        page.locator('#tw-settings-form [name="font_size"]').fill("18")
        page.locator('#tw-settings-form button[type="submit"]').click()
        expect(page.locator("#tw-notice")).to_have_text("Настройки сохранены.")
        expect_terminal_fit()
        page.screenshot(path=str(output / "terminal-split.png"), full_page=True)
        page.keyboard.press("Control+Shift+t")
        expect(page.locator("#tw-resource-dialog")).to_be_visible()
        page.locator(".tw-resource-choice").first.click()
        expect(page.locator("#tw-tabs .tw-tab")).to_have_count(2)
        page.screenshot(path=str(output / "terminal-tabs.png"), full_page=True)
        page.goto(base + "/workspace?lang=ru")
        page.locator('[data-workspace-view="recent"]').click()
        expect(page.locator(".workspace-resource")).not_to_have_count(0)
        assert connection_ids, "no actual connection was created"
        page.goto(base + "/replay/" + connection_ids[0] + "?lang=ru")
        expect(page.locator("#tr-state")).to_have_text("Запись готова к просмотру")
        page.locator("#tr-bookmark-label").fill("Проверка целевой учётки")
        page.locator('#tr-bookmark-form button[type="submit"]').click()
        expect(page.locator("#tr-bookmark-list")).to_contain_text("Проверка целевой учётки")
        page.reload()
        expect(page.locator("#tr-bookmark-list")).to_contain_text("Проверка целевой учётки")
        page.locator("#tr-play").click()
        page.locator("#tr-pause").click()
        page.screenshot(path=str(output / "replay-bookmarks.png"), full_page=True)
        page.goto(base + "/me/history?lang=ru")
        page.locator('a[href="/replay/' + connection_ids[0] + '?view=text"]').click()
        expect(page.locator("#tr-readable-toggle")).to_be_checked()
        expect(page.locator("#tr-readable")).to_contain_text("isolate-test$ whoami")
        expect(page.locator("#tr-readable")).to_contain_text("support")
        expect(page.locator("#tr-terminal")).to_be_hidden()
        transcript_url = "/replay/" + connection_ids[0] + ".txt"
        expect(page.locator('a[download][href="' + transcript_url + '"]')).to_be_visible()
        transcript = page.request.get(base + transcript_url)
        assert transcript.ok and "isolate-test$ whoami\nsupport" in transcript.text(), transcript.status
        page.locator("#tr-find-toggle").click()
        page.locator("#tr-find-input").fill("WHOAMI")
        page.locator("#tr-find-input").press("Enter")
        expect(page.locator("#tr-find-count")).to_have_text("1/1")
        page.screenshot(path=str(output / "replay-readable.png"), full_page=True)
        page.locator("#tr-readable-toggle").uncheck()
        expect(page.locator("#tr-terminal")).to_be_visible()
        page.goto(base + '/workspace/access/1?protocol=ssh&lang=ru')
        expect(page.locator('h1')).to_contain_text('Условия доступа')
        expect(page.locator('body')).to_contain_text('Isolate проверяет действие по одному выбранному правилу доступа')
        page.screenshot(path=str(output / 'access-explanation.png'), full_page=True)
        page.goto(base + '/policy/impact?grant_id=1')
        page.locator('[name="grant"]').fill(json.dumps({'allowed_actions': ['ssh', 'runbook']}))
        page.get_by_role('button', name='Проверить изменения').click()
        expect(page.get_by_role('heading', name='Какие права изменятся')).to_be_visible()
        page.screenshot(path=str(output / 'policy-impact.png'), full_page=True)
        page.goto(base + '/workspace/governance')
        page.locator('a[href*="action=new-review"]').first.click()
        review = page.locator('form').filter(has=page.locator('[name="operation"][value="create_review"]'))
        review.locator('[name="project"]').select_option('payments')
        review.locator('[name="reason"]').fill('Scheduled browser owner review')
        review.locator('[name="confirm"]').check()
        review.get_by_role('button', name='Начать проверку').click()
        expect(page.get_by_role('heading', name='Проверки владельцами проектов')).to_be_visible()
        page.locator('details.governance-decision > summary').first.click()
        decision = page.locator('form').filter(has=page.locator('[name="operation"][value="review"]')).first
        decision.locator('[name="reason"]').fill('Owner verified current rule without extending expiry')
        decision.locator('[name="confirm"]').check()
        decision.get_by_role('button', name='Записать решение').click()
        expect(page.locator('body')).to_contain_text('Завершено')
        page.screenshot(path=str(output / 'access-lifecycle.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(output / 'access-lifecycle-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'lifecycle page overflows mobile'
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.goto(base + '/operations/campaigns')
        page.locator('[name="runbook_id"]').select_option('uptime')
        page.locator('[name="host_ids"]').fill('1,2')
        page.get_by_text('Размер групп и условия остановки', exact=True).click()
        page.locator('[name="batch_size"]').fill('1')
        page.get_by_role('button', name='Проверить план').click()
        expect(page.get_by_role('heading', name='Проверьте план запуска')).to_be_visible()
        page.screenshot(path=str(output / 'canary-review.png'), full_page=True)
        page.locator('[name="confirm"]').check()
        page.get_by_role('button', name='Начать пробный запуск').click()
        expect(page.get_by_role('heading', name='Запуск uptime')).to_be_visible()
        page.locator('[name="confirm"]').check()
        page.get_by_role('button', name='Остановить запуск').click()
        expect(page.locator('body')).to_contain_text('Отменено')
        page.get_by_role('link', name='Открыть расследование').click()
        expect(page.locator('.investigation-event')).not_to_have_count(0)
        page.screenshot(path=str(output / 'investigation.png'), full_page=True)
        page.goto(base + '/history?lang=ru')
        history_search = page.locator('.content input[name="q"]')
        history_search.fill('MENTS-AP')
        history_search.press('Enter')
        expect(page.locator('a[href="/session/ui-legacy-own"]')).to_be_visible()
        exported = page.request.get(base + '/export/history?q=MENTS-AP&format=json')
        assert exported.ok and any(row['connection_id'] == 'ui-legacy-own' for row in exported.json())
        page.goto(base + '/me/history?q=MENTS-AP')
        expect(page.locator('.content table')).to_contain_text('legacy-own-account')
        expect(page.locator('.content table')).not_to_contain_text('legacy-other-account')
        page.get_by_text('Период', exact=True).click()
        start = page.locator('.content [name="since"]')
        start.fill('2026-02-30')
        with page.expect_navigation() as navigation:
            start.press('Enter')
        assert navigation.value.status == 400
        expect(page.locator('#history-filter-error')).to_contain_text('Укажите дату начала в UTC')
        expect(start).to_have_value('2026-02-30')
        expect(start).to_be_focused()
        start.fill('')
        with page.expect_navigation() as navigation:
            start.press('Enter')
        assert navigation.value.ok
        expect(page.locator('.content table')).to_contain_text('legacy-own-account')
        page.screenshot(path=str(output / 'session-history.png'), full_page=True)

        page.goto(base + '/inventory?project=payments')
        inventory = page.locator('.admin-inventory')
        def assert_centered(dialog):
            expect(dialog).to_be_visible()
            bounds = dialog.bounding_box()
            viewport = page.viewport_size
            # A classic vertical scrollbar can reserve a narrow strip beside the fixed dialog.
            for position, length, tolerance in (('x', 'width', 9), ('y', 'height', 2)):
                assert abs(bounds[position] + bounds[length] / 2 - viewport[length] / 2) <= tolerance, bounds
                assert bounds[position] >= 10, bounds
            assert dialog.evaluate('element => element.scrollWidth === element.clientWidth'), bounds

        add_host = inventory.get_by_role('button', name='Добавить сервер', exact=True)
        page.set_viewport_size({'width': 390, 'height': 420})
        add_host.click()
        add_dialog = inventory.get_by_role('dialog', name='Добавить сервер')
        assert_centered(add_dialog)
        assert add_dialog.evaluate('element => element.scrollHeight > element.clientHeight')
        close = add_dialog.get_by_role('button', name='Закрыть')
        add_dialog.evaluate('element => { element.scrollTop = element.scrollHeight; }')
        close.click()
        expect(add_dialog).to_be_hidden()
        expect(add_host).to_be_focused()
        page.set_viewport_size({'width': 1440, 'height': 1000})
        inventory.locator('input[name="selected_host_id"][value="1"]').check()
        expect(inventory.locator('.inventory-selection')).to_contain_text('1')
        inventory.get_by_role('button', name='Массовое обновление').click()
        bulk = inventory.locator('dialog[open]')
        expect(bulk.get_by_role('heading', name='Массовое обновление')).to_be_visible()
        assert_centered(bulk)
        bulk.locator('[name="owner"]').fill('Fixture inventory owner')
        bulk.locator('[name="confirm"]').check()
        bulk.get_by_role('button', name='Применить изменения').click()
        expect(inventory.locator('table')).to_contain_text('Fixture inventory owner')
        inventory.get_by_role('button', name='Подробнее').first.click()
        host_dialog = inventory.locator('dialog[open]')
        expect(host_dialog).to_contain_text('Учётная запись SSH')
        assert_centered(host_dialog)
        page.screenshot(path=str(output / 'inventory-details.png'), full_page=True)
        page.keyboard.press('Escape')

        page.goto(base + '/grants')
        rules_inspector = page.locator('.admin-split aside')
        expect(rules_inspector).to_contain_text('Support')
        grants_url = page.url
        edit_rule = rules_inspector.get_by_role('link', name='Редактировать')
        edit_rule.click()
        rule_dialog = page.get_by_role('dialog', name='Редактировать правило')
        assert_centered(rule_dialog)
        expect(rule_dialog.locator('[name="name"]')).to_have_value('Support')
        assert page.url == grants_url
        page.keyboard.press('Escape')
        expect(rule_dialog).to_be_hidden()
        expect(edit_rule).to_be_focused()
        rules_inspector.get_by_role('button', name='Удалить').click()
        remove_dialog = page.get_by_role('dialog', name='Удалить правило')
        assert_centered(remove_dialog)
        expect(remove_dialog).to_contain_text('Support')
        remove_dialog.get_by_role('button', name='Закрыть').click()

        page.get_by_role('link', name='Добавить правило').click()
        add_rule = page.get_by_role('dialog', name='Добавить правило')
        assert_centered(add_rule)
        add_rule.locator('[name="name"]').fill('Fixture invalid rule')
        add_rule.locator('[name="selector_value"]').fill('   ')
        add_rule.locator('[name="remote_user"]').fill('support')
        add_rule.locator('[name="confirm"]').check()
        add_rule.get_by_role('button', name='Сохранить правило').click()
        expect(add_rule.get_by_role('alert')).to_be_visible()
        expect(add_rule.locator('[name="name"]')).to_have_value('Fixture invalid rule')
        page.keyboard.press('Escape')

        page.get_by_role('link', name='Наборы проектов', exact=False).first.click()
        expect(page.locator('.admin-tabs [aria-current="page"]')).to_contain_text('Наборы проектов')
        page.get_by_role('link', name='Создать набор').click()
        add_set = page.get_by_role('dialog', name='Создать набор')
        assert_centered(add_set)
        add_set.locator('[name="name"]').fill('ui-dialog-fixture')
        add_set.locator('[name="projects"]').fill('payments')
        add_set.locator('[name="confirm"]').check()
        add_set.get_by_role('button', name='Сохранить набор').click()
        expect(add_set).to_be_hidden()
        page.get_by_role('link', name='ui-dialog-fixture').click()
        rules_inspector.get_by_role('link', name='Редактировать').click()
        edit_set = page.get_by_role('dialog', name='Редактировать набор')
        assert_centered(edit_set)
        expect(edit_set.locator('[name="projects"]')).to_have_value('payments')
        page.keyboard.press('Escape')
        rules_inspector.get_by_role('button', name='Удалить').click()
        remove_set = page.get_by_role('dialog', name='Удалить набор')
        assert_centered(remove_set)
        remove_set.locator('[name="confirm"]').check()
        remove_set.get_by_role('button', name='Удалить').click()
        expect(page.get_by_role('link', name='ui-dialog-fixture')).to_have_count(0)

        page.goto(base + '/packages?view=catalog&editor=new')
        builder = page.locator('[data-package-builder]')
        builder.locator('[data-package-add]').click()
        expect(builder.locator('[data-package-rule-list] fieldset')).not_to_have_count(0)
        rules = builder.locator('[data-package-rule-list] .admin-fields')
        expect(rules.last.locator(':scope > .field-help-trigger')).to_have_count(0)
        expect(rules.last.locator('.field-help-admin-slot > .field-help-trigger').first).to_be_visible()
        assert rules.evaluate_all("""groups => {
          const ids = groups.flatMap(group => Array.from(group.querySelectorAll('.field-hint[id]'), hint => hint.id));
          return ids.length && new Set(ids).size === ids.length;
        }"""), 'cloned rules must keep separate help descriptions'
        page.goto(base + '/policy/matrix')
        page.get_by_role('link', name='По субъектам').click()
        expect(page.locator('.admin-tabs [aria-current="page"]')).to_have_text('По субъектам')
        for view, field, value in (
            ('project', 'project', 'payments'), ('subject', 'principal', 'group:Support'), ('findings', 'finding', 'conflict'),
        ):
            page.goto(base + '/policy/matrix?view=' + view + '&lang=en')
            filters = page.locator('form.matrix-filters')
            controls = filters.locator('input[type="search"], select, button[type="submit"]')
            if view != 'findings':
                filters.get_by_role('searchbox').fill('Support')
            filters.locator(f'[name="{field}"]').select_option(value)
            with page.expect_navigation() as navigation:
                filters.get_by_role('button', name='Filter').click()
            assert navigation.value.ok
            expect(filters.locator('[name="view"]')).to_have_value(view)
            expect(filters.locator(f'[name="{field}"]')).to_have_value(value)
            if view != 'findings':
                expect(filters.get_by_role('searchbox')).to_have_value('Support')
            for width in (1440, 900, 390):
                page.set_viewport_size({'width': width, 'height': 844})
                bounds = controls.evaluate_all("items => items.map(item => item.getBoundingClientRect().toJSON())")
                assert len(bounds) == (2 if view == 'findings' else 3)
                assert max(rect['height'] for rect in bounds) - min(rect['height'] for rect in bounds) <= 1, (view, width, bounds)
                if width == 390:
                    assert max(rect['left'] for rect in bounds) - min(rect['left'] for rect in bounds) <= 1, (view, bounds)
                    assert max(rect['right'] for rect in bounds) - min(rect['right'] for rect in bounds) <= 1, (view, bounds)
                    assert all(a['bottom'] < b['top'] for a, b in zip(bounds, bounds[1:])), (view, bounds)
                else:
                    assert max(rect['bottom'] for rect in bounds) - min(rect['bottom'] for rect in bounds) <= 1, (view, width, bounds)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (view, width)
                if width != 900:
                    page.screenshot(path=str(output / f'access-matrix-{view}-{width}.png'), animations='disabled')
            page.set_viewport_size({'width': 1440, 'height': 1000})
        page.goto(base + '/policy/matrix?view=subject&lang=ru')
        page.get_by_role('link', name='Оценить изменение').click()
        matrix_fields = page.locator('.access-form .admin-fields')
        expect(matrix_fields.locator(':scope > *')).to_have_count(9)
        expect(matrix_fields.locator(':scope > .field-help-trigger')).to_have_count(0)
        help_button = matrix_fields.locator('.field-help-admin-slot > .field-help-trigger').first
        initial_layout = matrix_fields.locator('input, select').evaluate_all(
            "controls => controls.map(control => control.getBoundingClientRect().toJSON())")
        assert len({field['x'] for field in initial_layout}) == 3
        help_button.hover()
        expect(page.locator('.field-help-popup')).to_be_visible()
        assert initial_layout == matrix_fields.locator('input, select').evaluate_all(
            "controls => controls.map(control => control.getBoundingClientRect().toJSON())"), 'opening help shifts matrix fields'
        page.screenshot(path=str(output / 'access-matrix-fields.png'), animations='disabled')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert matrix_fields.locator('input, select').evaluate_all(
            'controls => new Set(controls.map(control => control.getBoundingClientRect().x)).size === 1'
        ), 'matrix fields must stack on a narrow screen'
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'matrix form overflows mobile'
        page.set_viewport_size({'width': 1440, 'height': 1000})
        page.goto(base + '/jobs?view=runbooks&runbook=uptime')
        page.locator('#runbook-launch [name="host_ids"]').fill('1')
        page.get_by_role('button', name='Проверить перед запуском').click()
        queue_form = page.locator('form').filter(has=page.locator('[name="action"][value="queue_runbook"]'))
        expect(queue_form.locator('[name="host_ids"]')).to_have_value('1')
        page.screenshot(path=str(output / 'runbook-review.png'), full_page=True)

        page.get_by_role('link', name='Управление регламентами').click()
        page.get_by_role('link', name='Новый регламент').click()
        page.locator('[name="runbook_id"]').fill('browser-runbook')
        page.locator('[name="runbook_title"]').fill('Browser runbook fixture')
        page.locator('[name="runbook_commands"]').fill('[["/usr/bin/id", "-u"]]')
        page.get_by_text('Предпросмотр команды', exact=True).click()
        page.get_by_role('button', name='Показать команду').click()
        expect(page.locator('.content pre')).to_have_text('/usr/bin/id -u')
        page.get_by_role('button', name='Сохранить черновик').click()
        page.get_by_role('button', name='Опубликовать черновик').click()
        publish_dialog = page.get_by_role('dialog', name='Опубликовать черновик')
        assert_centered(publish_dialog)
        publish_dialog.get_by_role('checkbox').check()
        publish_dialog.get_by_role('button', name='Опубликовать черновик').click()
        expect(page.locator('.content table')).to_contain_text('Текущая')
        page.screenshot(path=str(output / 'custom-runbook-admin.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'runbook editor overflows mobile'
        page.set_viewport_size({'width': 1440, 'height': 1000})

        page.goto(base + '/audit/search?event=ssh_start&host_id=')
        expect(page.locator('.audit-search table')).to_contain_text('alex.morgan')
        page.goto(base + '/audit/search?since=2026-02-30')
        expect(page.locator('#audit-filter-error')).to_be_visible()
        assert not errors, errors
        context.close()
        browser.close()
    assert "whoami" in commands and "first-command" in commands and "second-command" in commands, commands
    print("PASS: catalogue filters/favorites/recent, responsive layout, real Web SSH, tabs/split/search/settings, paste guard, persisted replay bookmarks")
    print('PASS: browser access explanation, policy impact, owner review, canary confirmation/cancellation and correlated investigation')
    print('PASS: light/dark/system themes, saved preference, OS appearance changes, blocked storage, navigation search and mobile controls')
    print('PASS: centered administrative dialogs, responsive scroll, focus restoration, policy form validation')
    print('PASS: custom runbook draft, command preview and confirmed publication')


async def main(output):
    output.mkdir(parents=True, exist_ok=True)
    fixture = fixtures.RuntimeTest()
    fixture.setUp()
    config = fixture.config
    fixture.claims['scope'] = 'isolate.runbook isolate.execute'
    fixture.token = fixture.sign(fixture.claims)
    work = Path(fixture.directory.name)
    options = {"backend": "sqlite", "sqlite_path": str(work / "state.db")}
    SQLState(options).initialize()
    store = StateClient(fixture.redis, options)
    config["state"] = options
    config["dashboard"].update(admin_groups=["Support"], locale="ru", refresh_seconds=0)
    config['session_control']['terminate_enabled'] = True
    from isolate_audit_index import AuditIndex
    config['audit_index'].update(enabled=True, driver='sqlite', path=str(work / 'audit.sqlite'))
    AuditIndex(config['audit_index']).initialize()
    import time
    overview_events = ('identity_login', 'connection_ticket_created', 'ssh_start',
                       'policy_selected', 'access_request_denied', 'ssh_end') * 2
    for index, event in enumerate(overview_events):
        AuditIndex(config['audit_index']).ingest({
            'event_id': 'overview-fixture-' + str(index), 'event': event,
            'ts': int(time.time()) - (len(overview_events) - index) * 34, 'username':'alex.morgan',
            'project':'payments', 'host_id':'1',
        })
    config['logging']['sinks'] = [dict(config['audit_index'], type='sql')]
    campaign_key = work / 'campaign-key'
    campaign_key.write_bytes(b'isolated-ui-campaign-key-with-at-least-32-bytes')
    campaign_key.chmod(0o600)
    config['identity_security']['delegation']['enabled'] = True
    config['command_execution'].update(enabled=True, allowed_groups=['Support'], signing_key_file=str(campaign_key), jobs_path=str(work / 'jobs'))
    config['runbooks']['enabled'] = True
    config['runbooks']['read_only']['allowed_groups'] = ['Support']
    config['campaigns']['enabled'] = True
    host_key, client_key = asyncssh.generate_private_key("ssh-ed25519"), asyncssh.generate_private_key("ssh-ed25519")
    client_path = work / "client-key"
    client_key.write_private_key(str(client_path))
    client_path.chmod(0o600)
    commands, connection_ids = [], []
    class Target(asyncssh.SSHServer):
        def begin_auth(self, username): return True
        def public_key_auth_supported(self): return True
        def validate_public_key(self, username, key): return username == "support" and key == client_key.convert_to_public()
    async def process(remote):
        remote.stdout.write("Isolate test target ready\r\n" + "\r\n" * 120 + "isolate-test$ ")
        pending = ""
        while True:
            try:
                data = await remote.stdin.read(4096)
            except asyncssh.TerminalSizeChanged:
                continue
            if not data:
                break
            # Simulate a real PTY's ICRNL processing for xterm's Enter key.
            pending += data.replace("\r\n", "\n").replace("\r", "\n")
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                command = line.strip()
                commands.append(command)
                remote.stdout.write(("support" if command == "whoami" else "completed: " + command) + "\r\n")
        remote.exit(0)
    target = await asyncssh.create_server(Target, "127.0.0.1", 0, server_host_keys=[host_key],
        process_factory=process, encoding="utf-8", config=[], line_editor=True)
    known = work / "known-hosts"
    known.write_bytes(("[127.0.0.1]:{} ".format(target.get_port())).encode() + host_key.export_public_key())
    config["gateway"].update(known_hosts=str(known), recheck_interval=.2)
    config["credentials"] = {"default": "ui", "known_hosts": str(known), "targets": {},
        "providers": {"ui": {"type": "file", "private_key_file": str(client_path)}}}
    for i, project, name in ((1, "payments", "payments-api"), (2, "payments", "payments-database"),
                              (3, "platform", "build-dashboard"), (4, "platform", "metrics-cluster"), (5, "analytics", "mysql-analytics")):
        store.set("server_" + str(i), json.dumps({"server_id": str(i), "project_name": project, "server_name": name,
            "server_ip": "127.0.0.1", "server_port": target.get_port(), "resource_owner": "Platform Engineering",
            "environment": "Staging", "tags": {"team": project, "region": "eu-west"}}))
    store.set("grant_1", json.dumps({"subject": "group", "name": "Support", "project": "*", "remote_user": "support", "sudo_mode": "none", "allowed_actions": ["ssh", "http", "kubernetes", "postgresql", "mysql", "runbook"]}))
    store.set('offset_grant_id', 1)
    service_token = work / "kubernetes-token"
    service_token.write_text("synthetic-unused-fixture-token")
    service_token.chmod(0o600)
    config["protocols"].update(enabled=True, targets={
        "2": {"protocol": "postgresql", "project": "payments", "upstream": "postgresql://database.example", "database_native_auth": True},
        "3": {"protocol": "http", "project": "platform", "upstream": "https://dashboard.example"},
        "4": {"protocol": "kubernetes", "project": "platform", "upstream": "https://cluster.example", "impersonation": True,
            "bearer_token_file": str(service_token), "allowed_paths": ["/api/*"]},
        "5": {"protocol": "mysql", "project": "analytics", "upstream": "mysql://mysql.example", "database_native_auth": True}})
    fixture.redis = store
    patcher = __import__('unittest.mock', fromlist=['patch']).patch("isolate_web.redis_client", return_value=store)
    patcher.start()
    app = create_app(config)
    app.config.update(TESTING=True, SECRET_KEY="ui-test-synthetic-signing-secret")
    http = make_server("127.0.0.1", 0, app, threaded=True, request_handler=Quiet)
    base = "http://127.0.0.1:" + str(http.server_port)
    config["dashboard"]["public_url"] = base
    config["gateway"]["allowed_origins"] = [base]
    runtime = Runtime(config, store)
    gateway = web.AppRunner(create_web_app(runtime), access_log=None)
    await gateway.setup()
    site = web.TCPSite(gateway, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    config["gateway"]["public_web_url"] = "ws://127.0.0.1:" + str(port)
    identity = runtime.authenticate(fixture.token)
    for owner, subject, suffix in ((identity['username'], identity['keycloak_sub'], 'own'),
                                   ('another-engineer', 'ui-other-subject', 'other')):
        connection_id = 'ui-legacy-' + suffix
        audit_dir = Path(config['logging']['base_path']) / owner / connection_id
        audit_dir.mkdir(parents=True)
        start = {'event': 'ssh_start', 'ts': time.time() - 300, 'username': owner, 'keycloak_sub': subject,
                 'host_id': '1', 'project': 'payments', 'target_host': '127.0.0.1', 'connection_id': connection_id,
                 'remote_user': 'legacy-' + suffix + '-account'}
        end = dict(start, event='ssh_end', ts=start['ts'] + 1, exit_code=0)
        (audit_dir / 'session.jsonl').write_text(json.dumps(start) + '\n' + json.dumps(end) + '\n', encoding='utf-8')
    store.set("isolate_browser_ui-test", json.dumps({"sub": identity["keycloak_sub"], "token": fixture.token}))
    cookie = app.session_interface.get_signing_serializer(app).dumps({"identity": identity, "runtime_session": "ui-test", "csrf_token": "ui-test-csrf"})
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        await asyncio.to_thread(browser_checks, base, cookie, output, commands, connection_ids, store, config['audit_index'])
    finally:
        await asyncio.to_thread(http.shutdown)
        http.server_close()
        await gateway.cleanup()
        target.close()
        await target.wait_closed()
        patcher.stop()
        fixture.doCleanups()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()) / "isolate-ui-verification")
    args = parser.parse_args()
    asyncio.run(main(args.output))
