# New pipeline: technical log (collection 2026-10-05)

Technical log of steps and decisions, in the order they were made; the clean summary is FINAL_RESULTS.md. Methods follow the thesis; data are freshly collected; no manual edits.
Tables: `reports/tables/new_*.csv`. Funnel: `reports/sample_funnel.csv`.

## Sample
- Tally: 7,864 organizations -> 3,234 with proposals -> 2,295 non-test -> 743 with a mainnet token
  -> 636 DAOs (distinct token contracts) -> 80 tickers in CryptoCompare -> 69 one contract per ticker
  -> **54 DAOs** after the supply check (42 automatic, 12 accepted by the author).
- Daily prices: 46 DAOs + BTC (8 tokens have no USD market in CryptoCompare). Jan 2021 - Sep 2026.
- Market cap: valid for 25 DAOs only. 18 quotes are stale (no update within 30 days), 10 have no
  market cap, 1 supply mismatch. [FACT] CryptoCompare covers small DAO tokens poorly in 2026.
- Events: 2,748 proposals -> 1,806 with a complete [-5,+5] price window, 35 DAOs, 1,391 unique event dates.

## Legacy errors found while collecting [FACT]
Besides LEND, the thesis matched several tickers to the wrong project: STRK (Strike vs Starknet),
UP (Unlock vs Superform), KITE (HAI vs Kite, $2.0B), GUILD, RING, ESS, ZEN, GAS, UNION, EYE.
The new pipeline rejects them by name and supply checks.

## Results (preliminary)
- H1 (redesigned 2026-10-06; tables `new_h1_*.csv`). Size: FDV of live tokens (main, N = 28),
  CryptoCompare market cap (N = 24), FDV averaged over trading life (N = 44).
  [FACT] Live FDV, N = 28: no governance measure that is free of the delegate count is related to
  size (ln HHI rho -0.12, 95% CI [-0.48, 0.26]); the minimum detectable |rho| at 80% power is 0.51,
  so moderate effects (thesis: -0.25) cannot be ruled out.
  [FACT] Life-average FDV, N = 44: ln HHI rho -0.29 (p 0.05), top-10 share -0.41 (p 0.01); OLS
  ln HHI -0.92 (SE 0.38, p 0.02). Adding ln(delegates) turns it to -0.10 (p 0.81) while
  ln(delegates) is 0.45 (p < 0.01). Delegates and holders correlate with size at about 0.5-0.6.
  [HYPOTHESIS] Larger DAOs are less concentrated because they have more delegates; given the
  delegate base, concentration is unrelated to size. Participation and Q ratio divide by the
  delegate count, so their correlation with size is partly mechanical.
- H2 (DAOs with >= 12 months of returns; tables `new_h2_*.csv`). M1-M3 (N = 30-43): no governance
  variable significant. M4 adds size as ln(FDV, live tokens) instead of the thesis ln(market cap):
  N = 19, ln HHI 0.027 (SE 0.016, p 0.09), ln FDV 0.015 (p 0.002) (after the 2026-10-06 fixes); with
  N = 19 and 4 regressors this is not interpreted. BTC-adjusted dependent variable in the same table (dep = avg_excess_return).
- H3 (tables `new_h3_summary.csv`, `new_h3_robust.csv`). CAR[-5,+5] -1.89% (1,806 proposals, 35 DAOs).
  [FACT] Raw CAR is negative in every sample with DAO and DAO x month clustering (p < 0.01), but raw
  CAR includes the general underperformance of DAO tokens against BTC.
  [FACT] Excess CAR over each DAO's own baseline (mean CAR of its event-free 11-day windows):
  proposals -1.70% (p 0.07 clustered by DAO, 0.09 two-way); unique event dates -1.91% (0.04 / 0.06);
  non-overlapping event dates (736) -1.46% (0.14 / 0.17); DAO-level tests p 0.09-0.19.
  [FACT] Placebo tests that draw windows independently give p 0.00-0.07, but they ignore that events
  cluster in calendar time; the clustered tests are the conservative reference.
  [HYPOTHESIS] Point estimates suggest about -1.5% to -2% over 11 days beyond the own baseline, but the
  evidence is weak and not robust to overlap and clustering. The thesis placebo result (p 0.87) came
  from comparing differently weighted quantities.
- H4 (revised 2026-10-06, `new_h4_panel.csv`). All 45 DAOs: BTC beta 0.91 (SE 0.06 clustered), R2 0.14.
  Nested models on a common sample (scale-free spec, 27 DAOs, 1,108 DAO-months): R2 0.259 (BTC)
  -> 0.262 (+ ln HHI, ln delegates) -> 0.272 (+ ln FDV). Governance adds 0.003 to R2. Inference with
  cluster SE, t(G-1) and wild cluster bootstrap (999 reps): no governance variable significant in M2.
  In M3, ln HHI is significant only conditional on size (wild p 0.04; thesis-like spec 20 DAOs: 0.13).
  [HYPOTHESIS] Not interpretable: size is measured at the end of the sample, so tokens that rose have
  a high end-of-sample FDV; the size control is mechanically related to past returns (the thesis had
  the same issue with market cap at the collection date). A size measure dated at the start of each
  token's return history would fix this.

