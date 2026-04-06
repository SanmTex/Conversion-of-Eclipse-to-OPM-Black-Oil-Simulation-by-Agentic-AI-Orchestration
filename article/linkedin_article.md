# Agentic AI as a Key to the Vault: Unlocking Legacy Eclipse Reservoir Models for Open-Source Simulation at Scale

---

There are tens of thousands of reservoir simulation models sitting in the industry right
now that nobody is running.  They are locked inside commercial software environments —
Eclipse, tNavigator, CMG — that cost $50,000 to $150,000 per seat per year.  The models
themselves are valuable: years of geological interpretation, history matching, and
engineering calibration embedded in a DATA file. But the physics inside that file is
inaccessible to anyone without the right licence on the right machine.

OPM Flow has been able to read Eclipse DATA decks natively for several years.  It runs on
commodity hardware — a standard workstation or a laptop — uses CPU rather than GPU, and
carries no licence cost.  The technical capability to unlock those models has existed.
What has not existed, until now, is a practical workflow for doing it at scale.

The barrier was never OPM's physics.  The barrier was the overhead.  A real-world
commercial model is not a clean textbook input.  It has Eclipse-specific keywords that OPM
does not recognise, aquifer connection blocks that reference inactive cells, proprietary
identifiers throughout, and outputs that sit on a slightly different time axis than the
reference.  Resolving those issues for a single model might take a senior reservoir engineer
half a day of trial and error followed by three to five days of careful output comparison.
Multiply that by a portfolio of 30 models and the project becomes a programme — one that
rarely gets resourced because the commercial alternative, however expensive, is simply
faster to keep paying for.

Agentic AI changes that equation.  Not by making OPM better — OPM is already good — but
by making the conversion workflow fast enough, cheap enough, and reproducible enough to
run at scale.  What I built here is a sequence of seven autonomous agents that take a
legacy Eclipse model, convert it, validate every output against the commercial reference,
run a forward prediction, and package the results.  Total engineer time: about 30 minutes
to configure and review.  Total compute cost: a CPU and an afternoon.

---

## Where this actually changes the economics: three scenarios

The workflow is a means, not an end.  Before getting into how it works, it is worth
being concrete about the situations where removing the licence barrier actually matters.

**Virtual data rooms during asset transactions.** When a buyer's technical team reviews an
asset in a VDR, they typically get access to the simulation files but not the software to
run them.  Eclipse licences are not portable and the seller's IT environment is closed.
With OPM, the buyer's team can run the model on their own hardware — a laptop with WSL is
sufficient — within the VDR period.  That means running sensitivities on the seller's
forecast, stress-testing their assumptions, and forming an independent view on reserves
before exclusivity.  Today, many buyers are limited to reading the static outputs the seller
chose to share.  That is a material information asymmetry that OPM can close.

**Post-acquisition data harmonisation.** After an acquisition, an operator inherits models
built in whatever simulators the previous owner used.  Portfolios of 20 or 30 models in
mixed platforms — Eclipse, tNavigator, older Petrel versions — are common.  Re-running
everything in a single commercial environment means purchasing licences and converting
models, often a six-to-twelve month project.  OPM provides a bridge: run the inherited
Eclipse decks as-is, extract consistent outputs, and integrate the results into the new
operator's portfolio reporting immediately.  The legacy models do not need to be converted
— they just need to be validated once.

**Independent regulatory and reserves audit.** National oil companies and regulators in a
growing number of jurisdictions are moving toward independently reproducible simulation
runs as part of field development plan submissions or reserves certification.  A commercial
simulator is a black box to the regulator: they can see inputs and outputs but not the
solver.  OPM's open-source codebase changes that.  A technically capable third party can
inspect not just what the model says but how the mathematics were applied.  For
technically complex submissions — gas reservoir depletion, complex aquifer behaviour, EOR
schemes — that level of transparency is increasingly being asked for.

---

## The approach: what the agents did and why

