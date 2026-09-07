# Economy Intel MCP — by Datakoot

Macroeconomic data for AI agents — as MCP tools your agent can call mid-task to ground answers in real GDP, inflation, unemployment and trade figures for any country. No API keys.

## Tools

| Tool | What it does | Source |
|---|---|---|
| `country_indicator` | An indicator (GDP, inflation, unemployment, population, ...) for a country over recent years | World Bank |
| `country_profile` | A snapshot of a country's key macro indicators, latest values | World Bank |
| `compare_countries` | Rank one indicator across several countries | World Bank |
| `us_series` | Key US time series: unemployment, CPI, nonfarm payrolls, participation, earnings | US BLS |
| `list_indicators` | Discover every indicator and series this server supports | — |

No API keys required.

## Quick start

```
claude mcp add --transport http economy-intel https://economy.datakoot.com/mcp
```

Or point any MCP client at `https://economy.datakoot.com/mcp`.

## Grounded, verifiable forecasting

economy-intel is not just data in — it is meant to improve what an agent
concludes. To show that, [`examples/`](examples/) has a small, legible agent that
calls this server's `us_series` mid-task, projects the next macro print against
the market consensus with the arithmetic shown, and submits it to
[Headline Arena](https://headlinearena.com) — a public arena where AI-agent
forecasts are scored against reality and the calibration is checkable by anyone.

The live version runs the loop the arena's maintainer asked for: it wakes on the
data-release calendar, discovers the open macro challenges, grounds each one it
can in official US series, and posts a forecast with its reasoning — while
**skipping the challenges it cannot honestly ground** (PPI, PMI, the FOMC rate —
anything economy-intel does not serve) instead of guessing. Post on signal, not
on a clock.

The point is not a clever model. It is that the inputs are official (World Bank,
US BLS), the reasoning is transparent, and the record is public. Run the example
yourself — no account, no cost:

```
python3 examples/datakoot_macro_agent.py cpi
```

## Data & attribution

Country data comes from the [World Bank Open Data](https://data.worldbank.org) API (CC-BY 4.0); US series come from the [US Bureau of Labor Statistics](https://www.bls.gov) public data API (US public domain). Informational only.

Part of [Datakoot](https://datakoot.com) — keyless intelligence APIs for AI agents.
