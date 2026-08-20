"""
ArbPro v4 — Mobile First + Bookmakers Afrique/Russie/International
"""
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json, urllib.request, urllib.error, time, os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///arbpro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'arbpro-secret-2024'
db = SQLAlchemy(app)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
ODDS_API_KEY  = os.environ.get("ODDS_API_KEY", "8e27b9c9d8ed94d3de84ecca7779338ea9f70a0854b9be884bbf909f87874332")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
CACHE_TTL     = 90

# ─── BOOKMAKERS DISPONIBLES SUR THE ODDS API ─────────────────────────────────
# Organisés par région / marché cible
BOOKMAKERS_EU_AFRICA = {
    # ── Disponibles en Afrique & très utilisés ──
    "onexbet":        {"name": "1xBet",         "flag": "🌍", "region": "eu"},
    "betway":         {"name": "Betway",         "flag": "🌍", "region": "eu"},
    "williamhill":    {"name": "William Hill",   "flag": "🇬🇧", "region": "uk"},
    "bwin":           {"name": "Bwin",           "flag": "🌍", "region": "eu"},
    "betclic":        {"name": "Betclic",        "flag": "🇫🇷", "region": "eu"},
    "unibet_eu":      {"name": "Unibet",         "flag": "🌍", "region": "eu"},
    # ── Exchanges & Sharp books ──
    "pinnacle":       {"name": "Pinnacle",       "flag": "📌", "region": "eu"},
    "betfair_ex_eu":  {"name": "Betfair Exch.",  "flag": "💱", "region": "eu"},
    "matchbook":      {"name": "Matchbook",      "flag": "💱", "region": "eu"},
    "smarkets":       {"name": "Smarkets",       "flag": "💱", "region": "eu"},
    # ── Europe classique ──
    "bet365":         {"name": "Bet365",         "flag": "🇬🇧", "region": "uk"},
    "coral":          {"name": "Coral",          "flag": "🇬🇧", "region": "uk"},
    "ladbrokes_uk":   {"name": "Ladbrokes",      "flag": "🇬🇧", "region": "uk"},
    "skybet":         {"name": "Sky Bet",        "flag": "🇬🇧", "region": "uk"},
    "paddypower":     {"name": "Paddy Power",    "flag": "🇮🇪", "region": "uk"},
    "888sport":       {"name": "888Sport",       "flag": "🌍", "region": "eu"},
    "marathonbet":    {"name": "MarathonBet",    "flag": "🌍", "region": "eu"},
    # ── US (bonus pour certains marchés) ──
    "draftkings":     {"name": "DraftKings",     "flag": "🇺🇸", "region": "us"},
    "fanduel":        {"name": "FanDuel",        "flag": "🇺🇸", "region": "us"},
    "betmgm":         {"name": "BetMGM",         "flag": "🇺🇸", "region": "us"},
    "pointsbetus":    {"name": "PointsBet",      "flag": "🇺🇸", "region": "us"},
    "bovada":         {"name": "Bovada",         "flag": "🇺🇸", "region": "us"},
    "betonlineag":    {"name": "BetOnline",      "flag": "🇺🇸", "region": "us"},
    "lowvig":         {"name": "LowVig",         "flag": "🇺🇸", "region": "us"},
    "mybookieag":     {"name": "MyBookie",       "flag": "🇺🇸", "region": "us"},
}

# Note sur les bookmakers non disponibles dans l'API
BOOKMAKERS_HORS_API = [
    "1Win", "Melbet", "Betwinner", "Paripesa", "SportyBet",
    "Bet9ja", "22Bet", "Betika", "SportPesa", "PariPesa",
    "Mostbet", "Linebet", "BC.Game"
]

