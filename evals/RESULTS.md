# Eval Results

- **Total cases:** 45  
- **Accuracy:** 100.0%  
- **Audit completeness:** 100.0%

## Per-class metrics

| Class | Precision | Recall | Support |
|---|---:|---:|---:|
| PASS | 100.0% | 100.0% | 25 |
| REJECT | 100.0% | 100.0% | 16 |
| ESCALATE | 100.0% | 100.0% | 4 |

## Confusion matrix

| expected \ actual | PASS | REJECT | ESCALATE |
|---|---:|---:|---:|
| **PASS** | 25 | 0 | 0 |
| **REJECT** | 0 | 16 | 0 |
| **ESCALATE** | 0 | 0 | 4 |

## Case breakdown by category

| Category | Cases | Correct |
|---|---:|---:|
| adversarial | 14 | 14 |
| alias | 3 | 3 |
| conflict | 4 | 4 |
| cooldown | 3 | 3 |
| edge | 9 | 9 |
| happy_path | 9 | 9 |
| watchlist | 3 | 3 |

_No mismatches. All cases passed._

