#!/usr/bin/env python3
"""Draw the POC plan's figures as SVG. Stdlib only.

    python3 docs/figures/make_figures.py   # writes docs/figures/<name>-light.svg and -dark.svg

Same helpers and colour roles as the bioc-infrastructure unified-search figures
(diagrams/unified-search/make_figures.py). Each figure is drawn twice, for GitHub's
light and dark themes; docs/poc-plan.md picks one with <picture>. Backgrounds are
transparent; BG is only used behind labels that sit on top of lines.

Colour roles: violet = data plane (logs, ClickHouse, Postgres), green = our code,
blue = serving and consumers (clients, proxy, gateway, dashboard), amber = external
(team-hosted servers, public registries, third parties), coral = problems, not visible,
out of scope.
"""
from pathlib import Path
from html import escape

OUT = Path(__file__).parent

PALETTES = {
    "light": dict(BG="#ffffff", TEXT="#14202e", MUTED="#4a5a6c", BLUE="#1f7fc4",
                  GREEN="#4f8f17", AMBER="#b87a00", CORAL="#cc4733", VIOLET="#6e4fd0"),
    "dark": dict(BG="#0d1117", TEXT="#e8eef6", MUTED="#a9b8ca", BLUE="#4aa8e8",
                 GREEN="#9fd05a", AMBER="#f2b441", CORAL="#ff7a66", VIOLET="#b49cff"),
}
ROLES = ("MUTED", "BLUE", "GREEN", "AMBER", "CORAL", "VIOLET")
SANS = "Inter, 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', Menlo, Consolas, 'DejaVu Sans Mono', monospace"
P = {}  # the active palette, set by use()


def use(name):
    P.clear()
    P.update(PALETTES[name])


def tw(s, size, mono=True):
    """Rough text width; good enough to size boxes and halos."""
    return len(s) * size * (0.62 if mono else 0.56)


def svg(w, h, body, title):
    marks = "".join(
        f'<marker id="ah-{r}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{P[r]}"/></marker>'
        for r in ROLES)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n'
            f"<defs>{marks}</defs>\n" + "".join(body) + "</svg>\n")


def text(x, y, s, size=18, role="TEXT", weight=400, anchor="start", mono=False, italic=False):
    fam = MONO if mono else SANS
    it = ' font-style="italic"' if italic else ""
    return (f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{P[role]}" '
            f'font-weight="{weight}" text-anchor="{anchor}"{it} xml:space="preserve">{escape(s)}</text>\n')


def halo(x, y, w, h):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{P["BG"]}" opacity="0.92"/>\n'


def box(x, y, w, h, title, lines=(), role="BLUE", title_size=20, line_size=15, anchor="start", dashed=False):
    c = P[role]
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{c}1a" stroke="{c}" stroke-width="2"{dash}/>\n']
    tx = x + w / 2 if anchor == "middle" else x + 16
    out.append(text(tx, y + 30, title, title_size, "TEXT", 650, anchor))
    for i, ln in enumerate(lines):
        out.append(text(tx, y + 36 + (i + 1) * (line_size + 7), ln, line_size, "MUTED", 400, anchor, mono=True))
    return "".join(out)


def group(x, y, w, h, label, role, label_y=None):
    c = P[role]
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="none" stroke="{c}" '
            f'stroke-width="1.8" stroke-dasharray="5 6"/>\n'
            + text(x + 16, label_y or y - 10, label.upper(), 14, role, 700, mono=True))


