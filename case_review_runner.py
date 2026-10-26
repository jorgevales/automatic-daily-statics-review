#!/usr/bin/env python3
"""Single-file Studio/Register case review runner, installed Edge, S: storage.

MINIMUM FILES: this runner, Run_case_reviews.cmd, your instructions Markdown and
base-message Markdown. No old modules, JSON configuration or requirements file.
Double-click the CMD and paste the prepared case root, or drag that root onto it.
The default action submits real cases. --discover-only validates without sending.
--setup installs missing Python dependencies on S: only; no browser download.

Default prompt names: daily_review_instructions.md and daily_review_base_message.md.
Also accepts instructions.md/base_message.md. Ambiguity prompts for a choice.
Prompt contents are not rewritten. A separated case-information block is appended.
If the base declares daily-case-review/v1, its strict completion contract is checked.
Otherwise terminal UI completion is used: exact user-message proof, a fresh assigned
conversation, a stable assistant response, no generation and visible response actions.
UI completion records raw review text, not an inferred substantive audit finding.

Six rolling slots, max 20 total attachments, immutable manifests, shared permanent
claims, no uncertain-send replay, no outcome-driven retries. Claims from the prior
package remain authoritative; no force-unlock or browser-session copying is offered.
An old submitted assignment is observation-only and never automatically resubmitted.

Only installed msedge.exe may execute outside S:. Windows/Edge OS-level activity is
outside Python's control. Profiles and evidence outputs on a network share require
appropriate user access permissions. No administrator elevation or policy bypass.
Local synthetic tests do not establish live tenant/Windows compatibility.
"""
from __future__ import annotations
import argparse, asyncio, contextlib, copy, ctypes, hashlib, importlib, importlib.util
import inspect, json, os, re, runpy, shutil, socket, stat, subprocess, sys, tempfile
import time, traceback, urllib.request, uuid, zipfile
import logging
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit


import argparse

from dataclasses import dataclass

import csv

import asyncio

import json

import os

import re

import shutil

import subprocess

import sys

import time

import threading

import urllib.error

import urllib.request

import traceback

import gc

import tempfile

import stat

from concurrent.futures import ThreadPoolExecutor, as_completed

from datetime import datetime

from pathlib import Path

from contextlib import contextmanager

from html import unescape

from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

_PROCESS_STARTED_AT = time.perf_counter()

_LAST_LOG_AT = _PROCESS_STARTED_AT

_BUILTIN_PRINT = print

_RECORDER = None

def print(*values: object, **kwargs: Any) -> None:
    """Print clean timestamped lines with elapsed time."""
    global _LAST_LOG_AT
    now = time.perf_counter()
    total = now - _PROCESS_STARTED_AT
    step = now - _LAST_LOG_AT
    _LAST_LOG_AT = now
    destination = kwargs.pop("file", sys.stdout)
    flush = kwargs.pop("flush", True)
    message = " ".join(str(value) for value in values)
    if _RECORDER is not None:
        _RECORDER.console(message, 'error' if destination is sys.stderr else 'info')
    lines = message.splitlines() or [""]
    for line in lines:
        prefix = f"[{time.strftime('%H:%M:%S')}] [{total:7.2f}s] [+{step:6.2f}s]"
        _BUILTIN_PRINT(prefix, line, file=destination, flush=flush, **kwargs)

class MissingDependencyError(RuntimeError):
    """Raised when the local Playwright package is unavailable."""

class _UninitializedPlaywrightError(Exception):
    """Placeholder replaced by Playwright's error type before automation runs."""

PlaywrightError: type[Exception] = _UninitializedPlaywrightError

PlaywrightTimeoutError: type[Exception] = TimeoutError

ATTACHMENT_INPUT_READY_TIMEOUT_SECONDS = 2.0

VERBOSE_FILE_INPUT_DETAILS = False

TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS = 2.25

TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS = 0.45

CACHED_LOCATOR_FAST_TIMEOUT_MS = 120

_PAGE_UI_CACHE: dict[int, dict[str,Any]] = {}

def load_playwright() -> None:
    """Load Playwright after command-line parsing so --help always works."""
    global PlaywrightError, PlaywrightTimeoutError, async_playwright

    try:
        from playwright.async_api import (
            Error as ImportedPlaywrightError,
            TimeoutError as ImportedPlaywrightTimeoutError,
            async_playwright as imported_async_playwright,
        )
    except ImportError as exc:
        raise MissingDependencyError(
            "Playwright is required.\n"
            "Install it, then run this script again:\n"
            "  py -m pip install --upgrade playwright\n"
            "(Use python3 instead of py on macOS or Linux.)"
        ) from exc

    PlaywrightError = ImportedPlaywrightError
    PlaywrightTimeoutError = ImportedPlaywrightTimeoutError
    async_playwright = imported_async_playwright

def get_cdp_version(endpoint: str, timeout: float = 1.5) -> Optional[dict[str, object]]:
    """Return the remote-debugging version payload when Edge is ready."""
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            f"{endpoint}/json/version", timeout=timeout
        ) as response:
            if response.status != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ):
        return None

    if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
        return None
    return payload

def _consume_background_task(task: asyncio.Task) -> asyncio.Task:
    """Prevent abandoned Playwright futures from producing unretrieved exceptions."""
    def _done(done: asyncio.Task) -> None:
        try:
            done.exception()
        except (asyncio.CancelledError, Exception):
            pass
    task.add_done_callback(_done)
    return task

async def page_target_id(page: Any) -> str:
    session = None
    try:
        session = await page.context.new_cdp_session(page)
        info = await session.send("Target.getTargetInfo")
        return str(info.get("targetInfo", {}).get("targetId", ""))
    except Exception:
        return ""
    finally:
        if session is not None:
            try:
                await session.detach()
            except Exception:
                pass

async def cached_visible(page: Page,key: str,timeout_ms: int = CACHED_LOCATOR_FAST_TIMEOUT_MS) -> Optional[Locator]:
    """Validate a cached Locator briefly; callers fall back to normal discovery."""
    locator=_PAGE_UI_CACHE.get(id(page),{}).get(key)
    if locator is None:
        return None
    deadline=time.monotonic()+max(0,timeout_ms)/1000
    while True:
        try:
            if await locator.count() and await locator.is_visible():
                return locator
        except PlaywrightError:
            break
        if time.monotonic()>=deadline:
            break
        await asyncio.sleep(0.010)
    _PAGE_UI_CACHE.get(id(page),{}).pop(key,None)
    return None

def cache_page_locator(page: Page,key: str,locator: Optional[Locator]) -> Optional[Locator]:
    if locator is not None:
        _PAGE_UI_CACHE.setdefault(id(page),{})[key]=locator
    return locator

async def cached_first_visible(page: Page,key: str,locators: Sequence[Locator],timeout_ms: int) -> Optional[Locator]:
    cached=await cached_visible(page,key)
    if cached is not None:
        return cached
    return cache_page_locator(page,key,await first_visible(locators,timeout_ms))

async def first_visible(
    locators: Sequence[Locator], timeout_ms: int, poll_interval_seconds: float = 0.008,
) -> Optional[Locator]:
    """Return the first visible match while probing locator strategies concurrently."""
    async def probe(locator: Locator) -> Optional[Locator]:
        try:
            count = min(await locator.count(), 12)
            for index in range(count):
                candidate = locator.nth(index)
                if await candidate.is_visible():
                    return candidate
        except PlaywrightError:
            return None
        return None
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000
    while True:
        for result in await asyncio.gather(*(probe(locator) for locator in locators)):
            if result is not None:
                return result
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(poll_interval_seconds)

def editor_locators(page: Page) -> list[Locator]:
    """Return editor locators from most specific to most general."""
    return [
        page.locator("#m365-chat-editor-target-element"),
        page.locator(
            "[data-testid*='chat-editor' i] [contenteditable='true']"
        ),
        page.locator(
            "[data-test-id*='chat-editor' i] [contenteditable='true']"
        ),
        page.locator(
            "[role='textbox'][contenteditable='true'][aria-label*='Copilot' i]"
        ),
        page.locator("[role='textbox'][aria-label*='Message' i]"),
        page.locator("textarea[aria-label*='Copilot' i]"),
        page.locator("textarea[placeholder*='message' i]"),
        page.locator("main [contenteditable='true'][role='textbox']"),
    ]

def model_switcher_locators(page: Page) -> list[Locator]:
    """Return known and accessible model-switcher locators."""
    return [
        page.locator("#gptModeSwitcher"),
        page.locator("[data-testid*='gptModeSwitcher' i]"),
        page.locator("[data-test-id*='gptModeSwitcher' i]"),
        page.get_by_role(
            "button",
            name=re.compile(
                r"Quick response|Think(?:ing)? deeper|Deep response|"
                r"Auto|Instant|Smart|GPT(?:[-\s]?\d)?",
                re.IGNORECASE,
            ),
        ),
        page.locator("button[aria-label*='response mode' i]"),
        page.locator("button[aria-label*='mode selector' i]"),
        page.locator("button[aria-label*='model selector' i]"),
        page.locator("button[aria-label*='GPT' i][aria-haspopup]"),
        page.locator("button[title*='model' i]"),
    ]

async def locator_description(locator: Locator) -> str:
    """Read the visible and accessible text exposed by a control."""
    try:
        value = await locator.evaluate(
            """
            element => [
                element.innerText,
                element.textContent,
                element.getAttribute('aria-label'),
                element.getAttribute('title')
            ].filter(Boolean).join(' ')
            """
        )
    except PlaywrightError:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()

async def editor_text(editor: Locator) -> str:
    value = await editor.evaluate(
        """
        element => {
            if ('value' in element) {
                return element.value || '';
            }
            return element.innerText || element.textContent || '';
        }
        """
    )
    return str(value)

async def make_urls_clickable(editor: Locator, message: str) -> None:
    """Turn URL text in the contenteditable editor into clickable links."""
    await editor.evaluate(
        r"""
        (element, originalMessage) => {
            const pattern = /https:\/\/[^\s<]+/g;
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const nodes = [];
            while (walker.nextNode()) nodes.push(walker.currentNode);
            for (const node of nodes) {
                const value = node.nodeValue || '';
                pattern.lastIndex = 0;
                if (!pattern.test(value)) continue;
                pattern.lastIndex = 0;
                const fragment = document.createDocumentFragment();
                let cursor = 0;
                for (const match of value.matchAll(pattern)) {
                    const url = match[0];
                    const index = match.index || 0;
                    if (index > cursor) fragment.appendChild(document.createTextNode(value.slice(cursor, index)));
                    const link = document.createElement('a');
                    link.href = url;
                    link.textContent = url;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    fragment.appendChild(link);
                    cursor = index + url.length;
                }
                if (cursor < value.length) fragment.appendChild(document.createTextNode(value.slice(cursor)));
                node.parentNode.replaceChild(fragment, node);
            }
            element.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: originalMessage}));
            element.dispatchEvent(new Event('change', {bubbles: true}));
        }
        """,
        message,
    )

async def add_text_to_editor(
    page: Page,
    message: str,
    timeout_ms: int,
) -> None:
    """Place text in the Copilot editor without triggering submission."""
    editor = await cached_first_visible(page,"editor",editor_locators(page),timeout_ms)
    if editor is None:
        raise RuntimeError("The Copilot message editor was not found.")

    await editor.click()
    try:
        await editor.fill(message)
    except PlaywrightError:
        select_all = "Meta+A" if sys.platform == "darwin" else "Control+A"
        await editor.press(select_all)
        await editor.press("Backspace")
        # insert_text emits text input only; it cannot submit the prompt through
        # an Enter key event.
        await page.keyboard.insert_text(message)

    # Ensure the visible SharePoint URL is a real hyperlink, not only plain text.
    try:
        await make_urls_clickable(editor, message)
    except PlaywrightError:
        # Keep the full URL visible if this Copilot UI build blocks rich HTML.
        pass

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            actual = await editor_text(editor)
        except PlaywrightError:
            actual = ""
        if message in actual:
            return
        await asyncio.sleep(0.015)

    raise RuntimeError("The test message could not be confirmed in the editor.")

def attachment_button_locators(page: Page) -> list[Locator]:
    """Only genuine composer attachment controls; never quick-action buttons."""
    return [
        page.locator("#plus-menu-container button[data-testid='PlusMenuButton']"),
        page.locator("button[data-testid='PlusMenuButton'][aria-label='Add and manage sources']"),
        page.locator("button[data-testid='chat-input-attach-button']"),
        page.locator("button[data-test-id='chat-input-attach-button']"),
        page.locator("button[aria-label='Add'][aria-haspopup='menu']"),
    ]

async def ensure_attachment_input(page: Page) -> None:
    """Expose a live file input using independent UI, DOM and coordinate routes.

    The Copilot home screen can show a valid Add button while no input exists.
    That state is not a failed tab. Each pass reacquires the current React nodes
    and tries a different activation technique before declaring the picker unusable.
    """
    async def input_exists() -> bool:
        try:
            return bool(await page.locator("input[type='file']").count())
        except PlaywrightError:
            return False

    if await input_exists():
        return
    deadline = time.monotonic() + max(5.0, ATTACHMENT_INPUT_READY_TIMEOUT_SECONDS)
    last_error: Optional[BaseException] = None
    technique = 0
    while time.monotonic() < deadline:
        if await input_exists():
            return
        technique += 1
        route = technique % 6
        try:
            button = await first_visible(attachment_button_locators(page), timeout_ms=180)
            if route == 1:
                # Native DOM click on the exact visible Add/attachment button.
                await page.evaluate(r"""() => {
                    const selectors=['button[data-testid="chat-input-attach-button"]','button[data-test-id="chat-input-attach-button"]','#plus-menu-container button','button[aria-label="Add"]'];
                    const b=selectors.map(s=>document.querySelector(s)).find(x=>x && !x.disabled && x.getAttribute('aria-disabled')!=='true');
                    if(!b) return false; b.click(); return true;
                }""")
            elif route == 2 and button is not None:
                await button.click(timeout=300, force=True, no_wait_after=True)
            elif route == 3 and button is not None:
                await button.focus(timeout=250)
                await page.keyboard.press("Enter")
            elif route == 4 and button is not None:
                box = await button.bounding_box()
                if box:
                    await page.mouse.click(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
            elif route == 5:
                await page.evaluate(r"""() => {
                    const b=document.querySelector('button[data-testid="chat-input-attach-button"],button[data-test-id="chat-input-attach-button"],button[aria-label="Add"]');
                    if(!b) return false;
                    for(const type of ['pointerdown','mousedown','pointerup','mouseup','click']) b.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window}));
                    return true;
                }""")
            else:
                await activate_page_like_manual_selection(page, 0, "attachment picker recovery", verbose=False)
            # Some builds create the input directly; others first expose an
            # Upload/Browse menu item. Activate that item through both DOM and UI.
            await asyncio.sleep(0.035)
            if await input_exists():
                return
            clicked = await page.evaluate(r"""() => {
                const rx=/upload|from (?:this )?device|computer|browse files/i;
                const el=[...document.querySelectorAll('[role="menuitem"],[role="button"],button')].find(x=>rx.test([x.innerText,x.textContent,x.getAttribute('aria-label')].filter(Boolean).join(' ')) && !x.disabled);
                if(!el) return false; el.click(); return true;
            }""")
            if not clicked:
                item = await first_visible([
                    page.get_by_role("menuitem", name=re.compile(r"upload|device|computer|browse", re.I)),
                    page.get_by_role("button", name=re.compile(r"upload|device|computer|browse", re.I)),
                ], timeout_ms=120)
                if item is not None:
                    await item.click(timeout=250, force=True, no_wait_after=True)
            if await input_exists():
                return
        except (PlaywrightError, RuntimeError) as exc:
            last_error = exc
        await asyncio.sleep(0.035)
    raise RuntimeError(
        "Copilot displayed an attachment button but no live file input appeared "
        f"after {technique} independent activation attempts. Last UI error: {concise_error(last_error or 'none')}"
    )

async def _best_attachment_input_node(page: Page) -> tuple[Any, int]:
    """Open Copilot's picker and return one live CDP session plus its best file input."""
    await ensure_attachment_input(page)
    session=await page.context.new_cdp_session(page)
    try:
        doc=await session.send('DOM.getDocument',{'depth':-1,'pierce':True})
        root=doc['root']['nodeId']
        result=await session.send('DOM.querySelectorAll',{'nodeId':root,'selector':'input[type=file]'})
        ids=result.get('nodeIds',[])
        if not ids:
            raise RuntimeError('Attachment picker opened, but CDP found no file input.')
        candidates=[]
        for node_id in ids:
            try:
                described=await session.send('DOM.describeNode',{'nodeId':node_id,'depth':1})
                node=described.get('node',{})
                attrs=node.get('attributes',[])
                a={str(attrs[i]):str(attrs[i+1]) for i in range(0,len(attrs)-1,2)}
                accept=a.get('accept','').lower(); score=10
                if '.pdf' in accept or 'application/pdf' in accept: score+=40
                if '.md' in accept or 'text/markdown' in accept: score+=30
                if a.get('disabled') is None: score+=5
                candidates.append((score,int(node_id),accept))
            except Exception:
                candidates.append((0,int(node_id),''))
        candidates.sort(reverse=True)
        score,selected,accept=candidates[0]
        if VERBOSE_FILE_INPUT_DETAILS:
            print(f"    Attachment input: score={score}, candidates={len(candidates)}, accept={accept!r}")
        return session,selected
    except Exception:
        await session.detach()
        raise

async def browser_local_set_input_files_bulk(page: Page, paths: Sequence[Path]) -> None:
    """Replicate one drag/drop selection by assigning the complete file list once."""
    resolved=[str(path.expanduser().resolve()) for path in paths]
    if not resolved:
        return
    session,selected=await _best_attachment_input_node(page)
    try:
        await session.send('DOM.setFileInputFiles',{'files':resolved,'nodeId':selected})
    finally:
        await session.detach()

async def attachment_limit_warning(page: Page) -> Optional[str]:
    """Read only likely visible warning containers; never scan the full page."""
    try:
        value = await page.evaluate(
            r"""() => {
                const visible = el => !!(
                    el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                );
                const pattern = /maximum(?:\s+of)?\s+20|up\s+to\s+20\s+files|20\s+file\s+limit|too\s+many\s+files|remove\s+(?:a|one)\s+file/i;
                const selectors = [
                    '[role="alert"]', '[role="dialog"]', '[aria-live="assertive"]',
                    '[class*="toast" i]', '[class*="messagebar" i]'
                ];
                for (const node of document.querySelectorAll(selectors.join(','))) {
                    if (!visible(node)) continue;
                    const text = (node.innerText || node.textContent || '').trim();
                    if (text && pattern.test(text)) return text.slice(0, 500);
                }
                return '';
            }"""
        )
        return str(value).strip() or None
    except PlaywrightError:
        return None

async def upload_error_message(page: Page) -> Optional[str]:
    """Return a visible Copilot upload error without confusing other alerts."""
    try:
        value = await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            const wanted = /an error occurred while uploading|error while uploading|upload failed|could not upload|try again/i;
            for (const el of document.querySelectorAll('[role="alert"],[aria-live="assertive"],[class*="toast" i],[class*="messagebar" i]')) {
                if (!visible(el)) continue;
                const text=(el.innerText || el.textContent || '').trim();
                if (wanted.test(text)) return text.slice(0,500);
            }
            return '';
        }""")
        return str(value).strip() or None
    except PlaywrightError:
        return None

def send_button_locators(page: Page) -> list[Locator]:
    """Return only controls explicitly identified as Send, never Stop generating."""
    safe_selector = (
        'button[aria-label="Send"], '
        'button[aria-label^="Send "]:not([aria-label*="stop" i]), '
        'button[type="submit"][aria-label*="send" i]:not([aria-label*="stop" i])'
    )
    return [
        page.locator(safe_selector),
        page.get_by_role("button", name=re.compile(r"^Send(?:\s|$)", re.IGNORECASE)),
    ]

async def stop_button_present(page: Page) -> bool:
    """Detect generation state. This control must never be clicked by send code."""
    try:
        return bool(await page.evaluate(r"""() => {
            const visible = el => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
            return [...document.querySelectorAll('button')].some(button => {
                const label=(button.getAttribute('aria-label') || '').trim().toLowerCase();
                return visible(button) && (label === 'stop generating' || label === 'stop' || label.startsWith('stop responding'));
            });
        }"""))
    except PlaywrightError:
        return False

async def attachment_transfer_snapshot(page: Page, expected_names: Sequence[str]) -> dict[str, Any]:
    """Read attachment presence plus live transfer indicators in one browser pass."""
    try:
        return dict(await page.evaluate(r"""names => {
            const visible=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
            const norm=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
            const roots=new Set(); const texts=[];
            for(const selector of ['[aria-label="Attachments"] > [data-overflow-item="true"]','[aria-label="Attachments"] > div[id^="SPO_"]','button[aria-label^="Remove attachment "]']) {
              for(const element of document.querySelectorAll(selector)) {
                const root=element.matches('[data-overflow-item="true"],div[id^="SPO_"]')?element:(element.closest('[data-overflow-item="true"],div[id^="SPO_"]')||element);
                roots.add(root); texts.push(norm([root.innerText,root.textContent,root.getAttribute('aria-label'),root.getAttribute('title')].filter(Boolean).join(' ')));
              }
            }
            const transferRx=/uploading|processing|attaching|scanning|loading|preparing|transferring|pending|in progress/i;
            const spinnerSelectors=['[aria-busy="true"]','[role="progressbar"]','[data-testid*="progress" i]','[data-testid*="upload" i] [class*="spinner" i]','[class*="upload" i] [class*="spinner" i]','[class*="attachment" i] [class*="spinner" i]'];
            const active=[];
            for(const selector of spinnerSelectors) for(const element of document.querySelectorAll(selector)) if(visible(element)) active.push(selector+':'+norm(element.getAttribute('aria-label')||element.innerText||element.textContent).slice(0,120));
            roots.forEach(root=>{ const text=norm([root.innerText,root.textContent,root.getAttribute('aria-label'),root.getAttribute('title')].filter(Boolean).join(' ')); if(transferRx.test(text)) active.push('chip:'+text.slice(0,120)); });
            const send=[...document.querySelectorAll('button')].find(b=>{const label=norm(b.getAttribute('aria-label'));return visible(b)&&(label==='send'||label.startsWith('send '))&&!label.includes('stop');});
            const matched=names.filter(name=>texts.some(text=>text.includes(norm(name))));
            return {count:roots.size, matched, active:[...new Set(active)], sendEnabled:!!(send&&!send.disabled&&send.getAttribute('aria-disabled')!=='true')};
        }""",list(expected_names)))
    except (PlaywrightError,TypeError,ValueError):
        return {'count':0,'matched':[],'active':['snapshot-error'],'sendEnabled':False}

def concise_error(error: BaseException | str) -> str:
    text=str(error or "").strip()
    text=re.split(r"\n(?:Call log:|\s*\. Visible controls:)",text,maxsplit=1)[0]
    return re.sub(r"\s+"," ",text).strip()[:300]

async def _bounded_activation_route(
    label: str,
    awaitable: Any,
    timeout_seconds: float = TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Own and bound one activation route without allowing cancellation to stall."""
    task = asyncio.ensure_future(awaitable)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=max(0.05, timeout_seconds))
        return True, label
    except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError) as exc:
        if not task.done():
            task.cancel()
        _consume_background_task(task)
        return False, f"{label}:{concise_error(exc)}"