LEAGUES = {
    "soccer_epl":                {"label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",   "regions": "eu,uk"},
    "soccer_uefa_champs_league":  {"label": "⚽ Champions League",  "regions": "eu,uk"},
    "soccer_france_ligue_one":    {"label": "🇫🇷 Ligue 1",          "regions": "eu,uk"},
    "soccer_spain_la_liga":       {"label": "🇪🇸 La Liga",           "regions": "eu,uk"},
    "soccer_germany_bundesliga":  {"label": "🇩🇪 Bundesliga",       "regions": "eu,uk"},
    "soccer_italy_serie_a":       {"label": "🇮🇹 Serie A",           "regions": "eu,uk"},
    "soccer_uefa_europa_league":  {"label": "🟠 Europa League",     "regions": "eu,uk"},
    "soccer_efl_champ":           {"label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship",    "regions": "eu,uk"},
    "soccer_brazil_campeonato":   {"label": "🇧🇷 Brésil Série A",   "regions": "eu"},
    "soccer_turkey_super_league": {"label": "🇹🇷 Süper Lig",        "regions": "eu"},
    "soccer_russia_premier_league":{"label":"🇷🇺 Russia Premier",   "regions": "eu"},
    "basketball_nba":             {"label": "🏀 NBA",               "regions": "us,eu"},
    "tennis_atp_french_open":     {"label": "🎾 Tennis ATP",        "regions": "eu,uk"},
}

# ─── CACHE ────────────────────────────────────────────────────────────────────
_cache    = {}
_api_info = {"remaining": "—", "used": "—", "updated": "—"}

def cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        ttl_left = CACHE_TTL - (time.time() - ts)
        if ttl_left > 0:
            return data, round(ttl_left)
    return None, 0

def cache_set(key, data):
    _cache[key] = (time.time(), data)