def arrow(pts, role="MUTED", label=None, lpos=None, width=2.2, lsize=14, dashed=False):
    c = P[role]
    d = "M" + " L".join(f"{a},{b}" for a, b in pts)
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    out = [f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{width}"{dash} marker-end="url(#ah-{role})"/>\n']
    if label:
        lx, ly = lpos if lpos else ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
        lines = label.split("\n")
        wmax = max(tw(s, lsize) for s in lines) + 14
        hh = len(lines) * (lsize + 5) + 8
        out.append(halo(lx - wmax / 2, ly - hh / 2, wmax, hh))
        for i, s in enumerate(lines):
            out.append(text(lx, ly - hh / 2 + (i + 1) * (lsize + 5), s, lsize, role, 500, "middle", mono=True))
    return "".join(out)


def pill(x, y, s, role, size=14, dashed=False):
    c = P[role]
    w = tw(s, size) + 20
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{size + 12}" rx="{(size + 12) / 2}" '
            f'fill="{c}22" stroke="{c}"{dash}/>\n' + text(x + w / 2, y + size + 3, s, size, role, 600, "middle", mono=True))


def legend(x, y, items, max_w):
    """items: (role, label, kind); kind is box, dashbox, line, dashline. Wraps at max_w."""
    out, cx, cy = [], x, y
    out.append(text(x, y + 13, "LEGEND", 13, "MUTED", 700, mono=True))
    cx += 80
    for role, label, kind in items:
        w = 34 + len(label) * 15 * 0.5 + 34
        if cx + w > x + max_w:
            cx, cy = x + 80, cy + 30
        c = P[role]
        if kind in ("box", "dashbox"):
            dash = ' stroke-dasharray="4 3"' if kind == "dashbox" else ""
            out.append(f'<rect x="{cx}" y="{cy}" width="24" height="16" rx="4" fill="{c}1a" stroke="{c}" stroke-width="2"{dash}/>\n')
        else:
            dash = ' stroke-dasharray="6 4"' if kind == "dashline" else ""
            out.append(f'<path d="M{cx},{cy + 8} L{cx + 24},{cy + 8}" stroke="{c}" stroke-width="2.2"{dash} marker-end="url(#ah-{role})"/>\n')
        out.append(text(cx + 34, cy + 13, label, 15, "TEXT", 400))
        cx += w
    return "".join(out), cy + 30


# --------------------------------------------------------------------------
# Sequence-diagram helpers
def participants(cols, y=30, w=190, h=66, bottom=1000):
    out = []
    for x, title, sub, role in cols:
        out.append(f'<path d="M{x},{y + h} L{x},{bottom}" stroke="{P["MUTED"]}" stroke-width="1.4" stroke-dasharray="3 5"/>\n')
        out.append(box(x - w / 2, y, w, h, title, [sub], role, title_size=18, line_size=13, anchor="middle"))
    return "".join(out)


def msg(x1, x2, y, label, role="BLUE", dashed=False, lsize=14):
    """Horizontal message arrow with its label stacked above the line."""
    out = [arrow([(x1, y), (x2 + (-4 if x2 > x1 else 4), y)], role, width=2, dashed=dashed)]
    lines = label.split("\n")
    mx = (x1 + x2) / 2
    wmax = max(tw(s, lsize) for s in lines) + 12
    top = y - 8 - len(lines) * (lsize + 4)
    out.append(halo(mx - wmax / 2, top, wmax, len(lines) * (lsize + 4) + 2))
    for i, s in enumerate(lines):
        out.append(text(mx, top + (i + 1) * (lsize + 4) - 3, s, lsize, role, 500, "middle", mono=True))
    return "".join(out)


def note(x, y, lines, role, size=14, w=None, title=None):
    """A note card; x is its left edge. Returns (svg, bottom y)."""
    ls = size + 6
    rows = ([title] if title else []) + list(lines)
    w = w or max(tw(s, size) for s in rows) + 24
    h = len(rows) * ls + 14
    c = P[role]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{P["BG"]}" stroke="{c}" stroke-width="1.5"/>\n',
           f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{c}14"/>\n']
    for i, s in enumerate(rows):
        bold = title and i == 0
        out.append(text(x + 12, y + 7 + (i + 1) * ls - 4, s, size, role if bold else "TEXT", 700 if bold else 400, mono=True))
    return "".join(out), y + h


def frame(x, y, w, h, label, role="MUTED"):
    c = P[role]
    lw = tw(label, 14) + 24
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="none" stroke="{c}" stroke-width="1.4"/>\n'
            f'<path d="M{x},{y + 28} L{x + lw},{y + 28} L{x + lw + 12},{y + 16} L{x + lw + 12},{y}" '
            f'fill="{P["BG"]}" stroke="none"/>\n'
            f'<path d="M{x},{y + 28} L{x + lw},{y + 28} L{x + lw + 12},{y + 16} L{x + lw + 12},{y}" '
            f'fill="{c}1a" stroke="{c}" stroke-width="1.4"/>\n'
            + text(x + 10, y + 19, label, 14, role, 700, mono=True))


