# Finding: price momentum carries the signal, news text does not

Separate from the data-prep handover. Results from the earlier modelling runs (before the new index), so re-check on the new data before quoting.

## Setup
- Labels: PriceCatcher 4 staples, 14-day-after vs 7-day-before median, flat band +-2%.
- Split: train 2023-12 to 2024-12, test 2025-01 to 2026-09 (4,747 rows), time-based with a 14-day purge.
- Caveat: the labelled news only starts 2023-12-21 (not 2020). News is The Star only; its robots.txt forbids scraping and ML training without permission, so disclose.

## Results (held-out)
| Model | Result |
|---|---|
| Always predict flat | accuracy 0.751 |
| TF-IDF news model | accuracy 0.617; 89 alerts at p>=0.6, 29% correct (chance/persistence ~25%); recall of real moves 2% |
| News text alone | AUC ~0.50 for detecting a move |
| Article volume | AUC 0.47 |
| Policy-keyword flags | no lift (hurt when added) |
| Past price momentum | AUC 0.66 (2025: 0.63, 2026: 0.68); precision in top 10% ~45-49% vs 25% base |

Cooking oil is 99% flat (subsidised); eggs are the most volatile (49% flat).

## What to claim
- Do not claim news predicts prices. The backtest contradicts it.
- Pitch: price-pressure alerts driven by momentum, with news as the explanation layer. Report the news ablation openly.
- The PRD's own advice fits: show baselines, show one wrong example, call it an awareness alert (flags F4, F7).

## Limits
- Momentum precision of ~45-49% is a ranking lift, not a forecast; most alerts are still wrong.
- Not yet re-run on the new per-item index; labels and thresholds may shift.
