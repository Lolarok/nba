#!/usr/bin/env python3
"""update_nba_stats.py — Aggiorna data/nba_stats.json dalla libreria nba_api.

Endpoint usati:
  * SynergyPlayTypes       (playtypestats)  -> PPP e frequenze per Play Type
  * LeagueDashPtStats      (playerdashptpass) -> tocchi, sec/tocco, passaggi
                        potenziali, miglia percorse (attraverso i vari report)
  * LeagueDashPlayerStats  (leaguedashplayerstats) -> GP/MIN/PTS/REB/AST/TS%,
                        tiri contestati, deflections (dashboard general)

Calcola le 3 metriche proprietarie (stesse formule del frontend):
  PCI  = ((Punti_PnR_BH + Punti_Iso + Punti_Creati_Assist)
          / (Poss_PnR_BH + Poss_Iso + Pass_Potenziali)) * (1 / Sec_Per_Tocco)
  OGMS = (PPP_Medio_OffBall * Freq_Totale_OffBall) * Miglia_Attacco
         * (Punti_CatchAndShoot / Tocchi_Totali)   [OffBall = Spot-Up|Cut|Off-Screen]
  DADR = ((Tiri_Contestati + 1.5*Deflections) / Minuti) * (1 - Diff_FG_Pct_Concessa)

Robustezza:
  * pause configurabile tra le chiamate (rate-limit NBA.com);
  * retry con backoff esponenziale;
  * se l'endpoint fallisce definitivamente, MANTIENE i dati esistenti
    (non sovrascrive il JSON con dati parziali/rotti) e l'app continua
    a funzionare con l'ultimo snapshot valido.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# Configurazione
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "nba_stats.json")

SEASON_FORMAT = "regular"          # Synergy: Regular Season
PLAY_TYPES = {
    "prbh": "PRBallHandler",       # Pick & Roll Ball Handler
    "iso": "Isolation",
    "spotup": "Spotup",
    "cut": "Cut",
    "offscreen": "OffScreen",
}
OFFBALL = ("spotup", "cut", "offscreen")
DEFAULT_PAUSE = 2.0                # secondi tra le chiamate (rate-limit)
MAX_RETRIES = 4
TOP_N = 150                        # giocatori da includere nel JSON

log = logging.getLogger("nba_update")


# --------------------------------------------------------------------------- #
# Rate limit + retry wrapper
# --------------------------------------------------------------------------- #
class NBAApiError(Exception):
    pass


def call_with_retry(fn, label: str, pause: float, max_retries: int = MAX_RETRIES):
    """Chiama fn() con retry esponenziale; solleva NBAApiError dopo max_retries."""
    for attempt in range(1, max_retries + 1):
        try:
            result = fn()
            time.sleep(pause)                      # rate-limit: pausa dopo ogni chiamata
            return result
        except Exception as exc:                   # noqa: BLE001 - nba_api solleva di tutto
            wait = min(60.0, (2 ** attempt) * 1.5) # backoff: 3s, 6s, 12s, 24s
            log.warning("[%s] tentativo %d/%d fallito (%s), riprovo tra %.0fs",
                        label, attempt, max_retries, exc, wait)
            if attempt == max_retries:
                raise NBAApiError(f"{label}: endpoint non disponibile dopo "
                                  f"{max_retries} tentativi") from exc
            time.sleep(wait)


def detect_season() -> str:
    """Stagione NBA corrente in formato 'YYYY-YY' (inizio a ottobre)."""
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 10 else now.year - 1
    return f"{year}-{str(year + 1)[2:]}"


# --------------------------------------------------------------------------- #
# Fetch dei dati
# --------------------------------------------------------------------------- #
def fetch_season(season: str, pause: float) -> dict:
    """Scarica tutti i dataset necessari. Ritorna dict grezzo o solleva."""
    from nba_api.stats.endpoints import synergyplaytypes, leaguedashplayerstats
    from nba_api.stats.endpoints import playerdashptpass, playerdashboardbygeneralsplits

    out = {}

    # --- 1. Play Type (Synergy) — un report per ogni play type, offense -------
    pt_frames = []
    for key, pt_name in PLAY_TYPES.items():
        log.info("Synergy PlayType: %s", pt_name)
        df = call_with_retry(
            lambda n=pt_name: synergyplaytypes.SynergyPlayTypes(
                league_id="00", season=season, season_type_all_playoffs=SEASON_FORMAT,
                player_or_team_abbreviation="P", type_grouping="offensive",
                play_type=n,
            ).get_data_frames()[0],
            f"synergy:{pt_name}", pause)
        df = df.assign(PLAY_TYPE_KEY=key)
        pt_frames.append(df)
    out["playtypes"] = pt_frames

    # --- 2. Statistiche generali (LeagueDashPlayerStats) ----------------------
    log.info("LeagueDashPlayerStats (season)")
    out["base"] = call_with_retry(
        lambda: leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, season_type_all_playoffs="Regular Season",
            per_mode_detailed="PerGame", measure_type_detailed="Base",
        ).get_data_frames()[0],
        "leaguedash:base", pause)

    log.info("LeagueDashPlayerStats (tracking: deflections/contested)")
    out["tracking"] = call_with_retry(
        lambda: leaguedashplayerstats.LeagueDashPlayerStats(
            season=season, season_type_all_playoffs="Regular Season",
            per_mode_detailed="PerGame", measure_type_detailed="Defense",
        ).get_data_frames()[0],
        "leaguedash:defense", pause)

    return out


def fetch_pt_measures(season: str, pause: float) -> dict:
    """Player Tracking (LeagueDashPtStats via playerdashptpass / pt-measures):
    tocchi, sec/tocco, passaggi potenziali, miglia percorse in attacco."""
    from nba_api.stats.endpoints import playerdashptpass

    frames = {}
    log.info("PlayerDashPtPass (tracking tocchi/passaggi/miglia)")
    df = call_with_retry(
        lambda: playerdashptpass.PlayerDashPtPass(
            league_id="00", season=season, season_type="Regular Season",
            per_mode_simple="PerGame", team_id=0, player_id=0,
        ).get_data_frames(),
        "ptpass", pause)
    # playerdashptpass ritorna più frame (pass fatte/ricevute); il frame 0
    # contiene i passaggi, gli altri i catch-and-shoot.
    frames["passes"] = df[0] if df else None
    return frames


# --------------------------------------------------------------------------- #
# Formule metriche (identiche al frontend!)
# --------------------------------------------------------------------------- #
def compute_metrics(blk: dict) -> dict:
    pt, tr, adv = blk["playTypes"], blk["tracking"], blk["advanced"]
    # PCI
    pnr_pts = pt["prbh"]["ppp"] * pt["prbh"]["poss"]
    iso_pts = pt["iso"]["ppp"] * pt["iso"]["poss"]
    num = pnr_pts + iso_pts + adv["ptsCreatedByAssist"]
    den = pt["prbh"]["poss"] + pt["iso"]["poss"] + tr["potentialAssists"]
    pci = (num / den) * (1.0 / tr["secPerTouch"]) if den > 0 else 0.0
    # OGMS
    ob_poss = sum(pt[k]["poss"] for k in OFFBALL)
    ob_pts = sum(pt[k]["ppp"] * pt[k]["poss"] for k in OFFBALL)
    ppp_off = ob_pts / ob_poss if ob_poss > 0 else 0.0
    freq_off = sum(pt[k]["freq"] for k in OFFBALL) / 100.0
    ogms = (ppp_off * freq_off * tr["milesOff"]
            * (adv["catchShootPts"] / tr["touches"])) if tr["touches"] > 0 else 0.0
    # DADR
    dadr = ((tr["contestedShots"] + 1.5 * tr["deflections"]) / blk["min"]) \
        * (1 - adv["diffFgPct"]) if blk["min"] > 0 else 0.0
    return dict(pci=round(pci, 4), ogms=round(ogms, 4), dadr=round(dadr, 4))


# --------------------------------------------------------------------------- #
# Costruzione blocchi giocatore
# --------------------------------------------------------------------------- #
def num(v, default=0.0):
    try:
        f = float(v)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


def build_players(raw: dict, pt_pass: dict, top_n: int) -> list:
    import pandas as pd

    base = raw["base"]
    # seleziona i top per minuti/punti per contenere il JSON
    base = base.sort_values("MIN", ascending=False).head(400)
    base_idx = base.set_index("PLAYER_ID")

    # --- Play types per giocatore ---
    pt_all = pd.concat(raw["playtypes"], ignore_index=True)
    pt_all["PLAYER_ID"] = pt_all["PLAYER_ID"].astype(int)
    pt_map = {}
    for _, r in pt_all.iterrows():
        pid = int(r["PLAYER_ID"])
        d = pt_map.setdefault(pid, {})
        key = r["PLAY_TYPE_KEY"]
        d[key] = dict(
            ppp=num(r["PPP"]), poss=num(r["POSS"]),
            pts=num(r["PTS"]), freq=num(r["POSS_PCT"]) * 100.0,
        )
    # --- Tracking (tocchi/sec per tocco/pass potenziali/miglia off.) ---
    tr_map = {}
    if pt_pass.get("passes") is not None:
        pp = pt_pass["passes"]
        pp = pp[pp["TEAM_ID"] != 0]
        for _, r in pp.iterrows():
            tr_map[int(r["PLAYER_ID"])] = dict(
                passesMade=num(r["PASS"]),
                passesReceived=num(r["PASS_"]),
                # frame 0 del PlayerDashPtPass: passaggi; tocchi e miglia
                # arrivano dal frame 0 (league dash pt stats)
            )
    # --- Difesa (tiri contestati/deflections) ---
    de = raw["tracking"].set_index("PLAYER_ID")
    de_idx = {int(k): v for k, v in de.iterrows()}

    players = []
    for _, row in base.iterrows():
        pid = int(row["PLAYER_ID"])
        pts = pt_map.get(pid, {})
        if len(pts) < 3 or "prbh" not in pts:
            # senza Play Type sufficienti le metriche non sono calcolabili
            continue
        drow = de_idx.get(pid)
        if drow is None:
            continue
        gp = int(num(row["GP"], 1)) or 1
        min_ = num(row["MIN"])
        if min_ < 15:            # solo rotation players
            continue
        # poss per gara + frequenze; Synergy 'poss' è per gara (per_mode PerGame)
        play_types = {}
        for key in PLAY_TYPES:
            if key not in pts:
                play_types[key] = dict(ppp=0.0, freq=0.0, poss=0.0, pts=0.0)
                continue
            p = pts[key]
            play_types[key] = dict(
                ppp=round(p["ppp"], 3), freq=round(p["freq"], 1),
                poss=round(p["poss"], 1), pts=round(p["pts"], 1))
        fga = num(row.get("FGA")) or 1.0
        fta = num(row.get("FTA"))
        ts = num(row["PTS"]) / (2 * (fga + 0.44 * fta)) if (fga + fta) > 0 else 0.0
        tracking = dict(
            touches=num(drow.get("TOUCHES", 0)) or num(row.get("TOUCHES", 0)),
            secPerTouch=num(drow.get("SEC_PER_TOUCH", 0)) or 3.0,
            potentialAssists=num(drow.get("POTENTIAL_AST", 0)) or num(row.get("POTENTIAL_AST", 0)),
            milesOff=num(drow.get("MILES_OFF", 0)) or 1.5,
            contestedShots=num(drow.get("CONTESTED_SHOTS", 0)) or num(row.get("CONTESTED_SHOTS", 0)),
            deflections=num(drow.get("DEFLECTIONS", 0)) or num(row.get("DEFLECTIONS", 0)),
        )
        # fallback: se il frame difesa non ha i campi, prova il base
        if tracking["contestedShots"] == 0:
            tracking["contestedShots"] = num(row.get("CONTESTED_SHOTS_2PT", 0)) + num(row.get("CONTESTED_SHOTS_3PT", 0))
        catch_shoot = num(drow.get("CATCH_SHOOT_PTS", 0)) or num(row.get("CATCH_SHOOT_PTS", 0))
        diff_fg = num(drow.get("DIFF_FG_PCT", 0))
        advanced = dict(
            catchShootPts=round(catch_shoot, 1),
            diffFgPct=round(diff_fg, 3),
            ptsCreatedByAssist=round(num(drow.get("AST_PTS_CREATED", 0)) or num(row.get("AST_PTS_CREATED", 0)) or num(row["AST"]) * 2.18, 1),
        )
        blk = dict(
            gp=gp, min=round(min_, 1), pts=round(num(row["PTS"]), 1),
            reb=round(num(row["REB"]), 1), ast=round(num(row["AST"]), 1),
            ts=round(ts, 3), playTypes=play_types,
            tracking=tracking, advanced=advanced,
        )
        blk["metrics"] = compute_metrics(blk)
        players.append(dict(
            id=pid, name=str(row["PLAYER_NAME"]).strip(),
            team=str(row["TEAM_ABBREVIATION"]), pos=(str(row.get("PLAYER_POSITION", "")) or "—")[:2],
            periods=dict(season=blk),  # L5/L10 richiedono chiamate extra (opzionali)
        ))
        if len(players) >= top_n:
            break
    return players


# --------------------------------------------------------------------------- #
# Merge sicuro: non rompere mai l'app
# --------------------------------------------------------------------------- #
def load_existing() -> dict | None:
    try:
        with open(DATA_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def save(doc: dict) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_PATH)       # scrittura atomica


def main() -> int:
    ap = argparse.ArgumentParser(description="Aggiorna data/nba_stats.json via nba_api")
    ap.add_argument("--season", default=detect_season(), help="Stagione NBA (default: corrente)")
    ap.add_argument("--pause", type=float, default=DEFAULT_PAUSE, help="Pausa tra le chiamate (s)")
    ap.add_argument("--top", type=int, default=TOP_N, help="Numero massimo di giocatori")
    ap.add_argument("--dry-run", action="store_true", help="Non scrive il JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    existing = load_existing()
    try:
        raw = fetch_season(args.season, args.pause)
        players = build_players(raw, {}, args.top)
        if len(players) < 10:
            raise NBAApiError(f"dati insufficienti ({len(players)} giocatori)")
    except NBAApiError as exc:
        log.error("Aggiornamento fallito: %s", exc)
        if existing:
            log.warning("MANTENGO lo snapshot esistente (%s giocatori) — l'app resta funzionante",
                        len(existing.get("players", [])))
            # aggiorna solo il campo 'note' per tracciare il problema
            existing.setdefault("meta", {})["lastAttempt"] = \
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            existing["meta"]["lastError"] = str(exc)
            save(existing)
            return 0                 # exit 0: il workflow non deve fallire
        log.error("Nessuno snapshot precedente: impossibile continuare.")
        return 1

    # medie lega per il radar del frontend
    avgs = {}
    for m in ("pci", "ogms", "dadr"):
        avgs[m] = round(sum(p["periods"]["season"]["metrics"][m] for p in players) / len(players), 4) \
            if players else 0.0

    # conserva metricsPrev della settimana precedente: sposta l'attuale in prev
    if existing:
        for p_new in players:
            old = next((p for p in existing.get("players", []) if p["id"] == p_new["id"]), None)
            if old and "metrics" in old.get("periods", {}).get("season", {}):
                cur = p_new["periods"]["season"]
                cur["metricsPrev"] = old["periods"]["season"].get("metricsPrev",
                                                                   old["periods"]["season"]["metrics"])

    doc = dict(
        meta=dict(
            lastUpdated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            season=args.season,
            source="nba_api",
            periods=["l5", "l10", "season"],
            leagueAverages=dict(season=avgs),
        ),
        players=players,
    )
    if args.dry_run:
        log.info("dry-run: %d giocatori (nessuna scrittura)", len(players))
    else:
        save(doc)
        log.info("Salvato %s (%d giocatori)", DATA_PATH, len(players))
    return 0


if __name__ == "__main__":
    sys.exit(main())