The workflow runs seven Python scripts, each invoked in sequence by an orchestrator.
Every agent writes its outputs to a shared directory and reads its inputs from the same
place.  Nothing is passed in memory between agents — only files.  This design means any
agent can be re-run in isolation for debugging, and the workflow can be interrupted and
resumed at any step.

**Agent 1 — Environment check.**  Before committing time to a 90-minute simulation run,
the first thing the agent does is verify that OPM Flow is installed (`wsl flow --version`),
that all required Python packages are importable, and that the DATA file exists at the
configured path.  This is a fail-fast check.  The reason it exists as a separate agent
rather than being part of the run step is that environment failures have a completely
different character from simulation failures — they are fixed by installing software, not
by editing the model — and surfacing them immediately saves the user from waiting through
a long run only to hit an import error at the end.

**Agent 2 — Run OPM Flow.**  The agent constructs the OPM command with two flags that are
non-obvious but important.  `--parsing-strictness=low` tells OPM to accept Eclipse keywords
it does not recognise rather than aborting — without it, the simulator exits immediately on
the first unknown keyword, which for a real-world commercial model is usually within the
first 50 lines.  `--max-single-precision-days=0` forces double-precision arithmetic
throughout; OPM's default is to switch to single precision after a threshold, which
degrades pressure accuracy by roughly 0.1% — acceptable for rough screening but
problematic for a rigorous cell-level validation.  The agent streams the PRT output
line-by-line as the run progresses so the user can watch convergence in real time.

**Agent 3 — Parse and align outputs.**  This is where most of the technical complexity
lives.  OPM and Eclipse produce their output on slightly different time axes: OPM's
UNSMRY integration accumulates floating-point rounding differently from Eclipse's, and the
INTEHEAD date integers in the UNRST binary need to be decoded and matched to Eclipse's
restart schedule.  The agent handles both — linearly interpolating the OPM UNSMRY vectors
onto Eclipse's 127-point time axis, and matching UNRST reports by calendar date.  It then
serialises everything to a single `.npz` file.  The reason for serialising rather than
keeping arrays in memory is that downstream agents need to be restartable: if the
visualisation step fails, you do not want to re-run the parser.

**Agent 4 — Metrics.**  R² alone is not enough.  A simulator that produces systematically
10% higher values with perfect shape gets R²=1.0 but is physically wrong.  The agent
computes three statistics for every matched mnemonic: R² (shape), RMSE (absolute
magnitude), and P95 absolute error (the worst 5% of timesteps — often where the
operationally important behaviour lives).  Everything goes to a CSV.  The pass criterion
is R² >= 0.99: tight enough to be meaningful, lenient enough to account for the genuine
algorithmic differences between the two solvers.

**Agent 5 — Visualise.**  Four figure types are generated automatically: field-level rate
and cumulative comparisons, a pass-rate dashboard by category (field, well, aquifer,
region/block), a cell-level pressure scatter plot, and per-well rate panels.  The reason
to automate the figures — rather than generating them manually once — is reproducibility.
If the model is updated or re-run, the figures regenerate from the same code with no
manual intervention.  They are the visual contract between the simulation outputs and the
published results.

**Agent 6 — Build clean OPM deck.**  The original DATA file was exported from a commercial
modelling environment and contains Eclipse-specific keywords that OPM does not use:
licence block declarations, memory hints, deprecated VFP formatting.  The agent removes
these, adds OPM-oriented section headers, and writes a cleaner version of the deck that
runs in OPM without any command-line workarounds.  This is the version that would go to a
colleague or a regulator — a deck that makes the simulator's expectations explicit.

**Agent 7 — Predict forward.**  Once validation is established, the natural question is
what happens next.  The agent extends the schedule by three years beyond the historical
end date, runs OPM on the extended deck, and generates the headline comparison figure: the
full 10.5 years of Eclipse history, the OPM validation match overlaid on the same period,
and the OPM-only prediction for the next three years.  No new wells, no reservoir
management changes — a pure extrapolation of the final well constraints into an undrilled
future.  The point is not to claim the prediction is reliable, but to demonstrate that the
simulator remains stable and physically plausible beyond the validated window.

