# Vastgoed - Claude Code Instructies

## Project
Luxury Short-Stay Rental Platform met booking engine, contracten, facturen en admin panel.
Target: expats, zakelijke reizigers, relocating professionals.
3 luxury properties, verblijf van 1 week tot 2 jaar.
Locatie: `E:\scripts\webscraper\CBSbuurt\vastgoed\`
GitHub: AnneVersion/vastgoed

## Starten
```bash
# Database migratie (eenmalig na setup)
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -d vastgoed -f sql/03_short_stay_migration.sql

# Server starten
python serve.py  # http://localhost:8088
```

## Branch-strategie
- **main** = stabiel/productie
- **develop** = dagelijkse ontwikkeling (standaard werkbranch)
- **feature/*** = nieuwe features, maak aan vanuit develop

## Database
PostgreSQL database `vastgoed`, user `postgres`, pw `postgres`.
Setup volgorde:
1. `sql/01_schema.sql` (basis schema)
2. `sql/02_seed.sql` (testdata met 9 demo properties)
3. `sql/03_short_stay_migration.sql` (short-stay kolommen + contracten/facturen tabellen + luxury property updates)

## Key Files
- `index.html` - Luxury booking engine (5-staps wizard: periode -> gegevens -> contract -> iDEAL -> bevestiging)
- `admin.html` - Admin panel (7 tabs: dashboard, residences, reserveringen, betalingen, contracten, facturen, kalender)
- `serve.py` - Python HTTP server met REST API, contract- en factuur-generatie
- `sql/` - PostgreSQL schema, seed data en migraties

## Architectuur
- Single-file frontend (index.html en admin.html)
- `serve.py` is een ThreadingHTTPServer met psycopg2 connection pool
- Geen Flask - gebruikt standaard http.server
- iDEAL betaling is een simulatie (Mollie-style UI met 9 banken, geen echte PSP)
- Contract generatie: HTML huurovereenkomst naar Nederlands recht
- Factuur generatie: HTML factuur met BTW berekening (21%), factuurnummer DC-2026-XXXX
- iCal: Airbnb kalender sync (import/export/sync endpoints)
- Design: luxury cream/gold theme (#B8860B), Verdana font

## API Endpoints
- `POST /api/contract/generate` - Genereer huurovereenkomst
- `GET  /api/contract/<id>` - Bekijk contract als HTML
- `GET  /api/contracten` - Lijst alle contracten
- `PUT  /api/contracten/<id>/sign` - Markeer als ondertekend
- `POST /api/factuur/generate` - Genereer factuur
- `GET  /api/factuur/<id>` - Bekijk factuur als HTML
- `GET  /api/facturen` - Lijst alle facturen
- `PUT  /api/facturen/<id>/status` - Update status (openstaand/betaald/verlopen)

## 3 Luxury Properties
1. **The Keizersgracht Suite** (Amsterdam) - Studio, 65m2, EUR 2.500/maand
2. **The Statenkwartier Residence** (Den Haag) - 2BR, 110m2, EUR 3.500/maand
3. **The Wilhelmina Penthouse** (Rotterdam) - 3BR, 155m2, EUR 5.000/maand

## Pricing
- Maandprijs (weekprijs voor <2 weken)
- Staffelkorting: 3+ mnd = -10%, 6+ mnd = -15%, 12+ mnd = -20%
- Servicekosten per maand
- Borg = 1x maandprijs (terugbetaling bij vertrek)
- BTW: 21% over huur + servicekosten
- Short-stay regels: Amsterdam geen nieuwe vergunningen (sinds 2014), Arnhem soepeler

## Let op
- Port 8088
- Database moet draaien voor de server start
- Admin wachtwoord: `admin`
- Contracten en facturen tabellen worden aangemaakt door `03_short_stay_migration.sql`
