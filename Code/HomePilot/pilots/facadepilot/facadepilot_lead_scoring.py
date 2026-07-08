#!/usr/bin/env python3
"""FacadePilot property-opportunity scoring v2.

Deze module vervangt de oude eenvoudige leadscore door een verklaarbare
property-opportunity score. De score zegt niets over bewonersintentie. Ze
rangschikt adressen op de kans dat een woning commercieel interessant is om
veilig en meetbaar in een gevelcampagne te testen.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

HERE = Path(__file__).parent.resolve()

try:
    SHARED = Path.home() / "Code" / "HomePilot" / "shared" / "python"
    if SHARED.exists() and str(SHARED) not in sys.path:
        sys.path.insert(0, str(SHARED))
    from homepilot_shared.campaign import ensure_profile, get_profile

    ensure_profile("facadepilot", HERE)
    _P = get_profile()
    NOUN_SURFACE = _P.surface
except Exception:
    NOUN_SURFACE = "gevel"


SCORING_VERSION = "facadepilot_property_opportunity_v2_2026_07"

# Weights add to 1.0. Penalties are applied afterwards.
COMPONENT_WEIGHTS = {
    "gevelvolume": 0.20,
    "woningtype": 0.18,
    "bouwouderdom": 0.18,
    "epc_zone": 0.15,
    "buurt_draagkracht": 0.14,
    "koop_verhuis_trigger": 0.10,
    "partner_fit": 0.05,
}

MIN_BEBOUWD_M2 = 60
CAP_GEVEL_M2 = 420
CAP_PERCEEL_M2 = 3000
CAP_INKOMEN = 55000

LEAD_CLASSES = [
    (82, "A+", "Topkandidaat: sterk woningprofiel, duidelijke renovatiecontext en bruikbare marktdata"),
    (66, "A", "Sterke kandidaat: goed testadres voor eerste golf of partnerbatch"),
    (50, "B", "Bruikbaar adres: vooral interessant binnen juiste regio, partner of boodschap"),
    (34, "C", "Lage prioriteit: pas meenemen wanneer regio of segment strategisch nodig is"),
    (0, "D", "Niet eerst benaderen: te weinig signalen of te veel belemmeringen"),
]

SOURCE_HINTS = {
    "gevelvolume": "GRB/Capakey of eigen gevelmeting",
    "woningtype": "GRB geometrie + perceelratio",
    "bouwouderdom": "Bouwjaar indien beschikbaar; anders Statbel bouwperiode per sector",
    "epc_zone": "VEKA/EPC-statistieken op zone + bouwjaar/woningtype proxy",
    "buurt_draagkracht": "Statbel fiscale inkomensstatistiek per statistische sector",
    "koop_verhuis_trigger": "Te contracteren: Realo/API, bpost Movers of andere vergunde verhuis/verkoopbron",
    "partner_fit": "Eigen campagnehistoriek en partnercapaciteit",
    "belemmering": "Erfgoed, vergunning, GIPOD/werken en recente renovatie indien beschikbaar",
}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    txt = str(value).strip()
    return txt if txt and txt.lower() not in {"nan", "none", "null"} else default


def _num(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return float(str(value).replace("EUR", "").replace("€", "").replace(" ", "").replace(",", "."))
    except Exception:
        return default


def _first(row: pd.Series, names: list[str], default: Any = None) -> Any:
    for name in names:
        if name in row.index:
            value = row.get(name)
            if _clean(value):
                return value
    return default


def _boolish(value: Any) -> bool:
    txt = _clean(value).lower()
    return txt in {"1", "true", "yes", "ja", "y", "x", "hit", "match", "pass", "recent", "blocked"}


def _clip(value: float, low: float = 0, high: float = 100) -> float:
    if value is None or math.isnan(float(value)):
        return low
    return max(low, min(high, float(value)))


def _linear(value: float | None, low: float, high: float, min_score: float = 0, max_score: float = 100) -> float:
    if value is None:
        return 50
    if high == low:
        return max_score
    return _clip(min_score + ((float(value) - low) / (high - low)) * (max_score - min_score))


def _score_from_percentile(series: pd.Series, fallback: float = 50) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() <= 1:
        return pd.Series([fallback] * len(series), index=series.index)
    ranks = numeric.rank(pct=True, method="average") * 100
    return ranks.fillna(fallback).clip(0, 100)


def classify_huistype(perceel_m2: float | None, bebouwd_ratio: float | None) -> tuple[str, float]:
    if perceel_m2 is None or bebouwd_ratio is None:
        return "onbekend", 50.0
    if perceel_m2 >= 400 and bebouwd_ratio <= 0.30:
        return "vrijstaand ruim", 92.0
    if perceel_m2 >= 250 and bebouwd_ratio <= 0.45:
        return "halfopen ruim", 82.0
    if perceel_m2 >= 180 and bebouwd_ratio <= 0.55:
        return "halfopen woning", 72.0
    if perceel_m2 >= 100 and bebouwd_ratio <= 0.75:
        return "rijwoning", 58.0
    if perceel_m2 >= 60 and bebouwd_ratio <= 0.85:
        return "stadswoning", 45.0
    return "appartement of dicht bebouwd", 24.0


def _building_age_score(row: pd.Series) -> tuple[float, str, str]:
    year = _num(_first(row, ["bouwjaar", "construction_year", "built_year", "year_built"]))
    if year:
        if year <= 1975:
            return 94, f"bouwjaar {int(year)}", "Exact bouwjaar: oudere woningen hebben vaker gevel-, isolatie- of comfortupgrade nodig."
        if year <= 1990:
            return 84, f"bouwjaar {int(year)}", "Exact bouwjaar: pre-1990 blijft een sterke renovatieproxy."
        if year <= 2005:
            return 58, f"bouwjaar {int(year)}", "Middengroep: mogelijke update, maar minder urgent dan pre-1990."
        if year <= 2014:
            return 34, f"bouwjaar {int(year)}", "Relatief recente woning: lager renovatiepotentieel."
        return 18, f"bouwjaar {int(year)}", "Nieuwe woning: meestal geen eerste golf."
    pre_1990 = _num(_first(row, ["pct_pre_1990", "stat_sector_pre_1990_share", "pre_1990_share"]))
    if pre_1990 is not None:
        if pre_1990 <= 1:
            pre_1990 *= 100
        return _clip(30 + pre_1990 * 0.65), f"{pre_1990:.0f}% pre-1990 in sector", "Geen exact bouwjaar; sectorproxy op basis van Statbel bouwperiode."
    return 50, "bouwjaar nog niet gekoppeld", "Neutrale score tot exacte bouwjaardata of sectorproxy beschikbaar is."


def _epc_zone_score(row: pd.Series) -> tuple[float, str, str]:
    label = _clean(_first(row, ["epc_label", "epc", "energy_label"])).upper().replace("+", "")
    if label:
        mapping = {"F": 96, "E": 88, "D": 72, "C": 50, "B": 28, "A": 15}
        if label in mapping:
            return mapping[label], f"EPC-label {label}", "EPC-label op adresniveau of toegestane bron."
    epc_kwh = _num(_first(row, ["epc_score", "epc_kwh_m2", "avg_epc_score", "gemiddelde_epc"]))
    if epc_kwh is not None:
        if epc_kwh >= 450:
            return 96, f"{epc_kwh:.0f} kWh/m2", "Zeer zwakke energieprestatie: sterk renovatiesignaal."
        if epc_kwh >= 350:
            return 84, f"{epc_kwh:.0f} kWh/m2", "Zwakke energieprestatie: interessant voor isolatie- of comfortboodschap."
        if epc_kwh >= 250:
            return 62, f"{epc_kwh:.0f} kWh/m2", "Middengroep: boodschap moet sterker getest worden."
        if epc_kwh >= 150:
            return 38, f"{epc_kwh:.0f} kWh/m2", "Relatief beter EPC: lager prioriteren voor gevelisolatie."
        return 20, f"{epc_kwh:.0f} kWh/m2", "Sterke energieprestatie: meestal geen eerste isolatiegolf."
    ef_share = _num(_first(row, ["pct_epc_ef", "epc_ef_share", "label_e_f_share"]))
    if ef_share is not None:
        if ef_share <= 1:
            ef_share *= 100
        return _clip(25 + ef_share * 0.75), f"{ef_share:.0f}% E/F in zone", "EPC-zoneproxy; bruikbaar voor prioritering, niet als adresclaim."
    age_proxy = _num(_first(row, ["pct_pre_1990", "stat_sector_pre_1990_share", "pre_1990_share"]))
    if age_proxy is not None:
        if age_proxy <= 1:
            age_proxy *= 100
        return _clip(35 + age_proxy * 0.45), "bouwouderdom als EPC-proxy", "EPC ontbreekt; oudere woningvoorraad verhoogt energie-renovatiekans."
    return 50, "EPC-zone nog niet gekoppeld", "Neutrale score tot VEKA/EPC-zone of partner-EPC beschikbaar is."


def _transaction_score(row: pd.Series) -> tuple[float, str, str]:
    explicit = _num(_first(row, ["recent_verkocht_score", "mover_score", "new_owner_score", "transaction_score"]))
    if explicit is not None:
        return _clip(explicit), f"bron-score {explicit:.0f}", "Vergunde koop/verhuisbron geeft directe triggersterkte."
    if _boolish(_first(row, ["recent_verkocht", "recent_sold", "new_owner", "mover", "bpost_mover"])):
        return 90, "recent gekocht/verhuisd", "Nieuwe eigenaars renoveren vaker in de eerste periode na aankoop of verhuis."
    months = _num(_first(row, ["months_since_sale", "maanden_sinds_verkoop", "months_since_move"]))
    if months is not None:
        if months <= 12:
            return 96, f"{months:.0f} maanden sinds verkoop/verhuis", "Zeer sterke timing-trigger."
        if months <= 24:
            return 86, f"{months:.0f} maanden sinds verkoop/verhuis", "Sterke timing-trigger."
        if months <= 48:
            return 66, f"{months:.0f} maanden sinds verkoop/verhuis", "Nog relevant, maar minder urgent."
        return 42, f"{months:.0f} maanden sinds verkoop/verhuis", "Timing minder sterk."
    return 50, "koop/verhuisdata te contracteren", "Neutrale score: Realo, bpost Movers of gelijkaardige bron nog koppelen."


def _income_band(score: float) -> str:
    if score >= 78:
        return "hogere draagkracht"
    if score >= 55:
        return "midden/hoger"
    if score >= 35:
        return "midden"
    return "budgetgevoeliger"


def _component(key: str, label: str, score: float, evidence: str, explanation: str, source: str) -> dict:
    weight = COMPONENT_WEIGHTS[key]
    return {
        "key": key,
        "label": label,
        "score": round(_clip(score), 1),
        "weight_pct": round(weight * 100, 1),
        "contribution": round(_clip(score) * weight, 1),
        "source": source,
        "evidence": evidence,
        "explanation": explanation,
    }


def _penalty(label: str, points: float, evidence: str, source: str) -> dict:
    return {
        "label": label,
        "points": round(max(0, points), 1),
        "evidence": evidence,
        "source": source,
    }


def _compute_confidence(row: pd.Series) -> tuple[float, list[str]]:
    signals = []
    score = 35
    if _clean(_first(row, ["lat", "lon", "latitude", "longitude"])):
        score += 7
        signals.append("geocodering")
    if _clean(_first(row, ["perceel_m2", "bebouwd_m2", "CAPAKEY", "capakey"])):
        score += 12
        signals.append("GRB/perceel")
    if _clean(_first(row, ["mediaan_inkomen", "income", "sector_income"])):
        score += 10
        signals.append("Statbel inkomen")
    if _clean(_first(row, ["bouwjaar", "construction_year", "pct_pre_1990", "stat_sector_pre_1990_share"])):
        score += 10
        signals.append("bouwouderdom")
    if _clean(_first(row, ["epc_label", "epc_score", "pct_epc_ef", "epc_ef_share"])):
        score += 10
        signals.append("EPC/EPC-zone")
    if _clean(_first(row, ["recent_verkocht", "recent_sold", "months_since_sale", "mover_score", "bpost_mover"])):
        score += 8
        signals.append("koop/verhuistrigger")
    if _clean(_first(row, ["heritage_flag", "erfgoed_flag", "permit_recent", "gipod_works"])):
        score += 4
        signals.append("belemmeringen")
    if _clean(_first(row, ["partner", "assigned_partner", "partner_response_rate", "partner_capacity_score"])):
        score += 4
        signals.append("partnerfit")
    return _clip(score, 30, 95), signals


def score_leads(df: pd.DataFrame) -> pd.DataFrame:
    """Score leads with a transparent, source-aware opportunity model."""
    if df is None or len(df) == 0:
        return df

    result = df.copy()

    for col in ["perceel_m2", "bebouwd_m2", "bebouwd_ratio", "mediaan_inkomen"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")

    if "bebouwd_ratio" not in result.columns and {"bebouwd_m2", "perceel_m2"}.issubset(result.columns):
        result["bebouwd_ratio"] = result["bebouwd_m2"] / result["perceel_m2"].replace(0, np.nan)

    if "bebouwd_m2" not in result.columns:
        result["bebouwd_m2"] = 0
    if "perceel_m2" not in result.columns:
        result["perceel_m2"] = 0
    if "bebouwd_ratio" not in result.columns:
        result["bebouwd_ratio"] = 0

    result["score_gevelvolume"] = result["bebouwd_m2"].apply(lambda v: _linear(_num(v, 0), MIN_BEBOUWD_M2, CAP_GEVEL_M2, 20, 100))
    result["score_perceel"] = result["perceel_m2"].apply(lambda v: _linear(_num(v, 0), 80, CAP_PERCEEL_M2, 20, 100))

    income_col = "mediaan_inkomen" if "mediaan_inkomen" in result.columns else None
    if income_col:
        income_numeric = pd.to_numeric(result[income_col], errors="coerce")
        income_score = _score_from_percentile(income_numeric, fallback=50)
        # Blend percentile with absolute buying-power ceiling where possible.
        abs_score = income_numeric.apply(lambda v: _linear(_num(v), 18000, CAP_INKOMEN, 20, 100))
        result["score_buurt_draagkracht"] = (income_score * 0.55 + abs_score * 0.45).fillna(50).clip(0, 100)
    else:
        result["score_buurt_draagkracht"] = 50.0

    lead_scores = []
    lead_classes = []
    lead_labels = []
    huistypes = []
    score_breakdowns = []
    score_sources = []
    confidence_values = []
    confidence_signals = []
    penalties_col = []
    score_notes = []
    income_bands = []

    for idx, row in result.iterrows():
        perceel = _num(row.get("perceel_m2"), 0) or 0
        bebouwd = _num(row.get("bebouwd_m2"), 0) or 0
        ratio = _num(row.get("bebouwd_ratio"), 0) or 0
        huistype, huistype_score = classify_huistype(perceel, ratio)
        age_score, age_evidence, age_expl = _building_age_score(row)
        epc_score, epc_evidence, epc_expl = _epc_zone_score(row)
        transaction_score, transaction_evidence, transaction_expl = _transaction_score(row)
        partner_fit = _num(_first(row, ["partner_fit_score", "partner_capacity_score", "partner_response_score"]))
        if partner_fit is None:
            response = _num(_first(row, ["partner_response_rate", "response_rate"]))
            partner_fit = _linear(response, 10, 55, 35, 90) if response is not None else 60

        draagkracht = float(result.at[idx, "score_buurt_draagkracht"])
        gevelvolume = float(result.at[idx, "score_gevelvolume"])
        perceel_score = float(result.at[idx, "score_perceel"])

        components = [
            _component("gevelvolume", "Gevelvolume", gevelvolume, f"{bebouwd:.0f} m2 bebouwd/gevelproxy", "Grotere gevels leveren meer productwaarde en sterkere visuele impact.", SOURCE_HINTS["gevelvolume"]),
            _component("woningtype", "Woningtype", huistype_score, huistype, "Vrijstaande en halfopen woningen zijn vaker interessanter dan kleine dichtbebouwde panden.", SOURCE_HINTS["woningtype"]),
            _component("bouwouderdom", "Bouwouderdom", age_score, age_evidence, age_expl, SOURCE_HINTS["bouwouderdom"]),
            _component("epc_zone", "EPC-/energieproxy", epc_score, epc_evidence, epc_expl, SOURCE_HINTS["epc_zone"]),
            _component("buurt_draagkracht", "Buurt-draagkracht", draagkracht, _income_band(draagkracht), "Duurdere renovaties vragen voldoende betalingscapaciteit in de omgeving.", SOURCE_HINTS["buurt_draagkracht"]),
            _component("koop_verhuis_trigger", "Koop/verhuis-trigger", transaction_score, transaction_evidence, transaction_expl, SOURCE_HINTS["koop_verhuis_trigger"]),
            _component("partner_fit", "Partnerfit", partner_fit, _clean(_first(row, ["partner", "assigned_partner"]), "partner nog te kiezen"), "Een sterk adres telt pas echt als de juiste partner kan opvolgen.", SOURCE_HINTS["partner_fit"]),
        ]

        penalties = []
        if bebouwd < MIN_BEBOUWD_M2:
            penalties.append(_penalty("Te kleine gevel", 22, f"{bebouwd:.0f} m2", SOURCE_HINTS["gevelvolume"]))
        if _boolish(_first(row, ["heritage_flag", "erfgoed_flag", "protected_building", "beschermd_erfgoed"])):
            penalties.append(_penalty("Erfgoed/vergunning complex", 24, "erfgoedsignaal aanwezig", SOURCE_HINTS["belemmering"]))
        if _boolish(_first(row, ["permit_recent", "recent_gevelvergunning", "recent_renovated", "renovatie_recent"])):
            penalties.append(_penalty("Recent al gerenoveerd of vergund", 20, "recente werken/vergunning", SOURCE_HINTS["belemmering"]))
        if _boolish(_first(row, ["gipod_works", "roadworks_flag", "werfzone"])):
            penalties.append(_penalty("Tijdelijke hinder/werfzone", 8, "GIPOD/werken-signaal", SOURCE_HINTS["belemmering"]))

        raw_score = sum(float(c["contribution"]) for c in components)
        penalty_points = sum(float(p["points"]) for p in penalties)
        final_score = _clip(raw_score - penalty_points)

        klass, label = "D", "Niet eerst benaderen"
        for threshold, class_name, class_label in LEAD_CLASSES:
            if final_score >= threshold:
                klass, label = class_name, class_label
                break

        confidence, conf_signals = _compute_confidence(row)
        breakdown = {
            "version": SCORING_VERSION,
            "score": round(final_score, 1),
            "klasse": klass,
            "label": label,
            "components": components,
            "penalties": penalties,
            "confidence": round(confidence, 1),
            "confidence_signals": conf_signals,
            "note": "Property opportunity score, geen bewonersintentie.",
        }

        lead_scores.append(round(final_score, 1))
        lead_classes.append(klass)
        lead_labels.append(label)
        huistypes.append(huistype)
        score_breakdowns.append(json.dumps(breakdown, ensure_ascii=False))
        score_sources.append(json.dumps({k: v for k, v in SOURCE_HINTS.items()}, ensure_ascii=False))
        confidence_values.append(round(confidence, 1))
        confidence_signals.append(", ".join(conf_signals) if conf_signals else "basisdata")
        penalties_col.append(json.dumps(penalties, ensure_ascii=False))
        score_notes.append("Property opportunity score, geen bewonersintentie.")
        income_bands.append(_income_band(draagkracht))

        result.at[idx, "score_bouwouderdom"] = round(age_score, 1)
        result.at[idx, "score_epc_zone"] = round(epc_score, 1)
        result.at[idx, "score_koop_verhuis_trigger"] = round(transaction_score, 1)
        result.at[idx, "score_partner_fit"] = round(partner_fit, 1)
        result.at[idx, "score_huistype"] = round(huistype_score, 1)
        result.at[idx, "score_woningtype"] = round(huistype_score, 1)
        result.at[idx, "score_woning"] = round(gevelvolume, 1)
        result.at[idx, "score_inkomen"] = round(draagkracht, 1)
        result.at[idx, "score_ratio"] = round(_linear(1 - min(max(ratio, 0), 1), 0, 1, 15, 100), 1)

    result["lead_score"] = lead_scores
    result["lead_klasse"] = lead_classes
    result["lead_label"] = lead_labels
    result["huistype"] = huistypes
    result["score_breakdown_json"] = score_breakdowns
    result["score_sources_json"] = score_sources
    result["score_penalties_json"] = penalties_col
    result["score_confidence"] = confidence_values
    result["score_confidence_signals"] = confidence_signals
    result["score_method_version"] = SCORING_VERSION
    result["score_note"] = score_notes
    result["income_band"] = income_bands
    result["source_scoring_model"] = SCORING_VERSION
    result["retrieved_at_scoring_model"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    result = result.sort_values(["lead_score", "score_confidence"], ascending=[False, False]).reset_index(drop=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Score FacadePilot leads met scoring v2")
    parser.add_argument("--input", "-i", required=True, help="Input CSV")
    parser.add_argument("--output", "-o", help="Output CSV")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_name(input_path.stem + "_scored.csv")
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    scored = score_leads(df)
    scored.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"{len(scored)} leads gescoord met {SCORING_VERSION} -> {output_path}")


if __name__ == "__main__":
    main()
