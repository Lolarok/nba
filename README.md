# NBA Advanced Stats — Dashboard Metriche Proprietarie

Dashboard web moderna (dark mode, tema dashboard sportiva professionale) dedicata
alle statistiche avanzate NBA: **Play Type Synergy**, **Player Tracking** e **3 metriche
proprietarie** calcolate automaticamente.

![Season](https://img.shields.io/badge/season-2026--27-ffb020) ![Update](https://img.shields.io/badge/aggiornamento-giornaliero_08%3A00_UTC-2f9dff)

## Funzionalità

- **Header e filtri**: ricerca per giocatore o squadra, selettore periodo
  (Ultime 5 / Ultime 10 / Stagione intera), filtri ruolo e squadra, badge con
  data/ora dell'ultimo aggiornamento.
- **Top Performers**: 3 card in evidenza con il leader NBA per ciascuna metrica
  proprietaria (valore, squadra, variazione % vs settimana precedente).
- **Tabella interattiva**: colonne ordinabili (clic sull'intestazione), con dati
  base (GP, MIN, PTS, REB, AST, TS%), Play Type (PPP e Frequenza % per P&R Ball
  Handler, Isolation, Spot-Up, Cut, Off-Screen), Player Tracking (tocchi, sec/tocco,
  passaggi potenziali, miglia in attacco, tiri contestati, deflections) e le 3
  metriche proprietarie con tooltip esplicativo al passaggio del mouse.
- **Scheda giocatore (drawer laterale)**: grafico radar che confronta le 3 metriche
  proprietarie con la media NBA e grafico a barre con la distribuzione dei Play Type
  (frequenza % + PPP).
- **Responsive**: layout ottimizzato da desktop a mobile (375px).

## Le 3 metriche proprietarie

| Metrica | Formula |
| --- | --- |
| **PCI** — Pressure Creation Index | `((Punti_PnR_BH + Punti_Iso + Punti_Creati_Assist) / (Poss_PnR_BH + Poss_Iso + Passaggi_Potenziali)) × (1 / Sec_Medi_Per_Tocco)` |
| **OGMS** — Off-Ball Gravity & Movement Score | `(PPP_Medio_OffBall × Frequenza_Totale_OffBall) × Miglia_Percorse_Attacco × (Punti_Catch_And_Shoot / Tocchi_Totali)` — OffBall = Spot-Up + Cut + Off-Screen |
| **DADR** — Defensive Activity & Deterrence Rate | `((Tiri_Contestati + 1.5 × Deflections) / Minuti) × (1 − Diff_FG_Pct_Concessa)` |

Le formule sono implementate **identiche** in tre punti: nel frontend (`app/app.js`,
`computeMetrics`), nello script di aggiornamento (`scripts/update_nba_stats.py`,
`compute_metrics`) e nel generatore dei dati demo (`scripts/generate_demo_data.py`).

## Struttura del repository

```
├── index.html                  # markup dell'app (GitHub Pages: serve questa cartella)
├── style.css                   # tema dark
├── app.js                      # logica: filtri, tabella, drawer, grafici Chart.js
├── data/
│   └── nba_stats.json          # dati (demo realistico ora; nba_api dopo il primo run)
├── scripts/
│   ├── update_nba_stats.py     # aggiornamento dati via nba_api (GitHub Actions)
│   ├── generate_demo_data.py   # generatore dataset demo (15 giocatori)
│   └── build_app.py            # assembla l'index.html single-file in download/
├── .github/workflows/
│   └── daily_nba_update.yml    # workflow giornaliero 08:00 UTC
├── requirements.txt
└── README.md
```

## Avvio locale

Nessuna build necessaria:

```bash
# opzione A — server statico qualsiasi (usa data/nba_stats.json via fetch)
python -m http.server 8080
# apri http://localhost:8080

# opzione B — apri direttamente download/nba-advanced-stats/index.html
# (versione single-file con dati demo incorporati, funziona anche offline)
```

## Aggiornamento automatico (GitHub Actions)

Il workflow `.github/workflows/daily_nba_update.yml` gira **ogni giorno alle 08:00 UTC**
(anche manualmente da *Actions → Daily NBA Stats Update → Run workflow*):

1. installa `nba_api` e `pandas`;
2. esegue `scripts/update_nba_stats.py`, che scarica da NBA.com:
   - `SynergyPlayTypes` (5 Play Type offensivi, per giocatore);
   - `LeagueDashPlayerStats` (base + difesa);
   - Player Tracking (`LeagueDashPtStats` / `PlayerDashPtPass`);
3. calcola le 3 metriche proprietarie e riscrive `data/nba_stats.json`
   (scrittura **atomica**);
4. verifica l'integrità del JSON e, se ci sono cambiamenti, fa commit + push.

### Robustezza anti-blocco

- **Rate limit**: pausa configurabile (`--pause`, default 2s) tra tutte le chiamate;
- **Retry con backoff esponenziale** (4 tentativi: 3s → 6s → 12s → 24s);
- **Fallback sicuro**: se NBA.com blocca temporaneamente le richieste, lo script
  **mantiene lo snapshot esistente** (aggiornando solo `meta.lastError`) ed esce con
  codice 0, così il workflow non fallisce e l'app continua a funzionare con gli
  ultimi dati validi;
- **Validazione**: il JSON viene ricontrollato prima del commit.

Aggiornamento manuale:

```bash
pip install -r requirements.txt
python scripts/update_nba_stats.py --season 2026-27 --pause 2 --top 120
```

## Dataset demo

`data/nba_stats.json` contiene 15 giocatori NBA attuali (stagione 2026-27, dati
realistici ma indicativi): Jokić, Gilgeous-Alexander, Dončić, Tatum, Wembanyama,
Curry, Edwards, Brunson, Antetokounmpo (Miami), Haliburton, James (Philadelphia),
Mitchell, Durant (Houston), Cunningham, Brown. Include le varianti per periodo
(L5/L10/stagione), le medie lega per il radar e i valori della settimana precedente
per le variazioni nelle card.

> Nota: i numeri del dataset demo sono generati per essere plausibili e navigabili,
> non sono statistiche ufficiali. Dopo il primo run del workflow su GitHub i dati
> reali sostituiranno progressivamente quelli demo (lo script conserva
> `metricsPrev` per le variazioni settimanali).

## Pubblicazione su GitHub

```bash
git init -b main            # se si parte dai file, non da un repo esistente
git add -A
git commit -m "feat: NBA Advanced Stats dashboard"
git remote add origin https://github.com/<utente>/<repo>.git
git push -u origin main
```

- **Actions**: il workflow `daily_nba_update` parte automaticamente dopo il push
  (gli schedule girano solo sul branch di default). È possibile anche *Actions →
  Daily NBA Stats Update → Run workflow* per un aggiornamento manuale. Nota:
  GitHub disabilita i workflow schedulati dopo 60 giorni di inattività del repo.
- **GitHub Pages** (dashboard online): *Settings → Pages → Source: Deploy from a
  branch → `main` / root*. L'app caricherà `data/nba_stats.json` aggiornato
  giornalmente dal workflow.

## Note tecniche

- Frontend vanilla (HTML/CSS/JS) + **Chart.js 4** via CDN per radar e bar chart;
- `meta.source` distingue i dati demo (`demo`) da quelli reali (`nba_api`);
- il badge "Aggiornato" mostra data/ora UTC dell'ultimo aggiornamento;
- licenza: MIT.