# --------------------------------------------------------------------------
UPSTREAMS = [
    ("/glygen/mcp", "GlyGen", "mcp.glygen.org · GlyGen DCC", "AMBER", False, None),
    ("/pwb/mcp", "Playbook Workflow Builder", "playbook-workflow-builder.cloud", "AMBER", False, None),
    ("/perturbseqr/mcp", "PerturbSeqr", "perturbseqr.maayanlab.cloud · DRC", "AMBER", False, None),
    ("/cfde-mcp/mcp", "cfde-mcp", "mcp.cfde.cloud · DRC · API key", "AMBER", False, "bearer pass-through"),
    ("/reference/mcp", "cfde-reference-mcp (ours)", "FastMCP · ground-truth counter", "GREEN", False, None),
    ("/<name>/mcp", "stdio target (optional)", "e.g. Standards Explorer, run", "AMBER", True, "stdio subprocess"),
]


def architecture():
    b = []
    # Request path -----------------------------------------------------------
    b.append(text(280, 205, "one stable URL per server", 15, "MUTED", 600, "middle"))
    b.append(text(280, 228, "https://cfde-mcp.cancerdatasci.org/<server>/mcp", 14, "BLUE", 600, "middle", mono=True))
    b.append(box(20, 250, 230, 170, "MCP clients", ["Claude, Cursor,", "VS Code, agents"], "BLUE"))
    b.append(box(310, 250, 230, 170, "Traefik", ["existing proxy", "TLS (Let's Encrypt)", "access log keeps", "Mcp-* headers"], "BLUE"))
    b.append(arrow([(250, 335), (305, 335)], "BLUE"))
    b.append(box(600, 40, 330, 590, "agentgateway", ["1 replica · JSON access log"], "BLUE", title_size=22))
    b.append(arrow([(540, 335), (595, 335)], "BLUE"))
    b.append(group(995, 100, 450, 4 * 84 + 4, "Team-hosted remote servers", "AMBER", label_y=92))
    for i, (route, name, sub, role, dashed, aside) in enumerate(UPSTREAMS):
        y = 108 + i * 84
        cy = y + 36
        b.append(pill(616, cy - 13, route, "BLUE", 14, dashed))
        if aside:
            b.append(text(616 + tw(route, 14) + 30, cy + 5, aside, 12, "MUTED", 500, mono=True))
        b.append(box(1010, y, 420, 72, name, [sub + (" by gateway" if dashed else "")], role,
                     title_size=18, line_size=14, dashed=dashed))
        b.append(arrow([(930, cy), (1005, cy)], role, dashed=dashed))

    # Logging path -----------------------------------------------------------
    b.append(arrow([(425, 420), (425, 725)], "VIOLET", "Traefik log\n(Mcp-* headers)", (425, 560)))
    b.append(arrow([(765, 630), (765, 665), (540, 665), (540, 725)], "VIOLET", "gateway JSON log", (655, 665)))
    b.append(box(270, 730, 330, 150, "Vector (existing)", ["tails both logs", "privacy transform:", "drops every field", "not in the schema"], "VIOLET"))
    b.append(group(660, 715, 790, 330, "Privacy boundary: no args, results or raw IPs inside", "CORAL", label_y=705))
    b.append(box(680, 730, 280, 150, "ClickHouse", ["mcp_requests", "raw rows", "90-day TTL"], "VIOLET"))
    b.append(arrow([(600, 805), (675, 805)], "VIOLET"))
    b.append(box(1060, 730, 370, 150, "Postgres analytics.mcp_*", ["mcp_daily", "mcp_clients_monthly", "mcp_downloads_daily"], "VIOLET"))
    b.append(arrow([(960, 790), (1055, 790)], "VIOLET", "daily\ntimer", (1008, 755)))
    b.append(box(1060, 935, 370, 95, "cfde-atlas", ["dashboard, chat, reports"], "BLUE"))
    b.append(arrow([(1245, 880), (1245, 930)], "VIOLET"))
    b.append(box(680, 935, 280, 95, "Floor-metrics collector", ["daily download counts"], "GREEN", title_size=18))
    b.append(arrow([(960, 982), (1010, 982), (1010, 850), (1055, 850)], "GREEN"))
    b.append(box(270, 935, 330, 95, "Public registries", ["PyPI, npm, Docker Hub,", "MCP Registry"], "AMBER", title_size=18))
    b.append(arrow([(600, 982), (675, 982)], "AMBER"))

    lg, bottom = legend(20, 1080, [
        ("BLUE", "Serving path and consumers", "box"),
        ("GREEN", "Our code", "box"),
        ("VIOLET", "Data plane", "box"),
        ("AMBER", "External (team-hosted, registries)", "box"),
        ("CORAL", "Privacy boundary", "dashbox"),
        ("MUTED", "Dashed = optional", "dashbox"),
    ], 1420)
    b.append(lg)
    return svg(1460, bottom + 10, b, "POC architecture. MCP clients reach one stable URL per server at cfde-mcp.cancerdatasci.org. Traefik terminates TLS and logs Mcp-* headers; agentgateway routes /glygen, /pwb, /perturbseqr and /cfde-mcp (bearer pass-through) to the team-hosted servers, /reference to our cfde-reference-mcp, and optionally runs a stdio server. Both access logs go to Vector, which drops every field not in the schema, then to ClickHouse mcp_requests (90-day TTL). A daily timer rolls them up into Postgres analytics.mcp_*, alongside a floor-metrics collector's download counts from PyPI, npm, Docker Hub and the MCP Registry; cfde-atlas reads Postgres. No arguments, results or raw IPs are stored past Vector.")


