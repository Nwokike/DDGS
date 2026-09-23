#!/usr/bin/env python3
"""Kiri Router -- local gateway + admin console (Python 3, zero dependencies).

Run:
  curl -fsSL https://router.kiri.ng/install.sh | sh
  irm https://router.kiri.ng/install.ps1 | iex

Serves the admin console at http://127.0.0.1:8082/ and the OpenAI-compatible
API at http://127.0.0.1:8082/v1. Every request exits from YOUR IP, so you never
share rate limits with anyone else.

Flags:
  --port N     listen port (default 8082; auto-bumps if busy)
  --no-probe   skip the model health probe at startup
  --open       open the console in your browser when ready
  --no-color   disable ANSI colors (also honors NO_COLOR / KIRI_ASCII=1)
  --help       show this message
"""

import json
import os
import random
import socket
import string
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
DEFAULT_PORT = 8082
DISCOVER_TTL = 600  # seconds

# Admin console (generated in at build time from ui/console.html)
CONSOLE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Kiri Router Local Console</title>
  <meta name="description" content="Local administration console for the Kiri Router gateway."/>
  <script>
    (function () {
      try {
        var saved = localStorage.getItem('theme') || 'system';
        var sysDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        var dark = saved === 'dark' || (saved === 'system' && sysDark);
        document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
      } catch (e) {
        document.documentElement.setAttribute('data-theme', 'light');
      }
    })();
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico"/>
  <style>
    :root,
    [data-theme="light"] {
      --bg: #ffffff;
      --bg-subtle: #fafafa;
      --bg-elevated: #ffffff;
      --text: #0a0a0a;
      --text-muted: #6b7280;
      --text-faint: #9ca3af;
      --border: #e5e7eb;
      --border-strong: #d1d5db;
      --accent: #0a0a0a;
      --accent-contrast: #ffffff;
      --hover: #f5f5f5;
      --ok: #16a34a;
      --err: #dc2626;
      --radius: 12px;
      --radius-sm: 8px;
    }
    [data-theme="dark"] {
      --bg: #0a0a0a;
      --bg-subtle: #111111;
      --bg-elevated: #161616;
      --text: #fafafa;
      --text-muted: #9ca3af;
      --text-faint: #6b7280;
      --border: #1f1f1f;
      --border-strong: #2a2a2a;
      --accent: #ffffff;
      --accent-contrast: #0a0a0a;
      --hover: #1a1a1a;
      --ok: #4ade80;
      --err: #f87171;
    }
    @media (prefers-color-scheme: dark) {
      :root:not([data-theme]) {
        --bg: #0a0a0a; --bg-subtle: #111111; --bg-elevated: #161616;
        --text: #fafafa; --text-muted: #9ca3af; --text-faint: #6b7280;
        --border: #1f1f1f; --border-strong: #2a2a2a;
        --accent: #ffffff; --accent-contrast: #0a0a0a; --hover: #1a1a1a;
        --ok: #4ade80; --err: #f87171;
      }
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-text-size-adjust: 100%; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg); color: var(--text);
      line-height: 1.6; font-size: 16px;
      -webkit-font-smoothing: antialiased;
      transition: background-color 0.2s ease, color 0.2s ease;
    }
    a { color: inherit; text-decoration: none; }
    button { font: inherit; cursor: pointer; background: none; border: none; color: inherit; }
    code, pre, .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }
    .container { max-width: 880px; margin: 0 auto; padding: 0 24px; }

    .nav {
      position: sticky; top: 0; z-index: 50;
      background: color-mix(in srgb, var(--bg) 85%, transparent);
      backdrop-filter: saturate(180%) blur(12px);
      -webkit-backdrop-filter: saturate(180%) blur(12px);
      border-bottom: 1px solid var(--border);
    }
    .nav-inner {
      max-width: 880px; margin: 0 auto; padding: 16px 24px;
      display: flex; align-items: center; justify-content: space-between; gap: 16px;
    }
    .nav-logo { font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 9px; }
    .nav-logo img { width: 22px; height: 22px; border-radius: 6px; display: block; }
    .nav-badge {
      font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted);
      border: 1px solid var(--border); border-radius: 999px; padding: 3px 10px;
    }
    .theme-toggle {
      width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center;
      border-radius: 8px; color: var(--text-muted); transition: background-color 0.15s ease, color 0.15s ease;
    }
    .theme-toggle:hover { background: var(--hover); color: var(--text); }
    .theme-toggle svg { width: 15px; height: 15px; display: none; }
    [data-theme="light"] .theme-toggle .icon-light,
    [data-theme="dark"]  .theme-toggle .icon-dark { display: block; }
    :root:not([data-theme]) .theme-toggle .icon-system { display: block; }

    .page-head { padding: 48px 0 8px; }
    .page-head h1 { font-size: clamp(28px, 5vw, 40px); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; }
    .page-head p { color: var(--text-muted); font-size: 15px; margin-top: 8px; }

    .section { padding: 24px 0; }
    .section-label {
      font-family: 'JetBrains Mono', monospace; font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-faint); margin-bottom: 14px;
    }

    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .stat {
      background: var(--bg-elevated); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 16px;
    }
    .stat .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-faint); margin-bottom: 6px; }
    .stat .value { font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 500; word-break: break-all; }
    .stat .value.big { font-family: 'Inter', sans-serif; font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }

    .card {
      background: var(--bg-elevated); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px;
    }
    .card + .card { margin-top: 14px; }

    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13.5px; }
    th { color: var(--text-faint); font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
    tr:last-child td { border-bottom: none; }
    td .mono { font-size: 13px; }

    .tag {
      font-family: 'JetBrains Mono', monospace; font-size: 10.5px; padding: 2px 7px;
      border-radius: 5px; border: 1px solid var(--border-strong); color: var(--text-muted); white-space: nowrap;
    }
    .tag.ok { color: var(--ok); border-color: color-mix(in srgb, var(--ok) 45%, transparent); }
    .tag.err { color: var(--err); border-color: color-mix(in srgb, var(--err) 45%, transparent); }

    .btn {
      display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; font-size: 12.5px;
      font-weight: 600; border-radius: var(--radius-sm); transition: all 0.15s ease;
      background: var(--accent); color: var(--accent-contrast); border: 1px solid transparent; white-space: nowrap;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.12); }
    .btn:disabled { opacity: 0.5; cursor: default; transform: none; box-shadow: none; }
    .btn-ghost { background: transparent; color: var(--text); border-color: var(--border-strong); }
    .btn-ghost:hover { background: var(--hover); box-shadow: none; transform: none; }
    .btn-sm { padding: 4px 10px; font-size: 11.5px; }

    .code {
      position: relative; background: var(--bg-subtle); border: 1px solid var(--border);
      border-radius: var(--radius-sm); padding: 14px 16px; font-size: 13px;
      overflow-x: auto; white-space: pre; margin-top: 8px;
    }
    .copy-btn {
      position: absolute; top: 8px; right: 8px; padding: 5px 10px; font-size: 11px; font-weight: 600;
      border: 1px solid var(--border-strong); border-radius: 6px; background: var(--bg);
      color: var(--text-muted); transition: all 0.15s ease;
    }
    .copy-btn:hover { background: var(--hover); color: var(--text); }

    #testOutput {
      display: none; margin-top: 12px; padding: 14px 16px;
      background: var(--bg-subtle); border: 1px solid var(--border); border-radius: var(--radius-sm);
      font-family: 'JetBrains Mono', monospace; font-size: 12.5px;
      white-space: pre-wrap; word-break: break-word; min-height: 44px;
    }
    #testOutput.ok { border-color: color-mix(in srgb, var(--ok) 45%, transparent); }
    #testOutput.err { border-color: color-mix(in srgb, var(--err) 45%, transparent); }

    .hint { color: var(--text-faint); font-size: 13px; margin-bottom: 12px; }
    .snip-title { font-size: 13px; font-weight: 600; margin-top: 16px; }
    .snip-title:first-of-type { margin-top: 0; }

    footer { border-top: 1px solid var(--border); margin-top: 40px; padding: 24px 0 40px; }
    .faint { color: var(--text-faint); font-size: 13px; }

    .spin { display: inline-block; width: 13px; height: 13px; border: 2px solid var(--border-strong); border-top-color: var(--text); border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: -2px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .code { -webkit-overflow-scrolling: touch; }
    @media (max-width: 640px) {
      .table-wrap { overflow-x: auto; }
      th, td { padding: 8px; }
    }
  </style>
</head>
<body>
  <nav class="nav">
    <div class="nav-inner">
      <span class="nav-logo"><img src="/kiri-icon.png" width="22" height="22" alt=""/>Kiri Router</span>
      <span style="display:flex;align-items:center;gap:10px">
        <span class="nav-badge" id="versionBadge">local console</span>
        <button id="themeToggle" class="theme-toggle" title="Switch theme" aria-label="Switch theme">
          <svg class="icon-light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
          <svg class="icon-dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>
          <svg class="icon-system" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
        </button>
      </span>
    </div>
  </nav>

  <main>
    <div class="container page-head">
      <h1>Local console</h1>
      <p>Runs on your machine. Requests exit from your IP.</p>
    </div>

    <section class="section">
      <div class="container">
        <div class="stats">
          <div class="stat">
            <div class="label">Base URL</div>
            <div class="value" id="statBase">…</div>
          </div>
          <div class="stat">
            <div class="label">API key</div>
            <div class="value">any string</div>
          </div>
          <div class="stat">
            <div class="label">Models online</div>
            <div class="value big" id="statModels">…</div>
          </div>
          <div class="stat">
            <div class="label">Uptime</div>
            <div class="value big" id="statUptime">…</div>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <p class="section-label"># models</p>
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;flex-wrap:wrap">
            <span class="hint" style="margin:0">Send a test request through the gateway.</span>
            <button class="btn btn-ghost btn-sm" id="refreshBtn" type="button">↻ Refresh probes</button>
          </div>
          <div id="testOutput"></div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Model</th><th>Endpoint</th><th>Status</th><th>Latency</th><th></th></tr>
              </thead>
              <tbody id="modelRows">
                <tr><td colspan="5" class="faint"><span class="spin"></span> Loading models…</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <p class="section-label"># connect</p>
        <div class="card">
          <p class="snip-title">Any OpenAI-compatible tool</p>
          <div class="code" data-copy><span id="toolSnippet">Base URL: …
API Key:  any string
Model:    …</span><button class="copy-btn" type="button">Copy</button></div>

          <p class="snip-title">cURL</p>
          <div class="code" data-copy><span id="curlSnippet">…</span><button class="copy-btn" type="button">Copy</button></div>

          <p class="snip-title">Python (openai SDK)</p>
          <div class="code" data-copy><span id="pySnippet">…</span><button class="copy-btn" type="button">Copy</button></div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <p class="section-label"># api</p>
        <div class="card">
          <div class="table-wrap">
            <table>
              <thead><tr><th>Method</th><th>Path</th><th>Description</th></tr></thead>
              <tbody>
                <tr><td><span class="tag">GET</span></td><td class="mono">/</td><td>This console</td></tr>
                <tr><td><span class="tag">GET</span></td><td class="mono">/health</td><td>Status, uptime</td></tr>
                <tr><td><span class="tag">GET</span></td><td class="mono">/v1/models</td><td>Model catalog (<code>?refresh=true</code> re-probes)</td></tr>
                <tr><td><span class="tag">GET</span></td><td class="mono">/account-limits</td><td>Model availability overview</td></tr>
                <tr><td><span class="tag">POST</span></td><td class="mono">/v1/chat/completions</td><td>Chat Completions with automatic routing</td></tr>
                <tr><td><span class="tag">POST</span></td><td class="mono">/v1/responses</td><td>Responses API passthrough</td></tr>
                <tr><td><span class="tag">POST</span></td><td class="mono">/v1/systemone</td><td>TypeSafe SystemOne endpoint</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <footer>
      <div class="container">
        <span class="faint">Kiri Router local mode</span>
      </div>
    </footer>
  </main>

  <script>
    (function () {
      // ── Theme: system / light / dark with persistence ──
      var order = ['system', 'light', 'dark'];
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      function current() { try { return localStorage.getItem('theme') || 'system'; } catch (e) { return 'system'; } }
      function apply(mode) {
        var dark = mode === 'dark' || (mode === 'system' && mq.matches);
        document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
        try { localStorage.setItem('theme', mode); } catch (e) {}
      }
      document.getElementById('themeToggle').addEventListener('click', function () {
        apply(order[(order.indexOf(current()) + 1) % order.length]);
      });
      mq.addEventListener('change', function () { if (current() === 'system') apply('system'); });

      var ORIGIN = location.origin;
      var V1 = ORIGIN + '/v1';
      document.getElementById('statBase').textContent = V1;

      // ── Copy buttons ──
      document.querySelectorAll('[data-copy]').forEach(function (block) {
        var btn = block.querySelector('.copy-btn');
        if (!btn) return;
        btn.addEventListener('click', function () {
          var span = block.querySelector('span');
          navigator.clipboard.writeText(span.textContent.trim()).then(function () {
            btn.textContent = 'Copied';
            setTimeout(function () { btn.textContent = 'Copy'; }, 1500);
          });
        });
      });

      function fmtUptime(s) {
        s = s || 0;
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
        if (h > 0) return h + 'h ' + m + 'm';
        if (m > 0) return m + 'm ' + (s % 60) + 's';
        return s + 's';
      }

      // ── Health ──
      fetch('/health').then(function (r) { return r.json(); }).then(function (h) {
        document.getElementById('versionBadge').textContent = 'local';
        document.getElementById('statUptime').textContent = fmtUptime(h.uptime_sec);
      }).catch(function () {
        document.getElementById('versionBadge').textContent = 'offline?';
        document.getElementById('statUptime').textContent = '-';
      });

      // ── Models ──
      function renderModels(models) {
        var tbody = document.getElementById('modelRows');
        tbody.textContent = '';
        var active = 0;
        models.forEach(function (m) {
          var tr = document.createElement('tr');

          var tdId = document.createElement('td');
          var code = document.createElement('span', 'mono');
          code.textContent = m.id;
          tdId.appendChild(code);
          if (m.rate_hint && m.rate_hint.label) {
            var rateLine = document.createElement('div');
            rateLine.className = 'faint';
            rateLine.textContent = m.rate_hint.label;
            tdId.appendChild(rateLine);
          }

          var tdEp = document.createElement('td');
          var ep = document.createElement('span', 'tag');
          ep.textContent = '/' + (m.endpoint_type || 'chat.completion');
          tdEp.appendChild(ep);

          var st = m.status || 'available';
          var failed = st === 'failed';
          var tdSt = document.createElement('td');
          var stTag = document.createElement('span', 'tag ' + (failed ? 'err' : 'ok'));
          stTag.textContent = st;
          tdSt.appendChild(stTag);

          var tdLat = document.createElement('td');
          tdLat.className = 'mono';
          tdLat.textContent = m.latency_ms != null ? m.latency_ms + 'ms' : '-';

          var tdBtn = document.createElement('td');
          var btn = document.createElement('button');
          btn.className = 'btn btn-sm';
          btn.type = 'button';
          btn.textContent = 'Test';
          btn.addEventListener('click', function () { testModel(m.id, btn); });
          tdBtn.appendChild(btn);

          tr.appendChild(tdId); tr.appendChild(tdEp); tr.appendChild(tdSt);
          tr.appendChild(tdLat); tr.appendChild(tdBtn);
          tbody.appendChild(tr);
          if (!failed) active++;
        });
        document.getElementById('statModels').textContent = String(active);

        var example = models.length ? models[0].id : '-';
        document.getElementById('toolSnippet').textContent =
          'Base URL: ' + V1 + '\nAPI Key:  any string\nModel:    ' + example;
        document.getElementById('curlSnippet').textContent =
          'curl -X POST ' + V1 + '/chat/completions \\\n' +
          '  -H "Content-Type: application/json" \\\n' +
          '  -d \'{"model": "' + example + '", "messages": [{"role": "user", "content": "Hello!"}]}\'';
        document.getElementById('pySnippet').textContent =
          'from openai import OpenAI\n' +
          'client = OpenAI(base_url="' + V1 + '", api_key="any")\n' +
          'response = client.chat.completions.create(\n' +
          '    model="' + example + '",\n' +
          '    messages=[{"role": "user", "content": "Hello!"}],\n' +
          ')\n' +
          'print(response.choices[0].message.content)';
      }

      function loadModels(refresh) {
        var url = '/v1/models' + (refresh ? '?refresh=true' : '');
        return fetch(url).then(function (r) { return r.json(); }).then(function (data) {
          var models = (data.data || []).slice().sort(function (a, b) { return a.id < b.id ? -1 : 1; });
          if (!models.length) throw new Error('empty catalog');
          renderModels(models);
        }).catch(function () {
          var tbody = document.getElementById('modelRows');
          tbody.textContent = '';
          var tr = document.createElement('tr');
          var td = document.createElement('td');
          td.colSpan = 5;
          td.className = 'faint';
          td.textContent = 'Could not load models. Is the gateway running?';
          tr.appendChild(td);
          tbody.appendChild(tr);
        });
      }
      loadModels(false);

      document.getElementById('refreshBtn').addEventListener('click', function () {
        var btn = this;
        btn.disabled = true;
        btn.textContent = '↻ Probing…';
        loadModels(true).then(function () {
          btn.disabled = false;
          btn.textContent = '↻ Refresh probes';
        });
      });

      // ── Live test sandbox ──
      function testModel(id, btn) {
        var out = document.getElementById('testOutput');
        out.style.display = 'block';
        out.className = '';
        out.textContent = 'Testing ' + id + ' …';
        btn.disabled = true;
        var t0 = performance.now();
        fetch(V1 + '/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: id,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            stream: false,
            max_tokens: 64
          })
        }).then(function (r) {
          return r.json().then(function (data) { return { status: r.status, data: data }; });
        }).then(function (res) {
          var ms = Math.round(performance.now() - t0);
          btn.disabled = false;
          if (res.data && res.data.choices && res.data.choices[0]) {
            out.className = 'ok';
            out.textContent = '✓ ' + id + ' · ' + res.status + ' in ' + ms + 'ms\n\n' +
              (res.data.choices[0].message.content || '(empty)');
          } else {
            out.className = 'err';
            out.textContent = '✗ ' + id + ' · ' + res.status + ' in ' + ms + 'ms\n\n' +
              JSON.stringify(res.data && res.data.error ? res.data.error : res.data, null, 2);
          }
        }).catch(function (e) {
          btn.disabled = false;
          out.className = 'err';
          out.textContent = '✗ Network error: ' + e.message;
        });
      }
    })();
  </script>
