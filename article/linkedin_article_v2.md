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
to configure and review.  Total compute cost: a CPU and 37 minutes.

---

## Where this actually changes the economics: three scenarios

The workflow is a means, not an end.  Before getting into how it works, it is worth
being concrete about the situations where removing the licence barrier actually matters.

**Virtual data rooms during asset transactions.**  When a buyer's technical team reviews an
asset in a VDR, they typically get access to the simulation files but not the software to
run them.  Eclipse licences are not portable and the seller's IT environment is closed.
With OPM, the buyer's team can run the model on their own hardware — a laptop with WSL is
sufficient — within the VDR period.  That means running sensitivities on the seller's
forecast, stress-testing their assumptions, and forming an independent view on reserves
before exclusivity.  Today, many buyers are limited to reading the static outputs the seller
chose to share.  That is a material information asymmetry that OPM can close.

**Post-acquisition data harmonisation.**  After an acquisition, an operator inherits models
built in whatever simulators the previous owner used.  Portfolios of 20 or 30 models in
mixed platforms — Eclipse, tNavigator, older Petrel versions — are common.  Re-licensing
or standardising onto one commercial platform takes months and costs.  OPM provides a
bridge: run the inherited Eclipse decks as-is, extract consistent outputs, and integrate
the results into the new operator's portfolio reporting immediately.  The legacy models do
not need to be converted — they just need to be validated once.

**Independent regulatory and reserves audit.**  National oil companies and regulators in a
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

**Agent 1 — Environment check.**  Before committing time to a simulation run, the first
thing the agent does is verify that OPM Flow is installed (`wsl flow --version`), that all
required Python packages are importable, and that the DATA file exists at the configured
path.  This is a fail-fast check.  The reason it exists as a separate agent rather than
being part of the run step is that environment failures have a completely different
character from simulation failures — they are fixed by installing software, not by editing
the model — and surfacing them immediately saves the user from waiting through a long run
only to hit an import error at the end.

**Agent 2 — Run OPM Flow.**  The agent constructs the OPM command with two flags that are
non-obvious but important.  `--parsing-strictness=low` tells OPM to accept Eclipse keywords
it does not recognise rather than aborting — without it, the simulator exits immediately on
the first unknown keyword, which for a real-world commercial model is usually within the
first 50 lines.  `--max-single-precision-days=0` forces double-precision arithmetic
throughout; OPM's default is to switch to single precision after a threshold, which
degrades pressure accuracy.  The agent streams the PRT output line-by-line as the run
progresses so the user can watch convergence in real time, and writes a convergence
summary (Newton iterations per timestep, retried steps) to a JSON file for the
performance dashboard.

**Agent 3 — Parse and align outputs.**  This is where most of the technical complexity
lives.  OPM and Eclipse produce their output on slightly different time axes: OPM's
UNSMRY integration accumulates floating-point rounding differently from Eclipse's, and the
INTEHEAD date integers in the UNRST binary need to be decoded and matched to Eclipse's
restart schedule.  The agent handles both — linearly interpolating the OPM UNSMRY vectors
onto Eclipse's 127-point time axis, and optionally loading Eclipse's UNRST binary for
cell-level comparison if supplied.  It then serialises everything to a single `.npz` file.
The reason for serialising rather than keeping arrays in memory is that downstream agents
need to be restartable: if the visualisation step fails, you do not want to re-run the
parser.

**Agent 4 — Metrics.**  R² alone is not enough.  A simulator that produces systematically
10% higher values with perfect shape gets R²=1.0 but is physically wrong.  The agent
computes R², RMSE, P95 absolute error, MAPE (for cumulative vectors where near-zero values
do not distort the percentage), normalised bias (as a percentage of the Eclipse mean), and
within-tolerance rate.  Everything goes to a CSV.  The pass criterion is R² >= 0.99: tight
enough to be meaningful, lenient enough to account for the genuine algorithmic differences
between the two solvers.

**Agent 5 — Visualise.**  Five figures are generated automatically: the field rate and
cumulative comparison with forward prediction, a concordance scatter for each field-level
rate vector, cell-level error distributions, an AI/ML metrics dashboard, and a pipeline
performance dashboard.  The reason to automate the figures — rather than generating them
manually once — is reproducibility.  If the model is updated or re-run, the figures
regenerate from the same code with no manual intervention.

**Agent 6 — Build clean OPM deck.**  The original DATA file was exported from a commercial
modelling environment and contains Eclipse-specific keywords that OPM does not use:
licence block declarations, memory hints, deprecated VFP formatting.  The agent removes
these, adds OPM-oriented section headers, and writes a cleaner version of the deck that
runs in OPM without any command-line workarounds.

**Agent 7 — Predict forward.**  Once validation is established, the natural question is
what happens next.  The agent extends the schedule by one year beyond the historical end
date, runs OPM on the extended deck, and generates the headline comparison figure: the
full 10.5 years of Eclipse history, the OPM validation match overlaid on the same period,
and the OPM-only prediction for the following year.  No new wells, no reservoir management
changes — a pure extrapolation of the final well constraints into an undrilled future.
Cumulative volumes are plotted on a secondary axis to show the integrated production
trajectory alongside the instantaneous rates.

**Time savings.**  A thorough manual validation of this model — patching the DATA deck,
running the simulation, exporting and aligning outputs, computing statistics across 200+
mnemonics, building comparison figures, writing a results summary — takes a senior
reservoir engineer roughly three to five working days.  The agent workflow completed in
37 minutes on a standard laptop: 35 minutes of OPM simulation compute running locally on
CPU, and under two minutes for all seven Python agents combined.  That is not a
replacement for the engineer's judgement — it is an elimination of the mechanical assembly
work that does not require it.