def sequence_tool_call():
    C, T, G, U, V, K = 120, 360, 610, 880, 1110, 1320
    bottom = 1130
    b = [participants([
        (C, "MCP client", "Claude, Cursor, agent", "BLUE"),
        (T, "Traefik", "TLS · access log", "BLUE"),
        (G, "agentgateway", "route /glygen/mcp", "BLUE"),
        (U, "Upstream server", "e.g. mcp.glygen.org", "AMBER"),
        (V, "Vector", "log shipper", "VIOLET"),
        (K, "ClickHouse", "mcp_requests", "VIOLET"),
    ], bottom=bottom)]

    b.append(frame(15, 115, 1410, 700, "2026-07-28 client: stateless, routing headers"))
    b.append(msg(C, T, 190, "POST /glygen/mcp"))
    n, _ = note(22, 205, ["Mcp-Method: tools/call", "Mcp-Name: get_glycan", "MCP-Protocol-Version: 2026-07-28",
                          "body _meta: clientInfo", "  {name, version}"], "BLUE", 13, title="headers + body")
    b.append(n)
    b.append(msg(T, G, 240, "proxy to gateway"))
    b.append(msg(G, U, 290, "tools/call\nauth passed through", "BLUE"))
    b.append(msg(U, G, 350, "result, or isError,\nor JSON-RPC error", "AMBER", dashed=True))
    b.append(msg(G, T, 400, "response", "BLUE", dashed=True))
    b.append(msg(T, C, 430, "response", "BLUE", dashed=True))
    n, _ = note(T - 115, 460, ["path, status,", "Mcp-* headers"], "BLUE", 13, w=200, title="Traefik log line")
    b.append(n)
    n, _ = note(G - 120, 460, ["server, method, tool,", "outcome, protocol version,", "client name/version,",
                               "User-Agent, hashed client id"], "BLUE", 13, w=300, title="gateway access-log line")
    b.append(n)
    b.append(msg(G, V, 620, "JSON log line (tailed)", "VIOLET", dashed=True))
    b.append(msg(T, V, 655, "Traefik log line", "VIOLET", dashed=True))
    n, _ = note(V - 140, 670, ["keep schema fields;", "drop args, results,", "raw IPs"], "VIOLET", 13, w=240,
                title="privacy transform")
    b.append(n)
    b.append(msg(V, K, 795, "INSERT", "VIOLET"))

    b.append(frame(15, 835, 1410, 280, "alt: legacy 2025-11-25 client (sessions)"))
    b.append(msg(C, G, 900, "initialize + clientInfo (via Traefik)"))
    b.append(msg(G, U, 930, "initialize"))
    b.append(msg(U, G, 965, "Mcp-Session-Id", "AMBER", dashed=True))
    b.append(msg(G, C, 1000, "Mcp-Session-Id", "BLUE", dashed=True))
    b.append(msg(C, G, 1060, "tools/call + Mcp-Session-Id"))
    n, _ = note(U + 20, 880, ["no Mcp-Method / Mcp-Name headers:", "gateway reads method and tool from",
                              "the JSON-RPC body, takes clientInfo", "from initialize, sets legacy flag;",
                              "then the same log path as above"], "MUTED", 13, w=400)
    b.append(n)

    lg, bot = legend(20, bottom + 20, [
        ("BLUE", "Client, proxy, gateway", "box"),
        ("AMBER", "Team-hosted server", "box"),
        ("VIOLET", "Data plane", "box"),
        ("BLUE", "Request", "line"),
        ("MUTED", "Response or async", "dashline"),
    ], 1400)
    b.append(lg)
    return svg(1440, bot + 10, b, "Sequence of one tools/call. A 2026-07-28 client POSTs to /glygen/mcp with Mcp-Method, Mcp-Name and MCP-Protocol-Version headers and clientInfo in the body _meta. Traefik proxies to agentgateway, which forwards the call (auth passed through) to the upstream server and returns its result, tool error or JSON-RPC error. Traefik and the gateway each write an access-log line; the gateway's carries server, method, tool, outcome, protocol version, client name, User-Agent and a hashed client id. Vector tails both, keeps only schema fields and inserts into ClickHouse mcp_requests. Alternative: a legacy 2025-11-25 client first calls initialize and gets an Mcp-Session-Id; the gateway then reads method and tool from the JSON-RPC body and sets a legacy flag.")


