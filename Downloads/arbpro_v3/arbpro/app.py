"""
ArbPro v3 — Arbitrage Sportif avec cotes bookmakers en temps réel
The Odds API v4 — 40+ bookmakers — auto-refresh — détection instantanée
"""

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os, json, urllib.request, urllib.error, time

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///arbpro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'arbpro-secret-2024'
db = SQLAlchemy(app)

# ─── CONFIG ──────────────────────────────────────────────────────────────────
# 1. Va sur https://the-odds-api.com/ → inscription gratuite
# 2. Copie ta clé et remplace la valeur ci-dessous
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "ef9614281c383afaaec9ff793e46ef3f")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
CACHE_TTL     = 90   # secondes entre chaque appel API (économise les crédits)

LEAGUES = {
    "soccer_epl":               {"label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",    "region": "uk"},
    "soccer_uefa_champs_league": {"label": "⚽ Champions League",   "region": "eu"},
    "soccer_france_ligue_one":   {"label": "🇫🇷 Ligue 1",           "region": "eu"},
    "soccer_spain_la_liga":      {"label": "🇪🇸 La Liga",            "region": "eu"},
    "soccer_germany_bundesliga": {"label": "🇩🇪 Bundesliga",        "region": "eu"},
    "soccer_italy_serie_a":      {"label": "🇮🇹 Serie A",            "region": "eu"},
    "soccer_efl_champ":          {"label": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Championship",     "region": "uk"},
    "soccer_uefa_europa_league": {"label": "🟠 Europa League",      "region": "eu"},
    "soccer_usa_mls":            {"label": "🇺🇸 MLS",                "region": "us"},
}

# Tous les bookmakers connus avec leur nom affiché
BOOKMAKERS = {
    "bet365":         "Bet365",
    "unibet_eu":      "Unibet",
    "williamhill":    "William Hill",
    "betfair_ex_eu":  "Betfair Exchange",
    "betfair":        "Betfair",
    "pinnacle":       "Pinnacle",
    "betclic":        "Betclic",
    "bwin":           "Bwin",
    "betway":         "Betway",
    "coral":          "Coral",
    "ladbrokes_uk":   "Ladbrokes",
    "skybet":         "Sky Bet",
    "paddypower":     "Paddy Power",
    "marathonbet":    "MarathonBet",
    "888sport":       "888sport",
    "suprabets":      "SupraBets",
    "onexbet":        "1xBet",
    "sport888":       "888Sport",
    "matchbook":      "Matchbook",
    "smarkets":       "Smarkets",
    "draftkings":     "DraftKings",
    "fanduel":        "FanDuel",
    "betmgm":         "BetMGM",
    "pointsbetus":    "PointsBet",
    "bovada":         "Bovada",
    "mybookieag":     "MyBookie",
    "betrivers":      "BetRivers",
    "unibet_us":      "Unibet US",
    "lowvig":         "LowVig",
    "betonlineag":    "BetOnline",
}

# ─── CACHE ───────────────────────────────────────────────────────────────────
_cache = {}
_api_usage = {"remaining": None, "used": None, "last_check": None}

def cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data, round(CACHE_TTL - (time.time() - ts))
    return None, 0

def cache_set(key, data):
    _cache[key] = (time.time(), data)

# ─── MODÈLE BDD ──────────────────────────────────────────────────────────────
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

# ─── ARBITRAGE ───────────────────────────────────────────────────────────────
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

def analyser_matchs(raw_data):
    """
    Pour chaque match : trouve la MEILLEURE cote de chaque issue
    sur l'ensemble des bookmakers. Calcule si une arb existe.
    Retourne aussi le détail complet par bookmaker.
    """
    resultats = []
    for match in raw_data:
        books = match.get('bookmakers', [])
        if not books:
            continue

        # Collecter toutes les cotes par issue et par bookmaker
        # Structure : { outcome_name: { bookmaker_name: price } }
        par_issue = {}
        for book in books:
            bname = BOOKMAKERS.get(book['key'], book.get('title', book['key']))
            for market in book.get('markets', []):
                if market['key'] != 'h2h':
                    continue
                for outcome in market['outcomes']:
                    name  = outcome['name']
                    price = float(outcome['price'])
                    if name not in par_issue:
                        par_issue[name] = {}
                    par_issue[name][bname] = price

        if len(par_issue) < 2:
            continue

        # Meilleure cote par issue (max sur tous les bookmakers)
        best_cotes = {}  # { issue: (price, bookmaker) }
        for issue, book_prices in par_issue.items():
            best_book = max(book_prices, key=book_prices.get)
            best_cotes[issue] = (book_prices[best_book], best_book)

        issues  = list(best_cotes.keys())
        cotes   = [best_cotes[i][0] for i in issues]
        bknames = [best_cotes[i][1] for i in issues]
        marge   = sum(1/c for c in cotes)
        is_arb  = marge < 1
        profit  = round((1-marge)/marge*100, 4) if is_arb else 0

        # Tableau complet par bookmaker (pour affichage détaillé)
        all_books = []
        for book in books:
            bname = BOOKMAKERS.get(book['key'], book.get('title', book['key']))
            prices = {}
            for market in book.get('markets', []):
                if market['key'] != 'h2h':
                    continue
                for outcome in market['outcomes']:
                    prices[outcome['name']] = float(outcome['price'])
            if prices:
                bk_marge = sum(1/p for p in prices.values())
                all_books.append({
                    'name':   bname,
                    'prices': prices,
                    'marge':  round(bk_marge, 4),
                    'marge_pct': round(bk_marge * 100, 2),
                })
        # Trier par marge croissante (bookmaker le plus généreux en premier)
        all_books.sort(key=lambda x: x['marge'])

        resultats.append({
            'id':            match['id'],
            'home':          match['home_team'],
            'away':          match['away_team'],
            'commence_time': match['commence_time'],
            'issues':        issues,
            'best_cotes':    cotes,
            'best_books':    bknames,
            'marge':         round(marge, 6),
            'marge_pct':     round(marge * 100, 2),
            'is_arb':        is_arb,
            'profit_pct':    profit,
            'all_books':     all_books,
            'nb_books':      len(all_books),
            'par_issue':     par_issue,
        })

    return resultats

def formater_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00')).replace(tzinfo=None)
        today    = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        d = dt.date()
        if d == today:
            label = "Aujourd'hui"
        elif d == tomorrow:
            label = "Demain"
        else:
            jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
            mois  = ["jan","fév","mar","avr","mai","juin","juil","aoû","sep","oct","nov","déc"]
            label = f"{jours[d.weekday()]} {d.day} {mois[d.month-1]}"
        return label, dt.strftime('%H:%M')
    except:
        return "À venir", "—"

# ─── FETCH API ───────────────────────────────────────────────────────────────
def fetch_odds(sport, region='eu', force=False):
    cache_key = f"{sport}_{region}"
    if not force:
        cached, ttl = cache_get(cache_key)
        if cached is not None:
            return cached, True, ttl

    if ODDS_API_KEY == "VOTRE_CLE_API_ICI":
        return None, False, 0

    # Récupérer toutes les régions pour avoir max de bookmakers
    regions = "eu,uk" if region == 'eu' else "us,uk"
    url = (f"{ODDS_API_BASE}/sports/{sport}/odds"
           f"?regions={regions}&markets=h2h&oddsFormat=decimal&apiKey={ODDS_API_KEY}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'ArbPro/3.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            # Lire les headers de quota
            _api_usage['remaining'] = r.headers.get('x-requests-remaining')
            _api_usage['used']      = r.headers.get('x-requests-used')
            _api_usage['last_check']= datetime.utcnow().strftime('%H:%M:%S')
            data = json.loads(r.read().decode())
            cache_set(cache_key, data)
            return data, False, CACHE_TTL
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {'error': f"Erreur API {e.code}: {body}"}, False, 0
    except Exception as e:
        return {'error': str(e)}, False, 0

# ─── ROUTES PAGES ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    sport = request.args.get('sport', 'soccer_epl')
    return render_template('index.html',
        leagues=LEAGUES,
        sport_actuel=sport,
        api_configuree=(ODDS_API_KEY != "VOTRE_CLE_API_ICI"),
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

# ─── API ENDPOINTS ────────────────────────────────────────────────────────────
@app.route('/api/matchs/<sport>')
def api_matchs(sport):
    """Matchs avec meilleures cotes de tous les bookmakers + détection arb"""
    force   = request.args.get('force', 'false') == 'true'
    league  = LEAGUES.get(sport, {})
    region  = league.get('region', 'eu')
    raw, from_cache, ttl = fetch_odds(sport, region, force)

    if raw is None:
        return jsonify({'error': 'api_non_configuree'}), 200
    if isinstance(raw, dict) and 'error' in raw:
        return jsonify({'error': raw['error']}), 500

    matchs = analyser_matchs(raw)

    # Grouper par date
    groupes = {}
    for m in matchs:
        label, heure = formater_date(m['commence_time'])
        m['heure'] = heure
        groupes.setdefault(label, []).append(m)

    # Trier : Aujourd'hui → Demain → suite
    ordre_fixe = ["Aujourd'hui", "Demain"]
    groupes_tries = {k: groupes[k] for k in ordre_fixe if k in groupes}
    for k in groupes:
        if k not in groupes_tries:
            groupes_tries[k] = groupes[k]

    arbs = [m for m in matchs if m['is_arb']]
    return jsonify({
        'groupes':      groupes_tries,
        'total_matchs': len(matchs),
        'total_arbs':   len(arbs),
        'from_cache':   from_cache,
        'cache_ttl':    ttl,
        'api_usage':    _api_usage,
        'top_arbs':     sorted(arbs, key=lambda x: x['profit_pct'], reverse=True)[:5],
    })

@app.route('/api/calculer', methods=['POST'])
def api_calculer():
    d = request.json
    try:
        cotes = [float(c) for c in d.get('cotes', [])]
        mise  = float(d.get('mise', 1000))
        if len(cotes) < 2:
            return jsonify({'error': 'Minimum 2 cotes requises'}), 400
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
            return jsonify({'error': "Pas d'opportunité détectée"}), 400
        opp = Opportunite(
            evenement=d.get('evenement', 'Match sans nom'),
            marche=d.get('marche', '1X2'),
            issues=json.dumps(d.get('issues', [])),
            cotes=json.dumps(cotes),
            bookmakers=json.dumps(d.get('bookmakers', [])),
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

@app.route('/api/statut/<int:opp_id>', methods=['POST'])
def api_statut(opp_id):
    opp = Opportunite.query.get_or_404(opp_id)
    opp.statut = request.json.get('statut', 'detectee')
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/supprimer/<int:opp_id>', methods=['DELETE'])
def api_supprimer(opp_id):
    opp = Opportunite.query.get_or_404(opp_id)
    db.session.delete(opp)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tout-supprimer', methods=['DELETE'])
def api_tout_supprimer():
    Opportunite.query.delete()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/usage')
def api_usage():
    return jsonify(_api_usage)

# ─── INIT ─────────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    print("\n🟢 ArbPro v3 lancé → http://localhost:5000")
    key_status = "✓ Configurée" if ODDS_API_KEY != "VOTRE_CLE_API_ICI" else "⚠️  À configurer sur https://the-odds-api.com/"
    print(f"🔑 Clé API : {key_status}")
    print(f"🔄 Cache   : {CACHE_TTL}s\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
