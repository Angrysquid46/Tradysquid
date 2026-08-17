# Meta-Model Results (Phase 6)

Trained on **317,910 labelled bars** from the Phase 2 feature store. Every figure below is **out-of-sample** under purged, embargoed, session-level splits - a model is never scored on a session it trained on, and whole sessions are dropped either side of each test block so a label's forward horizon cannot leak into training.


## Labels

Triple-barrier: an up barrier, a down barrier and a time limit, labelled by whichever is hit first. A bar that ends higher after a deep dip is a loss for anyone with a stop, and fixed-horizon labelling would call it a win.

| Label | Bars |
|---|---|
| NO_TRADE | 256,807 |
| DOWN | 33,361 |
| UP | 27,742 |

## Directional model, per fold

| Fold | Train | Test | Base rate | Accuracy | Brier |
|---|---|---|---|---|---|
| 1 | 43,047 | 17,987 | 0.470 | 0.519 | 0.2550 |
| 2 | 47,730 | 13,167 | 0.491 | 0.507 | 0.2518 |
| 3 | 47,042 | 13,781 | 0.425 | 0.571 | 0.2451 |
| 4 | 44,923 | 16,168 | 0.431 | 0.544 | 0.2497 |

Baseline Brier from always predicting the base rate: **0.2479**. A model only adds value below that number - accuracy alone can beat 50% purely by following the majority class.


## Calibration

Expected calibration error: **0.0235**

| Bin | n | Predicted | Observed | Gap |
|---|---|---|---|---|
| 0.2-0.3 | 40 | 0.286 | 0.175 | -0.111 |
| 0.3-0.4 | 4,149 | 0.380 | 0.446 | +0.066 |
| 0.4-0.5 | 47,776 | 0.450 | 0.454 | +0.003 |
| 0.5-0.6 | 6,507 | 0.535 | 0.454 | -0.082 |
| 0.6-0.7 | 2,243 | 0.641 | 0.481 | -0.160 |
| 0.7-0.8 | 378 | 0.740 | 0.489 | -0.250 |
| 0.8-0.9 | 3 | 0.844 | 0.667 | -0.177 |
| 0.9-1.0 | 7 | 0.949 | 0.000 | -0.949 |

A model can rank correctly and still be badly calibrated. Only a calibrated probability can be used to size a position - if the model says 70% and it happens 50% of the time, sizing on that number systematically over-bets.


## NO-TRADE as a class

Share of bars where either barrier was hit inside the horizon: **19.2%**. Predicting whether a bar is an opportunity at all scored Brier **0.1366** against a base-rate baseline of **0.1553**.

This is the more useful target for a system that already has 14 entry rules: knowing when NOT to act is worth more than another opinion about direction.


## Feature importance (permutation)

How much Brier score worsens when each feature is shuffled. More honest than reading coefficients - it measures dependence the model actually has.

| Feature | Importance |
|---|---|
| or15_width_atr | +0.00089 |
| atr_pct | +0.00080 |
| gap_atr | +0.00046 |
| relative_volume | +0.00033 |
| vwap_distance_atr | +0.00025 |
| range_position | +0.00020 |
| confluence_count | +0.00010 |
| momentum_score | +0.00010 |
| adx_14 | +0.00009 |
| gap_pct | +0.00008 |
| bar_range_atr | +0.00007 |
| minutes_since_open | +0.00006 |

## Drift

Population stability index, first half of the sample against the second. Under 0.10 stable, 0.10-0.25 moderate, above 0.25 the feature no longer resembles what the model trained on.

| Feature | PSI | Verdict |
|---|---|---|
| atr_pct | 3.761 | DRIFTED |
| gap_pct | 0.248 | moderate shift |
| or15_width_atr | 0.082 | stable |
| range_position | 0.068 | stable |
| gap_atr | 0.067 | stable |
| relative_volume | 0.048 | stable |
| alignment_score | 0.019 | stable |
| vwap_distance_atr | 0.015 | stable |
| bar_range_atr | 0.011 | stable |
| momentum_score | 0.004 | stable |
| volume_zscore_20 | 0.002 | stable |
| adx_14 | 0.001 | stable |

---

## Verdict

**Directional prediction: no edge.** Base rate is 45.4% UP, so always
predicting the majority class scores Brier ≈ 0.2478. Three of four folds
came in *worse* than that (0.2550, 0.2518, 0.2497) and one marginally
better (0.2451). Accuracy of 0.507-0.571 across folds is noise around a
coin flip.

This independently reproduces what Phases 3-5 found by a different method:
there is no easily-extractable directional signal in these features. The
one edge that survived — gap continuation ≥0.5% — is a specific conditional
setup, not a general predictive relationship, which is precisely why a model
averaging across all 317,910 bars finds nothing. An edge that lives in 2% of
sessions disappears into the mean.

### The model is confidently wrong exactly where it is confident

Calibration is excellent where the model is uncertain and collapses where
it is not:

| Predicted | n | Observed | Gap |
|---|---|---|---|
| 0.450 | 47,776 | 0.454 | **+0.003** |
| 0.641 | 2,243 | 0.481 | −0.160 |
| 0.740 | 378 | 0.489 | **−0.250** |
| 0.949 | 7 | 0.000 | −0.949 |

The headline ECE of 0.0235 is flattering because 87% of predictions sit in
the well-calibrated 0.4-0.5 bucket. Every bar the model felt strongly about
was roughly a coin flip in reality. **Any strategy that sized up on model
confidence would have systematically over-bet its worst predictions** — which
is the specific failure that makes an uncalibrated model more dangerous than
no model.

### The one place the model adds value: knowing when not to act

Predicting whether a bar is an opportunity *at all* scored Brier **0.1366**
against a base-rate baseline of **0.1553** — a genuine 12% improvement, and
the only result here that beats its baseline in every sense.

Only **19.2%** of bars resolve to either barrier within 30 minutes. Four in
five are noise. For a system that already has 14 entry rules, a filter that
identifies dead bars is worth more than another opinion about direction.

### Feature importance points away from direction

Permutation importance is tiny everywhere (max +0.00089), consistent with a
model that has found nothing. The ordering is still informative: the top
features are `or15_width_atr`, `atr_pct` and `gap_atr` — all **volatility and
range** measures, not directional ones. The model is picking up how much
price is likely to move, not which way. That is the same conclusion the
NO-TRADE result reaches from the other side.

### Drift: one feature is unusable across eras

`atr_pct` has a PSI of **3.761** — an order of magnitude past the 0.25
"drifted" threshold. ATR as a percentage of price simply is not the same
quantity in 2008 as in 2019, and a model trained on one era would be badly
miscalibrated on the other. `gap_pct` shows moderate shift at 0.248.

This retroactively justifies a decision made in Phase 3: reporting every
backtest result in **ATR multiples** rather than dollars or percentages.
Raw volatility levels are not comparable across this history, and any
analysis that treated them as stationary would be measuring the regime
rather than the strategy.

## What Phase 6 concludes

1. Do not build a directional model on these features. It has been tried
   here properly — purged, embargoed, session-level splits — and there is
   nothing to find.
2. If a model is used at all, use it as a **NO-TRADE filter** gating the
   existing rules, since that is the only target that beat its baseline.
3. Never size on this model's confidence. Its high-probability predictions
   are its worst ones.
4. Volatility features drift severely across eras; anything built on them
   needs retraining or normalising, not a single fit over all history.