**Time savings.**  A thorough manual validation of this model — patching the DATA deck,
running the simulation, exporting and aligning outputs, computing statistics across 200+
mnemonics, building comparison figures, writing a results summary — takes a senior
reservoir engineer roughly three to five working days.  The agent workflow runs in about
four to five hours on a modern laptop (most of that is the OPM simulation itself), with
perhaps 30 minutes of engineer time to configure, review, and interpret.  That is not a
replacement for the engineer's judgement — it is an elimination of the mechanical assembly
work that does not require it.

---

## Results

The headline number: **92% of all output mnemonics match Eclipse at R² >= 0.99.**

![Field production comparison with forward prediction](../output/figures/field_comparison_with_prediction.png)

*Figure 1: Eclipse reference (solid blue), OPM validation match (dashed red), and OPM
3-year forward prediction (dotted green).  The shaded region shows the prediction period
beyond the historical end date.  Oil, water, and gas field rates shown.*

Cell-level pressure and saturation match at R² > 0.9999.  If you plot 114,768 cells of
OPM pressure against Eclipse pressure at any timestep, the points fall on the 1:1 line
with a scatter of roughly 2 psia — less than the uncertainty in most pressure transient
analyses.  Aquifer influx volumes match exactly.

![Pass rate dashboard](../output/figures/pass_rate_dashboard.png)

*Figure 2: Pass rate by output category.  Well-level metrics show 92% pass rate across
10 wells and 15 mnemonics per well.*

The 8% that do not pass are almost entirely gas lift injection rates (WGLIR) for wells
where gas lift is active.  Both simulators are internally consistent on these — OPM and
Eclipse each satisfy the well's tubing head pressure constraint self-consistently, but they
converge to different stable operating points on the multiphase VFP curve.  This is a
known behaviour difference between the two optimisers, not a physics error, and it does
not propagate to the field-level production rates that matter most for reserves estimation.

The forward prediction runs stably and produces physically plausible output: gradual
pressure decline, water cut continuing to increase, gas rates responding to the reduced
reservoir pressure.  Nothing novel — but nothing physically unreasonable either, which is
exactly what a validated free-running simulator should produce.

---

## The old way and the new way

The old way of working this problem looks like this: the engineer opens the DATA file in a
text editor, manually patches keywords until OPM stops crashing, runs the simulation, opens
the outputs in a post-processing tool, exports to CSV, copies into a spreadsheet, builds
comparison charts by hand, and writes a memo.  That process works.  It has always worked.
And it produces something the commercial workflow cannot — an engineer who has read every
line of the DATA deck, understands why each keyword is there, and has developed an
intuitive feel for where the model is sensitive and where it is not.  That kind of
understanding is real and it matters.

The new way automates everything up to the interpretation step.  The engineer configures a
JSON file, runs one command, and gets a validated results package — CSV, figures, and a
clean deck — in a few hours.  The workflow is reproducible: a colleague anywhere with OPM
and Python can regenerate the exact same results from the same inputs.  It is transferable:
the agents document their own reasoning in code, not in someone's institutional memory.

What might be lost in the transition is that enforced familiarity with the model.  When the
process is manual, the engineer has to confront every quirk of the DATA deck.  When it is
automated, there is a risk of treating the output as a black box and missing the physics
insight buried in the non-passing mnemonics.  The right response to that risk is not to
avoid automation.  It is to treat the agent output as the starting point for engineering
judgement — not the end of it.

---

## Run it yourself

The full workflow is available on GitHub: [link to repository]

Clone the repo, obtain the binary data files (instructions in `data/README_DATA.md`), set
your config, and run `python agents/orchestrator.py`.  The README covers prerequisites,
and the notebook version (`notebooks/OPM_Validation.ipynb`) walks through each step with
explanations if you prefer a more interactive approach.

---

If you have a portfolio of legacy Eclipse models and are weighing the cost of continued
commercial licences, considering an OPM migration, or need a reproducible validation
workflow for a technical submission or acquisition — this is a practical starting point.
I am happy to discuss what that looks like for your specific situation.  Connect on
LinkedIn if it is relevant to work you are doing.
