from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

NET_FACTOR = 0.70  # planning assumption only; replace with settlement/tax inputs.
CRYSTAL_TOPUP = {"none": (0.0, 0.0), "small": (9.99, 0.351), "medium": (24.99, 0.666), "large": (59.99, 1.315)}

@dataclass(frozen=True)
class Variant:
    name: str
    prices: tuple[float, float, float, float]
    paid_conversion: float
    mix: tuple[float, float, float, float]
    crystal_attach: float
    crystal_basket: str
    monthly_retention: float

    def weighted_subscription(self) -> float:
        return sum(price * share for price, share in zip(self.prices, self.mix))

    def variable_cost(self) -> float:
        tier_costs = (0.351, 1.083, 1.315, 2.750)
        return sum(cost * share for cost, share in zip(tier_costs, self.mix))

    def contribution_per_payer(self) -> float:
        crystal_price, crystal_cost = CRYSTAL_TOPUP[self.crystal_basket]
        return (self.weighted_subscription() * NET_FACTOR - self.variable_cost()
                + self.crystal_attach * (crystal_price * NET_FACTOR - crystal_cost))

    def contribution_per_activated(self) -> float:
        return self.paid_conversion * self.contribution_per_payer()

VARIANTS = [
    Variant("A", (14.99, 29.99, 59.99, 99.99), 0.085, (0.60, 0.25, 0.10, 0.05), 0.20, "medium", 0.72),
    Variant("B", (19.99, 34.99, 69.99, 99.99), 0.075, (0.55, 0.28, 0.12, 0.05), 0.23, "medium", 0.75),
    Variant("C", (14.99, 39.99, 69.99, 99.99), 0.080, (0.65, 0.20, 0.10, 0.05), 0.22, "medium", 0.73),
]

SCENARIOS = {
    "conservative": {"conversion": 0.05, "mix": (0.70, 0.20, 0.08, 0.02), "crystal_attach": 0.12, "crystal_basket": "small"},
    "base": {"conversion": 0.075, "mix": (0.55, 0.28, 0.12, 0.05), "crystal_attach": 0.23, "crystal_basket": "medium"},
    "upside": {"conversion": 0.10, "mix": (0.45, 0.30, 0.17, 0.08), "crystal_attach": 0.32, "crystal_basket": "large"},
}


def scenario(variant: Variant, name: str, users: int = 1000) -> dict:
    s = SCENARIOS[name]
    prices = variant.prices
    weighted = sum(p * share for p, share in zip(prices, s["mix"]))
    tier_costs = (0.351, 1.083, 1.315, 2.750)
    payer_cost = sum(c * share for c, share in zip(tier_costs, s["mix"]))
    crystal_price, crystal_cost = CRYSTAL_TOPUP[s["crystal_basket"]]
    payer_revenue = weighted + s["crystal_attach"] * crystal_price
    payer_variable = payer_cost + s["crystal_attach"] * crystal_cost
    paid = users * s["conversion"]
    revenue = paid * payer_revenue
    variable = paid * payer_variable
    contribution = revenue * NET_FACTOR - variable
    return {
        "variant": variant.name,
        "scenario": name,
        "activated_users": users,
        "paid_conversion_pct": round(s["conversion"] * 100, 2),
        "paid_users": round(paid, 2),
        "weighted_subscription_usd": round(weighted, 2),
        "crystal_attach_pct": round(s["crystal_attach"] * 100, 2),
        "gross_revenue_usd": round(revenue, 2),
        "variable_cost_usd": round(variable, 2),
        "contribution_usd": round(contribution, 2),
        "contribution_per_payer_usd": round(contribution / paid, 2) if paid else 0,
        "arppu_usd": round(payer_revenue, 2),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rows = [scenario(v, name) for v in VARIANTS for name in SCENARIOS]
    out = root / "docs" / "MONETIZATION_V2_ECONOMICS.csv"
    out.write_text(
        "variant,scenario,activated_users,paid_conversion_pct,paid_users,weighted_subscription_usd,crystal_attach_pct,gross_revenue_usd,variable_cost_usd,contribution_usd,contribution_per_payer_usd,arppu_usd\n"
        + "\n".join(",".join(str(row[key]) for key in (
            "variant", "scenario", "activated_users", "paid_conversion_pct", "paid_users",
            "weighted_subscription_usd", "crystal_attach_pct", "gross_revenue_usd",
            "variable_cost_usd", "contribution_usd", "contribution_per_payer_usd", "arppu_usd"
        )) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(out)
    for v in VARIANTS:
        print(v.name, round(v.contribution_per_activated(), 2), round(v.contribution_per_payer(), 2))
    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
