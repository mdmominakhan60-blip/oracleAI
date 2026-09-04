# Matrix / numerology contract

`app/core/matrix.py` implements a deterministic product tradition called Matrix of Destiny. It is not an astronomical calculation and is not presented as an externally validated scientific model. The input is an ISO birth date; the output is always exactly seven positions:

`personal`, `spirit`, `family`, `destiny`, `center`, `love`, `money`.

Each position contains `n` in the range 1–22, arcana name, title, meaning, keywords, plus, minus and advice. The reducer `_r` repeatedly sums decimal digits while the value exceeds 22 and maps zero to 22. For date components `a=reduce(day)`, `b=reduce(month)` and `c=reduce(sum(year digits))`, the current formulas are:

| Position | Formula |
|---|---|
| Personal | `a` |
| Spirit | `b` |
| Family | `c` |
| Destiny | `reduce(a+b+c)` |
| Center | `reduce(a+b+c+destiny)` |
| Love | `reduce(a+destiny)` |
| Money | `reduce(c+destiny)` |

The contract is deterministic and versioned by the repository implementation, with golden values such as `1990-05-15` and reducer edge tests. The LLM may explain the bounded symbolic text returned by the module, but must not invent a different formula, score, arcana or future event. The system must not frame Matrix output as medical, legal, financial or scientific diagnosis. Changes to formulas or arcana meanings require a new contract/golden review rather than silently replacing historical evidence.