def sequence_daily_rollup():
    N, S, R, K, PG, D, REG, A = 95, 280, 465, 650, 835, 1020, 1205, 1390
    bottom = 900
    b = [participants([
        (N, "ntfy", "push alerts", "CORAL"),
        (S, "systemd timer", "daily", "GREEN"),
        (R, "rollup job", "ours", "GREEN"),
        (K, "ClickHouse", "mcp_requests", "VIOLET"),
        (PG, "Postgres", "analytics.mcp_*", "VIOLET"),
        (D, "collector", "downloads", "GREEN"),
        (REG, "Registries", "PyPI, npm, Docker", "AMBER"),
        (A, "cfde-atlas", "dashboard, chat", "BLUE"),
    ], w=170, bottom=bottom)]

    b.append(frame(10, 115, 1475, 455, "daily (OnCalendar, per SCHEDULING.md)"))
    b.append(msg(S, R, 175, "start", "GREEN"))
    b.append(msg(R, K, 245, "aggregate yesterday\nby server, tool,\nclient, outcome", "GREEN"))
    b.append(msg(K, R, 285, "rows", "VIOLET", dashed=True))
    b.append(msg(R, PG, 345, "UPSERT mcp_daily\nUPSERT mcp_clients_monthly", "GREEN"))
    b.append(msg(S, D, 400, "start", "GREEN"))
    b.append(msg(D, REG, 450, "GET counts,\nregistry entries", "GREEN"))
    b.append(msg(REG, D, 490, "downloads, pulls", "AMBER", dashed=True))
    b.append(msg(D, PG, 545, "UPSERT\nmcp_downloads_daily", "GREEN"))

    b.append(frame(10, 590, 1475, 120, "alt: a unit fails or hangs", "CORAL"))
    b.append(msg(S, N, 660, "OnFailure", "CORAL"))
    n, _ = note(S + 30, 640, ["operator gets a push; earlier aggregates are unaffected"], "CORAL", 13)
    b.append(n)

    b.append(frame(10, 730, 1475, 155, "any time: reading the numbers", "BLUE"))
    b.append(msg(A, PG, 800, "SELECT calls by server and client app, last 30 days", "BLUE"))
    b.append(msg(PG, A, 860, "rows + column comments", "VIOLET", dashed=True))

    lg, bot = legend(20, bottom + 20, [
        ("GREEN", "Our jobs", "box"),
        ("VIOLET", "Data plane", "box"),
        ("AMBER", "External registries", "box"),
        ("BLUE", "Consumer", "box"),
        ("CORAL", "Failure alert", "box"),
        ("MUTED", "Request", "line"),
        ("MUTED", "Response", "dashline"),
    ], 1460)
    b.append(lg)
    return svg(1500, bot + 10, b, "Sequence of the daily rollup. A systemd timer starts the rollup job, which aggregates yesterday's ClickHouse mcp_requests by server, tool, client and outcome and upserts Postgres analytics.mcp_daily and analytics.mcp_clients_monthly. The timer also starts the downloads collector, which fetches download and pull counts and registry entries from PyPI, npm, Docker Hub and the MCP Registry into analytics.mcp_downloads_daily. If a unit fails or hangs, OnFailure sends an ntfy push. cfde-atlas reads the Postgres tables at any time.")