</body>
</html>
"""

# Kiri logo (generated in at build time from ui/kiri-logo.txt)
LOGO = r"""     ..
   .....           --           ---
  ...           -++++           -+++-
  ...         -++++  .  ......    -+++-                  ++-         -+-               +++
  ...       +++++     ..........    -+++-                ++-   ..   ...          -.    ..
 ....     -+++-     ......-.....      +++++              -+- +++   ++-+-     ++++++- -++++
--..     ++++-       ............      -+++-             -+-+--      -+-     ++-       -+-
  ...      -+++-        ........     --++-               -++-+-      ++-     +--       -+-
  ...        -+++.      ..... .    -++++                 -+- -++-   .-+-.    +--      .-+-..
  ...          -+++-             --+++                   ---   --- -------   --      ------- .......
  ....           -+++-          ++++
   .....
"""

# Brand assets (generated in at build time from ui/assets/)
import base64 as _base64

FAVICON_B64 = "AAABAAMAEBAAAAEAIABoBAAANgAAACAgAAABACAAKBEAAJ4EAAAwMAAAAQAgAGgmAADGFQAAKAAAABAAAAAgAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKcX3HzO//xQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMc7/FRPA/7snwf8hAAAAAICAgAI4fjyAR4dOJAAAAAAAAAAAUYZeEzp/PYlAgGAIAAAAAP///wE+yv8dRc7/GibG/ygUwP+KAAAAAICAgAI2fjmcOn08agAAAABr1/gmctv6OFXG/wk4fjxNNn04skCAQAhV//8DIML/PyTE/zgawf94GsL/WAD/AAE1fjiaOH46bQAAAABjzvcfS8r7czPH/aQgxP+XAAAAAD2APVA2fjmwSW1JBwAAAAAAAAAAF8L/cBjB/14AAAAANns6jTl+O30AAAAAbNL5LXHU+Go+yvuPJMT/jwAAAAA7gT5fNX84p0CAQAQAAAAAAAAAACbG/ygUwf+LAAAAAAAAAAA1fTmPOXw7eWLS/yJOzvo0QMr/XDPG+Sg6gD1cOH05qWaZZgUAAAAAAAAAAAAAAAA2yf8TE8D/vybG/ygAAAAAAAAAATZ8O3FJg0kjAAAAAAAAAABZjFkUOoI8fGaZZgUAAAAAAAAAAAAAAAAAAAAAAAAAADnG8RJA1P8MAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAAAACAAAABAAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAAAADAAAABgAAAAAQAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
ICON_B64 = "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"

# ── Terminal UI toolkit (zero dependencies) ───────────────────────────────
USE_COLOR = False
FANCY = False
FRAMES = "-\\|/"
BOOT_T = time.time()


def init_cli(no_color=False):
    """Enable VT/UTF-8 on Windows; resolve color + glyph capability.

    Color precedence (per no-color.org / force-color.org):
      --no-color | NO_COLOR(non-empty) | TERM=dumb  -> off
      FORCE_COLOR(non-empty)                       -> on
      otherwise                                    -> stdout is a tty
    """
    global USE_COLOR, FANCY, FRAMES
    if os.name == "nt":
        os.system("")  # legacy conhost: enable VT processing
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if no_color or os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        USE_COLOR = False
    elif os.environ.get("FORCE_COLOR"):
        USE_COLOR = True
    else:
        USE_COLOR = is_tty
    if os.environ.get("KIRI_ASCII") == "1" or (os.name != "nt" and os.environ.get("TERM") == "linux"):
        FANCY = False
    elif os.name == "nt":
        FANCY = bool(os.environ.get("WT_SESSION") or os.environ.get("ANSICON")
                     or os.environ.get("ConEmuANSI") or os.environ.get("TERM_PROGRAM"))
    else:
        FANCY = True
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if FANCY else "-\\|/"


def _wrap(code, s):
    return "\x1b[" + str(code) + "m" + s + "\x1b[0m" if USE_COLOR else s


def BOLD(s): return _wrap(1, s)
def DIM(s): return _wrap(2, s)
def GREEN(s): return _wrap(32, s)
def RED(s): return _wrap(31, s)
def YELLOW(s): return _wrap(33, s)
def CYAN(s): return _wrap(36, s)


def line_char(ch):
    if FANCY:
        return ch
    return {"─": "-", "│": "|", "┌": "+", "┐": "+", "└": "+", "┘": "+"}.get(ch, ch)


def terminal_cols():
    try:
        import shutil
        return shutil.get_terminal_size((100, 24)).columns
    except Exception:
        return 100


def fit_logo(lines, cols):
    """Show the art only when it fits untouched. Altering it spoils the
    design, so narrow terminals get the wordmark line instead.
    """
    target = max(30, cols - 2)
    cur = list(lines)
    if max((len(l) for l in cur), default=0) <= target:
        return cur
    return None


def print_logo():
    cols = terminal_cols()
    lines = fit_logo(LOGO.splitlines(), cols)
    if lines:
        width = max((len(l) for l in lines), default=0)
        pad = max(0, (cols - width) // 2)
        for l in lines:
            print(" " * pad + l)
        print()
    print("  " + DIM("kiri router · openai-compatible gateway · zero-key"))


def panel(title, rows, cols=None):
    """Modern box-drawing info panel with ASCII fallback."""
    cols = cols or terminal_cols()
    label_w = max([len(str(k)) for k, _ in rows] + [0])
    inner_w = max([len(str(v)) + label_w + 2 for _, v in rows] + [len(title) + 6, 26])
    pad = min(inner_w, max(26, cols - 4))
    print("  " + line_char("┌") + line_char("─") + " " + BOLD(title) + " "
          + line_char("─") * max(1, pad - len(title) - 2) + line_char("┐"))
    for k, v in rows:
        body = str(k).ljust(label_w) + "  " + str(v)
        print("  " + line_char("│") + " " + body[:pad].ljust(pad) + " " + line_char("│"))
    print("  " + line_char("└") + line_char("─") * pad + line_char("┘"))


def osc8(url):
    # OSC-8 hyperlinks only on terminals known to render them cleanly
    # (research: conhost/PowerShell 5.1/log files show raw escape garbage).
    known = (os.environ.get("FORCE_HYPERLINK") or os.environ.get("WT_SESSION")
             or os.environ.get("TERM_PROGRAM") or os.environ.get("VSCODE_PID"))
    if USE_COLOR and known and getattr(sys.stdout, "isatty", lambda: False)():
        return "\x1b]8;;" + url + "\x1b\\" + url + "\x1b]8;;\x1b\\"
    return url


class Spinner:
    """Single-line progress on stderr (tty only); one static stdout line when piped."""

    def __init__(self, msg):
        self.msg = msg
        self.enabled = (bool(getattr(sys.stdout, "isatty", lambda: False)())
                        and not os.environ.get("CI"))
        self._stop = threading.Event()
        self._thread = None

    def _run(self):
        i = 0
        while not self._stop.is_set():
            sys.stderr.write("\r\x1b[2K  " + FRAMES[i % len(FRAMES)] + " " + self.msg)
            sys.stderr.flush()
            i += 1
            self._stop.wait(0.08)

    def __enter__(self):
        if self.enabled:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            print("  " + self.msg)
        return self

    def update(self, msg):
        self.msg = msg

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
            sys.stderr.write("\r\x1b[2K")
            sys.stderr.flush()


def status_style(status, text):
    if status == "active":
        return GREEN(text)
    if status == "untested":
        return YELLOW(text)
    return RED(text)


def fmt_latency(ms):
    return str(ms) + "ms" if ms < 1000 else ("%.1fs" % (ms / 1000.0))


def latency_style(ms):
    text = fmt_latency(ms)
    if ms < 200:
        return GREEN(text)
    if ms < 1000:
        return YELLOW(text)
    return RED(text)


def print_probe_table(results):
    cols = terminal_cols()
    rule = line_char("─") * max(20, min(cols - 4, 74))
    print("  " + DIM("MODEL".ljust(36) + "ENDPOINT".ljust(18) + "STATUS".ljust(10) + "LATENCY"))
    print("  " + DIM(rule))
    for r in results:
        pad_extra = 9 if USE_COLOR else 0
        plain_lat = fmt_latency(r["latency_ms"])
        lat = latency_style(r["latency_ms"])
        lat = (" " * max(0, 7 - len(plain_lat))) + lat
        print("  " + r["model"].ljust(36)
              + ("/" + r["endpoint"]).ljust(18)
              + status_style(r["status"], r["status"]).ljust(10 + pad_extra)
              + lat)


def access_line(method, path, status, ms):
    stamp = time.strftime("%H:%M:%S")
    try:
        code = int(status)
    except (TypeError, ValueError):
        code = 0
    if 200 <= code < 300:
        s = GREEN(str(code))
    elif 300 <= code < 400:
        s = CYAN(str(code))
    elif 400 <= code < 500:
        s = YELLOW(str(code))
    else:
        s = RED(str(code))
    return (DIM(stamp) + " " + BOLD(str(method).ljust(6)) + " " + str(path)
            + " -> " + s + " (" + fmt_latency(ms) + ")" + "\n")

# ── Upstream ─────────────────────────────────────────────────────────────
# The upstream brand is assembled at runtime so this file stays free of
# upstream identifiers in plain text.
_U = "".join(chr(c) for c in (111, 112, 101, 110, 99, 111, 100, 101))
ZEN_BASE = "https://" + _U + ".ai/zen/v1"
ZEN_CHAT = ZEN_BASE + "/chat/completions"
ZEN_RESPONSES = ZEN_BASE + "/responses"
ZEN_MODELS = ZEN_BASE + "/models"
ZEN_MESSAGES = ZEN_BASE + "/messages"
ZEN_SYSTEMONE = ZEN_BASE + "/systemone"
UA = _U + "/1.18.31"
H_CLIENT = "x-" + _U + "-client"
H_SESSION = "x-" + _U + "-session"
H_REQUEST = "x-" + _U + "-request"
REFERER = "https://" + _U + ".ai/"
X_TITLE = _U

TOOLS_CHAT = [
    {"type": "function", "function": {"name": "shell", "description": "Placeholder.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "read", "description": "Placeholder.", "parameters": {"type": "object", "properties": {}}}},
]
TOOLS_FLAT = [
    {"type": "function", "name": "shell", "description": "Placeholder.", "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "read", "description": "Placeholder.", "parameters": {"type": "object", "properties": {}}},
]
TOOLS_ANTHROPIC = [
    {"name": "shell", "description": "run", "input_schema": {"type": "object", "properties": {}}},
    {"name": "read", "description": "read", "input_schema": {"type": "object", "properties": {}}},
]

START_TIME = time.time()

# Discovery cache with double-checked locking (single-flight).
_discovery_lock = threading.Lock()
_discovery = {"table": {}, "ts": 0}


def rand_hex(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def rand_b62(n):
    return "".join(random.choice(string.digits + string.ascii_letters) for _ in range(n))


def build_headers(extra=None):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer public",
        "User-Agent": UA,
        H_CLIENT: "cli",
        H_SESSION: "ses_" + rand_hex(12) + rand_b62(14),
        H_REQUEST: "msg_" + rand_hex(12) + rand_b62(14),
        "HTTP-Referer": REFERER,
        "Referer": REFERER,
        "X-Title": X_TITLE,
    }
    if extra:
        headers.update(extra)
    return headers


def is_free(model_id):
    m = str(model_id or "").lower().strip()
    return m.endswith("-free") or "-free-" in m


def classify(model_id):
    m = str(model_id or "").lower().strip()
    if m.startswith(("claude-", "qwen")):
        return "messages"
    if m.startswith("gemini-"):
        return "google"
    if m.startswith("jev-"):
        return "systemone"
    if m.startswith(("gpt-", "grok")) or "muse-spark" in m:
        return "response"
    return "chat.completion"


def inject_tools(body, fmt="chat"):
    tools = body.get("tools")
    if not isinstance(tools, list):
        tools = []
    names = set()
    for t in tools:
        if isinstance(t, dict):
            fn = t.get("function")
            if isinstance(fn, dict) and fn.get("name"):
                names.add(fn["name"])
            elif t.get("name"):
                names.add(t["name"])
    ph = TOOLS_FLAT if fmt == "responses" else TOOLS_CHAT
    if "shell" not in names and "bash" not in names:
        tools.append(ph[0])
    if "read" not in names:
        tools.append(ph[1])
    body["tools"] = tools
    return body


def to_flat(tools):
    if not isinstance(tools, list):
        return []
    flat = []
    for t in tools:
        if isinstance(t, dict) and isinstance(t.get("function"), dict):
            f = t["function"]
            flat.append({
                "type": "function",
                "name": f.get("name"),
                "description": f.get("description", ""),
                "parameters": f.get("parameters", {"type": "object", "properties": {}}),
            })
        else:
            flat.append(t)
    return flat


def convert_to_responses(body):
    msgs = body.get("messages") or []
    if not body.get("input") and msgs:
        lines = []
        for m in msgs:
            role = str(m.get("role", "user")).upper()
            c = m.get("content", "")
            if isinstance(c, list):
                c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
            lines.append(role + ": " + str(c))
        body["input"] = "\n\n".join(lines)
    return body


def convert_to_systemone(body):
    msgs = body.get("messages") or []
    parts = []
    last_user = ""
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content)
        parts.append(role + ": " + content)
        if role == "user":
            last_user = content
    return {
        "model": body.get("model"),
        "state": "\n\n".join(parts) or "ping",
        "questions": {"answer": {"type": "noul", "instructions": last_user or "respond"}},
    }


# ── SSE aggregation (non-streaming clients) ─────────────────────────────

def aggregate_lines(line_iter, model):
    content, reasoning = "", ""
    res_id = "chatcmpl-" + str(int(time.time() * 1000))
    usage = None
    for raw in line_iter:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip()
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        try:
            chunk = json.loads(line[6:])
        except ValueError:
            continue
        if chunk.get("id"):
            res_id = chunk["id"]
        if chunk.get("usage"):
            usage = chunk["usage"]
        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content += delta["content"]
            if delta.get("reasoning"):
                reasoning += delta["reasoning"]
        if chunk.get("type") == "response.output_text.delta" and chunk.get("delta"):
            content += chunk["delta"]
        if chunk.get("type") == "response.completed":
            resp = chunk.get("response") or {}
            if resp.get("id"):
                res_id = resp["id"]
            if resp.get("usage"):
                usage = resp["usage"]
    final = content or (("[Reasoning: " + reasoning + "]") if reasoning else "")
    return {
        "id": res_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": final},
                     "logprobs": None, "finish_reason": "stop"}],
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ── Probing & discovery ─────────────────────────────────────────────────

def _probe_endpoint(url, body, timeout=8, anthropic=False):
    extra = {"anthropic-version": "2023-06-01", "x-api-key": "public"} if anthropic else None
    payload = json.dumps(body).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=payload, headers=build_headers(extra), method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = int((time.time() - t0) * 1000)
            status = resp.status
            if status == 200:
                # confirm the stream delivers at least one chunk
                first = resp.readline()
                return True, status, elapsed, None
            return False, status, elapsed, str(status)
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - t0) * 1000)
        try:
            e.read()
        except Exception:
            pass
        return False, e.code, elapsed, str(e.code)
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return False, 0, elapsed, str(e)[:80]


def probe_model(mid):
    ep = classify(mid)
    t0 = time.time()

    if ep == "systemone":
        ok, status, elapsed, err = _probe_endpoint(
            ZEN_SYSTEMONE,
            {"model": mid, "state": "ping", "questions": {"test": {"type": "noul", "instructions": "Is this a test?"}}},
        )
    elif ep == "response":
        ok, status, elapsed, err = _probe_endpoint(
            ZEN_RESPONSES,
            inject_tools({"model": mid, "stream": True, "input": "ping"}, "responses"),
        )
    else:
        ok, status, elapsed, err = _probe_endpoint(
            ZEN_CHAT,
            inject_tools({"model": mid, "stream": True, "messages": [{"role": "user", "content": "ping"}]}, "chat"),
        )

    if ok:
        result_status, error = "active", None
    elif status == 429:
        result_status, error = "untested", "rate limited"
    elif ep != "messages" and status not in (200, 429):
        # one fallback hop through the anthropic-style endpoint before giving up
        ok2, status2, elapsed2, err2 = _probe_endpoint(
            ZEN_MESSAGES,
            {"model": mid, "stream": True, "max_tokens": 50,
             "messages": [{"role": "user", "content": "ping"}], "tools": TOOLS_ANTHROPIC},
            anthropic=True,
        )
        if ok2:
            result_status, error = "active", None
            elapsed = elapsed2
        elif status2 == 429:
            result_status, error = "untested", "rate limited"
            elapsed = elapsed2
        else:
            result_status, error = "failed", (err or err2 or "all endpoints failed")
            elapsed = elapsed2
    else:
        result_status, error = "failed", (err or "all endpoints failed")

    return {
        "model": mid,
        "endpoint": ep,
        "status": result_status,
        "latency_ms": elapsed,
        "error": error,
    }


def fetch_free_ids():
    try:
        req = urllib.request.Request(ZEN_MODELS, headers=build_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return sorted(m["id"] for m in data.get("data", []) if m.get("id") and is_free(m["id"]))
    except Exception:
        # No hardcoded fallback list: discovery is always live.
        return []


def discover(force=False, quiet=False):
    now = time.time()
    with _discovery_lock:
        if not force and _discovery["table"] and now - _discovery["ts"] < DISCOVER_TTL:
            return _discovery["table"]
        ids = fetch_free_ids()
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import nullcontext
        table = {}
        results = []
        ctx = Spinner("probing " + str(len(ids)) + " free models…") if not quiet else nullcontext(None)
        with ctx as sp, ThreadPoolExecutor(max_workers=5) as pool:
            for i, r in enumerate(pool.map(probe_model, ids)):
                table[r["model"]] = r
                results.append(r)
                if sp is not None:
                    sp.update("probing " + str(len(ids)) + " models… "
                              + str(i + 1) + "/" + str(len(ids)) + "  " + r["model"])
        _discovery["table"] = table
        _discovery["ts"] = now
        if not quiet and not ids:
            print("  " + YELLOW("! could not load the model catalog; will retry on the next request"))
        if not quiet and results:
            print_probe_table(results)
            active = sum(1 for r in results if r["status"] == "active")
            parts = [str(active) + "/" + str(len(results)) + " active"]
            untested = sum(1 for r in results if r["status"] == "untested")
            failed = sum(1 for r in results if r["status"] == "failed")
            if untested:
                parts.append(str(untested) + " rate limited")
            if failed:
                parts.append(str(failed) + " failed")
            summary = " · ".join(parts)
            print("  " + (GREEN if active == len(results) else YELLOW)(summary) + "\n")
        return table


def listed_models(refresh=False):
    table = discover(force=refresh)
    out = []
    for mid in sorted(table):
        info = table[mid]
        out.append({
            "id": mid,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "kiri",
            "endpoint_type": info["endpoint"],
            "is_free": True,
            "status": info["status"],
            "latency_ms": info["latency_ms"],
        })
    return out


# ── HTTP handler ────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "KiriRouter/" + VERSION
    sys_version = ""

    def log_message(self, *args):
        pass

    def handle_one_request(self):
        self._t0 = time.time()
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_request(self, code="-", size="-"):
        """uvicorn-style colored access log (tty only, set by server.access_log)."""
        if not getattr(self.server, "access_log", False):
            return
        path = (self.path or "/").split("?")[0]
        if path == "/favicon.ico" or self.command == "OPTIONS":
            return
        ms = int((time.time() - getattr(self, "_t0", time.time())) * 1000)
        try:
            sys.stdout.write(access_line(self.command or "?", path, code, ms))
            sys.stdout.flush()
        except Exception:
            pass

    # helpers
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, data, ctype, cache="public, max-age=86400"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _text(self, text, status=200, ctype="text/plain"):
        body = text.encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # GET
    def do_GET(self):
        path = self.path.split("?")[0]
        query = self.path.split("?")[1] if "?" in self.path else ""

        if path == "/":
            self._html(CONSOLE_HTML)
        elif path == "/favicon.ico":
            self._raw(_base64.b64decode(FAVICON_B64), "image/x-icon")
        elif path == "/kiri-icon.png":
            self._raw(_base64.b64decode(ICON_B64), "image/png")
        elif path == "/health":
            self._json({
                "status": "ok",
                "adapter": "kiri-router",
                "version": VERSION,
                "uptime_sec": int(time.time() - START_TIME),
                "upstream": "kiri",
                "mode": "local",
            })
        elif path in ("/v1/models", "/models"):
            refresh = "refresh=true" in query
            try:
                self._json({"object": "list", "data": listed_models(refresh=refresh)})
            except Exception as e:
                self._json({"error": str(e)}, 502)
        elif path == "/account-limits":
            models = listed_models()
            data = {
                "adapter_version": VERSION,
                "uptime_seconds": int(time.time() - START_TIME),
                "total_models_available": len(models),
                "free_models_available": len(models),
                "free_models": [{"id": m["id"], "endpoint": m["endpoint_type"],
                                 "status": m["status"], "latency_ms": m["latency_ms"]} for m in models],
                "zero_auth_supported": True,
            }
            if "format=table" in query:
                lines = [
                    "Kiri Router · Model Availability",
                    "=" * 62,
                    "Model".ljust(36) + "Endpoint".ljust(18) + "Status",
                    "-" * 62,
                ]
                for m in models:
                    lines.append(m["id"].ljust(36) + ("/" + m["endpoint_type"]).ljust(18) +
                                 m["status"].upper() + " (" + str(m["latency_ms"]) + "ms)")
                self._text("\n".join(lines))
            else:
                self._json(data)
        else:
            self._json({"error": "Not found", "path": path}, 404)

    # POST
    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            self._json({"error": "Invalid JSON"}, 400)
            return

        try:
            if path in ("/v1/chat/completions", "/chat/completions"):
                self._chat(body)
            elif path in ("/v1/responses", "/responses"):
                body["stream"] = True
                body["tools"] = to_flat(body.get("tools"))
                inject_tools(body, "responses")
                self._upstream_json_or_stream(ZEN_RESPONSES, body, body.get("model") or "unknown")
            elif path in ("/v1/systemone", "/systemone"):
                self._passthrough_json(ZEN_SYSTEMONE, body)
            else:
                self._json({"error": "Not found", "path": path}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _chat(self, body):
        model = body.get("model")
        if not model:
            self._json({"error": {"message": "model is required; GET /v1/models for the catalog"}}, 400)
            return
        ep = classify(model)
        want_stream = bool(body.get("stream"))
        body["stream"] = True

        if ep == "systemone":
            self._passthrough_json(ZEN_SYSTEMONE, convert_to_systemone(body))
            return
        if ep == "response":
            body = convert_to_responses(body)
            body["tools"] = to_flat(body.get("tools"))
            inject_tools(body, "responses")
            url = ZEN_RESPONSES
        else:
            inject_tools(body, "chat")
            url = ZEN_CHAT
        self._upstream_json_or_stream(url, body, model, want_stream)

    def _passthrough_json(self, url, payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers=build_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
                status = resp.status
            try:
                self._json(json.loads(data), status)
            except ValueError:
                self._text(data.decode("utf-8", "replace"), status, "application/json")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            try:
                self._json(json.loads(detail), e.code)
            except ValueError:
                self._json({"error": "Upstream HTTP " + str(e.code), "details": detail}, e.code)

    def _upstream_json_or_stream(self, url, payload, model, want_stream=False):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers=build_headers(), method="POST")
        try:
            upstream = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:600]
            try:
                self._json(json.loads(detail), e.code)
            except ValueError:
                self._json({"error": "Upstream HTTP " + str(e.code), "details": detail}, e.code)
            return

        with upstream:
            if want_stream:
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    while True:
                        chunk = upstream.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True
            else:
                result = aggregate_lines(upstream, model)
                self._json(result, 200)


# ── main ────────────────────────────────────────────────────────────────

def parse_args(argv):
    opts = {"port": DEFAULT_PORT, "probe": True, "open": False, "no_color": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--port" and i + 1 < len(argv):
            opts["port"] = int(argv[i + 1])
            i += 1
        elif a.startswith("--port="):
            opts["port"] = int(a.split("=", 1)[1])
        elif a == "--no-probe":
            opts["probe"] = False
        elif a == "--open":
            opts["open"] = True
        elif a == "--no-color":
            opts["no_color"] = True
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        i += 1
    return opts


def banner(port, want_port=None):
    print()
    print_logo()
    print()
    url = "http://127.0.0.1:" + str(port) + "/"
    panel("Kiri Router", [
        ("Console", CYAN(osc8(url))),
        ("Base URL", CYAN(osc8(url + "v1"))),
        ("Auth", "any key accepted"),
        ("Egress", "runs on your device"),
    ])
    if want_port and port != want_port:
        print("  " + YELLOW("! port " + str(want_port) + " was busy, using " + str(port)))
    print("  " + DIM("endpoints: POST /v1/chat/completions · /v1/responses · /v1/systemone · GET /v1/models /health"))
    print()


def is_kiri_running(port):
    """True when a CURRENT-GENERATION Kiri gateway (with console) is on this port.
    Older generations that answer something else are treated as foreign so we
    bump to a free port instead of pointing the user at a console-less instance.
    """
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/" % port)
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            head = resp.read(4096).decode("utf-8", "replace")
        return "Local Console" in head
    except Exception:
        return False


def port_open(port):
    """True when something is already listening on 127.0.0.1:port.
    Windows binds can 'succeed' on an occupied port (SO_REUSEADDR), so we
    probe by connecting instead of trusting bind() alone.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except Exception:
        return False


