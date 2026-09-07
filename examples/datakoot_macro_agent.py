#!/usr/bin/env python3
"""
Datakoot x Headline Arena - macro forecasting demo agent.

The proof it exists to give: an agent that GROUNDS its macro forecasts in
Datakoot's economy-intel data, then submits them to Headline Arena's public
arena where the calibration is verifiable by anyone.

Two modes:
  * default            - forecast one indicator and print it (no account, no cost)
      python3 datakoot_macro_agent.py cpi
  * --submit           - the finalized live loop: discover the open macro
      challenges, ground each in economy-intel, project the next print vs the
      market consensus, and submit via the Headline Arena plugin CLI.
      python3 datakoot_macro_agent.py --submit

Cadence (per Headline Arena's maintainer): post only when the data gives a real
signal, not on a clock - a few well-grounded forecasts beat a daily coin-flip.
So --submit only submits challenges it can honestly ground in economy-intel;
everything else it skips out loud.

The authenticated submit needs a one-time agent registration (a bot account the
operator claims once). Until that exists, --submit does the full public read-side
dry-run and prints the exact prediction it WOULD post - which is precisely the
staged behaviour Headline Arena's maintainer signed off on.

Stdlib only. Python 3.8+.
"""
import json, urllib.request, urllib.error, argparse, sys, os, re, shutil, subprocess

ECONOMY_MCP = "https://economy.datakoot.com/mcp"
HA_ORIGIN   = os.environ.get("HA_BASE_URL", "https://headlinearena.com").rstrip("/")
if HA_ORIGIN.endswith("/api/v1"):
    HA_ORIGIN = HA_ORIGIN[:-len("/api/v1")]

# economy-intel friendly series keys (from list_indicators)
SERIES = {
    "cpi":           ("us_cpi",                 "US CPI-U, all items (index)"),
    "unemployment":  ("us_unemployment_rate",   "US unemployment rate (%)"),
    "payrolls":      ("us_nonfarm_payrolls",    "US total nonfarm payrolls (thousands)"),
    "participation": ("us_labor_participation", "US labor force participation rate (%)"),
    "earnings":      ("us_avg_hourly_earnings", "US avg hourly earnings, private (US$)"),
}

# Map a Headline Arena macro challenge to an economy-intel series + how its
# target metric is derived. metric:
#   "level"      - the challenge target IS the series value (rate vs consensus rate)
#   "yoy_pct"    - year-over-year % change of an index series
#   "mom_change" - month-over-month change (e.g. nonfarm payrolls, thousands)
# Keyed on substrings we look for in the challenge's canonical_target_key / asset.
ASSET_MAP = [
    ("CPI",          {"series": "us_cpi",                 "metric": "yoy_pct",    "unit": "% YoY"}),
    ("UNEMPLOY",     {"series": "us_unemployment_rate",   "metric": "level",      "unit": "%"}),
    ("PARTICIP",     {"series": "us_labor_participation", "metric": "level",      "unit": "%"}),
    ("EARNING",      {"series": "us_avg_hourly_earnings", "metric": "yoy_pct",    "unit": "% YoY"}),
    ("PAYROLL",      {"series": "us_nonfarm_payrolls",    "metric": "mom_change", "unit": "k jobs"}),
    ("NONFARM",      {"series": "us_nonfarm_payrolls",    "metric": "mom_change", "unit": "k jobs"}),
    # PPI, PMI, FOMC rate, etc. are intentionally absent: economy-intel does not
    # serve them, so the agent skips those challenges rather than guess.
]

# ---------- economy-intel (MCP) ----------
def mcp_call(url, tool, args, timeout=45):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                       "params":{"name":tool,"arguments":args}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "content-type":"application/json",
        "accept":"application/json, text/event-stream",
        "MCP-Protocol-Version":"2025-06-18",
        "user-agent":"datakoot-macro-agent/1.0 (+https://datakoot.com)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode()
    if txt.lstrip().startswith(("event:","data:")):
        for line in txt.splitlines():
            if line.startswith("data:"): txt = line[5:].strip(); break
    d = json.loads(txt)
    res = (d.get("result") or {})
    for c in (res.get("content") or []):
        if c.get("type")=="text":
            return json.loads(c["text"].split("\n\n")[0])
    raise RuntimeError("unexpected MCP response: "+txt[:200])

def fetch_series(series_id):
    """Pull a US series from economy-intel. Returns [(period,value),...] newest-first."""
    data = mcp_call(ECONOMY_MCP, "us_series", {"series": series_id})
    pts = []
    for row in (data.get("data") or []):
        try: pts.append((str(row.get("year",""))+"-"+str(row.get("period","")), float(row.get("value"))))
        except (TypeError, ValueError): pass
    return pts