def coverage():
    rows = [
        ("Remote server via the CFDE URL", "cfde-mcp.cancerdatasci.org/glygen/mcp",
         ["every call: server, tool,", "client app, outcome"], "visible", "BLUE", "BLUE"),
        ("Stdio server run by the gateway", "standards-explorer-mcp, run by CFDE",
         ["every call, as above", "(optional in the POC)"], "visible", "BLUE", "BLUE"),
        ("Same server via its original URL", "mcp.glygen.org/mcp",
         ["nothing; only the team's", "own server logs"], "not visible", "CORAL", "CORAL"),
        ("Local stdio install", "uvx standards-explorer-mcp",
         ["no calls; package", "downloads as a floor"], "downloads only", "CORAL", "AMBER"),
        ("Third-party wrapper (GTEx, Enrichr)", "@pipeworx/mcp-gtex, enrichr-mcp",
         ["no calls; they hit DCC APIs", "directly. Downloads only"], "downloads only", "CORAL", "AMBER"),
    ]
    b = []
    for x, h in ((36, "How a user reaches the server"), (420, "Example"), (790, "What CFDE sees"), (1110, "Verdict")):
        b.append(text(x, 40, h, 14, "MUTED", 700, mono=True))
    b.append(group(20, 85, 1300, 2 * 84 + 4, "Through the CFDE gateway", "BLUE", label_y=77))
    b.append(group(20, 85 + 2 * 84 + 30, 1300, 3 * 84 + 4, "Outside the gateway", "CORAL", label_y=85 + 2 * 84 + 22))
    y = 93
    for i, (path, ex, sees, verdict, role, prole) in enumerate(rows):
        if i == 2:
            y += 30
        c = P[role]
        b.append(f'<rect x="30" y="{y}" width="1280" height="72" rx="10" fill="{c}12" stroke="{c}" stroke-width="1.2"/>\n')
        b.append(text(46, y + 43, path, 18, "TEXT", 600))
        b.append(text(420, y + 42, ex, 14, "MUTED", 400, mono=True))
        b.append(text(790, y + 31, sees[0], 16, "TEXT", 400))
        b.append(text(790, y + 54, sees[1], 16, "TEXT", 400))
        b.append(pill(1110, y + 23, verdict, prole))
        y += 84
    lg, bot = legend(20, y + 20, [
        ("BLUE", "Measured by the gateway", "box"),
        ("AMBER", "Download counts only (a floor)", "box"),
        ("CORAL", "Not visible to CFDE", "box"),
    ], 1300)
    b.append(lg)
    return svg(1340, bot + 10, b, "Coverage. Visible to CFDE: remote servers reached through the CFDE gateway URL, and stdio servers the gateway runs (optional). Not visible: the same remote servers reached through their original URLs (only the team's own logs see them), local stdio installs (package downloads are a floor), and third-party wrappers such as the GTEx and Enrichr servers, which call DCC APIs directly and show up only as download counts.")


FIGS = {"architecture": architecture, "sequence-tool-call": sequence_tool_call,
        "sequence-daily-rollup": sequence_daily_rollup, "coverage": coverage}

if __name__ == "__main__":
    for theme in PALETTES:
        use(theme)
        for name, fn in FIGS.items():
            s = fn()
            assert s.count("<svg") == 1 and "<title>" in s and "LEGEND" in s, name
            (OUT / f"{name}-{theme}.svg").write_text(s)
            print("wrote", f"docs/figures/{name}-{theme}.svg")