async def activate_page_like_manual_selection(
    page: Page,
    tab_number: int,
    reason: str,
    verbose: bool = True,
) -> None:
    """Best-effort multi-route activation with a hard overall deadline.

    Activation is an optimisation, not a prerequisite for queue progression. Each
    Playwright/CDP route is independently bounded and the whole function returns
    quickly even when one target stops answering while browser-level CDP remains
    healthy. No reload or navigation is performed here.
    """
    if page.is_closed():
        raise RuntimeError(f"Tab {tab_number} is closed during {reason}")
    started = time.monotonic()
    successes: list[str] = []
    failures: list[str] = []
    session = None
    ok, detail = await _bounded_activation_route("playwright-front", page.bring_to_front())
    (successes if ok else failures).append(detail)
    try:
        session_task = asyncio.ensure_future(page.context.new_cdp_session(page))
        try:
            session = await asyncio.wait_for(
                asyncio.shield(session_task), TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS
            )
        except (asyncio.TimeoutError, PlaywrightTimeoutError, PlaywrightError) as exc:
            if not session_task.done():
                session_task.cancel()
            _consume_background_task(session_task)
            failures.append(f"cdp-session:{concise_error(exc)}")
        if session is not None:
            for method, params in (
                ("Page.bringToFront", {}),
                ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                ("Page.setWebLifecycleState", {"state": "active"}),
            ):
                if time.monotonic() - started >= TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS:
                    break
                ok, detail = await _bounded_activation_route(
                    method,
                    session.send(method, params),
                )
                (successes if ok else failures).append(detail)
        if time.monotonic() - started < TAB_ACTIVATION_TOTAL_TIMEOUT_SECONDS:
            ok, detail = await _bounded_activation_route(
                "renderer-focus",
                page.evaluate(r"""() => {
                    try { window.focus(); } catch (_) {}
                    document.dispatchEvent(new Event('visibilitychange'));
                    window.dispatchEvent(new Event('focus'));
                    return true;
                }"""),
            )
            (successes if ok else failures).append(detail)
    finally:
        if session is not None:
            detach_task = asyncio.ensure_future(session.detach())
            try:
                await asyncio.wait_for(
                    asyncio.shield(detach_task), TAB_ACTIVATION_ROUTE_TIMEOUT_SECONDS
                )
            except (asyncio.TimeoutError, PlaywrightError):
                if not detach_task.done():
                    detach_task.cancel()
                _consume_background_task(detach_task)
    elapsed = time.monotonic() - started
    if verbose:
        if successes:
            print(
                f"Tab {tab_number}: actively foregrounded for {reason} in {elapsed:.2f}s "
                f"via {','.join(successes)}"
            )
        else:
            print(
                f"TAB ACTIVATION WATCHDOG: Tab {tab_number} did not acknowledge foreground "
                f"activation within {elapsed:.2f}s during {reason}; continuing with direct UI "
                f"probe; routes={'; '.join(failures) or 'no response'}",
                file=sys.stderr,
            )

async def background_wake_page(page: Page) -> bool:
    """Wake a page through its renderer without selecting its visible Edge tab."""
    if page.is_closed():
        return False
    session=None
    try:
        session=await page.context.new_cdp_session(page)
        for method,params in (
            ('Page.enable',{}),
            ('Runtime.enable',{}),
            ('Network.enable',{}),
            ('Emulation.setFocusEmulationEnabled',{'enabled':True}),
            ('Page.setWebLifecycleState',{'state':'active'}),
            ('Runtime.evaluate',{'expression':'void(document.title); void(location.href);','returnByValue':True}),
        ):
            try:
                await session.send(method,params)
            except PlaywrightError:
                pass
        try:
            await page.evaluate(r"""() => {
                document.dispatchEvent(new Event('visibilitychange'));
                window.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new Event('pageshow'));
            }""")
        except PlaywrightError:
            pass
        return True
    except PlaywrightError:
        return False
    finally:
        if session is not None:
            try: await session.detach()
            except PlaywrightError: pass

PYTHON = Path(os.environ.get('DCR_PYTHON') or r'S:\REDACTED_PYTHON\python.exe')

NODE = Path(os.environ.get('DCR_NODE') or r'S:\REDACTED_NODE\node.exe')

RUNTIME_ROOT = Path(os.environ.get('DCR_RUNTIME_ROOT') or r'S:\REDACTED_RUNTIME')

PACKAGE = Path(__file__).resolve().parent

ENTRY = Path(__file__).resolve()

_LAYOUT = None

_S_ROOT = None

_ORIGINAL_EDGE_ENV = {key: os.environ.get('DCR_ORIGINAL_' + key, os.environ.get(key, '')) for key in
                      ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')}

_LAUNCH_ENVIRONMENT = dict(os.environ)

_ORIGINAL_USER_ENV = {key: os.environ.get('DCR_ORIGINAL_' + key, os.environ.get(key, '')) for key in
                      ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'HOME', 'HOMEDRIVE', 'HOMEPATH')}

_APPROVED_EDGE = set()

def edge_environment(folders):
    """'redirected': the S: copies this tool set up. 'normal': the environment the launcher had, as provided
    (what a plain Popen() call inherits), with nothing redirected to S:."""
    if folders == 'normal':
        return dict(_LAUNCH_ENVIRONMENT)
    return os.environ.copy()

def edge_candidates():
    """Read installed Edge locations only; never install, update or copy Edge."""
    candidates = []
    for key in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        root = _ORIGINAL_EDGE_ENV.get(key)
        if root:
            candidates.append(Path(root) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe')
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe',
                                        0, winreg.KEY_READ | view) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                    if isinstance(value, str) and value.strip():
                        candidates.append(Path(os.path.expandvars(value.strip().strip('"'))))
                except OSError:
                    pass
    seen = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path.name.casefold() == 'msedge.exe' and path.is_file() and str(path).casefold() not in seen:
            seen.add(str(path).casefold())
            yield path

def installed_edge(explicit=None, prompt=False):
    """The sole permitted non-S: executable is the installed Edge selected here."""
    if explicit:
        text = os.fsdecode(explicit).strip().strip('"').strip("'")
        path = Path(os.path.expandvars(text)).expanduser()
        if not path.is_absolute():
            raise ValueError('Edge executable must be an absolute path')
        path = path.resolve()
        if path.name.casefold() != 'msedge.exe' or not path.is_file():
            raise FileNotFoundError('Select an existing Microsoft Edge msedge.exe, not Chrome: ' + str(path))
    else:
        path = next(edge_candidates(), None)
        if path is None and prompt and sys.stdin.isatty():
            return installed_edge(input('Paste the installed Microsoft Edge msedge.exe path: '), prompt=False)
        if path is None:
            raise FileNotFoundError('Installed Microsoft Edge was not found. Supply --browser-path with its existing msedge.exe path. No browser will be installed or downloaded.')
    _APPROVED_EDGE.add(path)
    return path

