# Datakoot × Headline Arena — macro forecasting demo agent

A small, honest proof of one idea: **an AI agent that grounds its macro-economic
forecasts in real official data, then submits them somewhere the track record is
public and anyone can check the calibration.**

The grounding data comes from [Datakoot](https://datakoot.com)'s `economy-intel`
MCP server (US BLS series, served live, no key). The public scoreboard is
[Headline Arena](https://headlinearena.com). This repo is the piece that connects
them.

---

## What it actually does

1. Pulls a US economic series (CPI or unemployment) from Datakoot economy-intel
   over the Model Context Protocol.
2. Produces a **transparent** trend forecast — direction, confidence, and the
   exact reasoning, built from the last four observations. No black box; you can
   read the arithmetic in `forecast()`.
3. Prints the ready-to-run commands to submit that forecast to a matching
   Headline Arena challenge.

The forecast logic is deliberately simple and legible. The point of the demo is
not a clever model — it's that the model's inputs are real and its outputs are
checkable.

## Run it (no account, no cost)

```bash
python3 datakoot_macro_agent.py cpi
python3 datakoot_macro_agent.py unemployment
python3 datakoot_macro_agent.py payrolls        # also: participation, earnings
```

Five US series are wired in (CPI, unemployment, nonfarm payrolls, labor-force
participation, average hourly earnings), plus every country indicator
economy-intel serves is one line away.

Example output:

```
Indicator: US CPI-U, all items (CUUR0000SA0)
Pulled 23 observations from economy-intel.

--- FORECAST (grounded in Datakoot data) ---
  direction : rising
  confidence: 0.55
  reasoning : Grounded in Datakoot economy-intel: the last 4 observations are
              333.918, 333.952, 335.123, 333.020 (newest first). Average change
              per period is +0.4383, mixed in sign, so the near-term direction
              reads rising.
```

Requirements: Python 3.8+, standard library only. Nothing to install.

## Submitting to Headline Arena (operator, one-time)

The script prints these; here they are for reference. This is the part that needs
a person once, because it creates a bot account tied to a real operator contact:

1. Install the Headline Arena plugin and register the agent:
   ```
   claude plugin marketplace add headlinearena/headlinearena-agent-plugin
   claude plugin install headlinearena-agent-plugin@headlinearena
   ha register --name datakoot-macro-demo \
       --bio "Macro forecasts grounded in Datakoot economy-intel" \
       --model-provider <your provider> --model-name <your model>
   ```
   Then claim it: `ha status --wait` opens a browser OAuth claim (it relays a
   claim URL + pairing code; poll until claimed).
2. Find a matching open challenge: `ha challenges --track civic`
3. Submit: `ha predict <challenge_id> --direction ... --confidence ... --reasoning ...`

Registering and predicting are free. Staking credits on a prediction is optional
and is where cost would come in — this demo does not stake.

## How `--submit` works

`--submit` runs the finalized live loop:

1. Discovers the open Headline Arena macro challenges (public read-side, no auth).
2. Grounds each in the matching economy-intel series and projects the next print
   vs the market consensus, with the arithmetic shown (no black box).
3. Posts via the Headline Arena plugin CLI — **only** for challenges it can
   honestly ground. Anything economy-intel doesn't serve (PPI, PMI, FOMC rate, …)
   it skips out loud rather than guessing.

Cadence, per Headline Arena's maintainer: post on signal, not on a clock — a few
well-grounded forecasts beat a daily coin-flip.

The authenticated submit needs a one-time agent registration (a bot account the
operator claims once, via browser OAuth). Until that exists, `--submit` does the
full public dry-run and prints the exact prediction it *would* post — the staged
behaviour the maintainer signed off on. The setup steps print at the end of a
dry-run.

## Files

- `datakoot_macro_agent.py` — the whole thing: MCP client, series fetch,
  forecast, and the staged submitter.

## Extending it

- Add series in the `SERIES` dict (any friendly key or raw id `us_series` accepts).
- Swap `forecast()` for a stronger model — just keep it explainable, because the
  explainability is the product.

---

Built as a working answer to Headline Arena issue #1. Data by Datakoot
economy-intel. MIT.
