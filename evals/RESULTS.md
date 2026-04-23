# Eval Results

- **Total cases:** 31  
- **Accuracy:** 100.0%  
- **Audit completeness:** 100.0%

## Per-class metrics

| Class | Precision | Recall | Support |
|---|---:|---:|---:|
| PASS | 100.0% | 100.0% | 17 |
| REJECT | 100.0% | 100.0% | 11 |
| ESCALATE | 100.0% | 100.0% | 3 |

## Confusion matrix

| expected \ actual | PASS | REJECT | ESCALATE |
|---|---:|---:|---:|
| **PASS** | 17 | 0 | 0 |
| **REJECT** | 0 | 11 | 0 |
| **ESCALATE** | 0 | 0 | 3 |

## Case breakdown by category

| Category | Cases | Correct |
|---|---:|---:|
| alias | 3 | 3 |
| conflict | 4 | 4 |
| cooldown | 3 | 3 |
| edge | 9 | 9 |
| happy_path | 9 | 9 |
| watchlist | 3 | 3 |

_No mismatches. All cases passed._