def require_child_executable(value):
    if value is not None and isinstance(value, (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(value).strip().strip('"')).resolve()
        if path in _APPROVED_EDGE and path.name.casefold() == 'msedge.exe' and path.is_file():
            return path
    return require_s(value, 'Child executable')

def require_s(value, label='Path'):
    """Allow S: and its real resolved UNC destination, never invent a share."""
    if _S_ROOT is None:
        raise RuntimeError('S: storage has not been initialised.')
    if value is None:
        raise ValueError(label + ' is missing; no fallback path is permitted')
    if not isinstance(value, (str, bytes, os.PathLike)):
        raise ValueError(label + ' is not a filesystem path: ' + type(value).__name__)
    text = display_path(value).strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if not text:
        raise ValueError(label + ' is empty')
    path = Path(display_path(Path(os.path.expandvars(text)).expanduser().resolve()))
    try:
        path.relative_to(_S_ROOT)
    except ValueError:
        raise ValueError(f'{label} must be on S: or its actual resolved UNC destination, not {path}') from None
    return path

def identity_key(environ=None):
    env = os.environ if environ is None else environ
    parts = [env.get('USERDOMAIN', ''), env.get('USERNAME', ''), env.get('COMPUTERNAME', '')]
    if not parts[1] or not parts[2]:
        raise RuntimeError('Windows user/machine identity is unavailable; refusing a shared browser profile.')
    return hashlib.sha256('\0'.join(x.casefold() for x in parts).encode('utf-8')).hexdigest()[:32]

def s_spelling(value):
    """Return the same S: location spelled as S:\\..., never the long resolved network path."""
    path = Path(display_path(value))
    if _S_ROOT is None:
        return path
    try:
        return Path('S:/') / path.resolve().relative_to(_S_ROOT)
    except ValueError:
        return path


# Windows limit for a full path is 260 characters. The longest file in the Playwright package is 98
# characters below its folder, so the install folder must leave room for that plus a safety margin.
PACKAGE_LONGEST_RELATIVE = 108
WINDOWS_PATH_BUDGET = 250

def child_executable(executable, argv):
    """Resolve the executable when Windows reports None in the Popen audit event.

    Windows can pass executable=None and a quoted command-line string. Validate
    its first executable token instead of passing None to os.fsdecode. Never use
    PATH lookup, shell=True, a default interpreter or a personal-drive fallback.
    """
    if executable is not None:
        return require_child_executable(executable)
    if isinstance(argv, (list, tuple)):
        if not argv or argv[0] is None:
            raise ValueError('Child command has no executable; launch refused')
        return require_child_executable(argv[0])
    if isinstance(argv, (str, bytes)):
        command = os.fsdecode(argv).lstrip()
        if not command:
            raise ValueError('Child command is empty; launch refused')
        if command.startswith('"'):
            end = command.find('"', 1)
            if end < 0 or (end + 1 < len(command) and not command[end + 1].isspace()):
                raise ValueError('Child executable quoting is invalid; launch refused')
            token = command[1:end]
        else:
            token = command.split(None, 1)[0]
        # Relative names would make Windows search the current directory/PATH.
        if not Path(token).is_absolute():
            raise ValueError('Child executable must be an absolute S: path; launch refused')
        return require_child_executable(token)
    raise ValueError('Child command has no usable executable; launch refused')


def is_windows_null_device(value, *, windows=None):
    """Recognise only the Windows null device, not arbitrary device paths.

    This is an open-stream exception only. require_s still rejects device paths
    as evidence, outputs, executables, rename targets or cleanup destinations.
    No file is created on a personal drive when subprocess uses this device.
    """
    if windows is None:
        windows = os.name == 'nt'
    if not windows or isinstance(value, int) or value is None:
        return False
    try:
        text = os.fsdecode(value).replace('/', '\\').casefold()
    except (TypeError, ValueError, UnicodeError):
        return False
    return text in {'nul', '\\\\.\\nul', '\\\\?\\nul'}


class _PdfObjectHeaderWhitespaceFilter(logging.Filter):
    """Suppress this one pypdf warning, retaining other warnings and all errors."""
    _case_review_whitespace_filter = True
    _pattern = re.compile(
        r"Superfluous whitespace found in object header b['\"][0-9]+['\"] b['\"][0-9]+['\"]"
    )

    def filter(self, record):
        if record.name != 'pypdf._reader' or record.levelno != logging.WARNING:
            return True
        try:
            return self._pattern.fullmatch(record.getMessage()) is None
        except Exception:
            return True


def configure_pdf_diagnostics():
    """Idempotent, narrow logging filter; PDF parsing stays strict=True."""
    logger = logging.getLogger('pypdf._reader')
    if not any(getattr(item, '_case_review_whitespace_filter', False) for item in logger.filters):
        logger.addFilter(_PdfObjectHeaderWhitespaceFilter())


def _audit(event, args):
    """Fail closed on Python-level file writes outside S:, including dependency writes."""
    if event == 'open':
        path, mode, flags = args
        writing = (isinstance(mode, str) and any(x in mode for x in 'wax+')) or (
            isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if writing and not isinstance(path, int):
            if is_windows_null_device(path):
                return
            require_s(path, 'Write destination')
    elif event in {'os.mkdir', 'os.remove', 'os.rmdir', 'os.chmod', 'os.utime', 'os.truncate'}:
        if args and not isinstance(args[0], int):
            require_s(args[0], 'Filesystem change')
    elif event in {'os.rename', 'os.link'}:
        for path in args[:2]:
            if not isinstance(path, int):
                require_s(path, 'Filesystem change')
    elif event == 'os.symlink':
        require_s(args[0], 'Link target')
        require_s(args[1], 'Link destination')
    elif event == 'subprocess.Popen':
        executable, argv, cwd, env = args
        child_executable(executable, argv)
        if cwd is not None:
            require_s(cwd, 'Child working directory')

def configure_node_trust():
    """Use Windows-managed CA trust with the specified Node 24 runtime.

    Read-only access to the Windows trust store does not relocate any package
    files to C:. All caches, downloads and application writes remain on S:.
    Never disable TLS verification or trust the server's presented certificate.
    An optional IT-approved PEM may be supplied on S: via NODE_EXTRA_CA_CERTS.
    """
    os.environ['NODE_OPTIONS'] = '--use-system-ca'
    os.environ['NODE_USE_SYSTEM_CA'] = '1'
    os.environ['NODE_TLS_REJECT_UNAUTHORIZED'] = '1'
    extra = os.environ.get('NODE_EXTRA_CA_CERTS', '').strip()
    if extra:
        path = require_s(extra, 'IT-approved additional CA bundle')
        if not path.is_file():
            raise FileNotFoundError('Additional CA bundle is missing: ' + str(path))
        import ssl
        # Parse the supplied PEM with verification enabled. Do not install it
        # into the machine store or infer trust from a failed server handshake.
        ssl.create_default_context().load_verify_locations(cafile=str(path))
        os.environ['NODE_EXTRA_CA_CERTS'] = str(path)
    else:
        os.environ.pop('NODE_EXTRA_CA_CERTS', None)

def initialise():
    global _S_ROOT, _LAYOUT, PACKAGE, ENTRY, PYTHON, NODE, RUNTIME_ROOT
    if _LAYOUT is not None:
        return _LAYOUT
    if os.name != 'nt':
        raise RuntimeError('This entry point is for the specified Windows S: runtime only.')
    if not Path('S:/').is_dir():
        raise RuntimeError('S: is unavailable. No personal-drive fallback is permitted.')
    _S_ROOT = Path(display_path(Path('S:/').resolve(strict=True)))
    require_s(PACKAGE, 'Package folder')
    expected = require_s(PYTHON, 'Required Python executable')
    if not expected.is_file() or Path(sys.executable).resolve() != expected:
        raise RuntimeError(f'Use only the specified Python executable: {PYTHON}')
    # Use the short S: spelling everywhere. resolve() on a mapped drive returns the long network
    # path, which pushes package files past the Windows 260-character limit.
    PACKAGE, ENTRY = s_spelling(PACKAGE), s_spelling(ENTRY)
    PYTHON, NODE, RUNTIME_ROOT = s_spelling(PYTHON), s_spelling(NODE), s_spelling(RUNTIME_ROOT)
    home = s_spelling(require_s(RUNTIME_ROOT / 'users' / identity_key(), 'User runtime'))
    abi = sys.implementation.cache_tag or ('python-' + str(sys.version_info[:2]))
    paths = {
        'home': home,
        'temp': home / 'temp',
        'cache': home / 'cache',
        'pip_cache': home / 'cache' / 'pip',
        'browsers': home / 'browsers',
        'profile': home / 'BrowserProfile',
        'downloads': home / 'downloads',
        'outputs': home / 'outputs',
        'runs': home / 'runs',
        'coordination': RUNTIME_ROOT / 'coordination',
        'logs': home / 'logs',
        'deps': home / 'py' / abi,
        'userprofile': home / 'WindowsProfile',
        'appdata': home / 'AppData' / 'Roaming',
        'localappdata': home / 'AppData' / 'Local',
        'userbase': home / 'PythonUserBase',
        'npm_cache': home / 'cache' / 'npm',
        'crashes': home / 'crashes',
    }
    for label, path in paths.items():
        require_s(path, label).mkdir(parents=True, exist_ok=True)
    paths = {label: s_spelling(require_s(path, label)) for label, path in paths.items()}
    home = paths['home']
    for key, value in {**_ORIGINAL_EDGE_ENV, **_ORIGINAL_USER_ENV}.items():
        os.environ['DCR_ORIGINAL_' + key] = value
    env = {
        'TEMP': paths['temp'], 'TMP': paths['temp'], 'TMPDIR': paths['temp'],
        'APPDATA': paths['appdata'], 'LOCALAPPDATA': paths['localappdata'],
        'USERPROFILE': paths['userprofile'], 'HOME': paths['userprofile'],
        'XDG_CACHE_HOME': paths['cache'], 'XDG_STATE_HOME': home,
        'XDG_CONFIG_HOME': home / 'config',
        'PYTHONUSERBASE': paths['userbase'], 'PYTHONPYCACHEPREFIX': paths['cache'] / 'pycache',
        'PIP_CACHE_DIR': paths['pip_cache'], 'PIP_CONFIG_FILE': home / 'pip-isolated.ini',
        'PLAYWRIGHT_BROWSERS_PATH': paths['browsers'],
        'PLAYWRIGHT_NODEJS_PATH': NODE,
        'npm_config_cache': paths['npm_cache'], 'npm_config_prefix': home / 'npm',
        'NODE_REPL_HISTORY': home / 'node_repl_history',
        'CHROME_LOG_FILE': paths['logs'] / 'browser.log',
        'CRASHPAD_DATABASE_PATH': paths['crashes'],
    }
    for key, value in env.items():
        os.environ[key] = str(value)
    os.environ['HOMEDRIVE'] = 'S:'
    os.environ['HOMEPATH'] = str(RUNTIME_ROOT / 'users' / identity_key() / 'WindowsProfile')[2:]
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    os.environ['PIP_NO_INPUT'] = '1'
    os.environ.pop('PYTHONSTARTUP', None)
    os.environ.pop('PYTHONHOME', None)
    os.environ.pop('NODE_OPTIONS', None)
    os.environ.pop('NODE_PATH', None)
    configure_node_trust()
    sys.dont_write_bytecode = True
    tempfile.tempdir = str(paths['temp'])
    # Embedded Python can ignore PYTHONPATH; add the S: dependency directory explicitly.
    retained = []
    for item in sys.path:
        if not item:
            continue
        try:
            retained.append(str(require_s(item, 'Python import path')))
        except ValueError:
            pass
    sys.path[:] = [str(PACKAGE), str(paths['deps'])] + [x for x in retained if x not in {str(PACKAGE), str(paths['deps'])}]
    os.chdir(PACKAGE)
    _LAYOUT = paths
    sys.addaudithook(_audit)
    return paths

def child(mode, args, log_name):
    paths = initialise()
    command = [str(PYTHON), '-B', '-S', str(ENTRY), mode, *map(str, args)]
    log = paths['logs'] / log_name
    with log.open('a', encoding='utf-8') as out:
        out.write('\nCOMMAND: ' + subprocess.list2cmdline(command) + '\n')
        out.flush()
        with subprocess.Popen(command, executable=str(PYTHON), cwd=str(PACKAGE), env=os.environ.copy(),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding='utf-8', errors='replace') as process:
            for line in process.stdout:
                print(line, end='', flush=True)
                out.write(line)
                out.flush()
            code = process.wait()
    if code:
        raise RuntimeError(f'{mode} failed with exit code {code}. Log: {log}. No C: fallback was used.')

def bootstrap_pip():
    paths = initialise()
    if importlib.util.find_spec('pip') is not None:
        return
    print('Preparing pip in the private S: dependency folder. The shared Python installation is not changed.')
    # Fetch a wheel from the official package index and verify its published digest.
    with urllib.request.urlopen('https://pypi.org/pypi/pip/json', timeout=60) as response:
        metadata = json.load(response)
    wheels = [item for item in metadata['urls'] if item['filename'].endswith('py3-none-any.whl') and not item.get('yanked')]
    if len(wheels) != 1:
        raise RuntimeError('Could not identify one supported pip wheel from the official index.')
    wheel = wheels[0]
    if not wheel['url'].startswith('https://files.pythonhosted.org/'):
        raise RuntimeError('Unexpected pip wheel download host; refusing installation.')
    destination = paths['temp'] / ('pip-' + uuid.uuid4().hex + '.whl')
    try:
        h = hashlib.sha256()
        with urllib.request.urlopen(wheel['url'], timeout=120) as source, destination.open('xb') as target:
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                h.update(block)
                target.write(block)
        if h.hexdigest() != wheel['digests']['sha256']:
            raise RuntimeError('pip wheel checksum verification failed.')
        with zipfile.ZipFile(destination) as archive:
            for item in archive.infolist():
                target = require_s(paths['deps'] / item.filename, 'pip extraction target')
                try:
                    target.relative_to(paths['deps'])
                except ValueError:
                    raise RuntimeError('Unsafe wheel member rejected.') from None
                if item.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open('wb') as out:
                        shutil.copyfileobj(source, out)
        importlib.invalidate_caches()
        if importlib.util.find_spec('pip') is None:
            raise RuntimeError('pip bootstrap did not produce an importable package.')
    finally:
        destination.unlink(missing_ok=True)

EXCLUDED_EVIDENCE_DIRECTORY = '.edge-debug-9223'

REGISTER_IDENTITY_POINTER = '/Account Summary/sections/Account header/Account Code/value'

def display_path(value):
    text = os.fsdecode(value)
    if text.startswith('\\\\?\\UNC\\'):
        return '\\\\' + text[8:]
    if text.startswith('\\\\?\\'):
        return text[4:]
    return text

def long_io_path(value, windows=None):
    """Extended paths for filesystem I/O only; never send these to the browser."""
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return Path(value)
    import ntpath
    text = os.fsdecode(value)
    if text.startswith('\\\\?\\'):
        return text
    text = ntpath.abspath(text)
    if text.startswith('\\\\'):
        return '\\\\?\\UNC\\' + text[2:]
    return '\\\\?\\' + text

def evidence_hash(value):
    h = hashlib.sha256()
    with open(long_io_path(value), 'rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def evidence_json(value):
    with open(long_io_path(value), 'r', encoding='utf-8-sig') as source:
        return json.load(source)

def pointer_value(payload, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ValueError('Account identity pointer must be a JSON Pointer')
    value = payload
    for token in pointer[1:].split('/') if pointer else []:
        key = token.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    if isinstance(value, dict) and set(value).issuperset({'value'}):
        value = value['value']
    if not isinstance(value, str) or not value:
        raise ValueError('Primary Register account identity must be a nonempty string')
    return value

def register_identity(payload, config):
    """Never collect bank numbers, product numbers or linked-account identities."""
    import re
    if not isinstance(payload, dict):
        raise ValueError('Register snapshot must be a JSON object')
    identities = set()
    header_present = False
    try:
        header = payload['Account Summary']['sections']['Account header']
        header_present = isinstance(header, dict) and 'Account Code' in header
    except (KeyError, TypeError):
        pass
    if header_present:
        identities.add(pointer_value(payload, REGISTER_IDENTITY_POINTER))
    explicit = config.get('account_json_pointer', '')
    if explicit:
        identities.add(pointer_value(payload, explicit))
    if not header_present and not explicit:
        # Compatibility with simple snapshots: top-level primary fields only.
        # Deliberately no recursive scan through banking or interested parties.
        for key in ('Account Code', 'accountCode', 'Account Number', 'account_number', 'Client Account Number'):
            if key in payload:
                value = payload[key]
                if isinstance(value, dict):
                    value = value.get('value')
                if not isinstance(value, str) or not value:
                    raise ValueError('Invalid top-level primary account identity: ' + key)
                identities.add(value)
    if not identities:
        raise ValueError('Primary Register account identity missing. Expected ' + REGISTER_IDENTITY_POINTER)
    if any(re.fullmatch(r'[A-Za-z]{2}[0-9]+', value) is None for value in identities):
        raise ValueError('Primary Register identity is not an exact base account code; no suffix was removed')
    if len(identities) != 1:
        raise ValueError('Conflicting primary Register account identities: ' + repr(sorted(identities)))
    return identities

EVIDENCE_EXTENSIONS = {
    '.pdf', '.json', '.md', '.txt', '.csv', '.tsv', '.rtf', '.xml', '.html', '.htm', '.yaml', '.yml',
    '.doc', '.docx', '.docm', '.dotx', '.dotm', '.xls', '.xlsx', '.xlsm', '.xlsb', '.xltx', '.xltm',
    '.ppt', '.pptx', '.pptm', '.potx', '.potm', '.ppsx', '.ppsm',
    '.png', '.jpg', '.jpeg', '.jpe', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.eml', '.msg',
}

def validate_evidence_file(value, config):
    """Validate without modifying evidence. Upload acceptance is checked separately."""
    path = Path(display_path(value))
    suffix = path.suffix.lower()
    allowed = {str(x).lower() for x in config.get('supported_extensions', [])} | EVIDENCE_EXTENSIONS
    if suffix not in allowed:
        raise ValueError('Unsupported extension ' + (suffix or '[none]'))
    size = os.stat(long_io_path(path)).st_size
    if size == 0:
        raise ValueError('Empty file')
    if size > config.get('max_file_bytes', 50 * 1024 * 1024):
        raise ValueError('File exceeds configured size ceiling')
    # Pass file streams to readers: third-party libraries need not understand
    # extended UNC filenames themselves.
    if suffix == '.pdf':
        configure_pdf_diagnostics()
        from pypdf import PdfReader
        with open(long_io_path(path), 'rb') as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                raise ValueError('Encrypted PDF')
            if not len(reader.pages):
                raise ValueError('PDF has no pages')
            for page in reader.pages:
                page.get_contents()
    elif suffix in {'.doc', '.xls', '.ppt', '.docx', '.docm', '.dotx', '.dotm', '.xlsx', '.xlsm', '.xlsb', '.xltx', '.xltm', '.pptx', '.pptm', '.potx', '.potm', '.ppsx', '.ppsm'}:
        import olefile
        with open(long_io_path(path), 'rb') as stream:
            is_ole = olefile.isOleFile(stream)
        if is_ole:
            with open(long_io_path(path), 'rb') as stream:
                with olefile.OleFileIO(stream) as compound:
                    if compound.exists('EncryptedPackage') or compound.exists('EncryptionInfo'):
                        raise ValueError('Encrypted Office file')
            import msoffcrypto
            with open(long_io_path(path), 'rb') as stream:
                if msoffcrypto.OfficeFile(stream).is_encrypted():
                    raise ValueError('Encrypted Office file')
            if suffix not in {'.doc', '.xls', '.ppt'}:
                raise ValueError('Unexpected compound container for modern Office file')
        else:
            if suffix in {'.doc', '.xls', '.ppt'}:
                raise ValueError('Legacy Office file is not a validated compound document')
            with open(long_io_path(path), 'rb') as stream:
                with zipfile.ZipFile(stream) as archive:
                    if '[Content_Types].xml' not in archive.namelist():
                        raise ValueError('Invalid Office container: missing content types')
                    if any(info.flag_bits & 1 for info in archive.infolist()):
                        raise ValueError('Encrypted Office ZIP member')
                    if archive.testzip():
                        raise ValueError('Corrupt Office container')
                    prefix = 'word/' if suffix.startswith(('.doc', '.dot')) else 'xl/' if suffix.startswith(('.xls', '.xlt')) else 'ppt/'
                    if not any(name.startswith(prefix) for name in archive.namelist()):
                        raise ValueError('Office container does not match its extension')
    elif suffix in {'.png', '.jpg', '.jpeg', '.jpe', '.gif', '.bmp', '.tif', '.tiff', '.webp'}:
        from PIL import Image
        with open(long_io_path(path), 'rb') as stream:
            with Image.open(stream) as image:
                image.verify()
    elif suffix == '.json':
        evidence_json(path)
    elif suffix == '.msg':
        import olefile
        with open(long_io_path(path), 'rb') as stream:
            with olefile.OleFileIO(stream) as message:
                classes = []
                for name, encoding in (('__substg1.0_001A001F', 'utf-16-le'), ('__substg1.0_001A001E', 'cp1252')):
                    if message.exists(name):
                        classes.append(message.openstream(name).read().decode(encoding, errors='strict'))
                if not classes:
                    raise ValueError('MSG message class cannot be validated')
                if any('smime' in text.lower() for text in classes):
                    raise ValueError('S/MIME message requires manual evidence preparation')
    elif suffix == '.eml':
        from email.parser import BytesParser
        from email import policy
        with open(long_io_path(path), 'rb') as stream:
            message = BytesParser(policy=policy.default).parse(stream)
        if message.defects or any(part.defects for part in message.walk()):
            raise ValueError('Malformed email envelope')
        if any('pkcs7' in part.get_content_type() or part.get_content_type() == 'multipart/encrypted' for part in message.walk()):
            raise ValueError('Encrypted/signed email requires manual preparation')
    elif suffix in {'.txt', '.md', '.csv', '.tsv', '.xml', '.html', '.htm', '.yaml', '.yml', '.rtf'}:
        # Byte readability was checked by hashing. Text encoding is not proof
        # that a file is unreadable to the service; do not reject Windows text.
        with open(long_io_path(path), 'rb') as stream:
            stream.read(1)
    else:
        raise ValueError('No validator is implemented for configured extension ' + suffix)

def inspect_prepared_case(folder, config):
    import re
    import stat
    folder = Path(display_path(folder))
    record = {'folder_name': folder.name, 'source_location': str(folder), 'manifest': [],
              'validation': [], 'state': 'discovered', 'history': [], 'review_finding': None,
              'skipped_paths': [], 'file_count': 0, 'total_size': 0}
    match = re.fullmatch(config['folder_pattern'], folder.name)
    if not match:
        record.update(instruction_id=None, account_number=None, state='blocked')
        record['validation'].append('Malformed folder name; contents were not scanned')
        return record
    record.update(instruction_id=match.group('instruction_id'), account_number=match.group('account_number'))
    if any(part.casefold() == EXCLUDED_EVIDENCE_DIRECTORY for part in folder.parts):
        raise ValueError('Excluded browser profile cannot be inspected as case evidence')
    def error(exc):
        record['validation'].append('Inaccessible directory: ' + str(exc))
    for parent, directories, files in os.walk(long_io_path(folder), onerror=error, followlinks=False):
        directories.sort(key=lambda name: (name.casefold(), name))
        for name in list(directories):
            candidate = Path(display_path(os.path.join(parent, name)))
            if name.casefold() == EXCLUDED_EVIDENCE_DIRECTORY:
                directories.remove(name)
                record['skipped_paths'].append({'path': str(candidate), 'reason': 'Excluded browser profile; contents not read'})
                continue
            try:
                info = os.lstat(long_io_path(candidate))
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    directories.remove(name)
                    record['validation'].append('Linked/reparse directory not followed: ' + str(candidate))
            except OSError as exc:
                directories.remove(name)
                error(exc)
        for name in sorted(files, key=lambda value: (value.casefold(), value)):
            path = Path(display_path(os.path.join(parent, name)))
            if name.casefold() == EXCLUDED_EVIDENCE_DIRECTORY:
                record['skipped_paths'].append({'path': str(path), 'reason': 'Reserved excluded name'})
                continue
            item = {'relative_path': path.relative_to(folder).as_posix(), 'name': name, 'path': str(path),
                    'size': None, 'sha256': None, 'error': None}
            try:
                before = os.lstat(long_io_path(path))
                if not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('Linked, reparse or non-regular file is not eligible')
                item.update(size=before.st_size, mtime_ns=before.st_mtime_ns)
                item['sha256'] = evidence_hash(path)
                validate_evidence_file(path, config)
                after = os.stat(long_io_path(path))
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('File changed during discovery')
            except Exception as exc:
                item['error'] = repr(exc)
                record['validation'].append(item['relative_path'] + ': ' + repr(exc))
            record['manifest'].append(item)
    record['file_count'] = len(record['manifest'])
    record['total_size'] = sum(item['size'] or 0 for item in record['manifest'])
    if record['file_count'] + 1 > 20:
        record['validation'].append(f'Attachment limit: {record["file_count"]} evidence + 1 instructions = {record["file_count"] + 1}; maximum 20')
    audits = [item for item in record['manifest'] if re.search(config['audit_pattern'], Path(item['name']).stem, re.I)]
    snapshots = [item for item in record['manifest'] if item['name'].lower().endswith('.json') and re.search(config['snapshot_pattern'], item['name'], re.I)]
    record['audit_trail'] = audits[0]['relative_path'] if len(audits) == 1 else None
    record['register_json'] = snapshots[0]['relative_path'] if len(snapshots) == 1 else None
    if len(audits) != 1:
        record['validation'].append(f'Expected exactly one Audit Trail/History; found {len(audits)}')
    if len(snapshots) != 1:
        record['validation'].append(f'Expected exactly one Register snapshot; found {len(snapshots)}')
    else:
        try:
            item = snapshots[0]
            identities = register_identity(evidence_json(item['path']), config)
            if identities != {record['account_number']}:
                record['validation'].append('Snapshot primary Account Code does not match folder account: ' + repr(sorted(identities)))
            record['account_identity'] = {'values': sorted(identities), 'primary_field': REGISTER_IDENTITY_POINTER,
                                          'configured_pointer': config.get('account_json_pointer', '')}
            if not re.search(r'(?<![A-Za-z0-9])' + re.escape(record['account_number']) + r'(?![A-Za-z0-9])', item['name']):
                record['validation'].append('Snapshot filename account mismatch')
        except Exception as exc:
            record['validation'].append('Snapshot identity check failed: ' + repr(exc))
    record['evidence_fingerprint'] = digest([{key: item.get(key) for key in ('relative_path', 'size', 'sha256', 'error')} for item in record['manifest']])
    record['state'] = 'blocked' if record['validation'] else 'ready'
    return record

def discover_prepared_cases(root, config, excluded=()):
    import stat
    root = Path(display_path(root))
    if any(part.casefold() == EXCLUDED_EVIDENCE_DIRECTORY for part in root.parts):
        raise ValueError('The excluded browser profile cannot be selected as the evidence root')
    records, issues = [], []
    # Check the name BEFORE stat, hashing, recursion or opening any child.
    with os.scandir(long_io_path(root)) as iterator:
        entries = sorted(iterator, key=lambda entry: (entry.name.casefold(), entry.name))
    skipped = []
    for entry in entries:
        path = Path(display_path(entry.path))
        if entry.name.casefold() == EXCLUDED_EVIDENCE_DIRECTORY:
            skipped.append(str(path))
            continue
        if any(is_inside(path, value) for value in excluded):
            continue
        try:
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Linked/reparse root entry not scanned')
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError('Unexpected root-level file')
            records.append(inspect_prepared_case(path, config))
        except Exception as exc:
            issues.append({'path': str(path), 'error': repr(exc)})
    if skipped:
        print('Excluded browser profile folders (not scanned): ' + ', '.join(skipped), flush=True)
    groups = {}
    for record in records:
        if record['instruction_id']:
            groups.setdefault(record['instruction_id'], []).append(record)
    for identity, group in groups.items():
        if len(group) > 1:
            for record in group:
                record['validation'].append('Conflicting duplicate instruction ID: ' + identity)
                record['state'] = 'blocked'
    return records, issues

def evidence_unchanged(record, config):
    current = inspect_prepared_case(record['source_location'], config)
    return current.get('evidence_fingerprint') == record.get('evidence_fingerprint') and not current['validation']

def short_stage_root():
    # Keep the mapped spelling short for Edge while requiring the real S: mapping.
    return RUNTIME_ROOT / 'stage' / identity_key()

# ---------- Durable state and review-resource discovery ----------
CONTRACT_VERSION = 'daily-case-review/v1'
UNCERTAIN = {'submitted', 'awaiting response', 'manual reconciliation required'}
REQUIREMENTS = ['playwright>=1.48,<2', 'pypdf>=5,<7', 'msoffcrypto-tool>=5.4,<6', 'Pillow>=10,<13', 'olefile>=0.47,<1']
DEFAULTS = {
    'url': 'https://m365.cloud.microsoft/chat', 'tabs': 6, 'port': 9237,
    'model': '', 'technical_attempts': 2, 'reconnect_attempts': 4,
    'operation_timeout': 30, 'login_timeout': 300, 'upload_timeout': 600,
    'response_timeout': 1800, 'poll_seconds': 2, 'stable_seconds': 12,
    'max_file_bytes': 50 * 1024 * 1024,
    'folder_pattern': r'(?P<instruction_id>[A-Za-z0-9][A-Za-z0-9_-]*?)[ _-]+(?P<account_number>[A-Za-z]{2}[0-9]+)',
    'audit_pattern': r'(?<![A-Za-z])audit[ _-]*(?:trail|history)(?![A-Za-z])',
    'snapshot_pattern': r'Complete[ _-]*Register[ _-]*Account[ _-]*Profile',
    'account_json_pointer': '', 'supported_extensions': sorted(EVIDENCE_EXTENSIONS),
    'contract': {'version': CONTRACT_VERSION, 'begin': 'DAILY_REVIEW_RESULT_BEGIN', 'end': 'DAILY_REVIEW_RESULT_END'},
    'selectors': {
        'user': '[data-testid="chatQuestion"],.fai-UserMessage,[aria-labelledby^="user-message-"]',
        'assistant': '[data-testid="copilot-message-reply-div"] [data-testid="markdown-reply"][data-message-type="Chat"],[data-testid="copilot-message-div"] [data-testid="markdown-reply"][data-message-type="Chat"],[data-testid="lastChatMessage"] [data-testid="markdown-reply"][data-message-type="Chat"],.fai-CopilotMessage__content',
        'streaming': '[data-testid*="streaming" i],[data-test-id*="streaming" i]',
    },
}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def read_json(path, default=None):
    try:
        return evidence_json(path)
    except FileNotFoundError:
        return default


def atomic_json(path, value):
    path = Path(display_path(path))
    os.makedirs(long_io_path(path.parent), exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with open(long_io_path(temporary), 'x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(long_io_path(temporary), long_io_path(path))
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(.1 * (attempt + 1))
    finally:
        try:
            os.unlink(long_io_path(temporary))
        except FileNotFoundError:
            pass


def write_text(path, text):
    path = Path(display_path(path))
    os.makedirs(long_io_path(path.parent), exist_ok=True)
    with open(long_io_path(path), 'w', encoding='utf-8') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def is_inside(child_path, parent):
    try:
        Path(display_path(child_path)).resolve().relative_to(Path(display_path(parent)).resolve())
        return True
    except ValueError:
        return False


@contextlib.contextmanager
def controller_lock(path):
    path = Path(path)
    os.makedirs(long_io_path(path.parent), exist_ok=True)
    stream = open(long_io_path(path), 'a+b')
    stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('Another controller/setup is active for this user and machine. No browser changes made.') from None
    try:
        yield
    finally:
        stream.close()


class SharedStore:
    """Legacy-compatible permanent claims; no stale expiry or automatic takeover."""
    def __init__(self, root, owner):
        self.root, self.owner = Path(root), owner
        self.claims, self.records = self.root / 'claims', self.root / 'records'
        for path in (self.root, self.claims, self.records):
            os.makedirs(long_io_path(path), exist_ok=True)
        probe = self.root / ('probe-' + uuid.uuid4().hex)
        try:
            with open(long_io_path(probe), 'x', encoding='utf-8') as stream:
                stream.write(owner); stream.flush(); os.fsync(stream.fileno())
            try:
                with open(long_io_path(probe), 'x'):
                    pass
            except FileExistsError:
                pass
            else:
                raise RuntimeError('Shared coordination does not provide exclusive file creation')
            with open(long_io_path(probe), encoding='utf-8') as stream:
                if stream.read() != owner:
                    raise RuntimeError('Shared coordination read-back failed')
        finally:
            try:
                os.unlink(long_io_path(probe))
            except FileNotFoundError:
                pass

    def key(self, cid):
        return hashlib.sha256(cid.encode()).hexdigest()

    def get(self, cid):
        direct = read_json(self.records / (self.key(cid) + '.json'))
        matches = []
        for path in self.records.glob('*.json'):
            item = read_json(path)
            if isinstance(item, dict) and item.get('instruction_id') == cid:
                matches.append(item)
        if len(matches) > 1:
            raise RuntimeError('Multiple durable records for instruction ' + cid + '; reconcile manually')
        return direct or (matches[0] if matches else None)

    def claim(self, cid):
        path = self.claims / (self.key(cid) + '.json')
        value = {'instruction_id': cid, 'owner': self.owner, 'machine': socket.gethostname(),
                 'created': now(), 'claim_token': uuid.uuid4().hex}
        for existing in self.claims.glob('*.json'):
            item = read_json(existing)
            if isinstance(item, dict) and item.get('instruction_id') == cid and existing != path:
                return None  # Unknown legacy claim layout: never create a parallel claim.
        try:
            with open(long_io_path(path), 'x', encoding='utf-8') as stream:
                json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        except FileExistsError:
            value = read_json(path)
            if not value or value.get('owner') != self.owner or value.get('instruction_id') != cid:
                return None
        return value

    def save(self, record):
        cid = record['instruction_id']
        claim = read_json(self.claims / (self.key(cid) + '.json'))
        if not claim or claim.get('owner') != self.owner:
            raise RuntimeError('Shared claim ownership lost; submission prohibited')
        atomic_json(self.records / (self.key(cid) + '.json'), record)


def choose_markdown(kind, explicit=None, other=None):
    if explicit:
        path = require_s(explicit, kind + ' Markdown')
        if path.suffix.lower() != '.md' or not path.is_file():
            raise ValueError('Markdown file not found: ' + str(path))
        return path
    preferred = (('daily_review_base_message.md', 'base_message.md') if kind == 'base message'
                 else ('daily_review_instructions.md', 'instructions.md'))
    named = [PACKAGE / name for name in preferred if (PACKAGE / name).is_file()]
    if len(named) == 1 and named[0] != other:
        return require_s(named[0], kind + ' Markdown')
    candidates = sorted((p for p in PACKAGE.glob('*.md') if p != other), key=lambda p: (p.name.casefold(), p.name))
    if kind == 'base message':
        matching = [p for p in candidates if 'base' in p.stem.casefold() and 'message' in p.stem.casefold()]
    else:
        matching = [p for p in candidates if 'instruction' in p.stem.casefold() and 'base' not in p.stem.casefold()]
    if len(matching) == 1:
        return require_s(matching[0], kind + ' Markdown')
    if kind != 'base message' and len(candidates) == 1:
        return require_s(candidates[0], kind + ' Markdown')
    if not sys.stdin.isatty():
        raise ValueError('Cannot uniquely identify ' + kind + '; supply --' + ('base-message' if kind == 'base message' else 'instructions'))
    print('\nSelect the ' + kind + ' Markdown. Ambiguous files are never chosen silently.')
    for index, path in enumerate(candidates, 1):
        print(f'  {index}. {path.name}')
    value = input('Enter its number or paste the full .md path: ').strip()
    if value.isdigit() and 1 <= int(value) <= len(candidates):
        return require_s(candidates[int(value) - 1], kind + ' Markdown')
    return choose_markdown(kind, value, other)


def load_resources(instructions, base, mode='auto', model=''):
    if Path(instructions).resolve() == Path(base).resolve():
        raise ValueError('Instructions and base message must be two separate Markdown files')
    texts = []
    for path in (instructions, base):
        with open(long_io_path(path), encoding='utf-8-sig') as stream:
            text = stream.read()
        if not text.strip():
            raise ValueError('Empty Markdown resource: ' + str(path))
        texts.append(text)
    declarations = re.findall(r'Completion contract:\s*([^\s]+)', texts[1])
    if any(value != CONTRACT_VERSION for value in declarations):
        raise ValueError('Unsupported completion contract in base message: ' + repr(declarations))
    if mode == 'auto':
        mode = 'contract' if CONTRACT_VERSION in declarations else 'ui'
    contract = copy.deepcopy(DEFAULTS['contract'])
    if mode == 'contract':
        if CONTRACT_VERSION not in declarations or any(contract[key] not in texts[1] for key in ('begin', 'end')):
            raise ValueError('Base message must declare daily-case-review/v1 and its begin/end markers for contract completion')
        required = ('instruction_id', 'account_number', 'run_id', 'assignment_id', 'evidence_fingerprint',
                    'resources_fingerprint', 'received_files', 'review_finding', 'limitations', 'outputs', 'exposure')
        if any(key not in texts[1] for key in required):
            raise ValueError('Base message completion contract is missing required keys; no cases submitted')
    hashes = {'instructions': evidence_hash(instructions), 'base_message': evidence_hash(base)}
    fp = digest({'hashes': hashes, 'mode': mode, 'contract': contract if mode == 'contract' else None, 'model': model})
    return {'instructions': str(instructions), 'base_message': str(base), 'base_text': texts[1],
            'hashes': hashes, 'fingerprint': fp, 'completion_mode': mode, 'contract': contract}


def parse_completion(text, assignment, contract):
    if text.count(contract['begin']) != 1 or text.count(contract['end']) != 1:
        raise ValueError('Missing/duplicate completion markers')
    body, after = text.split(contract['begin'], 1)[1].split(contract['end'], 1)
    if after.strip():
        raise ValueError('Text follows terminal marker')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key ' + key)
            result[key] = value
        return result
    result = json.loads(body.strip(), object_pairs_hook=pairs)
    if result.get('contract_version') != CONTRACT_VERSION or result.get('complete') is not True:
        raise ValueError('Incomplete/incompatible completion contract')
    for key in ('instruction_id', 'account_number', 'run_id', 'assignment_id', 'evidence_fingerprint', 'resources_fingerprint'):
        if result.get(key) != assignment.get(key):
            raise ValueError('Stale/mismatched ' + key)
    if Counter(result.get('received_files', [])) != Counter(assignment['attachment_names']):
        raise ValueError('File receipt differs from full manifest')
    if not isinstance(result.get('review_finding'), dict) or not isinstance(result.get('limitations'), list) or not isinstance(result.get('outputs'), list):
        raise ValueError('Invalid review finding, limitations or outputs')
    if result.get('exposure') not in {'complete', 'limited', 'not established'}:
        raise ValueError('Invalid exposure')
    return result


def transition(record, state, **values):
    record.setdefault('history', []).append({'at': now(), 'from': record.get('state'), 'to': state, **values})
    record.update(values); record['state'] = state; record['updated'] = now()


def unpack_wheels(wheels, target):
    """Unpack downloaded wheels into target the way pip --target does, keeping every path on S:."""
    wheels, target = s_spelling(require_s(wheels, 'Wheel folder')), s_spelling(require_s(target, 'Dependency folder'))
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for wheel in sorted(Path(os.fsdecode(wheels)).glob('*.whl')):
        with zipfile.ZipFile(long_io_path(wheel)) as archive:
            for item in archive.infolist():
                name = item.filename
                # Installer scripts and data folders are not needed by this tool; skip them.
                if '.data/' in name:
                    continue
                destination = Path(os.path.normpath(str(target / name)))
                if not str(destination).casefold().startswith(str(target).casefold() + os.sep):
                    raise RuntimeError('Unsafe path inside downloaded package ' + wheel.name + '; not unpacked.')
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, open(long_io_path(destination), 'wb') as out:
                    shutil.copyfileobj(source, out)
                count += 1
    print(f'Unpacked {count} package files onto S:.')
    return count


def ensure_dependencies(paths, setup=False):
    modules = ('playwright.async_api', 'pypdf', 'msoffcrypto', 'PIL.Image', 'olefile', 'greenlet', 'pyee', 'cryptography')
    missing = []
    for name in modules:
        try:
            module = importlib.import_module(name)
            if getattr(module, '__file__', None):
                require_s(module.__file__, 'Dependency ' + name)
        except ImportError:
            missing.append(name)
    if missing:
        print('Installing missing Python dependencies on S: only: ' + ', '.join(missing))
        needed = len(str(paths['deps'])) + 1 + PACKAGE_LONGEST_RELATIVE
        if needed > WINDOWS_PATH_BUDGET:
            raise RuntimeError(f'The working folder is too long for Windows ({needed} characters needed, limit 260). '
                               'Choose a shorter working folder on S: and run again. The tool will ask for it again '
                               'after you delete local_paths.cmd.')
        bootstrap_pip()
        # pip's own install step converts S: to the long network path and hits the 260-character
        # limit. So pip only DOWNLOADS the wheels (including dependencies of dependencies), and this
        # tool unpacks them into the short S: folder itself. A wheel is a zip file.
        wheels = paths['deps'].parent / 'wheels'
        child('--pip-internal', ['--isolated', '--disable-pip-version-check', 'download', '--only-binary=:all:',
              '--dest', wheels, '--cache-dir', paths['pip_cache'], *REQUIREMENTS], 'dependency-download.log')
        unpack_wheels(wheels, paths['deps'])
        # A clean child verifies DLL/native-extension imports after installation.
        child('--verify-dependencies', [], 'dependency-check.log')
        importlib.invalidate_caches()
    if not NODE.is_file():
        raise FileNotFoundError('Required S: Node executable missing: ' + str(NODE))
    if setup:
        print('Python dependencies ready; installed Edge will be used. No browser download or elevation.')

# ---------- Browser transactions ----------
class UncertainOperation(RuntimeError):
    pass


def exact_upload_ready(state, names):
    return (Counter(state.get('names', [])) == Counter(names) and state.get('count') == len(names)
            and not state.get('active') and not state.get('error') and not state.get('warning')
            and state.get('sendEnabled'))



def mapped_browser_path(value):
    """Use the existing S: spelling, verifying it resolves to the same storage."""
    resolved = require_s(value, 'Browser storage')
    if os.name != 'nt':
        return str(resolved)
    mapped = Path('S:/') / resolved.relative_to(_S_ROOT)
    if require_s(mapped, 'Mapped browser storage') != resolved:
        raise ValueError('Mapped browser path does not match its verified destination')
    return str(mapped)


def edge_policy_snapshot():
    """Read only relevant Edge policies. Never modify registry or policy."""
    result = []
    if os.name != 'nt':
        return result
    import winreg
    for label, hive in (('machine', winreg.HKEY_LOCAL_MACHINE), ('user', winreg.HKEY_CURRENT_USER)):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Policies\Microsoft\Edge', 0, winreg.KEY_READ | view) as key:
                    for name in ('RemoteDebuggingAllowed', 'UserDataDir', 'DevToolsAvailability'):
                        try:
                            value, kind = winreg.QueryValueEx(key, name)
                            result.append({'scope': label, 'view': view, 'name': name, 'value': value, 'type': kind})
                        except FileNotFoundError:
                            pass
            except FileNotFoundError:
                pass
            except OSError as exc:
                result.append({'scope': label, 'view': view, 'read_error': str(exc)})
    return result


def probe_browser_storage(directory):
    """Check create/write/read/delete access using an owned temporary probe."""
    directory = require_s(directory, 'Browser storage probe')
    directory.mkdir(parents=True, exist_ok=True)
    probe = directory / ('.startup-probe-' + uuid.uuid4().hex)
    try:
        with open(probe, 'xb') as stream:
            stream.write(b'case-review-startup-probe')
        if probe.read_bytes() != b'case-review-startup-probe':
            raise OSError('Browser storage probe readback failed')
    finally:
        if probe.exists():
            probe.unlink()



class ProfileSingletonError(RuntimeError):
    """Edge explicitly refused its profile singleton; never delete its lock."""


def profile_singleton_failure(text):
    return ('Failed to create a ProcessSingleton for your profile directory' in text
            and 'Lock file can not be created!' in text)


def assert_profile_recovery_safe(browser):
    """Fail closed before changing profile identity. Shared records are read only."""
    if browser.marker.exists():
        raise RuntimeError('A previous verified browser session exists. Profile recovery is blocked to preserve its conversations. Close only the dedicated review window normally, or reconcile the original session; no profile or lock was deleted.')
    store = getattr(browser, 'startup_store', None)
    if store is None or not store.records.is_dir():
        raise RuntimeError('Shared case records are unavailable; cannot prove profile recovery is safe.')
    for path in store.records.glob('*.json'):
        record = read_json(path)
        if not isinstance(record, dict) or 'state' not in record:
            raise RuntimeError('Unreadable or unknown shared case record; profile recovery blocked: ' + str(path))
        state = record['state']
        if state not in {'discovered', 'ready', 'blocked', 'retryable failure', 'completed'}:
            raise RuntimeError('Unresolved case prevents profile recovery: ' + str(record.get('instruction_id', path.name)) + ' (' + str(state) + ')')
        if state != 'completed' and (record.get('assignment') or record.get('send_intent_at') or record.get('message')):
            raise RuntimeError('Existing assignment requires reconciliation before any new profile: ' + str(record.get('instruction_id', path.name)))



async def _daily_review_stop_playwright_v1(owner):
    import inspect
    manager = getattr(owner, 'manager', None)
    if manager is None:
        return
    stop = getattr(manager, 'stop', None)
    exit_context = getattr(manager, '__aexit__', None)
    if callable(stop):
        result = stop()
    elif callable(exit_context):
        result = exit_context(None, None, None)
    else:
        raise RuntimeError('Unknown Playwright owner: ' + type(manager).__name__)
    if inspect.isawaitable(result):
        await result
    owner.manager = None

# ---------- Diagnostics (--diagnose): full-run event log plus INTERNAL and EXTERNAL reports ----------
# Read-only. Uses built-in Windows APIs (ctypes/winreg/socket) only: the audit hook forbids
# child processes such as netstat, tasklist or PowerShell, and no setting is ever changed.
_DIAG_SAFE_FILES = {'msedge.exe', 'python.exe', 'node.exe', 'devtoolsactiveport', 'preferences', 'local state',
                    'browser.log', 'singletonlock', 'singletoncookie', 'singletonsocket', 'lockfile',
                    'summary.md', 'failures.log', 'settings.json', 'browser-session.json'}
_DIAG_SAFE_HOSTS = ('microsoft.com', 'cloud.microsoft', 'microsoft', 'office.com', 'live.com',
                    'microsoftonline.com', 'localhost', '127.0.0.1')
_DIAG_STANDARD_ENV = {name.upper() for name in (
    'ALLUSERSPROFILE', 'APPDATA', 'COMMONPROGRAMFILES', 'COMMONPROGRAMFILES(X86)', 'COMMONPROGRAMW6432', 'COMPUTERNAME',
    'COMSPEC', 'DRIVERDATA', 'HOMEDRIVE', 'HOMEPATH', 'LOCALAPPDATA', 'LOGONSERVER', 'NUMBER_OF_PROCESSORS', 'ONEDRIVE',
    'ONEDRIVECOMMERCIAL', 'ONEDRIVECONSUMER', 'OS', 'PATH', 'PATHEXT', 'PROCESSOR_ARCHITECTURE', 'PROCESSOR_IDENTIFIER',
    'PROCESSOR_LEVEL', 'PROCESSOR_REVISION', 'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'PROMPT',
    'PSMODULEPATH', 'PUBLIC', 'SESSIONNAME', 'SYSTEMDRIVE', 'SYSTEMROOT', 'TEMP', 'TMP', 'USERDOMAIN', 'USERDOMAIN_ROAMINGPROFILE',
    'USERNAME', 'USERPROFILE', 'WINDIR', 'HOME', 'TMPDIR', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'ALL_PROXY', 'CLIENTNAME',
    'PYTHONHOME', 'PYTHONPATH', 'PYTHONUSERBASE', 'PYTHONDONTWRITEBYTECODE', 'PYTHONNOUSERSITE', 'PYTHONPYCACHEPREFIX',
    'NODE_OPTIONS', 'NODE_PATH', 'NODE_USE_SYSTEM_CA', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_EXTRA_CA_CERTS', 'PIP_CACHE_DIR',
    'PIP_CONFIG_FILE', 'PIP_DISABLE_PIP_VERSION_CHECK', 'PIP_NO_INPUT', 'PLAYWRIGHT_BROWSERS_PATH', 'PLAYWRIGHT_NODEJS_PATH',
    'XDG_CACHE_HOME', 'XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'CHROME_LOG_FILE', 'CRASHPAD_DATABASE_PATH', 'DCR_PYTHON',
    'DCR_NODE', 'DCR_RUNTIME_ROOT', 'DCR_RUNNER', 'DCR_EXIT', 'NPM_CONFIG_CACHE', 'NPM_CONFIG_PREFIX', 'NODE_REPL_HISTORY')}
_DIAG_URL = re.compile(r'https?://[^\s"\'<>)\]]+', re.I)
_DIAG_PATH = re.compile(r'(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|\\{2,}[^\s\\/:*?"|<>]+[\\/])(?:[^\\/:*?"|\r\n]*[\\/])*[^\\/:*?"|\r\n]*')
_DIAG_MIDDLE_END = re.compile(r'[,;]\s|\s*->')
_DIAG_TAIL_END = re.compile(r'\s+(?:is|was|are|were|not|must|does|do|could|cannot|can|failed|already|has|have|and|or|to|from|in|on|at|with|for|will|should|because|which|that)\b|[.,;]\s|\s*[(\[]|\s*->', re.I)
_DIAG_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_DIAG_RUN = re.compile(r'\brun-\d{8}-\d{6}-[0-9a-f]{8}\b')
_DIAG_GUID = re.compile(r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b')
_DIAG_HEX = re.compile(r'(?<![0-9A-Za-z])[0-9A-Fa-f]{24,}(?![0-9A-Za-z])')
_DIAG_IP = re.compile(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])')
_DIAG_RESIDUAL = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]\S*|(?<![A-Za-z0-9])\\\\[A-Za-z0-9$_.-]+\\\S*')


class Private:
    """A value shown in the INTERNAL report but never in the EXTERNAL one."""
    def __init__(self, value):
        self.value = value


class BrowserLines(list):
    """Free text written by Edge; unverified lines are dropped from the EXTERNAL report."""


def diag_plain(value):
    if isinstance(value, Private):
        return value.value
    if isinstance(value, dict):
        return {str(k): diag_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [diag_plain(v) for v in value]
    return value


class DiagSanitizer:
    """Replaces identifying values with numbered labels and counts everything it removes."""
    def __init__(self):
        self.known, self.labels, self.counts = [], {}, Counter()
        self.unverified = self.residual = 0

    def learn(self, kind, value):
        text = str(value or '').strip().strip('\\/')
        if len(text) >= 3 and not any(k == kind and v.casefold() == text.casefold() for k, v in self.known):
            self.known.append((kind, text))
            self.known.sort(key=lambda item: -len(item[1]))

    def label(self, kind, raw, detail=''):
        key = (kind, raw.casefold())
        if key not in self.labels:
            self.labels[key] = (kind + '-' + str(1 + sum(1 for k in self.labels if k[0] == kind)), raw)
        self.counts[kind] += 1
        return '<' + self.labels[key][0] + (' ' + detail if detail else '') + '>'

    def _url(self, match):
        full = match.group(0)
        url = full.rstrip('.,;')
        tail = full[len(url):]
        try:
            parts = urlsplit(url)
            host, port = (parts.hostname or '').lower(), parts.port
        except ValueError:
            return self.label('URL', url, 'unparsed') + tail
        if any(host == s or host.endswith('.' + s) for s in _DIAG_SAFE_HOSTS):
            segments = [s for s in parts.path.split('/') if s]
            keep = '/' + segments[0] if segments and re.fullmatch(r'[A-Za-z]{2,12}', segments[0]) else ''
            if parts.query or parts.fragment or len(segments) > (1 if keep else 0):
                self.counts['URL-details'] += 1
                keep += '/...'
            return parts.scheme + '://' + host + (':' + str(port) if port else '') + keep + tail
        return self.label('URL', url, 'scheme=' + parts.scheme) + tail

    def _cut(self, text, start, pattern, limit):
        """Start of the first sentence-like break in text[start:limit] that is not inside a known name."""
        pos = start
        while True:
            found = pattern.search(text, pos, limit)
            if not found:
                return None
            if any(m.start() < found.start() < m.end() for _, v in self.known for m in re.finditer(re.escape(v), text, re.I)):
                pos = found.end()
                continue
            return found.start()

    def _path(self, match):
        text = match.group(0)
        last = max(text.rfind('\\'), text.rfind('/'))
        # Folder names may contain words like "and"; only punctuation ends a path before its last segment.
        end = self._cut(text, 3, _DIAG_MIDDLE_END, last)
        piece = text if end is None else text[:end]
        # Words after the final separator of the piece belong to the sentence, not the file name.
        tail = self._cut(piece, max(piece.rfind('\\'), piece.rfind('/')) + 1, _DIAG_TAIL_END, len(piece))
        keep = piece if tail is None else piece[:tail]
        stripped = keep.rstrip(' .,;:')
        parts = [p for p in re.split(r'[\\/]+', stripped) if p]
        name = parts[-1] if parts else ''
        drive = 'UNC' if stripped.startswith('\\\\') else stripped[:2].upper()
        detail = drive + ' depth=' + str(len(parts))
        extension = name.rsplit('.', 1)[1] if '.' in name else ''
        if name.casefold() in _DIAG_SAFE_FILES:
            detail += ' file=' + name
        elif extension and len(extension) <= 6 and extension.isalnum():
            detail += ' ext=.' + extension
        token = self.label('PATH', stripped, detail)
        return token + _DIAG_PATH.sub(self._path, text[len(stripped):])

    def _ip(self, match):
        value = match.group(0)
        if value in ('127.0.0.1', '0.0.0.0') or any(int(p) > 255 for p in value.split('.')):
            return value
        return self.label('IP', value)

    def clean(self, text):
        text = str(text).replace('\\\\?\\UNC\\', '\\\\').replace('\\\\?\\', '')
        text = _DIAG_URL.sub(self._url, text)
        text = _DIAG_PATH.sub(self._path, text)
        for kind, value in self.known:
            if value.casefold() in text.casefold():
                text = re.sub(re.escape(value), lambda m, k=kind: self.label(k, m.group(0)), text, flags=re.I)
        text = _DIAG_EMAIL.sub(lambda m: self.label('EMAIL', m.group(0)), text)
        text = _DIAG_RUN.sub(lambda m: self.label('RUN', m.group(0)), text)
        text = _DIAG_GUID.sub(lambda m: self.label('GUID', m.group(0)), text)
        text = _DIAG_HEX.sub(lambda m: self.label('HASH', m.group(0), 'len=' + str(len(m.group(0)))), text)
        text = _DIAG_IP.sub(self._ip, text)

        def residual(match):
            self.residual += 1
            return '<REMOVED residual-path>'
        return _DIAG_RESIDUAL.sub(residual, text)

    def browser_line(self, line):
        cleaned = self.clean(line)
        body = re.sub(r'<[^<>]*>', '', cleaned)
        if re.search(r'[\\/][A-Za-z0-9_.-]+[\\/]|@|[A-Za-z0-9_.-]{40,}', body):
            self.unverified += 1
            return '<line removed: unverified free text>'
        return cleaned

    def obj(self, value):
        if isinstance(value, Private):
            self.counts['PRIVATE-values'] += 1
            return '<value removed: private, length ' + str(len(str(value.value))) + '>'
        if isinstance(value, BrowserLines):
            return [self.browser_line(item) for item in value]
        if isinstance(value, dict):
            return {self.clean(k): self.obj(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self.obj(v) for v in value]
        if isinstance(value, str):
            return self.clean(value)
        return value


def diag_try(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        return {'unavailable': type(exc).__name__ + ': ' + str(exc)}


def diag_process_rows():
    if os.name != 'nt':
        raise OSError('process list is only available on Windows')
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateToolhelp32Snapshot(0x2, 0)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise OSError('process snapshot failed')
    rows = []
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        ok = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while ok:
            rows.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            ok = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return rows


def diag_processes():
    rows = diag_process_rows()
    names = {pid: exe for pid, _, exe in rows}
    edge = []
    for pid, parent, exe in rows:
        if exe.casefold() == 'msedge.exe':
            edge.append({'pid': pid, 'parent_pid': parent, 'parent': names.get(parent, 'exited/unknown'),
                         'role': 'child' if names.get(parent, '').casefold() == 'msedge.exe' else 'main',
                         'started_by_this_tool': parent == os.getpid()})
    return {'total': len(rows), 'msedge': edge}


def diag_process_summary():
    full = diag_processes()
    return {'total': full['total'], 'msedge_main_processes': [p for p in full['msedge'] if p['role'] == 'main'],
            'msedge_child_process_count': sum(1 for p in full['msedge'] if p['role'] == 'child')}


def diag_edge_pids():
    try:
        return {item['pid'] for item in diag_processes()['msedge']}
    except Exception:
        return set()


def diag_listeners(port=None):
    if os.name != 'nt':
        raise OSError('listener table is only available on Windows')
    import struct
    from ctypes import wintypes
    iphlpapi = ctypes.WinDLL('iphlpapi')
    names = {pid: exe for pid, _, exe in diag_process_rows()}
    found, total = [], 0
    for family, af, size in (('ipv4', 2, 24), ('ipv6', 23, 56)):
        length = wintypes.DWORD(0)
        iphlpapi.GetExtendedTcpTable(None, ctypes.byref(length), False, af, 3, 0)
        buffer = ctypes.create_string_buffer(length.value)
        if iphlpapi.GetExtendedTcpTable(buffer, ctypes.byref(length), False, af, 3, 0) != 0:
            continue
        for index in range(struct.unpack_from('<I', buffer, 0)[0]):
            offset = 4 + index * size
            if af == 2:
                _, address, raw_port, _, _, pid = struct.unpack_from('<IIIIII', buffer, offset)
                address = socket.inet_ntoa(struct.pack('<I', address))
            else:
                raw_address, _, raw_port, _, _, _, _, pid = struct.unpack_from('<16sII16sIIII', buffer, offset)
                address = socket.inet_ntop(socket.AF_INET6, raw_address)
            number = ((raw_port & 0xFF) << 8) | ((raw_port >> 8) & 0xFF)
            total += 1
            found.append({'family': family, 'address': address, 'port': number, 'pid': pid, 'program': names.get(pid, 'unknown')})
    return {'all_listening': found, 'total_listening': total,
            'on_configured_port': [x for x in found if port and x['port'] == int(port)],
            'in_debug_range_9000_9300': [x for x in found if 9000 <= x['port'] <= 9300]}


def diag_probe_port(port):
    result = {}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for host in ('127.0.0.1', 'localhost', '[::1]'):
        entry = {}
        try:
            with socket.create_connection((host.strip('[]'), int(port)), timeout=2):
                entry['tcp_connect'] = 'connected'
        except OSError as exc:
            entry['tcp_connect'] = type(exc).__name__ + ' errno=' + str(getattr(exc, 'errno', None))
        started = time.perf_counter()
        try:
            with opener.open(f'http://{host}:{int(port)}/json/version', timeout=3) as response:
                body = json.loads(response.read(8192).decode('utf-8', 'replace'))
                entry.update(http_status=response.status, browser=body.get('Browser'), protocol=body.get('Protocol-Version'),
                             has_websocket_url=bool(body.get('webSocketDebuggerUrl')))
        except Exception as exc:
            entry['http_error'] = type(exc).__name__ + ': ' + str(exc)
        entry['http_seconds'] = round(time.perf_counter() - started, 2)
        result[host] = entry
    return result


def diag_loopback():
    server = socket.socket()
    try:
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        client = socket.create_connection(('127.0.0.1', server.getsockname()[1]), timeout=2)
        connection, _ = server.accept()
        connection.close(); client.close()
        return {'local_connection_between_own_sockets': 'ok'}
    finally:
        server.close()


def diag_policies():
    if os.name != 'nt':
        return []
    import winreg
    found = []
    for label, hive in (('machine', winreg.HKEY_LOCAL_MACHINE), ('user', winreg.HKEY_CURRENT_USER)):
        for view_label, view in (('64', winreg.KEY_WOW64_64KEY), ('32', winreg.KEY_WOW64_32KEY)):
            for sub in ('', '\\Recommended'):
                try:
                    with winreg.OpenKey(hive, r'SOFTWARE\Policies\Microsoft\Edge' + sub, 0, winreg.KEY_READ | view) as key:
                        count, subkeys, _ = winreg.QueryInfoKey(key)
                        for index in range(count):
                            name, value, kind = winreg.EnumValue(key, index)
                            found.append({'scope': label, 'registry_view': view_label, 'recommended': bool(sub), 'name': name,
                                          'type': kind, 'value': value if isinstance(value, int) else Private(value)})
                        if subkeys:
                            found.append({'scope': label, 'registry_view': view_label, 'recommended': bool(sub),
                                          'name': '(sub-keys, e.g. lists)', 'value': subkeys})
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    found.append({'scope': label, 'registry_view': view_label, 'read_error': str(exc)})
    return found


def diag_proxy():
    result = {'environment': {k: Private(os.environ[k]) for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                                                                  'http_proxy', 'https_proxy', 'no_proxy') if os.environ.get(k)}}
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
                for name in ('ProxyEnable', 'ProxyServer', 'AutoConfigURL', 'ProxyOverride'):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        result[name] = value if isinstance(value, int) else Private(value)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            result['read_error'] = str(exc)
    return result


def diag_env():
    plain = {'SESSIONNAME', 'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'OS'}
    standard = {n: v for n, v in sorted(os.environ.items()) if n.upper() in _DIAG_STANDARD_ENV}
    custom = {n: v for n, v in sorted(os.environ.items()) if n.upper() not in _DIAG_STANDARD_ENV}
    return {'standard_variable_names': list(standard), 'plain_values': {n: v for n, v in standard.items() if n in plain},
            'standard_values': Private(standard), 'custom_variable_count': len(custom), 'custom_variables': Private(custom)}


def diag_machine():
    import platform
    version = sys.getwindowsversion() if os.name == 'nt' else None
    result = {'platform': platform.platform(), 'windows_build': getattr(version, 'build', None),
              'python': sys.version.split()[0], 'python_executable': sys.executable, 'cpu_count': os.cpu_count(),
              'session_name': os.environ.get('SESSIONNAME'), 'client_name': Private(os.environ.get('CLIENTNAME', ''))}
    if os.name == 'nt':
        from ctypes import wintypes

        class Memory(ctypes.Structure):
            _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD), ('total', ctypes.c_ulonglong),
                        ('avail', ctypes.c_ulonglong), ('total_page', ctypes.c_ulonglong), ('avail_page', ctypes.c_ulonglong),
                        ('total_virtual', ctypes.c_ulonglong), ('avail_virtual', ctypes.c_ulonglong),
                        ('avail_extended', ctypes.c_ulonglong)]
        memory = Memory(); memory.length = ctypes.sizeof(Memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result['memory_mb'] = {'total': memory.total >> 20, 'available': memory.avail >> 20, 'load_percent': memory.load}
        kinds = {0: 'unknown', 1: 'no root', 2: 'removable', 3: 'fixed local disk', 4: 'network drive', 5: 'cd', 6: 'ram disk'}
        result['s_drive_type'] = kinds.get(ctypes.windll.kernel32.GetDriveTypeW('S:\\'), 'unknown')
    for label, target in (('s_drive', 'S:\\'), ('temp_folder', tempfile.gettempdir())):
        try:
            usage = shutil.disk_usage(target)
            result['disk_' + label + '_free_mb'] = usage.free >> 20
        except OSError as exc:
            result['disk_' + label] = 'unreadable: ' + str(exc)
    return result


def diag_edge_version(executable):
    try:
        found = [p.name for p in Path(executable).parent.iterdir() if p.is_dir() and re.fullmatch(r'\d+(?:\.\d+){3}', p.name)]
        return max(found, key=lambda v: [int(x) for x in v.split('.')]) if found else None
    except OSError:
        return None


def diag_profile(profile):
    profile = Path(profile)
    result = {'exists': profile.is_dir()}
    if not result['exists']:
        return result
    names = sorted(p.name for p in profile.iterdir())
    result['top_level_names'] = names[:80]
    result['singleton_files_present'] = [n for n in names if n.lower().startswith('singleton') or n.lower() == 'lockfile']
    result['has_default_folder'] = (profile / 'Default').is_dir()
    result['devtools_active_port'] = diag_devtools_port(profile)
    return result


def diag_devtools_port(profile):
    path = Path(profile) / 'DevToolsActivePort'
    if not path.is_file():
        return None
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    return {'port': lines[0].strip() if lines else None, 'websocket_path': lines[1].strip() if len(lines) > 1 else None}


def diag_tail(path, lines=150, limit=65536):
    path = Path(path)
    if not path.is_file():
        return BrowserLines()
    with open(path, 'rb') as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - limit))
        text = stream.read().decode('utf-8', errors='replace')
    return BrowserLines(text.splitlines()[-lines:])


def collect_system_snapshot(port=None, profile=None, logs=None, light=False):
    data = {'taken': now(), 'processes': diag_try(diag_process_summary), 'listeners': diag_try(diag_listeners, port)}
    if port:
        data['port_probe'] = diag_try(diag_probe_port, int(port))
    if profile:
        data['profile'] = diag_try(diag_profile, profile)
    if light:
        return data
    data.update(machine=diag_try(diag_machine), loopback_selftest=diag_try(diag_loopback), edge_policies=diag_try(diag_policies),
                proxy=diag_try(diag_proxy), environment_variables=diag_try(diag_env))
    data['log_tails'] = {name: diag_try(diag_tail, path) for name, path in (logs or {}).items()}
    return data


def diag_assess_edge(port, profile, before_pids, launcher_exit_code, stderr_path, policies):
    after = diag_try(diag_processes)
    edge = after.get('msedge', []) if isinstance(after, dict) else []
    listeners = diag_try(diag_listeners, port)
    on_port = listeners.get('on_configured_port', []) if isinstance(listeners, dict) else []
    blocks = []
    for item in policies or []:
        if item.get('name') == 'RemoteDebuggingAllowed' and item.get('value') == 0:
            blocks.append('RemoteDebuggingAllowed=0')
        if item.get('name') == 'DevToolsAvailability' and item.get('value') == 2:
            blocks.append('DevToolsAvailability=2')
    text = ''
    try:
        text = ' '.join(diag_tail(stderr_path, 400))
    except Exception:
        pass
    return {'configured_port': port, 'launcher_exit_code': launcher_exit_code,
            'edge_processes_before': len(before_pids), 'edge_processes_after': len(edge),
            'new_edge_processes': [p for p in edge if p['pid'] not in before_pids],
            'listeners_on_port': on_port, 'probe': diag_try(diag_probe_port, port),
            'devtools_active_port': diag_try(diag_devtools_port, profile), 'policy_blocks': blocks,
            'singleton': profile_singleton_failure(text),
            'devtools_refusal': (re.search(r'DevTools remote debugging [^.\n]*\.', text) or [None])[0] if text else None}


def diag_explain_edge(a):
    port, out = a.get('configured_port'), []
    if a.get('policy_blocks'):
        out.append('Company policy on this machine appears to block Edge remote debugging (' + ', '.join(a['policy_blocks'])
                   + '). Ask IT to allow it for this user. The tool will not bypass it.')
    if a.get('singleton'):
        out.append('The dedicated Edge profile is locked by another Edge window. Close only the dedicated review Edge window '
                   '(not your other Edge windows) and run again.')
    probe = a.get('probe') if isinstance(a.get('probe'), dict) else {}
    working = [h for h, r in probe.items() if isinstance(r, dict) and r.get('http_status') == 200]
    listeners = a.get('listeners_on_port') or []
    others = [x for x in listeners if str(x.get('program', '')).casefold() != 'msedge.exe']
    dev = a.get('devtools_active_port') if isinstance(a.get('devtools_active_port'), dict) else None
    if others:
        out.append(f'Port {port} is held by another program ({others[0]["program"]}), not by Edge. Close that program or choose a different port with --port.')
    elif listeners and not working:
        out.append(f'Edge did open debug port {port}, but this tool could not read its answer. Something on this VDI '
                   '(a proxy, security software or a local network rule) is probably blocking local connections.')
    elif working and '127.0.0.1' not in working:
        out.append(f'Edge answers on {", ".join(working)} but not on 127.0.0.1. The tool only tries 127.0.0.1.')
    elif working:
        out.append(f'Edge is answering on port {port} now. It was probably just slower than the wait allowed; run again.')
    if dev and dev.get('port') and str(dev['port']) != str(port) and not working:
        out.append(f'Edge started its debug connection on port {dev["port"]} instead of {port}.')
    if not listeners and not dev and not working:
        if not a.get('new_edge_processes'):
            out.append('Edge did not start a new process. It most likely handed the request to an Edge that was already running '
                       '(ignoring the dedicated profile) or a security tool closed it immediately.')
        else:
            out.append('Edge started and its window opened, but it never opened the debugging port. Typical reasons: a company '
                       'setting that disables debugging in a way this tool cannot see, or the changed user folders given to Edge. '
                       'Run Run_case_reviews_DIAGNOSE_ALT.cmd once; it starts Edge with your normal user folders.')
    return out or ['The cause could not be identified automatically. Send the EXTERNAL report.']


_DIAG_KNOWN_ERRORS = (
    ('Long Path support', 'Windows refused a file path because it is too long (about 260 characters) while installing the Python packages on S:. '
                          'Choose a shorter working folder (for example S:\\DCR): delete local_paths.cmd and run again. '
                          'If it still fails, ask IT to enable Windows long paths.'),
    ('S: is unavailable', 'The S: drive is not connected in this VDI session. Reconnect it, then run again.'),
    ('Use only the specified Python executable', 'The Python you pasted is not the one that started this tool. Delete local_paths.cmd and run again to re-enter the paths.'),
    ('Playwright is required', 'A required add-on (Playwright) is missing. Run this tool once with --setup so it installs on S:.'),
    ('Another controller/setup is active', 'Another copy of this tool is still running (or crashed). Close it, then run again.'),
    ('No clean signed-in Copilot composer', 'Edge opened but the Copilot chat page never became ready. Most likely you were not signed in (or MFA was pending) in the dedicated window within 5 minutes. Sign in there and run again.'),
    ('unverified/old session', 'An older review browser is still open on this port. Close only that dedicated window, then run again.'),
    ('UserDataDir policy', 'A company Edge policy decides where Edge keeps its profile. IT must confirm it matches the dedicated S: profile.'),
    ('RemoteDebuggingAllowed', 'A company Edge policy blocks remote debugging. Ask IT to allow it for this user.'),
    ('ProcessSingleton', 'The dedicated Edge profile is locked by another Edge window. Close only the dedicated review window and run again.'),
    ('Installed Edge was not found', 'Microsoft Edge could not be found. Pass its msedge.exe location with --browser-path.'),
    ('Reconnection exhausted', 'The tool lost its connection to Edge during the run. Do not rerun blindly: check the Copilot chats first, uncertain sends are kept and never repeated.'),
    ('Browser instance changed', 'Edge was restarted during the run. Check the Copilot chats before running again; uncertain sends are kept and never repeated.'),
)


def diag_wait_sample(port, profile, edge_before):
    sample = {'listening_on_127.0.0.1': None, 'devtools_active_port': diag_try(diag_devtools_port, profile),
              'edge_processes_now': len(diag_edge_pids()), 'edge_processes_before_launch': len(edge_before)}
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=0.5):
            sample['listening_on_127.0.0.1'] = True
    except OSError as exc:
        sample['listening_on_127.0.0.1'] = False
        sample['connect_error'] = type(exc).__name__
    return sample


class DiagnosticRecorder:
    def __init__(self, directory, argv):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.started, self.started_at = time.perf_counter(), now()
        self.events, self.snapshots, self.facts = [], {}, {}
        self.records, self.exit_code, self.failure_text = None, None, ''
        self.sanitizer, self.argv = DiagSanitizer(), list(argv)
        self._busy, self._closed = False, False
        self.stream = open(self.dir / 'events.jsonl', 'a', encoding='utf-8')
        for kind, key in (('USER', 'USERNAME'), ('HOST', 'COMPUTERNAME'), ('DOMAIN', 'USERDOMAIN'),
                          ('DOMAIN', 'USERDNSDOMAIN'), ('HOST', 'LOGONSERVER'), ('HOST', 'CLIENTNAME')):
            self.sanitizer.learn(kind, os.environ.get(key))
        try:
            import getpass
            self.sanitizer.learn('USER', getpass.getuser())
        except Exception:
            pass

    def event(self, step, message, level='info', **data):
        item = {'t': round(time.perf_counter() - self.started, 2), 'at': now(), 'step': step, 'level': level, 'message': str(message)}
        if data:
            item['data'] = data
        self.events.append(item)
        try:
            self.stream.write(json.dumps(diag_plain(item), default=str, ensure_ascii=False) + '\n')
            self.stream.flush()
        except Exception:
            pass

    def console(self, text, level='info'):
        if self._busy or self._closed:
            return
        self._busy = True
        try:
            self.event('console', text, level)
        finally:
            self._busy = False

    def learn_cases(self, records):
        self.records = records
        for record in records:
            for kind, key in (('ID', 'instruction_id'), ('ACCOUNT', 'account_number'), ('FOLDER', 'folder_name')):
                self.sanitizer.learn(kind, record.get(key))
            for item in record.get('manifest', [])[:400]:
                self.sanitizer.learn('FILE', item.get('name'))

    def snapshot(self, label, **kwargs):
        name, number = label, 1
        while name in self.snapshots:
            number += 1
            name = label + '#' + str(number)
        self.snapshots[name] = snapshot = diag_try(collect_system_snapshot, **kwargs)
        variables = snapshot.get('environment_variables') if isinstance(snapshot, dict) else None
        custom = variables.get('custom_variables') if isinstance(variables, dict) else None
        for variable in custom.value if isinstance(custom, Private) else ():
            self.sanitizer.learn('VAR', variable)
        self.event('snapshot', 'system details captured: ' + name)

    def failure(self, exc, details):
        self.failure_text = (str(exc) + '\n' + details).strip()
        self.event('failure', type(exc).__name__ + ': ' + str(exc), 'error', traceback=details)
        if not any(k.startswith('at_failure') for k in self.snapshots):
            self.snapshot('at_failure', port=self.facts.get('port'), profile=self.facts.get('profile'), logs=self.facts.get('logs'))

    def likely_causes(self):
        causes = list(self.facts.get('edge_causes', []))
        text = (self.failure_text + ' ' + ' '.join(e['message'] for e in self.events if e['step'] == 'console')).casefold()
        for needle, advice in _DIAG_KNOWN_ERRORS:
            if needle.casefold() in text and advice not in causes:
                causes.append(advice)
        if self.exit_code == 2 and not causes:
            causes.append('The run finished, but not every case completed (exit code 2). See the case states in the report.')
        if self.exit_code not in (0, 2, None) and not causes:
            causes.append('The run stopped with an error that is not in the list of known problems. Send the EXTERNAL report.')
        return causes

    def _timeline(self, view):
        lines = []
        for item in self.events:
            extra = ''
            if item.get('data'):
                extra = ' ' + json.dumps(view(item['data']), ensure_ascii=False, default=str)
            lines.append(f'[{item["t"]:8.2f}s] {item["step"]:9} {item["level"]:5} ' + str(view(item['message'])).replace('\n', ' | ') + extra)
        return '\n'.join(lines)

    def _body(self, view):
        states = Counter(r.get('state') for r in (self.records or []))
        sections = [('Run', {'tool': 'case_review_runner', 'argv_flags': [a for a in self.argv if a.startswith('--')],
                             'started': self.started_at, 'finished': now(), 'exit_code': self.exit_code,
                             'case_states': dict(states), 'cases_found': len(self.records or [])}),
                    ('Facts gathered during Edge startup', {k: v for k, v in self.facts.items() if k not in ('logs',)})]
        parts = []
        for title, data in sections:
            parts.append('## ' + title + '\n```json\n' + json.dumps(view(data), indent=2, ensure_ascii=False, default=str) + '\n```')
        parts.append('## Timeline (everything the tool printed or recorded)\n```text\n' + self._timeline(view) + '\n```')
        for label, snap in self.snapshots.items():
            parts.append('## System details: ' + label + '\n```json\n' + json.dumps(view(snap), indent=2, ensure_ascii=False, default=str) + '\n```')
        if self.failure_text:
            parts.append('## Error and traceback\n```text\n' + str(view(self.failure_text)) + '\n```')
        return '\n\n'.join(parts)

    def finish(self, code):
        self.exit_code = code
        self.event('end', 'Run ended with exit code ' + str(code), 'info' if code == 0 else 'error')
        self._closed = True
        causes = self.likely_causes()
        outcome = 'finished successfully' if code == 0 else 'ended with exit code ' + str(code)
        plain_view = diag_plain
        internal = ('# INTERNAL diagnostic report (keep inside the VDI)\n\nOutcome: ' + outcome + '\n\n## Likely cause (plain English)\n'
                    + ''.join('- ' + c + '\n' for c in causes or ['No problem detected.']) + '\n' + self._body(plain_view))
        external_body = self._body(self.sanitizer.obj)
        cause_text = ''.join('- ' + str(self.sanitizer.clean(c)) + '\n' for c in causes or ['No problem detected.'])
        sanitizer = self.sanitizer
        legend = {'PATH': 'file or folder path (kept: drive, depth, extension)', 'USER': 'user name', 'HOST': 'computer or server name',
                  'DOMAIN': 'network domain', 'ID': 'instruction ID', 'ACCOUNT': 'account number', 'FOLDER': 'case folder name',
                  'FILE': 'evidence file name', 'URL': 'web address outside Microsoft', 'EMAIL': 'e-mail address',
                  'GUID': 'unique identifier', 'HASH': 'long hexadecimal value', 'RUN': 'run identifier', 'IP': 'network address',
                  'PRIVATE-values': 'private values, e.g. environment variable contents and proxy settings',
                  'URL-details': 'page paths and query text on Microsoft web addresses'}
        rows = ['| What was removed | Distinct values | Times replaced |', '|---|---|---|']
        for kind in sorted(sanitizer.counts):
            distinct = sum(1 for k in sanitizer.labels if k[0] == kind) or '-'
            rows.append(f'| {kind}: {legend.get(kind, "other")} | {distinct} | {sanitizer.counts[kind]} |')
        rows.append(f'| Browser output lines removed as unverified free text | - | {sanitizer.unverified} |')
        rows.append(f'| Leftover path-like text removed in the final check | - | {sanitizer.residual} |')
        external = ('# EXTERNAL diagnostic report (details removed; safe to send)\n\nOutcome: ' + outcome
                    + '\n\nEvery removed value is replaced by a numbered label such as `<PATH-3 S: depth=4 ext=.json>`. '
                    'The same label always means the same original value, so the order of events stays readable. '
                    'Timestamps, exit codes, error types, Edge flag names, policy names and process counts are kept.\n\n'
                    '## What was removed\n' + '\n'.join(rows) + '\n\n## Likely cause (plain English)\n' + cause_text + '\n' + external_body)
        external = _DIAG_RESIDUAL.sub('<REMOVED residual-path>', external)
        mapping = ['\n\n## Label key (INTERNAL ONLY: what each label in the EXTERNAL report stood for)\n', '| Label | Original |', '|---|---|']
        for (kind, _), (name, raw) in sorted(sanitizer.labels.items(), key=lambda kv: kv[1][0]):
            mapping.append('| ' + name + ' | ' + raw.replace('|', '\\|') + ' |')
        internal_path, external_path = self.dir / 'INTERNAL_do_not_share.md', self.dir / 'EXTERNAL_safe_to_share.md'
        write_text(internal_path, internal + '\n'.join(mapping) + '\n')
        write_text(external_path, external + '\n')
        try:
            self.stream.close()
        except Exception:
            pass
        _BUILTIN_PRINT('\n================ DIAGNOSE RESULT ================', flush=True)
        _BUILTIN_PRINT('Outcome: ' + outcome, flush=True)
        _BUILTIN_PRINT('Likely cause, in plain English:', flush=True)
        for number, cause in enumerate(causes or ['No problem detected.'], 1):
            _BUILTIN_PRINT(f'  {number}. {cause}', flush=True)
        _BUILTIN_PRINT('Two reports were saved:', flush=True)
        _BUILTIN_PRINT('  KEEP INSIDE THE VDI (full details): ' + str(internal_path), flush=True)
        _BUILTIN_PRINT('  SAFE TO SEND BACK (details removed): ' + str(external_path), flush=True)
        return internal_path, external_path


def begin_diagnostics(paths, argv):
    global _RECORDER
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    _RECORDER = DiagnosticRecorder(paths['logs'] / 'diagnose' / stamp, argv)
    _RECORDER.event('start', 'Diagnose mode on: this is a normal run, recorded in full')
    return _RECORDER


# ---------- Edge launch variants: tried in order, the last winner first, and remembered ----------
# One dedicated profile can run only one Edge at a time, so the ways of starting Edge run one after
# another. The ways of DETECTING the debug port all run at once on every check.
EDGE_ATTEMPT_SECONDS = 50
EDGE_PIPE_TIMEOUT_MS = 60000
EDGE_VARIANTS = [
    {'name': 'pipe-installed-edge', 'label': 'Playwright-started Edge, installed Edge file, S: folders', 'mode': 'pipe', 'exe': 'path', 'port': None, 'folders': 'redirected'},
    {'name': 'pipe-edge-channel', 'label': 'Playwright-started Edge, Edge channel, S: folders', 'mode': 'pipe', 'exe': 'channel', 'port': None, 'folders': 'redirected'},
    {'name': 'pipe-normal-folders', 'label': 'Playwright-started Edge, installed Edge file, normal Windows folders', 'mode': 'pipe', 'exe': 'path', 'port': None, 'folders': 'normal'},
    {'name': 'configured-port', 'label': 'debugging port, S: folders', 'mode': 'cdp', 'port': 'configured', 'folders': 'redirected'},
    {'name': 'normal-windows-folders', 'label': 'debugging port, normal Windows folders', 'mode': 'cdp', 'port': 'configured', 'folders': 'normal'},
    {'name': 'automatic-port', 'label': 'debugging automatic port, S: folders', 'mode': 'cdp', 'port': 'automatic', 'folders': 'redirected'},
]


def write_edge_preferences(paths, profile):
    preferences = profile / 'Default' / 'Preferences'
    if not preferences.exists():
        atomic_json(preferences, {'download': {'default_directory': mapped_browser_path(paths['downloads']), 'prompt_for_download': False},
                                  'savefile': {'default_directory': mapped_browser_path(paths['downloads'])}})


class PipeBrowser:
    """Stands in for a Browser when Playwright started Edge itself. Only the parts the runner uses are provided."""
    def __init__(self, context):
        self.context = context
        self.contexts = [context]
        self.closed = False
        context.on('close', lambda *_: setattr(self, 'closed', True))

    def is_connected(self):
        return not self.closed


def edge_memory_path(paths):
    return paths['home'] / 'edge-startup-memory.json'


def edge_memory_read(paths):
    memory = read_json(edge_memory_path(paths), {})
    return memory if isinstance(memory, dict) else {}


def edge_cdp_variants(order):
    return [v for v in order if v['mode'] == 'cdp']


def edge_variant_order(memory, forced_normal_folders=False):
    if forced_normal_folders:
        return [v for v in EDGE_VARIANTS if v['folders'] == 'normal']
    winner = memory.get('winner')
    return [v for v in EDGE_VARIANTS if v['name'] == winner] + [v for v in EDGE_VARIANTS if v['name'] != winner]


def edge_memory_record(paths, memory, attempts, variant, attempt):
    """Count every attempt. A success becomes the remembered first choice for future runs."""
    history = dict(memory.get('history', {}))
    for item in attempts:
        entry = dict(history.get(item['variant'], {'ok': 0, 'failed': 0}))
        entry['ok' if item['ready'] else 'failed'] = entry.get('ok' if item['ready'] else 'failed', 0) + 1
        history[item['variant']] = entry
    if variant is None:
        record = {**memory, 'history': history, 'last_run_found_port': False, 'saved': now()}
    else:
        record = {'winner': variant['name'], 'winner_label': variant['label'], 'mode': variant['mode'],
                  'detected_by': attempt['detected_by'], 'port': attempt['port'], 'saved': now(), 'history': history,
                  'last_run_found_port': True}
    atomic_json(edge_memory_path(paths), record)
    return record


def edge_tree_pids(root, before_edge):
    """The launched Edge process and the Edge processes started under it. Other Edge windows are never included."""
    try:
        rows = diag_processes()['msedge']
    except Exception:
        return set()
    tree = {root} if any(row['pid'] == root for row in rows) else set()
    changed = True
    while changed:
        changed = False
        for row in rows:
            if row['pid'] not in tree and row['pid'] not in before_edge and row['parent_pid'] in tree:
                tree.add(row['pid'])
                changed = True
    return tree


def diag_terminate(pids):
    """Terminate only the given processes (children first). Used only on processes this run started."""
    if os.name != 'nt':
        return {}
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    results = {}
    for pid in sorted(pids, reverse=True):
        handle = kernel.OpenProcess(0x0001, False, pid)
        if not handle:
            results[pid] = 'could not open (already closed)'
            continue
        ok = kernel.TerminateProcess(handle, 0)
        kernel.CloseHandle(handle)
        results[pid] = 'closed' if ok else 'could not close'
    return results


def _listener_rows():
    listing = diag_try(diag_listeners, None)
    return listing.get('all_listening', []) if isinstance(listing, dict) else []


def edge_explain_attempts(attempts):
    """Plain-English causes for a run in which no way of starting Edge opened the debug port."""
    causes = []
    refusals = [a['assessment'].get('devtools_refusal') for a in attempts
                if isinstance(a.get('assessment'), dict) and a['assessment'].get('devtools_refusal')]
    if refusals and len(refusals) == len(attempts):
        causes.append(f'Edge refused remote debugging in all {len(attempts)} ways it was started. Its own message: "' + refusals[0] + '". '
                      'The dedicated profile folder is probably not accepted as a non-default data folder on this VDI. Send this report.')
    elif refusals:
        causes.append('Edge refused remote debugging in some of the ways it was started (its message: "' + refusals[0] + '").')
    for number, attempt in enumerate(attempts, 1):
        assessment = attempt.get('assessment') if isinstance(attempt.get('assessment'), dict) else {}
        if attempt.get('failure_kind') == 'profile_singleton_lock':
            causes.append(f'Way {number} ({attempt["label"]}): another Edge window is still using the dedicated profile. '
                          'Close only the dedicated review Edge window (not your other Edge windows) and run again.')
            continue
        if 'playwright_error' in assessment:
            causes.append(f'Way {number} ({attempt["label"]}): Playwright could not start Edge. Its message: "' + str(assessment['playwright_error'])[:300] + '"')
            continue
        causes.append(f'Way {number} ({attempt["label"]}): no debug port after {attempt["seconds"]} s; '
                      f'{attempt["new_edge_processes"]} new Edge processes; this attempt closed its own Edge: '
                      + ('yes' if (attempt.get('closed') or {}).get('terminated') else 'no') + '.')
        for cause in diag_explain_edge(assessment):
            if cause not in causes:
                causes.append(cause)
    return causes


class EdgeBrowser:
    def __init__(self, config, paths):
        self.c, self.paths = config, paths
        self.endpoint = f'http://127.0.0.1:{config["port"]}'
        self.marker = paths['home'] / 'browser-session.json'
        self.browser = None
        self.mode = None
        self.last_cdp_summary = None
        self.used = set()
        self.connection_lock = asyncio.Lock()
        self.slot_lock = asyncio.Lock()
        # Only one tab uploads at a time; overlapping uploads failed with "An error occurred while uploading".
        self.upload_lock = asyncio.Lock()

    def ensure_started(self, only=None):
        """Debugging-port way: profile selection, reconciliation, then the port launch attempts."""
        remembered = read_json(self.marker, {})
        if remembered.get('port') and remembered.get('profile') == str(require_s(self.c['profile_dir'], 'Edge profile')):
            # The verified dedicated session may be on the port that worked last time.
            self.c['port'] = int(remembered['port'])
            self.endpoint = f'http://127.0.0.1:{self.c["port"]}'
        self._apply_profile_selection()
        self._check_reconciliation()
        try:
            return self._ensure_started_once(only)
        except ProfileSingletonError as first:
            if only:
                # start() reports the lock and never creates a new profile on its own.
                raise
            assert_profile_recovery_safe(self)
            selection, original = self._selection, self._original_profile
            if selection:
                raise RuntimeError('The selected isolated Edge profile is also locked. No additional profile will be created. Close only the dedicated review window normally and retry. ' + str(first)) from first
            budget_path = self.paths['home'] / ('edge-profile-recovery-' + digest(str(original))[:16] + '.json')
            if budget_path.exists():
                raise RuntimeError('One isolated-profile recovery has already been attempted for this profile. No further profile creation or lock deletion. Review: ' + str(budget_path)) from first
            isolated = require_s(original.with_name(original.name + '-isolated-' + uuid.uuid4().hex[:12]), 'Isolated Edge profile')
            # Exclusive creation prevents accidentally reusing another profile.
            isolated.mkdir(parents=True, exist_ok=False)
            recovery = {'created': now(), 'original_profile': str(original), 'selected_profile': str(isolated),
                        'reason': 'Edge reported ProcessSingleton lock creation failure', 'status': 'attempting',
                        'old_profile_preserved': True, 'shared_records_unchanged': True}
            atomic_json(budget_path, recovery)
            print('Edge profile is locked. Original profile and all case records are preserved.')
            print('Starting one new isolated profile on S:; sign in in that new dedicated window.')
            self.c['profile_dir'] = str(isolated)
            try:
                result = self._ensure_started_once()
            except Exception as exc:
                recovery.update(status='failed', error=str(exc))
                atomic_json(budget_path, recovery)
                raise RuntimeError('Isolated Edge profile also failed. No more automatic attempts, profile deletion or process termination. ' + str(exc)) from exc
            recovery.update(status='endpoint_ready', completed=now())
            atomic_json(budget_path, recovery)
            atomic_json(self._selection_path, recovery)
            return result

    def _apply_profile_selection(self):
        if getattr(self, '_original_profile', None) is None:
            self._original_profile = require_s(self.c['profile_dir'], 'Edge profile')
        self._selection_path = self.paths['home'] / 'edge-profile-selection.json'
        self._selection = read_json(self._selection_path, {})
        selection, original = self._selection, self._original_profile
        if selection and selection.get('original_profile') == str(original):
            selected = require_s(selection.get('selected_profile'), 'Selected Edge profile')
            if selected.parent != original.parent or not selected.name.startswith(original.name + '-isolated-'):
                raise RuntimeError('Unexpected selected profile location; startup stopped without changing it.')
            self.c['profile_dir'] = str(selected)

    def _check_reconciliation(self):
        if self.marker.exists() and not get_cdp_version(self.endpoint):
            # Never relaunch a verified session with unresolved assignments.
            store = getattr(self, 'startup_store', None)
            if store is None:
                raise RuntimeError('Original browser endpoint unavailable and shared reconciliation records missing; no relaunch.')
            for path in store.records.glob('*.json'):
                record = read_json(path)
                if not isinstance(record, dict) or record.get('state') not in {'discovered', 'ready', 'blocked', 'retryable failure', 'completed'} or (record.get('state') != 'completed' and record.get('assignment')):
                    raise RuntimeError('Original browser endpoint unavailable with an unresolved case. Preserve the original session; no new profile or relaunch was attempted.')

    async def _run_ways(self, order, memory):
        attempts, winner = [], None
        for variant in order:
            if variant['mode'] == 'pipe':
                result = await self._pipe_attempt(variant)
            else:
                result = await self._cdp_attempt(variant)
            attempts.append(result['summary'])
            if result['ready']:
                winner = (variant, result['summary'])
                break
            print(f'Way "{variant["label"]}" did not work. Trying the next way.', flush=True)
        return attempts, winner

    async def start(self):
        """Start the dedicated Edge by each way in order (remembered winner first) and remember the one that works."""
        memory = edge_memory_read(self.paths)
        order = edge_variant_order(memory, self.c.get('edge_original_env'))
        attempts, winner = await self._run_ways(order, memory)
        if winner is None and sys.stdin.isatty():
            # The one thing only the user can supply: where Edge is installed on this computer.
            print('', flush=True)
            print('Edge did not start. If Microsoft Edge is installed in a different folder on this computer,', flush=True)
            print('paste the full path of its msedge.exe file below and this tool will try once more.', flush=True)
            while True:
                answer = input('Full path of msedge.exe (press Enter alone to stop): ').strip().strip('"')
                if not answer:
                    break
                try:
                    self.c['browser_path'] = str(installed_edge(answer))
                except Exception as exc:
                    print('That file cannot be used: ' + str(exc) + '. Try again, or press Enter to stop.', flush=True)
                    continue
                retry_attempts, winner = await self._run_ways(order, memory)
                attempts += retry_attempts
                break
        edge_memory_record(self.paths, memory, attempts, winner[0] if winner else None, winner[1] if winner else None)
        if winner is None:
            causes = edge_explain_attempts(attempts)
            print('LIKELY CAUSE (plain English):')
            for cause in causes:
                print('  - ' + cause)
            raise RuntimeError(f'Edge did not start in any of {len(attempts)} ways. Likely cause: ' + ' '.join(causes)
                               + ' No profile was deleted and no uncertain submission was repeated. Send the EXTERNAL report from the logs folder.')
        variant, summary = winner
        print(f'Dedicated Edge started using: {variant["label"]}. This choice is remembered for next time.', flush=True)
        if self.mode == 'cdp':
            await self.connect()

    async def _cdp_attempt(self, variant):
        self.last_cdp_summary = None

        def run():
            self.ensure_started(only=variant)
            return self.last_cdp_summary

        try:
            summary = await asyncio.to_thread(run)
            self.mode = 'cdp'
            return {'ready': True, 'summary': summary}
        except Exception as exc:
            summary = dict(self.last_cdp_summary or {'variant': variant['name'], 'label': variant['label'], 'ready': False,
                                                     'seconds': None, 'new_edge_processes': 0, 'closed': None, 'assessment': None})
            summary['error'] = str(exc)[:600]
            return {'ready': False, 'summary': summary}

    async def _pipe_attempt(self, variant):
        """Playwright starts the dedicated Edge itself over a private pipe: no debugging port is opened or needed."""
        started = time.monotonic()
        summary = {'variant': variant['name'], 'label': variant['label'], 'mode': 'pipe', 'port_argument': None,
                   'ready': False, 'detected_by': None, 'port': None, 'seconds': None, 'new_edge_processes': 0,
                   'launcher_exit_code': None, 'assessment': None, 'closed': None}
        context = None
        try:
            await asyncio.to_thread(self._apply_profile_selection)
            await asyncio.to_thread(self._check_reconciliation)
            executable = installed_edge(self.c.get('browser_path'), prompt=False)
            profile = require_s(self.c['profile_dir'], 'Edge profile')
            profile.mkdir(parents=True, exist_ok=True)
            write_edge_preferences(self.paths, profile)
            cache = self.paths['cache'] / 'browser'; cache.mkdir(parents=True, exist_ok=True)
            env = edge_environment(variant['folders'])
            options = {'user_data_dir': mapped_browser_path(profile), 'headless': os.environ.get('DCR_TEST_HEADLESS') == '1',
                       'args': [f'--disk-cache-dir={mapped_browser_path(cache)}', f'--crash-dumps-dir={mapped_browser_path(self.paths["crashes"])}',
                                '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
                                '--disable-background-timer-throttling', '--disable-component-update', '--disable-breakpad',
                                '--disable-crash-reporter'],
                       'env': env, 'timeout': EDGE_PIPE_TIMEOUT_MS, 'accept_downloads': True}
            if variant['exe'] == 'path':
                options['executable_path'] = str(executable)
            else:
                options['channel'] = 'msedge'
            context = await self.pw.chromium.launch_persistent_context(**options)
            page = context.pages[0] if context.pages else await context.new_page()
            # Two independent checks before this way counts: a page must run script, and the browser must answer a DevTools command.
            if not await asyncio.wait_for(page.evaluate('() => navigator.userAgent'), 30):
                raise RuntimeError('The started Edge did not run a page script.')
            session = await context.new_cdp_session(page)
            version = await asyncio.wait_for(session.send('Browser.getVersion'), 30)
            await session.detach()
            summary.update(ready=True, detected_by='Playwright-started Edge (no debugging port)', seconds=round(time.monotonic() - started, 1),
                           browser_version=version.get('product'))
            self.browser = PipeBrowser(context)
            self.mode = 'pipe'
            # A stale record of an earlier debugging-port session must not be trusted now.
            self.marker.unlink(missing_ok=True)
            return {'ready': True, 'summary': summary}
        except Exception as exc:
            if context is not None:
                try:
                    await context.close()
                except Exception:
                    pass
            summary.update(seconds=round(time.monotonic() - started, 1), error=str(exc)[:600],
                           assessment={'playwright_error': str(exc)[:600]},
                           closed={'terminated': {}, 'note': 'Playwright closed its own browser for this way.'})
            return {'ready': False, 'summary': summary}

    def _ensure_started_once(self, only=None):
        profile = require_s(self.c['profile_dir'], 'Edge profile')
        profile.mkdir(parents=True, exist_ok=True)
        marker = read_json(self.marker, {})
        if marker.get('port') and marker.get('profile') == str(profile):
            # A previous run recorded which port its verified dedicated session used.
            self.c['port'] = int(marker['port'])
            self.endpoint = f'http://127.0.0.1:{self.c["port"]}'
        payload = get_cdp_version(self.endpoint)
        if payload:
            if marker.get('websocket') != payload['webSocketDebuggerUrl'] or marker.get('profile') != str(profile):
                raise RuntimeError('Debug port belongs to an unverified/old session. Preserve unresolved cases; close only your old dedicated browser or choose --port. No unrelated session was adopted.')
            if not marker.get('executable'):
                raise RuntimeError('Existing browser marker has no verified Edge executable')
            installed_edge(marker['executable'])
            return
        executable = installed_edge(self.c.get('browser_path'), prompt=True)
        write_edge_preferences(self.paths, profile)
        cache = self.paths['cache'] / 'browser'; cache.mkdir(parents=True, exist_ok=True)
        diagnostic = self.paths['logs'] / ('edge-startup-' + uuid.uuid4().hex + '.json')
        stderr_path = diagnostic.with_suffix('.stderr.log')
        memory = edge_memory_read(self.paths)
        variants = [only] if only else edge_cdp_variants(edge_variant_order(memory, self.c.get('edge_original_env')))
        report = {'created': now(), 'endpoint': self.endpoint, 'profile': str(profile),
                  'executable': str(executable), 'edge_version': diag_edge_version(executable),
                  'policies': edge_policy_snapshot(), 'status': 'preflight', 'stderr_log': str(stderr_path),
                  'variants_in_order': [v['name'] for v in variants], 'remembered_winner': memory.get('winner'),
                  'attempts': [], 'storage_checks': [],
                  'note': 'No policy changes, elevation, browser download or profile reset.'}
        atomic_json(diagnostic, report)
        recorder = _RECORDER
        log_files = {'edge stderr': stderr_path, 'browser.log': self.paths['logs'] / 'browser.log'}
        if recorder:
            recorder.facts.update(port=self.c['port'], profile=str(profile), logs=log_files, edge_exe=str(executable),
                                  edge_version=report['edge_version'], variants_in_order=report['variants_in_order'],
                                  remembered_winner=memory.get('winner'))
            recorder.event('edge', 'Starting the dedicated Edge', variants=report['variants_in_order'])
        before_edge = diag_edge_pids()
        try:
            for directory in (profile, cache, self.paths['downloads'], self.paths['crashes'], self.paths['logs']):
                probe_browser_storage(directory)
                report['storage_checks'].append({'path': str(directory), 'writable': True})
            if any(item.get('name') == 'RemoteDebuggingAllowed' and item.get('value') == 0 for item in report['policies']):
                raise RuntimeError('An Edge RemoteDebuggingAllowed policy is set to 0. Ask IT to confirm the effective policy. It will not be bypassed.')
            if any(item.get('name') == 'UserDataDir' for item in report['policies']):
                raise RuntimeError('Edge UserDataDir policy is configured. IT must confirm its effective destination matches the dedicated S: profile before automation starts.')
            # Detect an occupied port without adopting another browser or killing it.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
                if check.connect_ex(('127.0.0.1', int(self.c['port']))) == 0:
                    raise RuntimeError('The selected debug port is occupied but has no verified Edge endpoint. No existing process was stopped or adopted.')
            report['status'] = 'launching'
            atomic_json(diagnostic, report)
            print('Edge startup diagnostics: ' + str(diagnostic))
            if recorder:
                recorder.snapshot('before_launch', port=self.c['port'], profile=profile, logs=log_files)
            winner = None
            for number, variant in enumerate(variants, 1):
                print(f'Edge start attempt {number} of {len(variants)}: {variant["label"]}')
                attempt = self._launch_attempt(variant, executable, profile, cache, stderr_path, before_edge, report, recorder)
                report['attempts'].append(attempt['summary'])
                atomic_json(diagnostic, report)
                if attempt['ready']:
                    winner = (variant, attempt)
                    break
                if attempt['summary'].get('failure_kind') == 'profile_singleton_lock':
                    # Every other way uses the same profile, so it would hit the same lock. Stop here and report it.
                    self.last_cdp_summary = attempt['summary']
                    raise ProfileSingletonError('Edge cannot create its profile lock (ProcessSingleton): another Edge window is still using the dedicated profile. Close only the dedicated review Edge window and run again. Nothing was deleted, copied or terminated.')
                print(f'Attempt {number} did not open a debugging port. Trying the next way.')
            if winner:
                variant, attempt = winner
                self.last_cdp_summary = attempt['summary']
                report.update(status='endpoint_ready', winner=variant['name'], detected_by=attempt['detected_by'])
                atomic_json(diagnostic, report)
                print(f'Edge debug port found by "{attempt["detected_by"]}" using: {variant["label"]}. This choice is remembered for next time.')
                if recorder:
                    recorder.event('edge', 'Edge debug endpoint is ready', winner=variant['name'], detected_by=attempt['detected_by'])
                    recorder.snapshot('after_ready', port=self.c['port'], profile=profile, light=True)
                return
            self.last_cdp_summary = report['attempts'][-1] if report['attempts'] else None
            causes = edge_explain_attempts(report['attempts'])
            report.update(likely_cause=causes)
            atomic_json(diagnostic, report)
            if recorder:
                recorder.facts.update(edge_attempts=[{k: v for k, v in a.items() if k != 'assessment'} for a in report['attempts']],
                                      edge_causes=causes)
            print('LIKELY CAUSE (plain English):')
            for cause in causes:
                print('  - ' + cause)
            raise RuntimeError(f'Edge did not open a debugging port in any of {len(variants)} attempts. Likely cause: ' + ' '.join(causes)
                               + ' No profile was deleted and no uncertain submission was repeated.')
        except Exception as exc:
            report.update(status='failed', error=str(exc))
            atomic_json(diagnostic, report)
            if recorder:
                recorder.event('edge', 'Edge startup failed: ' + str(exc), 'error')
                recorder.snapshot('at_failure', port=self.c['port'], profile=profile, logs=log_files)
            error_type = ProfileSingletonError if isinstance(exc, ProfileSingletonError) else RuntimeError
            raise error_type(str(exc) + '\nStartup diagnostics: ' + str(diagnostic) + '\nBrowser output: ' + str(stderr_path)) from exc

    def _launch_attempt(self, variant, executable, profile, cache, stderr_path, before_edge, report, recorder):
        """Start Edge one way, watch every detection method at once, and clean up only this attempt's processes."""
        configured = variant['port'] == 'configured'
        port = self.c['port'] if configured else 0
        attempt_stderr = stderr_path.with_name(stderr_path.name.replace('.stderr.log', '') + '.' + variant['name'] + '.stderr.log')
        flags = [str(executable), f'--remote-debugging-port={port}', '--remote-debugging-address=127.0.0.1',
                 f'--user-data-dir={mapped_browser_path(profile)}', f'--disk-cache-dir={mapped_browser_path(cache)}',
                 f'--crash-dumps-dir={mapped_browser_path(self.paths["crashes"])}', f'--log-file={mapped_browser_path(self.paths["logs"] / "browser.log")}', '--enable-logging',
                 '--no-first-run', '--no-default-browser-check', '--disable-backgrounding-occluded-windows',
                 '--disable-renderer-backgrounding', '--disable-background-timer-throttling', '--disable-component-update',
                 '--disable-breakpad', '--disable-crash-reporter', self.c['url']]
        child_env = edge_environment(variant['folders'])
        summary = {'variant': variant['name'], 'label': variant['label'], 'port_argument': port, 'ready': False,
                   'detected_by': None, 'port': None, 'seconds': None, 'new_edge_processes': None,
                   'launcher_exit_code': None, 'assessment': None, 'closed': None}
        if recorder:
            recorder.event('edge', 'Starting the dedicated Edge (' + variant['name'] + ')', port=port, flags=flags)
        started = time.monotonic()
        deadline, next_note = started + EDGE_ATTEMPT_SECONDS, started + 10
        with open(attempt_stderr, 'ab', buffering=0) as browser_log:
            process = subprocess.Popen(flags, executable=str(executable), cwd=mapped_browser_path(PACKAGE), env=child_env,
                                       stdin=subprocess.DEVNULL, stdout=browser_log, stderr=browser_log,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        found = None
        while time.monotonic() < deadline:
            new = diag_edge_pids() - before_edge
            found = self._detect_endpoint(profile, new, configured)
            if found:
                break
            if process.poll() is not None:
                with open(long_io_path(attempt_stderr), encoding='utf-8', errors='replace') as stream:
                    if profile_singleton_failure(stream.read(1024 * 1024)):
                        summary['failure_kind'] = 'profile_singleton_lock'
                        break
            if time.monotonic() >= next_note:
                next_note += 10
                print(f'  waiting for the debug port ({int(time.monotonic() - started)}s of {EDGE_ATTEMPT_SECONDS}s)...')
            time.sleep(.3)
        summary.update(seconds=round(time.monotonic() - started, 1), launcher_exit_code=process.poll(),
                       new_edge_processes=len(diag_edge_pids() - before_edge))
        if found:
            method, found_port, payload = found
            self.c['port'] = found_port
            self.endpoint = f'http://127.0.0.1:{found_port}'
            atomic_json(self.marker, {'websocket': payload['webSocketDebuggerUrl'], 'profile': str(profile),
                                      'executable': str(executable), 'created': now(), 'storage_policy': 'S-drive-only/v1',
                                      'port': found_port, 'variant': variant['name'], 'detected_by': method})
            summary.update(ready=True, detected_by=method, port=found_port)
            return {'ready': True, 'detected_by': method, 'port': found_port, 'summary': summary}
        summary['assessment'] = diag_assess_edge(self.c['port'], profile, before_edge, process.poll(), attempt_stderr, report['policies'])
        summary['closed'] = self._close_attempt(process.pid, before_edge, profile)
        if recorder:
            recorder.event('edge', 'Attempt ' + variant['name'] + ' did not open a debug port', 'error', closed=summary['closed'])
        return {'ready': False, 'summary': summary}

    def _detect_endpoint(self, profile, new_edge_pids, configured):
        """Run every detection method at once. Only ports owned by Edge processes started since launch count."""
        probes = []
        if configured and self.c['port'] in {item['port'] for item in _listener_rows() if item['pid'] in new_edge_pids}:
            probes.append(('configured port owned by new Edge', self.c['port']))
        active = diag_try(diag_devtools_port, profile)
        if isinstance(active, dict) and str(active.get('port') or '').isdigit():
            probes.append(('DevToolsActivePort file in the dedicated profile', int(active['port'])))
        for item in _listener_rows():
            if item['pid'] in new_edge_pids and 1024 <= item['port'] <= 65535:
                probes.append(('listening port owned by new Edge', item['port']))
        unique = list(dict.fromkeys(probes))
        if not unique:
            return None
        with ThreadPoolExecutor(max_workers=len(unique)) as pool:
            futures = {pool.submit(get_cdp_version, f'http://127.0.0.1:{number}', 1.5): (method, number) for method, number in unique}
            for future in as_completed(futures):
                try:
                    payload = future.result()
                except Exception:
                    payload = None
                if payload:
                    method, number = futures[future]
                    return method, number, payload
        return None

    def _close_attempt(self, root, before_edge, profile):
        """Close only the Edge processes this attempt started (the launcher and its children)."""
        tree = edge_tree_pids(root, before_edge)
        if not tree:
            return {'terminated': {}, 'note': 'The launched Edge had already handed off; nothing of this attempt was closed.'}
        results = diag_terminate(tree)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (diag_edge_pids() & tree):
            time.sleep(.3)
        return {'terminated': results, 'still_running': sorted(diag_edge_pids() & tree)}

    async def __aenter__(self):
        load_playwright()
        self.manager = async_playwright()
        self.pw = await self.manager.start()
        await self.start()
        return self

    async def __aexit__(self, *args):
        # Disconnect transport only. Never close the browser, context or unrelated tabs.
        await _daily_review_stop_playwright_v1(self)

    async def connect(self):
        async with self.connection_lock:
            if self.mode == 'pipe':
                if self.browser and self.browser.is_connected():
                    return
                raise UncertainOperation('The dedicated Edge window was closed during the run. Check the Copilot chats before running again; uncertain sends are kept and never repeated.')
            if self.browser and self.browser.is_connected():
                return
            last = None
            for attempt in range(self.c['reconnect_attempts']):
                payload = await asyncio.to_thread(get_cdp_version, self.endpoint)
                marker = read_json(self.marker, {})
                if payload and payload.get('webSocketDebuggerUrl') != marker.get('websocket'):
                    raise UncertainOperation('Browser instance changed. Exact assigned targets require manual reconciliation.')
                if payload:
                    for endpoint in (payload['webSocketDebuggerUrl'], self.endpoint):
                        try:
                            self.browser = await self.pw.chromium.connect_over_cdp(endpoint, timeout=10000)
                            session = await self.browser.new_browser_cdp_session()
                            try:
                                await session.send('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(self.paths['downloads']), 'eventsEnabled': True})
                            finally:
                                await session.detach()
                            return
                        except Exception as exc:
                            last = exc
                await asyncio.sleep(.3 * (attempt + 1))
            raise UncertainOperation('Reconnection exhausted; assignments preserved: ' + repr(last))

    async def target(self, page):
        value = await page_target_id(page)
        if not value:
            raise UncertainOperation('Exact browser target identity unavailable')
        return value

    async def page(self, target):
        await self.connect()
        for context in self.browser.contexts:
            for page in context.pages:
                if not page.is_closed() and await self.target(page) == target:
                    if urlsplit(page.url).netloc != urlsplit(self.c['url']).netloc:
                        raise UncertainOperation('Assigned target left the configured Copilot origin')
                    return page
        raise UncertainOperation('Exact assigned target is unavailable: ' + str(target))

    async def read(self, target, operation):
        last = None
        for attempt in range(self.c['reconnect_attempts']):
            try:
                page = await self.page(target)
                return await asyncio.wait_for(operation(page), self.c['operation_timeout'])
            except UncertainOperation:
                raise
            except Exception as exc:
                last = exc
                await asyncio.sleep(.2)
                if not self.browser or not self.browser.is_connected():
                    await self.connect()
        raise UncertainOperation('Read/rebind failed without replaying any mutation: ' + repr(last))

    async def snapshot(self, page):
        return await page.evaluate(r'''s => {
            const visible=e=>!!(e&&(e.offsetWidth||e.offsetHeight||e.getClientRects().length));
            const norm=v=>String(v||'').replace(/\s+/g,' ').trim();
            const user=n=>!!n.closest(s.user);
            const userNodes=[...document.querySelectorAll(s.user)];
            const users=userNodes.filter(n=>!userNodes.some(other=>other!==n&&other.contains(n))).map(n=>norm(n.innerText||n.textContent));
            const candidates=[...document.querySelectorAll(s.assistant)].filter(n=>!user(n)&&!n.closest('[role="dialog"],[data-testid*="preview" i]'));
            const replies=candidates.filter(n=>!candidates.some(other=>other!==n&&other.contains(n))).map(n=>{
                const container=n.closest('[data-testid="copilot-message-div"],[data-testid="copilot-message-reply-div"],.fai-CopilotMessage,[data-testid="lastChatMessage"]')||n.parentElement;
                const actions=container?[...container.querySelectorAll('button')].filter(visible).map(b=>b.getAttribute('aria-label')||b.innerText||''):[];
                return {text:(n.innerText||n.textContent||'').trim(),html:n.outerHTML,
                    actions:actions.filter(v=>/copy|good response|bad response|thumbs|feedback/i.test(v)),
                    links:[...n.querySelectorAll('a[href]')].map(a=>({text:a.innerText,href:a.href}))};
            });
            return {url:location.href,users,replies,streaming:[...document.querySelectorAll(s.streaming)].some(visible)};
        }''', self.c['selectors'])

    async def upload_snapshot(self, page):
        state = await page.evaluate(r'''() => {
            const roots=new Set();
            for(const e of document.querySelectorAll('[aria-label="Attachments"] > [data-overflow-item="true"],[aria-label="Attachments"] > div[id^="SPO_"],button[aria-label^="Remove attachment "]'))
                roots.add(e.matches('[data-overflow-item="true"],div[id^="SPO_"]')?e:e.closest('[data-overflow-item="true"],div[id^="SPO_"]')||e);
            const names=[];
            for(const root of roots){
                const remove=root.matches('button[aria-label^="Remove attachment "]')?root:root.querySelector('button[aria-label^="Remove attachment "]');
                let name=remove?.getAttribute('aria-label')?.replace(/^Remove attachment /,'').trim();
                if(!name){const values=[root.getAttribute('aria-label'),root.getAttribute('title'),...[...root.querySelectorAll('[title]')].map(n=>n.getAttribute('title'))].filter(Boolean);name=values.find(v=>/^\d{3}__/.test(v));}
                if(name)names.push(name);
            }
            return {count:roots.size,names};
        }''')
        transfer = await attachment_transfer_snapshot(page, [])
        state.update(active=transfer.get('active', ['unknown']), sendEnabled=transfer.get('sendEnabled', False),
                     error=await upload_error_message(page), warning=await attachment_limit_warning(page))
        return state

    async def clean(self, page):
        snapshot = await self.snapshot(page)
        editor = await first_visible(editor_locators(page), 0)
        return bool(editor is not None and not (await editor_text(editor)).strip() and not snapshot['users']
                    and not snapshot['replies'] and not snapshot['streaming'] and not await stop_button_present(page)
                    and (await self.upload_snapshot(page))['count'] == 0)

    async def acquire(self, slot):
        async with self.slot_lock:
            await self.connect()
            saved = read_json(self.paths['home'] / 'slots.json', {})
            target = None
            for candidate in [saved.get(str(slot)), *self.c.get('prepared_targets', [])]:
                if not candidate or candidate in self.used:
                    continue
                try:
                    page = await self.page(candidate)
                    if await self.clean(page):
                        target = candidate
                        break
                except Exception:
                    continue
            if target is None:
                page = await self.browser.contexts[0].new_page()
                target = await self.target(page)
                self.used.add(target)
                saved[str(slot)] = target
                atomic_json(self.paths['home'] / 'slots.json', saved)
                await page.goto(self.c['url'], wait_until='domcontentloaded', timeout=60000)
            self.used.add(target)
            saved[str(slot)] = target
            atomic_json(self.paths['home'] / 'slots.json', saved)
            return target

    async def fresh(self, target):
        page = await self.page(target)
        # A background tab may not render, so Playwright cannot finish a click on it. Bring it forward first.
        await self.wake(target, foreground=True)
        deadline = time.monotonic() + self.c['login_timeout']
        while time.monotonic() < deadline:
            if await first_visible(editor_locators(page), 0) is not None:
                break
            await asyncio.sleep(.5)
        button = await first_visible([
            page.get_by_role('button', name=re.compile(r'^New chat(?:\s|\(|$)', re.I)),
            page.get_by_role('link', name=re.compile(r'^New chat(?:\s|\(|$)', re.I)),
            page.locator('[data-testid="new-chat-button"]')], 3000)
        if button is None:
            raise RuntimeError('New chat control unavailable. Sign in to Copilot in the dedicated Edge window; existing conversations were preserved.')
        clicked = False
        try:
            await button.click(timeout=15000)
            clicked = True
        except Exception:
            try:
                await button.dispatch_event('click')
                clicked = True
            except Exception:
                pass
        if not clicked:
            # Open the Copilot address again in this same dedicated tab: a clean conversation.
            await page.goto(self.c['url'], wait_until='domcontentloaded', timeout=60000)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if await self.clean(page):
                return
            await asyncio.sleep(.3)
        raise RuntimeError('Fresh conversation could not be proven; no evidence submitted')

    async def model(self, page):
        label = self.c.get('model', '')
        if not label:
            return
        switcher = await first_visible(model_switcher_locators(page), 2000)
        if switcher is None:
            raise RuntimeError('Configured model selector not found')
        if (await locator_description(switcher)).strip().casefold() == label.casefold():
            return
        await switcher.click(timeout=5000)
        option = await first_visible([page.get_by_role(role, name=label, exact=True) for role in ('menuitemradio', 'radio', 'option', 'menuitem')], 3000)
        if option is None:
            raise RuntimeError('Configured exact model label unavailable: ' + label)
        if await option.get_attribute('aria-checked') == 'true':
            await page.keyboard.press('Escape'); return
        await option.click(timeout=5000)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if await option.count() and await option.get_attribute('aria-checked') == 'true':
                return
            switcher = await first_visible(model_switcher_locators(page), 0)
            if switcher and (await locator_description(switcher)).strip().casefold() == label.casefold():
                return
            await asyncio.sleep(.1)
        raise RuntimeError('Configured model selection not confirmed; no send performed')

    async def prepare(self, target, paths, message):
        page = await self.page(target)
        if not await self.clean(page):
            raise RuntimeError('Composer is not a proven fresh conversation')
        await self.model(page)
        async with self.upload_lock:
            # Assign FileList once. No uncertain upload replay.
            try:
                await asyncio.wait_for(browser_local_set_input_files_bulk(page, paths), self.c['operation_timeout'])
            except Exception as exc:
                raise UncertainOperation('Upload assignment uncertain; no replay: ' + repr(exc)) from exc
            await add_text_to_editor(page, message, 10000)
            deadline = time.monotonic() + self.c['upload_timeout']
            stable_at = None
            while time.monotonic() < deadline:
                state = await self.read(target, self.upload_snapshot)
                if state.get('error') or state.get('warning'):
                    raise RuntimeError('Upload error/limitation: ' + json.dumps(state))
                if exact_upload_ready(state, [path.name for path in paths]):
                    stable_at = stable_at or time.monotonic()
                    if time.monotonic() - stable_at >= 2:
                        return
                else:
                    stable_at = None
                await self.read(target, background_wake_page)
                await asyncio.sleep(.3)
            raise RuntimeError('Partial/unverified uploads; no files omitted and no send performed')

    async def verify_pre_send(self, target, paths, message):
        page = await self.page(target)
        if not exact_upload_ready(await self.upload_snapshot(page), [path.name for path in paths]):
            raise RuntimeError('Attachment identities/readiness changed before send')
        editor = await first_visible(editor_locators(page), 1000)
        if editor is None or (await editor_text(editor)).replace('\r\n', '\n').strip() != message.strip():
            raise RuntimeError('Full composer message verification failed')
        snapshot = await self.snapshot(page)
        if snapshot['users'] or snapshot['replies'] or snapshot['streaming'] or await stop_button_present(page):
            raise UncertainOperation('Conversation is no longer fresh; send prohibited')

    async def send_once(self, target):
        page = await self.page(target)
        button = await first_visible(send_button_locators(page), 2000)
        if button is None:
            raise UncertainOperation('Send intent persisted but Send unavailable; reconcile without replay')
        label = (await button.get_attribute('aria-label') or '').lower()
        if not (label == 'send' or label.startswith('send ')) or 'stop' in label or await stop_button_present(page):
            raise UncertainOperation('Send/Stop guard failed; no repeated click')
        try:
            await button.click(timeout=5000)
        except Exception as exc:
            raise UncertainOperation('Send outcome uncertain: ' + repr(exc)) from exc

    async def observe(self, target, assignment, message):
        async def operation(page):
            snapshot = await self.snapshot(page)
            snapshot['stop'] = await stop_button_present(page)
            return snapshot
        snapshot = await self.read(target, operation)
        normalize = lambda text: re.sub(r'\s+', ' ', text).strip()
        snapshot['user_proven'] = any(normalize(message) == text for text in snapshot['users'])
        if snapshot['user_proven'] and len(snapshot['users']) != 1:
            raise UncertainOperation('Additional user messages appeared in assigned conversation; response not accepted')
        expected = assignment.get('conversation_url', '')
        if expected and expected != self.c['url'] and snapshot['url'] != expected:
            raise UncertainOperation('Conversation address changed; stale response rejected')
        return snapshot

    async def wake(self, target, foreground=False):
        await self.read(target, background_wake_page)
        if foreground:
            # read() passes only the page; this activation also needs a tab number and a reason.
            await self.read(target, lambda page: activate_page_like_manual_selection(page, 0, 'foreground wake', verbose=False))

    async def diagnostics(self, target, directory, error):
        directory = Path(directory)
        atomic_json(directory / 'error.json', {'at': now(), 'error': repr(error), 'target_id': target})
        try:
            page = await self.page(target)
            atomic_json(directory / 'dom-state.json', await self.snapshot(page))
            write_text(directory / 'page.html', await page.content())
            await page.screenshot(path=str(directory / 'page.png'))
        except Exception as exc:
            atomic_json(directory / 'capture-error.json', {'error': repr(exc)})

# ---------- Queue, immutable staging and one-send lifecycle ----------
def build_message(base, assignment):
    keys = ('instruction_id', 'account_number', 'run_id', 'assignment_id', 'evidence_fingerprint', 'resources_fingerprint')
    block = {key: assignment[key] for key in keys}
    block.update(attached_files=assignment['attachment_names'], evidence_manifest=assignment['manifest'])
    return base + '\n\n---\nCASE_INFORMATION\n' + json.dumps(block, ensure_ascii=False, indent=2) + '\nEND_CASE_INFORMATION'


def stage_case(record, assignment, resources):
    token = assignment['assignment_id']
    if re.fullmatch('[a-f0-9]{32}', token) is None:
        raise ValueError('Invalid staging assignment identifier')
    directory = short_stage_root() / token
    require_s(directory, 'Short upload staging')
    if len(str(directory)) > 180:
        raise ValueError('Staging path exceeds browser-safe budget')
    os.makedirs(long_io_path(directory), exist_ok=False)
    assignment['stage_dir'] = str(directory)
    entries = [{'path': resources['instructions'], 'relative_path': '[review instructions]', 'sha256': resources['hashes']['instructions']}] + record['manifest']
    if len(entries) > 20:
        raise ValueError('Full evidence plus instructions exceeds 20 attachments; no evidence selected out')
    files, manifest = [], []
    for index, item in enumerate(entries):
        original = Path(display_path(item['path']))
        suffix = original.suffix.lower()
        if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
            raise ValueError('Unsafe attachment extension: ' + suffix)
        name = f'{index:03d}__' + ('instructions' if index == 0 else 'evidence') + suffix
        target = directory / name
        before = os.stat(long_io_path(original))
        with open(long_io_path(original), 'rb') as source, open(long_io_path(target), 'xb') as destination:
            shutil.copyfileobj(source, destination, 1024 * 1024)
        after = os.stat(long_io_path(original))
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or evidence_hash(target) != item['sha256']:
            raise RuntimeError('Evidence changed while staging: ' + str(original))
        files.append(target)
        manifest.append({'attachment_name': name, 'original_path': item['relative_path'], 'original_name': original.name,
                         'sha256': item['sha256'], 'size': before.st_size})
    assignment['attachment_names'], assignment['manifest'] = [path.name for path in files], manifest
    atomic_json(directory / 'staging_manifest.json', {'assignment_id': token, 'instruction_id': record['instruction_id'], 'files': manifest})
    return files


def cleanup_stage(assignment):
    value = assignment.get('stage_dir')
    if not value:
        return
    directory = require_s(value, 'Owned staging cleanup')
    root = require_s(short_stage_root(), 'Owned staging root')
    if directory.parent != root or re.fullmatch('[a-f0-9]{32}', directory.name) is None:
        raise ValueError('Refusing cleanup outside exact owned assignment directory')
    if os.path.isdir(long_io_path(directory)):
        shutil.rmtree(long_io_path(directory))


class Runner:
    def __init__(self, config, paths, resources, root, owner, store, records, issues, run_dir, run_id, browser):
        self.c, self.paths, self.res, self.root, self.owner = config, paths, resources, root, owner
        self.store, self.records, self.issues, self.run_dir, self.run_id, self.browser = store, records, issues, run_dir, run_id, browser
        self.queue = asyncio.Queue()
        self.targets = {}
        self.summary_lock = asyncio.Lock()

    def report(self):
        master = {'run_id': self.run_id, 'source_root': str(self.root), 'resources': self.res,
                  'coordination_dir': str(self.store.root), 'updated': now(), 'cases': self.records, 'discovery_issues': self.issues}
        atomic_json(self.run_dir / 'master_cases.json', master)
        counts = Counter(record['state'] for record in self.records)
        lines = [f'# Daily case-review run {self.run_id}', '', f'Cases: {len(self.records)}; discovery issues: {len(self.issues)}',
                 'Completion mode: ' + self.res['completion_mode'], '']
        lines.extend(f'- {key}: {value}' for key, value in sorted(counts.items()))
        lines += ['', '## Case outcomes']
        for record in self.records:
            lines.append(f'- {record.get("instruction_id") or record["folder_name"]}  {record.get("account_number") or ""}  {record["state"]}')
            for error in record.get('validation', []):
                lines.append('  - ' + error)
            if record.get('error'):
                lines.append('  - ' + record['error'])
            if record.get('assignment', {}).get('conversation_url'):
                lines.append('  - Conversation: ' + record['assignment']['conversation_url'])
        lines += ['', '## Discovery issues', json.dumps(self.issues, ensure_ascii=False, indent=2), '',
                  'UI completion means a terminal response was captured, not that its business finding was independently verified.',
                  'Generated output links are references only unless a local download is explicitly recorded.',
                  'No stale claim expiry, automatic resend, force unlock or outcome-driven retry.']
        write_text(self.run_dir / 'summary.md', '\n'.join(lines))

    def persist(self, record):
        if record.get('instruction_id') and record.get('claim_owner') == self.owner:
            self.store.save(record)
        self.report()

    def reconcile(self):
        for record in self.records:
            cid = record.get('instruction_id')
            if not cid or record['validation']:
                continue
            previous = self.store.get(cid)
            if previous:
                if previous.get('evidence_fingerprint') != record['evidence_fingerprint'] or previous.get('account_number') != record['account_number']:
                    transition(record, 'manual reconciliation required', error='Previously claimed case has different evidence/account. Existing record preserved.')
                    continue
                record.update(copy.deepcopy(previous))
                if record.get('state') == 'completed':
                    # Never silently repeat a completed review because Markdown changed.
                    if record.get('resources_fingerprint') != self.res['fingerprint']:
                        record['current_resource_note'] = 'Completed with different prompt resources; not automatically resubmitted'
                    continue
            claim = self.store.claim(cid)
            if not claim:
                transition(record, 'manual reconciliation required', error='Claim belongs to another controller; no takeover attempted')
                continue
            record['claim_owner'] = self.owner
            if previous:
                assignment = record.get('assignment', {})
                if assignment.get('send_intent') or record.get('state') in {'submitted', 'awaiting response'}:
                    transition(record, 'manual reconciliation required', error='Existing send intent/submission preserved. Observation-only recovery; never resend.')
                    self.queue.put_nowait(record)
                    self.persist(record)
                    continue
                if record.get('resources_fingerprint') not in (None, self.res['fingerprint']):
                    transition(record, 'manual reconciliation required', error='Prompt resources changed after prior preparation; previous assignment preserved')
                    self.persist(record)
                    continue
                if record.get('state') in {'blocked', 'manual reconciliation required'}:
                    continue
                # No uncertain mutation may be replayed after a crash during preparation.
                if record.get('state') in {'preparing', 'uploading', 'ready to submit'}:
                    transition(record, 'manual reconciliation required', error='Interrupted preparation requires inspection; no upload replay')
                    self.persist(record)
                    continue
            record['resources_fingerprint'] = self.res['fingerprint']
            self.queue.put_nowait(record)
            self.persist(record)
        self.report()

    async def monitor(self, record):
        assignment = record['assignment']
        target = assignment['target_id']
        self.browser.used.add(target)
        message = assignment.get('message')
        if not message:
            raise UncertainOperation('Saved assignment has no exact composer text. Inspect existing conversation; no resend.')
        contract = assignment.get('contract')
        mode = assignment.get('completion_mode', 'contract' if contract else 'ui')
        deadline = time.monotonic() + self.c['response_timeout']
        last_hash, stable_at, last_error = None, None, None
        last_wake, foreground = 0, False
        while time.monotonic() < deadline:
            snapshot = await self.browser.observe(target, assignment, message)
            if snapshot['user_proven']:
                if not assignment.get('user_proven'):
                    assignment['user_proven'] = True
                    assignment['conversation_url'] = snapshot['url']
                    transition(record, 'awaiting response')
                    self.persist(record)
                elif assignment.get('conversation_url') != snapshot['url']:
                    raise UncertainOperation('Conversation URL changed after exact submission proof')
            replies = snapshot['replies']
            if snapshot['user_proven'] and replies and not snapshot['stop'] and not snapshot['streaming']:
                reply = replies[-1]
                text = reply['text']
                hashed = hashlib.sha256(text.encode()).hexdigest()
                if text and hashed == last_hash:
                    stable_at = stable_at or time.monotonic()
                else:
                    last_hash, stable_at = hashed, time.monotonic()
                terminal_actions = bool(reply.get('actions'))
                if text and terminal_actions and time.monotonic() - stable_at >= self.c['stable_seconds']:
                    result = None
                    if mode == 'contract':
                        try:
                            result = parse_completion(text, assignment, contract)
                        except Exception as exc:
                            last_error = repr(exc)
                            # A stable malformed terminal result is a technical failure,
                            # not a reason to regenerate a more favourable audit finding.
                            raise UncertainOperation('Terminal completion contract invalid: ' + last_error) from exc
                    output = self.run_dir / 'responses' / assignment['assignment_id']
                    write_text(output / 'response.md', text)
                    write_text(output / 'response.html', reply['html'])
                    atomic_json(output / 'observation.json', {'at': now(), 'target_id': target, 'url': snapshot['url'],
                                'response_sha256': hashed, 'mode': mode, 'terminal_actions': reply['actions'],
                                'links': reply['links'], 'user_message_sha256': hashlib.sha256(message.encode()).hexdigest()})
                    if result is not None:
                        atomic_json(output / 'completion.json', result)
                        record['review_finding'] = result['review_finding']
                        record['limitations'], record['outputs'], record['exposure'] = result['limitations'], result['outputs'], result['exposure']
                    else:
                        record['review_finding'] = None
                        record['outputs'] = reply['links']
                        record['limitations'] = ['UI-terminal response captured; substantive findings remain in response.md and are not parsed/inferred']
                        record['exposure'] = 'not independently established'
                    transition(record, 'completed', response_dir=str(output), completion_mode=mode, error=None)
                    self.persist(record)
                    cleanup_stage(assignment)
                    return
            else:
                last_hash, stable_at = None, None
            if time.monotonic() - last_wake >= 10:
                await self.browser.wake(target, foreground=False)
                last_wake = time.monotonic()
            if not foreground and deadline - time.monotonic() < self.c['response_timeout'] * .75:
                await self.browser.wake(target, foreground=True)
                foreground = True
            await asyncio.sleep(self.c['poll_seconds'])
        raise UncertainOperation('Response not conclusively complete before observation deadline. No resend. ' + str(last_error or ''))

    async def process(self, record, slot):
        if record.get('assignment', {}).get('send_intent') or record.get('state') in UNCERTAIN:
            await self.monitor(record)
            return
        attempts = int(record.get('technical_attempts', 0))
        while attempts < self.c['technical_attempts']:
            attempts += 1
            record['technical_attempts'] = attempts
            target = self.targets.get(slot)
            if target is None:
                target = await self.browser.acquire(slot)
                self.targets[slot] = target
            assignment = {'assignment_id': uuid.uuid4().hex, 'run_id': self.run_id, 'instruction_id': record['instruction_id'],
                          'account_number': record['account_number'], 'evidence_fingerprint': record['evidence_fingerprint'],
                          'resources_fingerprint': self.res['fingerprint'], 'target_id': target, 'slot': slot,
                          'created': now(), 'send_intent': False, 'completion_mode': self.res['completion_mode'],
                          'contract': self.res['contract'] if self.res['completion_mode'] == 'contract' else None}
            record['assignment'] = assignment
            transition(record, 'preparing'); self.persist(record)
            try:
                if not evidence_unchanged(record, self.c):
                    raise RuntimeError('Evidence changed after frozen discovery; case blocked')
                for key in ('instructions', 'base_message'):
                    if evidence_hash(self.res[key]) != self.res['hashes'][key]:
                        raise RuntimeError('Markdown changed during this run; start a new run after inspecting any submitted assignments')
                files = stage_case(record, assignment, self.res)
                assignment['message'] = build_message(self.res['base_text'], assignment)
                self.persist(record)
                await self.browser.fresh(target)
                transition(record, 'uploading'); self.persist(record)
                await self.browser.prepare(target, files, assignment['message'])
                transition(record, 'ready to submit'); self.persist(record)
                await self.browser.verify_pre_send(target, files, assignment['message'])
                if not evidence_unchanged(record, self.c):
                    raise RuntimeError('Evidence changed before send')
                for key in ('instructions', 'base_message'):
                    if evidence_hash(self.res[key]) != self.res['hashes'][key]:
                        raise RuntimeError('Markdown changed before send')
                # Persist intent durably BEFORE the sole Send click.
                assignment['send_intent'] = True
                assignment['send_intent_at'] = now()
                transition(record, 'submitted'); self.persist(record)
                await self.browser.send_once(target)
                await self.monitor(record)
                return
            except Exception as exc:
                print("CASE BLOCK DIAGNOSTIC: " + type(exc).__name__ + ": " + str(exc), flush=True)
                __import__("traceback").print_exc()
                await self.browser.diagnostics(target, self.run_dir / 'diagnostics' / assignment['assignment_id'], exc)
                if assignment.get('send_intent') or isinstance(exc, UncertainOperation):
                    transition(record, 'manual reconciliation required', error=repr(exc))
                    self.persist(record)
                    # Uncertain upload/preparation never reuses this target for a new case.
                    self.targets.pop(slot, None)
                    return
                # Retry only pre-send technical preparation, in a proven fresh chat. The failed tab may still
                # hold attachments, so the retry takes another tab that proves clean.
                self.targets.pop(slot, None)
                if attempts >= self.c['technical_attempts']:
                    transition(record, 'blocked', error=repr(exc))
                    self.persist(record)
                    cleanup_stage(assignment)
                    return
                transition(record, 'retryable failure', error=repr(exc)); self.persist(record)
                cleanup_stage(assignment)
        transition(record, 'blocked', error='Pre-send technical attempt ceiling reached'); self.persist(record)

    async def worker(self, slot):
        while True:
            try:
                record = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                print(f'[{slot + 1}] {record["instruction_id"]} {record["account_number"]}: starting', flush=True)
                await self.process(record, slot)
            except Exception as exc:
                transition(record, 'manual reconciliation required', error=repr(exc))
                self.persist(record)
                self.targets.pop(slot, None)
            finally:
                print(f'[{slot + 1}] {record["instruction_id"]}: {record["state"]}', flush=True)
                self.queue.task_done()

    async def run(self):
        self.reconcile()
        if self.queue.empty():
            print('No unclaimed ready cases or recoverable submissions remain. See summary.')
            return
        # Reserve all observation-only targets before any slot can create a new chat.
        for record in self.records:
            assignment = record.get('assignment', {})
            if assignment.get('target_id'):
                self.browser.used.add(assignment['target_id'])
        await asyncio.gather(*(self.worker(slot) for slot in range(min(self.c['tabs'], self.queue.qsize()))))
        self.report()

# ---------- Single-command entry point ----------
def parser():
    p = argparse.ArgumentParser(description='Review all prepared instruction folders using installed Edge. Default action sends real evidence.')
    p.add_argument('folder', nargs='?', help='Prepared case root, or drag a folder onto the CMD')
    p.add_argument('--source-root', help='Alternative named form of folder')
    p.add_argument('--instructions', help='Instructions Markdown to attach unchanged')
    p.add_argument('--base-message', help='Markdown text to put in the composer')
    p.add_argument('--tabs', type=int, default=6, choices=range(1, 7))
    p.add_argument('--url', help='Copilot chat URL, otherwise reuse saved URL')
    p.add_argument('--port', type=int, help='Dedicated Edge debugging port, otherwise reuse saved port')
    p.add_argument('--model', help='Exact model label, otherwise preserve the current UI selection')
    p.add_argument('--browser-path', help='Existing msedge.exe only')
    p.add_argument('--completion', choices=('auto', 'contract', 'ui'), default='auto')
    p.add_argument('--discover-only', action='store_true', help='Validate and report without sending or claiming cases')
    p.add_argument('--diagnose', action='store_true', help='Normal run (real submissions) recorded in full; writes an INTERNAL and an EXTERNAL (sanitized) report')
    p.add_argument('--edge-original-env', action='store_true', help='Test only: start Edge with your normal Windows user folders instead of the S: copies')
    p.add_argument('--setup', action='store_true', help='Check/install missing S: Python dependencies, no browser download')
    return p


def configure_simple(args, paths):
    saved = read_json(paths['home'] / 'settings.json', {})
    old = {**saved, **saved.get('settings', {})}
    config = copy.deepcopy(DEFAULTS)
    # Reuse operational browser/coordination settings, not old prompt paths.
    for key in ('url', 'port', 'browser_path', 'model', 'folder_pattern', 'audit_pattern', 'snapshot_pattern',
                'account_json_pointer', 'max_file_bytes', 'response_timeout', 'upload_timeout', 'contract', 'selectors'):
        if key in old:
            config[key] = old[key]
    for key in ('url', 'port', 'browser_path', 'model'):
        value = getattr(args, key, None)
        if value is not None:
            config[key] = value
    config['tabs'] = args.tabs
    config['edge_original_env'] = bool(args.edge_original_env)
    config['profile_dir'] = str(paths['profile'])
    if not 1024 <= config['port'] <= 65535:
        raise ValueError('Debugging port must be between 1024 and 65535')
    if urlsplit(config['url']).scheme != 'https' or not urlsplit(config['url']).netloc:
        raise ValueError('Copilot URL must be an absolute HTTPS URL')
    # Only known selector keys are merged; no old module is imported.
    config['selectors'] = {**DEFAULTS['selectors'], **config.get('selectors', {})}
    value = args.source_root or args.folder
    if not value:
        value = input('Paste the folder containing ALL instruction case folders: ').strip()
    root = require_s(value, 'Prepared case root')
    if not os.path.isdir(long_io_path(root)):
        raise NotADirectoryError(str(root))
    instructions = choose_markdown('instructions', args.instructions)
    base = choose_markdown('base message', args.base_message, instructions)
    resources = load_resources(instructions, base, args.completion, config.get('model', ''))
    # Keep the same shared namespace for the same canonical root as the old runtime.
    canonical = str(root.resolve()).casefold()
    legacy = read_json(PACKAGE / 'review_config.json', {})
    previous_root = old.get('source_root') or legacy.get('source_root')
    previous_coordination = old.get('coordination_dir') or legacy.get('coordination_dir')
    same_root = previous_root and str(require_s(previous_root, 'Previous source root').resolve()).casefold() == canonical
    coordination = require_s(previous_coordination if same_root and previous_coordination else paths['coordination'] / hashlib.sha256(canonical.encode()).hexdigest(), 'Shared coordination')
    config.update(source_root=str(root), coordination_dir=str(coordination), instructions=str(instructions), base_message=str(base))
    owner = saved.get('owner') or identity_key()
    atomic_json(paths['home'] / 'settings.json', {'owner': owner, 'settings': config, 'storage_policy': 'S-drive-only/v1'})
    return config, resources, root, coordination


async def execute_simple(args, paths):
    config, resources, root, coordination = configure_simple(args, paths)
    owner = read_json(paths['home'] / 'settings.json', {}).get('owner') or identity_key()
    store = SharedStore(coordination, owner)
    run_id = 'run-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
    run_dir = paths['runs'] / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    print('Instructions attached: ' + resources['instructions'])
    print('Base message in composer: ' + resources['base_message'])
    print('Source root: ' + str(root))
    print('Run summary: ' + str(run_dir / 'summary.md'))
    print('Discovering every case; .edge-debug-9223 is always excluded.', flush=True)
    records, issues = discover_prepared_cases(root, config, excluded=(RUNTIME_ROOT,))
    if _RECORDER:
        _RECORDER.learn_cases(records)
        _RECORDER.event('discovery', f'{len(records)} cases found, {len(issues)} discovery issues')
    atomic_json(run_dir / 'frozen_discovery.json', {'cases': records, 'issues': issues, 'created': now(), 'resources': resources})
    browser = EdgeBrowser(config, paths)
    browser.startup_store = store
    runner = Runner(config, paths, resources, root, owner, store, records, issues, run_dir, run_id, browser)
    runner.report()
    ready = sum(record['state'] == 'ready' for record in records)
    print(f'Cases: {len(records)}; ready: {ready}; discovery issues: {len(issues)}', flush=True)
    if args.discover_only:
        print('Discovery only. No cases claimed or submitted.')
        return 0 if ready == len(records) and not issues else 2
    if not ready:
        print('No eligible cases. Review the summary; nothing submitted.')
        return 2
    print('REAL REVIEW: all eligible cases will be sent, one case per chat. Keep the dedicated Edge window open.')
    print('Sign in there if needed. No old browser session will be copied.', flush=True)
    async with browser:
        # Only the clean landing page from this verified dedicated session may be
        # adopted. No conversation tab is selected by index or by title.
        prepared = []
        deadline = time.monotonic() + config['login_timeout']
        while time.monotonic() < deadline and not prepared:
            for context in browser.browser.contexts:
                for page in context.pages:
                    if urlsplit(page.url).netloc == urlsplit(config['url']).netloc:
                        try:
                            if await browser.clean(page):
                                prepared.append(await browser.target(page))
                        except Exception:
                            pass
            if not prepared:
                # Existing signed-in session may have conversations only. Create
                # one owned landing page once, then observe it without replay.
                if not getattr(browser, '_landing_created', False):
                    browser._landing_created = True
                    landing = await browser.browser.contexts[0].new_page()
                    await landing.goto(config['url'], wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(.5)
        if not prepared:
            raise RuntimeError('No clean signed-in Copilot composer available. No cases submitted.')
        config['prepared_targets'] = prepared
        await runner.run()
    print('Finished. Summary: ' + str(run_dir / 'summary.md'))
    return 0 if all(record['state'] == 'completed' for record in records) and not issues else 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    code = _main(argv)
    if _RECORDER is not None:
        _RECORDER.finish(code)
    return code


def _main(argv):
    # --help must work without S: or dependency imports.
    if '-h' in argv or '--help' in argv:
        parser().print_help(); return 0
    try:
        paths = initialise()
        if argv and argv[0] == '--pip-internal':
            sys.argv = ['pip', *argv[1:]]
            runpy.run_module('pip', run_name='__main__')
            return 0
        if argv and argv[0] == '--verify-dependencies':
            for name in ('playwright.async_api', 'pypdf', 'msoffcrypto', 'PIL.Image', 'olefile', 'greenlet', 'pyee', 'cryptography'):
                module = importlib.import_module(name)
                require_s(module.__file__, 'Dependency ' + name)
            print('S: dependency imports verified.')
            return 0
        args = parser().parse_args(argv)
        if args.diagnose:
            begin_diagnostics(paths, argv)
        with controller_lock(paths['home'] / 'controller.lock'):
            ensure_dependencies(paths, setup=args.setup)
            if args.setup:
                print('Installed Edge: ' + str(installed_edge(prompt=True)))
                return 0
            return asyncio.run(execute_simple(args, paths))
    except KeyboardInterrupt:
        print('\nStopped. Existing send intents remain durable; restart never resends an uncertain submission.', file=sys.stderr)
        return 130
    except Exception as exc:
        details = traceback.format_exc()
        print('ERROR: ' + str(exc), file=sys.stderr)
        print(details, file=sys.stderr)
        if _RECORDER is not None:
            _RECORDER.failure(exc, details)
        try:
            if _LAYOUT:
                with open(_LAYOUT['logs'] / 'failures.log', 'a', encoding='utf-8') as stream:
                    stream.write(now() + '\n' + details + '\n')
        except Exception:
            pass
        print('No administrator elevation, browser download or personal-drive storage fallback was attempted.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
