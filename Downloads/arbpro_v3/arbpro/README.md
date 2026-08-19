# ArbPro — Calculateur d'Arbitrage Sportif

Application web Python/Flask complète avec base de données SQLite.

## Installation (une seule fois)

```bash
# 1. Aller dans le dossier
cd arbpro

# 2. Installer Python (si pas déjà fait) → python.org

# 3. Installer les dépendances
pip install flask flask-sqlalchemy

# 4. Lancer l'application
python app.py
```

## Utilisation

```bash
python app.py
# Ouvrir → http://localhost:5000
```

## Structure du projet

```
arbpro/
├── app.py              ← Serveur Flask (logique + API)
├── arbpro.db           ← Base de données SQLite (créée auto)
├── README.md
└── templates/
    ├── base.html       ← Template de base (navigation, styles)
    ├── index.html      ← Page Calculateur
    ├── historique.html ← Page Historique
    └── dashboard.html  ← Page Tableau de bord
```

## Fonctionnalités

- Calculateur temps réel (5 types de marchés)
- Base de données persistante (SQLite)
- Gestion des statuts (Détectée / Placée / Gagnée / Perdue)
- Historique avec filtres et recherche
- Dashboard avec graphiques (Chart.js)
- API REST complète
- Interface responsive (mobile compatible)

## API disponible

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| /api/calculer | POST | Calcule un arbitrage |
| /api/sauvegarder | POST | Sauvegarde une opportunité |
| /api/statut/:id | POST | Met à jour le statut |
| /api/supprimer/:id | DELETE | Supprime une opportunité |
| /api/tout-supprimer | DELETE | Vide l'historique |
| /api/stats | GET | Retourne les statistiques |