## Specification changes vs the thesis
| Test | Thesis | New pipeline |
|---|---|---|
| Sample | 65 DAOs, ticker matching (10 wrong tokens) | 54 DAOs, ticker + name + supply check |
| Imputation | means for missing / invalid values | none; complete cases, reasons recorded |
| H1 size | CryptoCompare market cap | FDV of live tokens (main); market cap and life-average FDV (robustness) |
| H1 governance | ln HHI, ln participation, ln Q ratio | measures free of the delegate count (HHI, top-k, Nakamoto, Q, turnout); participation and Q ratio kept for comparison |
| H1 inference | HC3, Spearman, bootstrap | same, plus 95% CI and power for every correlation; controls ln delegates, age, chain |
| H2 | 59 DAOs incl. < 12 months; M4 control ln market cap | >= 12 months applied; M4 control ln FDV |
| H3 main | proposal-weighted CAR vs DAO-equal placebo (100 reps) | excess CAR over each DAO's own baseline; DAO and DAO x month clustering; non-overlapping sample; placebo 1,000 reps with matching weights |
| H4 | HC3 | HC3 and DAO-clustered SE |
| Period | Jan 2021 - May 2026 | Jan 2021 - Sep 2026 |

## Data handling decisions (no imputation)
- Participation > 1 (voters are historical, delegatesCount is today's): set missing (Flayer).
- Turnout = votes cast / token supply; above 1 means different units (YAM, rebasing): set missing.
- Q status (`q_status`, after fixes 1-2): reached 38; quorum exceeds all delegated votes 11 (quorum is a
  plausible 2-25% of supply, but current delegation is 0.0002-8% of supply: not a unit error); implausible
  quorum units 2 (YAM, rebasing token; Optimism pool governor); no delegation data 2 (OOKI, Venus); no quorum 1. Q is missing unless reached. Arbitrum Core: quorum 25% of supply per Tally
  (quorumNumerator 5000/10000), to be checked against the contract.
- FDV above 100 billion USD is set missing as implausible (OOKI: 5.7e15 tokens in both Tally and
  CryptoCompare, life-average FDV 572 trillion USD).

## Update 2026-10-06
- H1 with controls (ln delegates, token age, Ethereum mainnet; model M5 in `new_h1_ols.csv`): ln HHI is
  insignificant for every size measure (p 0.47-0.62); ln(delegates) is the only predictor close to
  significance (p 0.02-0.06).
- [FACT] Quorum capture (updated after fixes 1-2 below): in 24 of the 38 DAOs whose quorum is reached, the single largest delegate's
  current voting power exceeds the quorum of the most recent concluded proposal (median quorum 24% of
  delegated votes, median top-1 share 38%); active DAOs: 14 of 23. Includes Aave, ENS, Compound, Ondo, Gitcoin. Caveat:
  current voting power vs the latest quorum; a proposal also needs a majority of votes cast.
- Figures (`reports/figures/`, PNG and PDF, 300 dpi):
  Figure 2 `figure2_governance_distributions`: HHI, top-10 share, participation, Q.
  Figure 3 `figure3_placebo`: placebo distributions of the mean CAR (1,000 reps) with the observed CAR;
  panel (b) also marks the thesis comparison (DAO-equal placebo vs proposal-weighted CAR). Note for the
  caption: placebo draws are independent and ignore calendar clustering; see `new_h3_robust.csv`.

## Fixes 2026-10-06 (external review; each verified before changing)
1. Governor selection: ties on primary flag and delegated votes are now broken by the most recent
   concluded proposal, then proposal count; test governors excluded. 9 DAOs changed governor
   (`reports/governor_selection_changes.csv`), e.g. Compound: deprecated Alpha -> Compound Governor
   (0x309a862b...); Optimism: a governor named "test" -> Optimism_pool. Optimism's main governance
   runs outside Tally (Agora), so Tally offers no better OP governor; OP results are limited.
2. Quorum = median of the last 5 concluded proposals; passed proposals with total votes cast below
   their quorum are flagged as data errors and excluded (1 case: Arbitrum 2026-05-28, quorum 2.46e27
   vs about 2.1e26 before). Q changed for 6 DAOs (`reports/q_status_changes.csv`).
3. Activity: `active_12m` = at least one concluded proposal in the 12 months before collection:
   25 of 54 DAOs. H1 and quorum capture reported for all and for active DAOs (`sample` column).
   Active DAOs, CryptoCompare market cap: ln HHI rho -0.65 (p 0.03) but N = 11; live FDV N = 14:
   -0.42 (p 0.14). Too few observations to change the conclusion.
4. Dormancy: `dormancy_ratio` = largest votes cast in any past proposal / current delegated votes.
   Above 1 for 18 of 51 DAOs: delegation has shrunk since past votes, so today's snapshot understates
   historical participation for a third of the sample.
5. `reports/paper_numbers.tex`: 708 \newcommand macros for every cited number, generated by
   run_all.py. Use \input{paper_numbers} in the paper; do not type numbers by hand.
