#!/usr/bin/env python3
"""Genera data/nba_stats.json: dataset demo realistico (stagione 2026-27, ~18 gare)
per la dashboard NBA Advanced Stats. Calcola le 3 metriche proprietarie con le
formule esatte richieste e produce anche le varianti L5/L10 e i valori della
settimana precedente (per la variazione nelle card Top Performers)."""
import hashlib
import json
import math
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nba_stats.json")

# ---------------------------------------------------------------- utility ----
def seeded_uniform(key: str) -> float:
    """Uniforme [0,1) deterministica (stabile tra processi)."""
    h = hashlib.md5(key.encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64

def perturb(value, key, scale):
    return value * (1 + (seeded_uniform(key) - 0.5) * 2 * scale)

# ------------------------------------------------------------- dati base ----
# Stagione 2026-27 (novembre 2026, ~15-19 gare). Movimenti reali dell'estate
# 2026: Giannis -> Miami Heat, LeBron -> Philadelphia 76ers.
# Ogni giocatore: statistiche medie a partita + componenti Synergy/tracking.
# playTypes: {ppp, freq} -> poss = freq/100*totalPoss, pts = ppp*poss.
BASE = [
    dict(id=203999, name="Nikola Jokić", team="Denver Nuggets", teamAbbr="DEN", pos="C",
         totalPoss=48, gp=17, min=35.8, pts=28.9, reb=12.5, ast=10.8, ts=0.664,
         pt={"prbh": (0.98, 24.0), "iso": (1.02, 10.5), "spotup": (1.18, 12.0), "cut": (1.32, 11.5), "offscreen": (1.05, 3.0)},
         tr=dict(touches=88.5, secPerTouch=6.2, potentialAssists=15.8, milesOff=1.42, contestedShots=9.8, deflections=2.1),
         adv=dict(catchShootPts=4.2, diffFgPct=0.015)),
    dict(id=1628983, name="Shai Gilgeous-Alexander", team="Oklahoma City Thunder", teamAbbr="OKC", pos="G",
         totalPoss=46, gp=18, min=34.5, pts=32.1, reb=5.4, ast=6.8, ts=0.618,
         pt={"prbh": (1.02, 34.5), "iso": (1.08, 16.0), "spotup": (1.12, 9.0), "cut": (1.28, 4.0), "offscreen": (0.98, 2.5)},
         tr=dict(touches=74.2, secPerTouch=4.9, potentialAssists=12.4, milesOff=1.85, contestedShots=5.4, deflections=3.2),
         adv=dict(catchShootPts=5.8, diffFgPct=-0.018)),
    dict(id=1629029, name="Luka Dončić", team="Los Angeles Lakers", teamAbbr="LAL", pos="G",
         totalPoss=47, gp=16, min=35.9, pts=30.4, reb=8.3, ast=8.9, ts=0.587,
         pt={"prbh": (0.99, 33.0), "iso": (1.04, 17.5), "spotup": (1.10, 8.5), "cut": (1.24, 3.5), "offscreen": (0.96, 2.0)},
         tr=dict(touches=76.8, secPerTouch=6.4, potentialAssists=13.9, milesOff=1.66, contestedShots=4.8, deflections=2.2),
         adv=dict(catchShootPts=4.9, diffFgPct=0.022)),
    dict(id=1628369, name="Jayson Tatum", team="Boston Celtics", teamAbbr="BOS", pos="F",
         totalPoss=42, gp=19, min=35.2, pts=27.8, reb=8.2, ast=5.6, ts=0.588,
         pt={"prbh": (0.94, 27.0), "iso": (1.00, 12.0), "spotup": (1.14, 15.0), "cut": (1.26, 6.5), "offscreen": (1.02, 5.5)},
         tr=dict(touches=58.4, secPerTouch=4.6, potentialAssists=9.2, milesOff=1.92, contestedShots=6.8, deflections=2.6),
         adv=dict(catchShootPts=8.4, diffFgPct=-0.012)),
    dict(id=1641705, name="Victor Wembanyama", team="San Antonio Spurs", teamAbbr="SAS", pos="C",
         totalPoss=38, gp=18, min=31.5, pts=26.5, reb=11.2, ast=3.8, ts=0.601,
         pt={"prbh": (0.92, 14.0), "iso": (1.01, 12.5), "spotup": (1.22, 16.5), "cut": (1.34, 10.0), "offscreen": (1.12, 8.0)},
         tr=dict(touches=42.6, secPerTouch=4.6, potentialAssists=6.1, milesOff=1.95, contestedShots=14.6, deflections=3.4),
         adv=dict(catchShootPts=8.8, diffFgPct=-0.048)),
    dict(id=201939, name="Stephen Curry", team="Golden State Warriors", teamAbbr="GSW", pos="G",
         totalPoss=41, gp=17, min=32.4, pts=24.6, reb=4.6, ast=5.9, ts=0.604,
         pt={"prbh": (1.00, 28.0), "iso": (1.05, 10.0), "spotup": (1.24, 18.0), "cut": (1.22, 3.0), "offscreen": (1.18, 12.5)},
         tr=dict(touches=56.2, secPerTouch=4.9, potentialAssists=9.8, milesOff=1.98, contestedShots=4.2, deflections=2.4),
         adv=dict(catchShootPts=12.6, diffFgPct=0.008)),
    dict(id=1630162, name="Anthony Edwards", team="Minnesota Timberwolves", teamAbbr="MIN", pos="G",
         totalPoss=43, gp=18, min=35.1, pts=28.2, reb=5.8, ast=4.7, ts=0.577,
         pt={"prbh": (0.96, 31.5), "iso": (1.03, 14.0), "spotup": (1.16, 12.0), "cut": (1.26, 4.5), "offscreen": (1.00, 4.0)},
         tr=dict(touches=60.8, secPerTouch=5.2, potentialAssists=8.4, milesOff=1.88, contestedShots=5.6, deflections=2.5),
         adv=dict(catchShootPts=8.9, diffFgPct=-0.008)),
    dict(id=1628973, name="Jalen Brunson", team="New York Knicks", teamAbbr="NYK", pos="G",
         totalPoss=45, gp=18, min=34.8, pts=26.3, reb=3.2, ast=7.7, ts=0.588,
         pt={"prbh": (1.01, 36.0), "iso": (1.06, 13.5), "spotup": (1.10, 8.0), "cut": (1.22, 3.0), "offscreen": (0.94, 3.5)},
         tr=dict(touches=71.4, secPerTouch=5.6, potentialAssists=11.2, milesOff=1.72, contestedShots=4.6, deflections=2.0),
         adv=dict(catchShootPts=5.2, diffFgPct=0.014)),
    dict(id=203507, name="Giannis Antetokounmpo", team="Miami Heat", teamAbbr="MIA", pos="F",
         totalPoss=44, gp=17, min=33.9, pts=29.8, reb=11.0, ast=6.1, ts=0.621,
         pt={"prbh": (1.04, 26.0), "iso": (1.09, 15.0), "spotup": (1.12, 7.5), "cut": (1.36, 12.0), "offscreen": (0.92, 2.0)},
         tr=dict(touches=66.2, secPerTouch=5.0, potentialAssists=9.6, milesOff=1.78, contestedShots=10.2, deflections=2.8),
         adv=dict(catchShootPts=4.6, diffFgPct=-0.036)),
    dict(id=1630169, name="Tyrese Haliburton", team="Indiana Pacers", teamAbbr="IND", pos="G",
         totalPoss=38, gp=19, min=33.2, pts=21.4, reb=4.1, ast=11.2, ts=0.595,
         pt={"prbh": (0.97, 30.0), "iso": (0.99, 7.0), "spotup": (1.20, 16.0), "cut": (1.24, 5.0), "offscreen": (1.06, 5.0)},
         tr=dict(touches=68.9, secPerTouch=4.4, potentialAssists=15.2, milesOff=1.94, contestedShots=4.9, deflections=3.1),
         adv=dict(catchShootPts=9.4, diffFgPct=-0.010)),
    dict(id=2544, name="LeBron James", team="Philadelphia 76ers", teamAbbr="PHI", pos="F",
         totalPoss=40, gp=15, min=32.6, pts=21.8, reb=6.9, ast=7.9, ts=0.585,
         pt={"prbh": (0.98, 25.5), "iso": (1.03, 11.0), "spotup": (1.14, 13.0), "cut": (1.30, 9.0), "offscreen": (1.04, 4.5)},
         tr=dict(touches=62.4, secPerTouch=5.1, potentialAssists=12.2, milesOff=1.68, contestedShots=5.8, deflections=2.6),
         adv=dict(catchShootPts=7.2, diffFgPct=-0.006)),
    dict(id=1628378, name="Donovan Mitchell", team="Cleveland Cavaliers", teamAbbr="CLE", pos="G",
         totalPoss=40, gp=18, min=33.5, pts=26.1, reb=4.4, ast=5.2, ts=0.581,
         pt={"prbh": (0.98, 30.0), "iso": (1.04, 12.5), "spotup": (1.14, 12.5), "cut": (1.24, 4.0), "offscreen": (1.00, 4.5)},
         tr=dict(touches=58.6, secPerTouch=5.0, potentialAssists=8.8, milesOff=1.82, contestedShots=5.2, deflections=2.7),
         adv=dict(catchShootPts=8.1, diffFgPct=-0.004)),
    dict(id=201142, name="Kevin Durant", team="Houston Rockets", teamAbbr="HOU", pos="F",
         totalPoss=39, gp=17, min=33.8, pts=25.7, reb=5.9, ast=4.3, ts=0.598,
         pt={"prbh": (0.99, 24.0), "iso": (1.07, 16.5), "spotup": (1.20, 15.5), "cut": (1.26, 5.5), "offscreen": (1.10, 7.5)},
         tr=dict(touches=54.8, secPerTouch=4.3, potentialAssists=8.2, milesOff=1.86, contestedShots=6.4, deflections=1.9),
         adv=dict(catchShootPts=9.6, diffFgPct=-0.015)),
    dict(id=1630595, name="Cade Cunningham", team="Detroit Pistons", teamAbbr="DET", pos="G",
         totalPoss=44, gp=19, min=34.9, pts=27.2, reb=6.2, ast=9.4, ts=0.566,
         pt={"prbh": (0.97, 32.0), "iso": (1.02, 13.0), "spotup": (1.12, 11.0), "cut": (1.24, 4.0), "offscreen": (0.98, 3.0)},
         tr=dict(touches=69.2, secPerTouch=5.5, potentialAssists=12.8, milesOff=1.76, contestedShots=5.0, deflections=2.3),
         adv=dict(catchShootPts=6.8, diffFgPct=0.010)),
    dict(id=1627759, name="Jaylen Brown", team="Boston Celtics", teamAbbr="BOS", pos="F",
         totalPoss=40, gp=16, min=34.1, pts=24.5, reb=6.8, ast=4.9, ts=0.569,
         pt={"prbh": (0.95, 28.0), "iso": (1.01, 12.0), "spotup": (1.14, 14.0), "cut": (1.28, 7.5), "offscreen": (1.02, 4.0)},
         tr=dict(touches=55.2, secPerTouch=4.5, potentialAssists=8.6, milesOff=1.90, contestedShots=6.6, deflections=2.4),
         adv=dict(catchShootPts=8.6, diffFgPct=-0.011)),
]

# Scale delle perturbazioni per periodo (L10/L5) e settimana precedente.
SCALE = dict(min=0.03, pts=0.05, reb=0.07, ast=0.07, ts=0.015, ppp=0.03, freq=0.06,
             touches=0.05, secPerTouch=0.04, potentialAssists=0.06, milesOff=0.04,
             contestedShots=0.06, deflections=0.09, catchShootPts=0.07, diffFgPct=0.012,
             totalPoss=0.04)
PERIOD_SCALE = {"season": 0.0, "l10": 0.55, "l5": 1.0}   # moltiplicatore di intensità
PREV_SCALE = 0.4

def build_block(p, period):
    """Costruisce il blocco statistiche di un periodo, con perturbazioni coerenti."""
    k = f"{p['id']}|{period}"
    s = PERIOD_SCALE[period]
    def f(field, base):
        return perturb(base, f"{k}|{field}", SCALE[field] * s) if s else base
    gp = {"season": p["gp"], "l10": min(10, p["gp"]), "l5": min(5, p["gp"])}[period]
    total_poss = max(20.0, f("totalPoss", p["totalPoss"]))
    play_types = {}
    for pt_key, (ppp, freq) in p["pt"].items():
        ppp_v = min(1.45, max(0.70, perturb(ppp, f"{k}|{pt_key}|ppp", SCALE["ppp"] * s)))
        frq_v = min(45.0, max(0.5, perturb(freq, f"{k}|{pt_key}|freq", SCALE["freq"] * s)))
        poss = frq_v / 100.0 * total_poss
        play_types[pt_key] = dict(ppp=round(ppp_v, 3), freq=round(frq_v, 1),
                                  poss=round(poss, 1), pts=round(ppp_v * poss, 1))
    tr = {fld: max(0.2, perturb(p["tr"][fld], f"{k}|{fld}", SCALE[fld] * s))
          for fld in p["tr"]}
    adv = dict(
        catchShootPts=round(max(0.5, perturb(p["adv"]["catchShootPts"], f"{k}|catchShootPts", SCALE["catchShootPts"] * s)), 1),
        diffFgPct=round(min(0.05, max(-0.06, perturb(p["adv"]["diffFgPct"], f"{k}|diffFgPct", SCALE["diffFgPct"] * s))), 3),
    )
    adv["ptsCreatedByAssist"] = round(tr["potentialAssists"] * 2.18, 1)
    blk = dict(
        gp=gp,
        min=round(f("min", p["min"]), 1),
        pts=round(f("pts", p["pts"]), 1),
        reb=round(f("reb", p["reb"]), 1),
        ast=round(f("ast", p["ast"]), 1),
        ts=round(min(0.72, max(0.45, f("ts", p["ts"]))), 3),
        playTypes=play_types,
        tracking={fld: (round(v, 1) if fld != "secPerTouch" else round(v, 2))
                  for fld, v in tr.items()},
        advanced=adv,
    )
    blk["metrics"] = compute_metrics(blk)
    return blk

# ------------------------------------------------------------ formule ----
def compute_metrics(blk):
    """Formule esatte delle 3 metriche proprietarie (identiche al frontend
    e a scripts/update_nba_stats.py)."""
    pt, tr, adv = blk["playTypes"], blk["tracking"], blk["advanced"]
    # PCI: pressione creata con palla in mano
    pnr_pts = pt["prbh"]["ppp"] * pt["prbh"]["poss"]
    iso_pts = pt["iso"]["ppp"] * pt["iso"]["poss"]
    num = pnr_pts + iso_pts + adv["ptsCreatedByAssist"]
    den = pt["prbh"]["poss"] + pt["iso"]["poss"] + tr["potentialAssists"]
    pci = (num / den) * (1.0 / tr["secPerTouch"]) if den > 0 else 0.0
    # OGMS: gravità off-ball (Spot-Up + Cut + Off-Screen)
    ob = ["spotup", "cut", "offscreen"]
    ob_poss = sum(pt[k]["poss"] for k in ob)
    ob_pts = sum(pt[k]["ppp"] * pt[k]["poss"] for k in ob)
    ppp_off = ob_pts / ob_poss if ob_poss > 0 else 0.0
    freq_off = sum(pt[k]["freq"] for k in ob) / 100.0
    ogms = ppp_off * freq_off * tr["milesOff"] * (adv["catchShootPts"] / tr["touches"]) \
        if tr["touches"] > 0 else 0.0
    # DADR: attività/deterrenza difensiva
    dadr = ((tr["contestedShots"] + 1.5 * tr["deflections"]) / blk["min"]) * (1 - adv["diffFgPct"]) \
        if blk["min"] > 0 else 0.0
    return dict(pci=round(pci, 4), ogms=round(ogms, 4), dadr=round(dadr, 4))

def build_prev(block, pid, period):
    """Valori della settimana precedente: perturba gli input e ricalcola."""
    k = f"{pid}|{period}|prev"
    blk = json.loads(json.dumps(block))
    blk["min"] = round(perturb(block["min"], k + "|min", SCALE["min"] * PREV_SCALE), 1)
    for fld in ("touches", "secPerTouch", "potentialAssists", "milesOff", "contestedShots", "deflections"):
        blk["tracking"][fld] = round(perturb(block["tracking"][fld], k + "|" + fld, SCALE[fld] * PREV_SCALE), 2)
    blk["advanced"]["catchShootPts"] = round(perturb(block["advanced"]["catchShootPts"], k + "|cs", SCALE["catchShootPts"] * PREV_SCALE), 1)
    blk["advanced"]["diffFgPct"] = round(perturb(block["advanced"]["diffFgPct"], k + "|dfg", SCALE["diffFgPct"] * PREV_SCALE), 3)
    blk["advanced"]["ptsCreatedByAssist"] = round(blk["tracking"]["potentialAssists"] * 2.18, 1)
    for pk in blk["playTypes"]:
        blk["playTypes"][pk]["ppp"] = round(perturb(block["playTypes"][pk]["ppp"], k + "|" + pk, SCALE["ppp"] * PREV_SCALE), 3)
    return compute_metrics(blk)

# -------------------------------------------------------------- build ----
def main():
    players = []
    for p in BASE:
        periods = {}
        for period in ("season", "l10", "l5"):
            blk = build_block(p, period)
            blk["metricsPrev"] = build_prev(blk, p["id"], period)
            periods[period] = blk
        players.append(dict(id=p["id"], name=p["name"], team=p["team"],
                            teamAbbr=p["teamAbbr"], pos=p["pos"], periods=periods))
    # medie del campione per il radar (il metodo reale usa tutta la lega)
    avgs = {}
    for period in ("season", "l10", "l5"):
        for m in ("pci", "ogms", "dadr"):
            avgs.setdefault(period, {})[m] = round(
                sum(pl["periods"][period]["metrics"][m] for pl in players) / len(players), 4)
    doc = dict(
        meta=dict(
            lastUpdated="2026-11-24T08:00:12Z",
            season="2026-27",
            source="demo",
            periods=["l5", "l10", "season"],
            leagueAverages=avgs,
        ),
        players=players,
    )
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    # report di controllo
    print(f"OK -> {os.path.abspath(OUT)}  ({len(players)} giocatori)")
    for period in ("season", "l10", "l5"):
        print(f"\n[{period}]")
        for m, label in (("pci", "PCI"), ("ogms", "OGMS"), ("dadr", "DADR")):
            rank = sorted(players, key=lambda pl: -pl["periods"][period]["metrics"][m])[:3]
            row = "  ".join(f"{pl['name'].split()[-1]} {pl['periods'][period]['metrics'][m]:.3f}" for pl in rank)
            print(f"  {label:5s} top3: {row}")
    # sanity check: le metriche ricalcolate dal frontend devono coincidere
    pl = players[0]["periods"]["season"]
    assert abs(compute_metrics(pl)["pci"] - pl["metrics"]["pci"]) < 1e-9

if __name__ == "__main__":
    main()