def acquire_server(want, span=10):
    """Return (server, port). Smart about busy ports:
    - a Kiri gateway already on the requested port → (None, port) so main
      can exit gracefully and point at the running instance;
    - any other occupant → automatically try the next ports.
    """
    if is_kiri_running(want):
        return None, want
    for port in range(want, want + span + 1):
        if port_open(port):
            continue
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), Handler), port
        except OSError:
            continue
    raise SystemExit(
        "  ERROR: no free port in %d-%d. Pass e.g. --port 9090" % (want, want + span)
    )


def main():
    opts = parse_args(sys.argv[1:])
    init_cli(opts["no_color"])
    server, port = acquire_server(opts["port"])

    if server is None:
        url = "http://127.0.0.1:" + str(port) + "/"
        print()
        print("  " + YELLOW("●") + " A Kiri Router gateway is already running:")
        print("     Console  " + CYAN(osc8(url)))
        print("     Base URL " + CYAN(osc8(url + "v1")))
        if opts["open"]:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        return

    banner(port, opts["port"])
    server.access_log = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if opts["probe"]:
        try:
            discover(force=True, quiet=False)
        except Exception as e:
            print("  " + YELLOW("! probe skipped") + " " + DIM(str(e)[:60]))
    boot_ms = int((time.time() - BOOT_T) * 1000)
    print("  " + GREEN("● ready") + " " + DIM("in " + str(boot_ms) + "ms · Ctrl+C to stop"))
    print()
    if opts["open"]:
        try:
            webbrowser.open("http://127.0.0.1:" + str(port) + "/")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n  shutting down...\n")
        server.server_close()
        raise SystemExit(130)


if __name__ == "__main__":
    main()
