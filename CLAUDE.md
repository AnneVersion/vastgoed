# Vastgoed - Claude Code Instructies

## Project
Serviced Apartments Booking Engine met admin panel.
Locatie: `E:\scripts\webscraper\CBSbuurt\vastgoed\`

## Starten
```bash
python serve.py  # http://localhost:8088
```

## Branch-strategie
- **main** = stabiel/productie
- **develop** = dagelijkse ontwikkeling (standaard werkbranch)
- **feature/*** = nieuwe features, maak aan vanuit develop

## Database
PostgreSQL database `vastgoed`, user `postgres`, pw `postgres`.
Setup: `sql/01_schema.sql` (schema) + `sql/02_seed.sql` (testdata)

## Key Files
- `index.html` - Booking engine (5-staps wizard, Leaflet kaart)
- `admin.html` - Admin panel (5 tabs: dashboard, panden, reserveringen, betalingen, kalender)
- `serve.py` - Python HTTP server met REST API en connection pooling
- `sql/` - PostgreSQL schema en seed data

## Architectuur
- Single-file frontend (index.html en admin.html)
- `serve.py` is een ThreadingHTTPServer met psycopg2 connection pool
- Geen Flask - gebruikt standaard http.server
- iDEAL betaling is een simulatie (geen echte PSP)

## Let op
- Port 8088
- Database moet draaien voor de server start
- Foto URLs in `foto_urls` array per woning
- Tarieven als JSONB: `{"flexibel": x, "standaard": y, "niet_restitueerbaar": z}`
