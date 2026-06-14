#!/usr/bin/env python3
"""
Lambda-12 dimension scorer
Usage: python3 tools/lambda12_score.py [--input <comparison.json>] [--output <scores.json>]
"""

import argparse
import json
import os
from datetime import date

def _default_output(input_path: str) -> str:
    base = os.path.basename(input_path)
    name = base.replace("comparison_", "lambda12_scores_")
    return os.path.join(os.path.dirname(input_path), name)

_parser = argparse.ArgumentParser()
_parser.add_argument("--input",  default=os.path.expanduser("~/everbluesea/data/wto/comparison_2023.json"))
_parser.add_argument("--output", default=None)
_args = _parser.parse_args()

INPUT  = os.path.expanduser(_args.input)
OUTPUT = os.path.expanduser(_args.output) if _args.output else _default_output(INPUT)

# (indicator_code, inverse, transform)
# inverse=True  → lower raw value = higher score
# transform="abs" → use |value| before scoring
DIMENSIONS = {
    "A1":  ("인프라",   [("ITS_MTV_AX",   False, None),
                         ("ITS_MTP_AXVG", False, None)]),
    "A2":  ("제도신뢰", [("TP_B_0020",    False, None),
                         ("TP_A_0010",    True,  None)]),
    "A3":  ("사회결속", [("ITS_CS_QAX",   False, None),
                         ("ITS_CS_QAM",   False, None)]),
    "A4":  ("경제역량", [("ITS_MTV_AX",   False, None),
                         ("ITS_MTV_AM",   False, None),
                         ("ITS_MTP_AXVG", False, None),
                         ("ITS_MTP_AMVG", False, None)]),
    "A5":  ("지식혁신", [("ITS_MTP_AUVX", False, None),
                         ("ITS_MTP_AUVM", False, None)]),
    "A6":  ("환경지속", [("TP_A_0160",    True,  None),
                         ("TP_A_0430",    False, None)]),
    "A7":  ("인구동태", []),   # null — 데이터 없음
    "A8":  ("거버넌스", [("TP_A_0010",    True,  None),
                         ("TP_B_0090",    False, None)]),
    "A9":  ("지정학",   [("ITS_MTP_AXVG", False, "abs"),
                         ("ITS_MTP_AMVG", False, "abs")]),
    "A10": ("문화정체", [("ITS_CS_QAX",   False, None)]),
    "A11": ("에너지",   [("ITS_MTV_AM",   False, None),
                         ("ITS_MTP_AMVG", False, None)]),
    "A12": ("이동성",   [("ITS_CS_QAX",   False, None),
                         ("ITS_CS_QAM",   False, None),
                         ("BAT_BV_X",     False, None),
                         ("BAT_BV_M",     False, None)]),
}


def load_values(data: dict) -> dict[str, dict[str, float | None]]:
    """Flatten comparison JSON → {indicator: {country: value}}"""
    flat = {}
    for group in data["data"].values():
        for code, item in group.items():
            flat[code] = item["values"]
    return flat


def normalize(vals: dict[str, float | None], inverse: bool) -> dict[str, float | None]:
    """Min-max normalize across countries. Returns None where input is None."""
    present = {c: v for c, v in vals.items() if v is not None}
    if not present:
        return {c: None for c in vals}
    lo, hi = min(present.values()), max(present.values())
    if hi == lo:
        return {c: (0.5 if v is not None else None) for c, v in vals.items()}
    result = {}
    for c, v in vals.items():
        if v is None:
            result[c] = None
        else:
            score = (v - lo) / (hi - lo)
            result[c] = 1.0 - score if inverse else score
    return result


def score_dimension(
    dim_indicators: list,
    flat: dict[str, dict[str, float | None]],
    countries: list[str],
) -> dict[str, float | None]:
    """Average normalized scores across a dimension's indicators."""
    if not dim_indicators:
        return {c: None for c in countries}

    normed_layers = []
    for code, inverse, transform in dim_indicators:
        raw = {c: flat.get(code, {}).get(c) for c in countries}
        if transform == "abs":
            raw = {c: abs(v) if v is not None else None for c, v in raw.items()}
        normed_layers.append(normalize(raw, inverse))

    result = {}
    for c in countries:
        vals = [layer[c] for layer in normed_layers if layer[c] is not None]
        result[c] = round(sum(vals) / len(vals), 4) if vals else None
    return result


def compute_eta(dim_scores: dict[str, dict], countries: list[str]) -> dict[str, float | None]:
    """η = mean of A1–A12 excluding A7."""
    eta = {}
    for c in countries:
        vals = [
            dim_scores[d][c]
            for d in DIMENSIONS
            if d != "A7" and dim_scores[d][c] is not None
        ]
        eta[c] = round(sum(vals) / len(vals), 4) if vals else None
    return eta


def print_table(dim_scores: dict, eta: dict, countries: list[str]) -> None:
    col = 9
    header = f"{'':12}" + "".join(f"{c:>{col}}" for c in countries)
    print(header)
    print("─" * (12 + col * len(countries)))
    for dim, (name, _) in DIMENSIONS.items():
        scores = dim_scores[dim]
        row = f"{dim}({name})"
        vals = "".join(
            f"{'—':>{col}}" if scores[c] is None else f"{scores[c]:>{col}.4f}"
            for c in countries
        )
        print(f"{row:<12}{vals}")
    print("─" * (12 + col * len(countries)))
    eta_row = "".join(
        f"{'—':>{col}}" if eta[c] is None else f"{eta[c]:>{col}.4f}"
        for c in countries
    )
    print(f"{'η (평균)':<12}{eta_row}")


def main() -> None:
    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)

    countries = data["countries"]
    flat = load_values(data)

    dim_scores = {
        dim: score_dimension(indicators, flat, countries)
        for dim, (_, indicators) in DIMENSIONS.items()
    }
    eta = compute_eta(dim_scores, countries)

    print(f"\n Lambda-12 점수 — {data['year']}년 ({', '.join(countries)})\n")
    print_table(dim_scores, eta, countries)

    output = {
        "year": data["year"],
        "updated": date.today().isoformat(),
        "countries": countries,
        "dimensions": {
            dim: {
                "name": DIMENSIONS[dim][0],
                "scores": dim_scores[dim],
            }
            for dim in DIMENSIONS
        },
        "eta": eta,
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n저장 → {OUTPUT}\n")


if __name__ == "__main__":
    main()