# ─── MODÈLE ───────────────────────────────────────────────────────────────────
class Opportunite(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    date        = db.Column(db.DateTime, default=datetime.utcnow)
    evenement   = db.Column(db.String(200), nullable=False)
    marche      = db.Column(db.String(50),  nullable=False)
    issues      = db.Column(db.Text, nullable=False)
    cotes       = db.Column(db.Text, nullable=False)
    bookmakers  = db.Column(db.Text, nullable=False)
    mise_totale = db.Column(db.Float, nullable=False)
    profit_pct  = db.Column(db.Float, nullable=False)
    profit_eur  = db.Column(db.Float, nullable=False)
    marge       = db.Column(db.Float, nullable=False)
    statut      = db.Column(db.String(20), default='detectee')

    def to_dict(self):
        return {
            'id': self.id, 'date': self.date.strftime('%d/%m/%Y %H:%M'),
            'evenement': self.evenement, 'marche': self.marche,
            'issues': json.loads(self.issues), 'cotes': json.loads(self.cotes),
            'bookmakers': json.loads(self.bookmakers),
            'mise_totale': self.mise_totale, 'profit_pct': self.profit_pct,
            'profit_eur': self.profit_eur, 'marge': self.marge, 'statut': self.statut,
        }

# ─── ARBITRAGE ────────────────────────────────────────────────────────────────
def calculer_arbitrage(cotes, mise):
    if not all(c > 1 for c in cotes): return None
    marge = sum(1/c for c in cotes)
    is_arb = marge < 1
    profit_pct = (1-marge)/marge if is_arb else (marge-1)
    mises = [{'mise': round((mise/marge)*(1/c), 2),
              'retour': round((mise/marge)*(1/c)*c, 2)} for c in cotes]
    return {
        'marge': round(marge, 6), 'is_arb': is_arb,
        'profit_pct': round(profit_pct*100, 4),
        'profit_eur': round(mise*profit_pct, 2) if is_arb else 0,
        'retour_garanti': round(mise/marge, 2),
        'mises': mises,
        'cotes_cibles': [round(c/marge, 2) for c in cotes],
    }

def analyser_matchs(raw):
    resultats = []
    for match in raw:
        books = match.get('bookmakers', [])
        if not books: continue

        # Cotes par issue par bookmaker
        par_issue = {}
        all_books_data = []
        for book in books:
            key   = book['key']
            bname = BOOKMAKERS_EU_AFRICA.get(key, {}).get('name', book.get('title', key))
            bflag = BOOKMAKERS_EU_AFRICA.get(key, {}).get('flag', '🌐')
            prices = {}
            for market in book.get('markets', []):
                if market['key'] != 'h2h': continue
                for o in market['outcomes']:
                    prices[o['name']] = float(o['price'])
                    if o['name'] not in par_issue:
                        par_issue[o['name']] = {}
                    par_issue[o['name']][bname] = float(o['price'])
            if prices:
                bk_marge = sum(1/p for p in prices.values())
                all_books_data.append({
                    'key': key, 'name': bname, 'flag': bflag,
                    'prices': prices,
                    'marge': round(bk_marge, 4),
                    'marge_pct': round(bk_marge*100, 2),
                })

        if len(par_issue) < 2: continue
        all_books_data.sort(key=lambda x: x['marge'])

        # Meilleures cotes
        issues  = list(par_issue.keys())
        best_cotes = {}
        for iss, book_prices in par_issue.items():
            best_bk = max(book_prices, key=book_prices.get)
            best_cotes[iss] = (book_prices[best_bk], best_bk)

        cotes   = [best_cotes[i][0] for i in issues]
        bknames = [best_cotes[i][1] for i in issues]
        marge   = sum(1/c for c in cotes)
        is_arb  = marge < 1
        profit  = round((1-marge)/marge*100, 4) if is_arb else 0

        resultats.append({
            'id': match['id'],
            'home': match['home_team'],
            'away': match['away_team'],
            'commence_time': match['commence_time'],
            'issues': issues,
            'best_cotes': cotes,
            'best_books': bknames,
            'marge': round(marge, 6),
            'marge_pct': round(marge*100, 2),
            'is_arb': is_arb,
            'profit_pct': profit,
            'all_books': all_books_data,
            'nb_books': len(all_books_data),
            'par_issue': par_issue,
        })
    return resultats

def formater_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z','+00:00')).replace(tzinfo=None)
        today    = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        d = dt.date()
        jours = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
        mois  = ["jan","fév","mar","avr","mai","jun","jul","aoû","sep","oct","nov","déc"]
        if d == today:    label = "Aujourd'hui"
        elif d == tomorrow: label = "Demain"
        else: label = f"{jours[d.weekday()]} {d.day} {mois[d.month-1]}"
        return label, dt.strftime('%H:%M')
    except: return "À venir", "—"

# ─── FETCH API ────────────────────────────────────────────────────────────────
def fetch_odds(sport, regions='eu,uk', force=False):
    key = f"{sport}_{regions}"
    if not force:
        cached, ttl = cache_get(key)
        if cached: return cached, True, ttl

    if ODDS_API_KEY == "VOTRE_CLE_API_ICI":
        return None, False, 0

    url = (f"{ODDS_API_BASE}/sports/{sport}/odds"
           f"?regions={regions}&markets=h2h&oddsFormat=decimal&apiKey={ODDS_API_KEY}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'ArbPro/4.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            _api_info['remaining'] = r.headers.get('x-requests-remaining','—')
            _api_info['used']      = r.headers.get('x-requests-used','—')
            _api_info['updated']   = datetime.utcnow().strftime('%H:%M:%S')
            data = json.loads(r.read().decode())
            cache_set(key, data)
            return data, False, CACHE_TTL
    except urllib.error.HTTPError as e:
        return {'error': f"Erreur {e.code}: {e.read().decode()}"}, False, 0
    except Exception as e:
        return {'error': str(e)}, False, 0

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    sport = request.args.get('sport', 'soccer_epl')
    return render_template('index.html',
        leagues=LEAGUES, sport_actuel=sport,
        api_configuree=(ODDS_API_KEY != "VOTRE_CLE_API_ICI"),
        bookmakers_hors_api=BOOKMAKERS_HORS_API,
        cache_ttl=CACHE_TTL,
    )

@app.route('/historique')
def historique():
    opps = Opportunite.query.order_by(Opportunite.date.desc()).all()
    return render_template('historique.html', opportunites=[o.to_dict() for o in opps])

@app.route('/dashboard')
def dashboard():
    opps = Opportunite.query.order_by(Opportunite.date.asc()).all()
    data = [o.to_dict() for o in opps]
    stats = {
        'total_opps':    len(data),
        'capital_total': round(sum(o['mise_totale'] for o in data), 2),
        'profit_total':  round(sum(o['profit_eur']  for o in data), 2),
        'roi_moyen':     round(sum(o['profit_pct']  for o in data)/len(data), 4) if data else 0,
        'meilleure':     max(data, key=lambda x: x['profit_pct']) if data else None,
    }
    cumul, total = [], 0
    for o in data:
        total += o['profit_eur']
        cumul.append({'date': o['date'], 'profit': round(total, 2)})
    marches = {}
    for o in data:
        marches[o['marche']] = marches.get(o['marche'], 0) + 1
    return render_template('dashboard.html', stats=stats,
        cumul=json.dumps(cumul), marches=json.dumps(marches), opportunites=data)

@app.route('/api/matchs/<sport>')
def api_matchs(sport):
    force   = request.args.get('force','false') == 'true'
    league  = LEAGUES.get(sport, {})
    regions = league.get('regions', 'eu,uk')
    raw, from_cache, ttl = fetch_odds(sport, regions, force)

    if raw is None:
        return jsonify({'error':'api_non_configuree'})
    if isinstance(raw, dict) and 'error' in raw:
        return jsonify({'error': raw['error']}), 500

    matchs = analyser_matchs(raw)
    groupes = {}
    for m in matchs:
        label, heure = formater_date(m['commence_time'])
        m['heure'] = heure
        groupes.setdefault(label, []).append(m)

    ordre = ["Aujourd'hui","Demain"]
    gt = {k: groupes[k] for k in ordre if k in groupes}
    for k in groupes:
        if k not in gt: gt[k] = groupes[k]

    arbs = sorted([m for m in matchs if m['is_arb']],
                  key=lambda x: x['profit_pct'], reverse=True)
    return jsonify({
        'groupes': gt, 'total_matchs': len(matchs),
        'total_arbs': len(arbs), 'top_arbs': arbs[:5],
        'from_cache': from_cache, 'cache_ttl': ttl,
        'api_info': _api_info,
    })

@app.route('/api/calculer', methods=['POST'])
def api_calculer():
    d = request.json
    try:
        cotes = [float(c) for c in d.get('cotes',[])]
        mise  = float(d.get('mise',1000))
        if len(cotes) < 2: return jsonify({'error':'Minimum 2 cotes'}), 400
        return jsonify(calculer_arbitrage(cotes, mise))
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/sauvegarder', methods=['POST'])
def api_sauvegarder():
    d = request.json
    try:
        cotes  = [float(c) for c in d['cotes']]
        mise   = float(d['mise'])
        result = calculer_arbitrage(cotes, mise)
        if not result or not result['is_arb']:
            return jsonify({'error': "Pas d'opportunité"}), 400
        opp = Opportunite(
            evenement=d.get('evenement','Match sans nom'),
            marche=d.get('marche','1X2'),
            issues=json.dumps(d.get('issues',[])),
            cotes=json.dumps(cotes),
            bookmakers=json.dumps(d.get('bookmakers',[])),
            mise_totale=mise,
            profit_pct=result['profit_pct'],
            profit_eur=result['profit_eur'],
            marge=result['marge'],
        )
        db.session.add(opp)
        db.session.commit()
        return jsonify({'success': True, 'id': opp.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/statut/<int:i>', methods=['POST'])
def api_statut(i):
    opp = Opportunite.query.get_or_404(i)
    opp.statut = request.json.get('statut','detectee')
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/supprimer/<int:i>', methods=['DELETE'])
def api_supprimer(i):
    opp = Opportunite.query.get_or_404(i)
    db.session.delete(opp); db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tout-supprimer', methods=['DELETE'])
def api_tout_supprimer():
    Opportunite.query.delete(); db.session.commit()
    return jsonify({'success': True})

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"\n🟢 ArbPro v4 → http://localhost:{port}")
    k = "✓" if ODDS_API_KEY != "VOTRE_CLE_API_ICI" else "⚠ À configurer"
    print(f"🔑 API: {k}\n")
    app.run(debug=False, host="0.0.0.0", port=port)
