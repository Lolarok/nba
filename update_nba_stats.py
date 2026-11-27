#!/usr/bin/env python3
"""Build a real NBA season snapshot from official stats.nba.com endpoints.

Only published NBA statistics are populated. Synergy, tracking and proprietary
metrics remain null until their source endpoints return verified data.
"""
from __future__ import annotations
import argparse, json, logging, math, os, sys, time
from datetime import datetime, timezone

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DATA_PATH=os.path.join(BASE_DIR,"data","nba_stats.json")
LOG=logging.getLogger("nba_update")

def season_now():
    now=datetime.now(timezone.utc)
    y=now.year if now.month>=10 else now.year-1
    return f"{y}-{str(y+1)[2:]}"

def fetch_stats(season, last_n, pause):
    from nba_api.stats.endpoints import leaguedashplayerstats
    def request():
        return leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",
            measure_type="Base",
            last_n_games=last_n,
        ).get_data_frames()[0]
    error=None
    for attempt in range(4):
        try:
            df=request()
            if df is None or df.empty:
                raise RuntimeError("NBA endpoint returned an empty dataset")
            time.sleep(pause)
            return df
        except Exception as exc:
            error=exc
            wait=min(45,3*(2**attempt))
            LOG.warning("LastN=%s attempt %s/4 failed: %s",last_n,attempt+1,exc)
            if attempt<3: time.sleep(wait)
    raise RuntimeError(f"LeagueDashPlayerStats LastN={last_n} failed: {error}")

def n(row,key,default=None):
    try:
        value=float(row[key])
        return None if math.isnan(value) else value
    except (KeyError,TypeError,ValueError):
        return default

def build_period(df):
    result={}
    for _,r in df.iterrows():
        pid=int(r["PLAYER_ID"])
        gp=int(n(r,"GP",0) or 0)
        if gp<=0: continue
        fga=n(r,"FGA",0) or 0
        fta=n(r,"FTA",0) or 0
        pts=n(r,"PTS",0) or 0
        denom=2*(fga+0.44*fta)
        result[pid]={
            "gp":gp,"min":round(n(r,"MIN",0) or 0,1),
            "pts":round(pts,1),"reb":round(n(r,"REB",0) or 0,1),
            "ast":round(n(r,"AST",0) or 0,1),
            "ts":round(pts/denom,3) if denom else None,
            "playTypes":{k:{"ppp":None,"freq":None,"poss":None,"pts":None}
                         for k in ("prbh","iso","spotup","cut","offscreen")},
            "tracking":{"touches":None,"secPerTouch":None,"potentialAssists":None,
                        "milesOff":None,"contestedShots":None,"deflections":None},
            "advanced":{"catchShootPts":None,"diffFgPct":None,"ptsCreatedByAssist":None},
            "metrics":{"pci":None,"ogms":None,"dadr":None},
            "metricsPrev":{"pci":None,"ogms":None,"dadr":None},
        }
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--season",default=season_now())
    ap.add_argument("--pause",type=float,default=1.5)
    ap.add_argument("--top",type=int,default=400)
    ap.add_argument("--dry-run",action="store_true")
    args=ap.parse_args()
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    try:
        season=build_period(fetch_stats(args.season,0,args.pause))
        l10=build_period(fetch_stats(args.season,10,args.pause))
        l5=build_period(fetch_stats(args.season,5,args.pause))
        if len(season)<50:
            raise RuntimeError(f"Only {len(season)} season player rows; refusing to publish")
        players=[]
        for pid,b in season.items():
            p5=l5.get(pid); p10=l10.get(pid)
            # Keep the full season player pool, including players missing from a recent split.
            src=next((r for r in []),None)
            players.append({"id":pid,"periods":{"season":b,
                "l10":p10 if p10 else dict(b,gp=0,min=None,pts=None,reb=None,ast=None,ts=None),
                "l5":p5 if p5 else dict(b,gp=0,min=None,pts=None,reb=None,ast=None,ts=None)}})
        # Get names/team/position from the same verified season endpoint.
        from nba_api.stats.endpoints import leaguedashplayerstats
        df=leaguedashplayerstats.LeagueDashPlayerStats(
            season=args.season,season_type_all_star="Regular Season",
            per_mode_detailed="PerGame",measure_type="Base",last_n_games=0
        ).get_data_frames()[0]
        info={int(r["PLAYER_ID"]):r for _,r in df.iterrows()}
        for p in players:
            r=info[p["id"]]
            p["name"]=str(r["PLAYER_NAME"]).strip()
            p["team"]=str(r["TEAM_ABBREVIATION"])
            p["teamAbbr"]=str(r["TEAM_ABBREVIATION"])
            p["pos"]="—"
        players.sort(key=lambda p:p["periods"]["season"]["min"] or 0,reverse=True)
        players=players[:args.top]
        now=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        doc={"meta":{"lastUpdated":now,"season":args.season,"source":"nba_api",
             "periods":["l5","l10","season"],
             "dataCoverage":{"baseStats":"official NBA stats.nba.com",
               "playTypes":"not_loaded","tracking":"not_loaded",
               "proprietaryMetrics":"not_calculated"},
             "leagueAverages":{"season":{"pci":None,"ogms":None,"dadr":None},
               "l10":{"pci":None,"ogms":None,"dadr":None},
               "l5":{"pci":None,"ogms":None,"dadr":None}}},
             "players":players}
        if len(players)<50: raise RuntimeError("Insufficient player records after validation")
        if args.dry_run:
            LOG.info("Dry run OK: %d real NBA player records",len(players))
            return 0
        os.makedirs(os.path.dirname(DATA_PATH),exist_ok=True)
        tmp=DATA_PATH+".tmp"
        with open(tmp,"w",encoding="utf-8") as f: json.dump(doc,f,ensure_ascii=False,indent=2)
        os.replace(tmp,DATA_PATH)
        LOG.info("Published %d real NBA player records for %s",len(players),args.season)
        return 0
    except Exception as exc:
        LOG.exception("NBA data refresh failed; existing snapshot left untouched: %s",exc)
        return 1

if __name__=="__main__": sys.exit(main())