---

## Results

The headline number: **89% of all output mnemonics match Eclipse at R² >= 0.99**
(72 of 81 matched vectors).

![Field production comparison with forward prediction](../output/figures/field_comparison_with_prediction.png)

*Figure 1: Eclipse reference (solid blue), OPM validation match (dashed red), and OPM
1-year forward prediction (dotted green with shaded band).  Instantaneous rates on the
primary axis; cumulative volumes on the secondary axis.  The vertical line marks the end
of the validation period.  Oil, water, and gas field vectors shown.*

The concordance plot below shows each of the 127 report timesteps as a single point,
plotted OPM against Eclipse, coloured by simulation time.  Points lying on the 1:1 line
indicate perfect agreement.  The gas rate (R²=0.999) is effectively indistinguishable from
perfect; the oil rate (R²=0.995) and water rate (R²=0.982) show slight scatter, consistent
with the solver-level differences described below.

![Time-series concordance scatter](../output/figures/timeseries_1to1_scatter.png)

*Figure 2: OPM vs Eclipse at each of the 127 report timesteps for oil, water, and gas
field production rates.  Colour indicates simulation time (early = purple, late = yellow).
R² values annotated per panel.*

The AI/ML metrics dashboard below shows three complementary perspectives on match quality.
MAPE is reported only for cumulative volumes, where percentage errors are meaningful: FOPT
at 1.5%, FWPT at 1.3%, and FGPT at 0.5% — all comfortably below the 2% engineering
threshold.  The bias panel shows that OPM consistently under-predicts oil and water
production rates by approximately 4–6%, while gas rate bias is negligible.  The
within-tolerance panel shows the percentage of timesteps where rates fall within 2% of
Eclipse: water achieves 75%, oil and gas 52–65%, reflecting that rate differences are
concentrated at low-production periods where small absolute errors translate to large
percentages.

![AI/ML validation metrics](../output/figures/metrics_visual.png)

*Figure 3: Three validation metrics across field production vectors.  Top: MAPE for
cumulative volumes only (rates excluded — unreliable near zero production).  Centre:
normalised mean bias error as a percentage of the Eclipse mean.  Bottom: percentage of
timesteps within 2% of Eclipse.*

Cell-level pressure and saturation error distributions confirm that the 3D physics are
being solved consistently.  The distributions shown below are computed across all 114,768
active cells and 61 restart timesteps.  Pressure residuals are centred near zero with a
standard deviation of approximately 2 psia — less than the uncertainty in most pressure
transient analyses.  Saturation residuals are tighter still.

![Cell-level error distribution](../output/figures/cell_error_distribution.png)

*Figure 4: Histograms of OPM minus Eclipse residuals across all cells and timesteps for
pressure, water saturation, and gas saturation.  Dashed line at zero; solid line shows
the mean; orange curve is the normal distribution fit.*

The 11% that do not pass at R²=0.99 are almost entirely gas lift injection rates (WGLIR)
for the three wells where gas lift is active, plus water rate (WWPR) for two of those same
wells.  Both simulators are internally consistent on these — OPM and Eclipse each satisfy
the well's tubing head pressure constraint self-consistently, but they converge to different
stable operating points on the multiphase VFP curve.  This is a known behaviour difference
between the two optimisers, not a physics error, and it does not propagate to the
field-level production rates that matter most for reserves estimation.  Field gas production
rate and total (FGPR, FGPT) pass at R²=0.999 and R²=1.000 respectively, confirming that
the gas lift optimiser difference is local to the well level.

The forward prediction runs stably and produces physically plausible output: rates
continuing their decline trajectory, cumulatives accumulating at a consistent pace.
Nothing novel — but nothing physically unreasonable either, which is exactly what a
validated free-running simulator should produce.

The pipeline performance dashboard below captures the full workflow economics.

![Agent pipeline performance dashboard](../output/figures/agent_performance.png)

*Figure 5: Left — runtime for each of the seven agents; the two OPM simulation runs
(validation and 1-year prediction) run entirely on local CPU with no token consumption.
Right — OPM solver behaviour: 86.2% of timesteps solved on the first Newton attempt;
the remaining 13.8% were retried after automatic step-size halving and subsequently
converged.*

---

## The old way and the new way

The old way of working this problem looks like this: the engineer opens the DATA file in a
text editor, manually patches keywords until OPM stops crashing, runs the simulation, opens
the outputs in a post-processing tool, exports to CSV, copies into a spreadsheet, builds
comparison charts by hand, and writes a memo.  That process works.  It has always worked.
And it produces something the automated workflow cannot — an engineer who has read every
line of the DATA deck, understands why each keyword is there, and has developed an
intuitive feel for where the model is sensitive and where it is not.  That kind of
understanding is real and it matters.

The new way automates everything up to the interpretation step.  The engineer configures a
JSON file, runs one command, and gets a validated results package — CSV, figures, and a
clean deck — in under 40 minutes.  The workflow is reproducible: a colleague anywhere with
OPM and Python can regenerate the exact same results from the same inputs.  It is
transferable: the agents document their own reasoning in code, not in someone's
institutional memory.

What might be lost in the transition is that enforced familiarity with the model.  When the
process is manual, the engineer has to confront every quirk of the DATA deck.  When it is
automated, there is a risk of treating the output as a black box and missing the physics
insight buried in the non-passing mnemonics.  The right response to that risk is not to
avoid automation.  It is to treat the agent output as the starting point for engineering
judgement — not the end of it.

---

## Run it yourself

The full workflow is available on GitHub: https://github.com/SanmTex/Conversion-of-Eclipse-to-OPM-Black-Oil-Simulation-by-Agentic-AI-Orchestration

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