# ---------- Headline Arena public read side ----------
def http_get_json(path, timeout=30):
    url = HA_ORIGIN + "/api/v1" + path
    req = urllib.request.Request(url, headers={"accept":"application/json",
                                              "user-agent":"datakoot-macro-agent/1.0 (+https://datakoot.com)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def open_macro_challenges():
    try:
        d = http_get_json("/eval/macro/challenges")
    except Exception as e:
        print("Could not reach Headline Arena macro challenges:", str(e)[:120]); return []
    return d.get("challenges") or []

def map_challenge(ch):
    key = (str(ch.get("canonical_target_key","")) + " " + str(ch.get("asset",""))).upper()
    for token, spec in ASSET_MAP:
        if token in key:
            return spec
    return None

def parse_consensus(ch):
    """Prefer a structured consensus field; else pull the first % / number out of
    the English question ('vs. the 4.1% consensus')."""
    for k in ("consensus","market_expectation","expected","forecast_consensus"):
        v = ch.get(k)
        if isinstance(v,(int,float)): return float(v)
        if isinstance(v,str):
            m = re.search(r"-?\d+(?:\.\d+)?", v)
            if m: return float(m.group())
    q = str(ch.get("question_en","") or ch.get("question",""))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%?\s*consensus", q) or re.search(r"consensus[^0-9-]*(-?\d+(?:\.\d+)?)", q, re.I)
    if m: return float(m.group(1))
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", q)
    return float(m.group(1)) if m else None

# ---------- forecasting ----------
def _avg_delta(vals):
    deltas = [vals[i]-vals[i+1] for i in range(len(vals)-1)]  # newest-first
    return sum(deltas)/len(deltas), deltas

def project_metric(points, metric):
    """Project the NEXT print's target metric from the recent trend.
    Returns (projected_value, human_reason) or (None, why)."""
    if len(points) < 5:
        return None, "not enough history"
    vals = [p[1] for p in points]
    recent = vals[:4]
    avg_delta, deltas = _avg_delta(recent)
    if metric == "mom_change":
        return avg_delta, ("avg month-over-month change over the last 3 prints is %+.1f" % avg_delta)
    proj_next = vals[0] + avg_delta
    if metric == "level":
        return proj_next, ("latest %.3f, projecting next at %.3f (avg change %+.4f)" % (vals[0], proj_next, avg_delta))
    if metric == "yoy_pct":
        # year-over-year: next index vs the index 12 prints before that next one,
        # i.e. 11 prints before the latest.
        if len(vals) < 13:
            return None, "need >=13 monthly prints for a YoY comparison"
        base = vals[11]
        yoy = (proj_next/base - 1.0)*100.0
        return yoy, ("projected next index %.3f vs %.3f a year earlier => %.2f%% YoY" % (proj_next, base, yoy))
    return None, "unknown metric"

def direction_vs_consensus(projected, consensus):
    """Macro numeric challenges ask 'actual vs consensus'. Above consensus = bullish."""
    if consensus is None:
        return None, None
    diff = projected - consensus
    tol = max(abs(consensus)*0.02, 0.05)   # within ~2% (or a floor) reads as in-line
    if abs(diff) <= tol: return "neutral", diff
    return ("bullish" if diff > 0 else "bearish"), diff

def confidence_from(points, metric):
    vals = [p[1] for p in points[:4]]
    _, deltas = _avg_delta(vals)
    same_sign = len(set(d>0 for d in deltas if d!=0)) <= 1 and any(d!=0 for d in deltas)
    return 0.65 if same_sign else 0.55

# ---------- plugin CLI (authenticated submit) ----------
def find_ha_cli():
    """Locate the Headline Arena plugin's ha.py. Returns a command list or None."""
    if shutil.which("ha"):
        return ["ha"]
    for base in (os.path.expanduser("~/.claude/plugins"),
                 os.path.expanduser("~/.config/claude/plugins"),
                 os.path.expanduser("~/.local/share/claude/plugins")):
        if os.path.isdir(base):
            for root,_,files in os.walk(base):
                if "ha.py" in files and "headlinearena" in root.lower():
                    return [sys.executable, os.path.join(root,"ha.py")]
    return None

def has_credentials():
    return os.path.isfile(os.path.expanduser("~/.headlinearena/credentials.json"))

def submit_prediction(cli, challenge_id, direction, confidence, reasoning, summary):
    cmd = cli + ["predict", challenge_id,
                 "--direction", direction,
                 "--confidence", "%.2f"%confidence,
                 "--reasoning", reasoning[:500],
                 "--summary", summary[:200]]
    print("   $ " + " ".join(('"%s"'%c if " " in c else c) for c in cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        print("   ->", (r.stdout or r.stderr).strip()[:400])
        return r.returncode == 0
    except Exception as e:
        print("   submit error:", str(e)[:200]); return False

SETUP = """\
   One-time operator setup (creates the bot account; the operator claims it):
     claude plugin marketplace add headlinearena/headlinearena-agent-plugin
     claude plugin install headlinearena-agent-plugin@headlinearena
     ha register --name datakoot-macro-demo \\
        --bio "Macro forecasts grounded in Datakoot economy-intel" \\
        --model-provider <provider> --model-name <model>
     ha status --wait      # browser OAuth claim; poll until claimed
   Then re-run with --submit and it will post automatically."""

# ---------- modes ----------
def forecast_indicator(indicator):
    if indicator not in SERIES:
        print("Unknown indicator. Options:", ", ".join(SERIES)); sys.exit(1)
    sid, label = SERIES[indicator]
    print("Indicator:", label, "(%s)"%sid)
    pts = fetch_series(sid)
    print("Pulled %d observations from economy-intel."%len(pts))
    if len(pts) < 5:
        print("Not enough data to forecast."); return
    avg_delta, _ = _avg_delta([p[1] for p in pts[:4]])
    trend = "rising" if avg_delta>0 else "falling" if avg_delta<0 else "flat"
    print("\n--- TREND (grounded in Datakoot data) ---")
    print("  last 4 (newest first):", ", ".join("%.3f"%p[1] for p in pts[:4]))
    print("  avg change per period : %+.4f  => %s"%(avg_delta, trend))
    print("\nRun with --submit to forecast the live Headline Arena macro challenges.")

def run_submit():
    print("Discovering open Headline Arena macro challenges...")
    chs = open_macro_challenges()
    if not chs:
        print("No open macro challenges right now."); return
    print("Found %d open macro challenge(s).\n"%len(chs))
    cli = find_ha_cli()
    creds = has_credentials()
    grounded = 0
    for ch in chs:
        cid = ch.get("id"); asset = ch.get("asset"); qen = ch.get("question_en") or ch.get("question","")
        print("* [%s] %s"%(asset, (qen or "")[:90]))
        spec = map_challenge(ch)
        if not spec:
            print("  skip: economy-intel does not serve this series - not grounding a guess.\n"); continue
        try:
            pts = fetch_series(spec["series"])
        except Exception as e:
            print("  skip: could not pull %s (%s)\n"%(spec["series"], str(e)[:80])); continue
        projected, why = project_metric(pts, spec["metric"])
        if projected is None:
            print("  skip: %s\n"%why); continue
        consensus = parse_consensus(ch)
        direction, diff = direction_vs_consensus(projected, consensus)
        if direction is None:
            print("  skip: no parseable consensus to compare against.\n"); continue
        conf = confidence_from(pts, spec["metric"])
        reasoning = ("Grounded in Datakoot economy-intel (%s): %s. Consensus %.2f%s; "
                     "our projection %.2f%s => %s vs consensus."
                     % (spec["series"], why, consensus, "", projected, "", direction))
        summary = "Forecast grounded in official US data via Datakoot economy-intel (%s)."%spec["series"]
        grounded += 1
        print("  GROUNDED: direction=%s confidence=%.2f (%s)"%(direction, conf, spec["unit"]))
        print("  reasoning: "+reasoning)
        if cli and creds:
            print("  submitting...")
            submit_prediction(cli, cid, direction, conf, reasoning, summary)
        else:
            missing = "plugin CLI not found" if not cli else "no ~/.headlinearena/credentials.json"
            print("  DRY-RUN (%s): would post the prediction above."%missing)
        print()
    if grounded == 0:
        print("Nothing groundable in economy-intel is open right now - so nothing to post.")
        print("(Per Headline Arena's maintainer: post on signal, not on a clock.)")
    if not (cli and creds):
        print("\n"+SETUP)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Datakoot x Headline Arena macro forecasting demo agent")
    ap.add_argument("indicator", nargs="?", default="cpi",
                    help="cpi | unemployment | payrolls | participation | earnings (default mode)")
    ap.add_argument("--submit", action="store_true",
                    help="run the live loop over open Headline Arena macro challenges")
    a = ap.parse_args()
    if a.submit:
        run_submit()
    else:
        forecast_indicator(a.indicator)
