# Serviced Apartments Booking Engine

Booking engine en admin panel voor serviced apartments. 5-staps boekingswizard voor gasten, admin panel voor pand- en reserveringsbeheer.

## Features

### Booking Engine (index.html)
- 5-staps boekingswizard: Appartement kiezen > Datums > Gasten > Gegevens > Betaling
- Beschikbaarheidscheck in realtime
- iDEAL betaalsimulatie
- Leaflet kaart met pand locaties
- Tariefberekening (flexibel, standaard, niet-restitueerbaar)

### Admin Panel (admin.html)
- 5 tabs: Dashboard, Panden, Reserveringen, Betalingen, Kalender
- Pand CRUD met foto's, amenities, tarieven
- Reserveringsbeheer met statuswijzigingen
- Betalingsoverzicht met refund mogelijkheid
- Kalender met beschikbaarheid per pand
- Dashboard statistieken

## Tech Stack

- **Frontend**: Vanilla JS, Leaflet.js (kaarten)
- **Backend**: Python (http.server met ThreadingHTTPServer)
- **Database**: PostgreSQL met connection pooling (psycopg2)
- **Betaling**: iDEAL simulatie

## Starten

```bash
# Database setup
psql -U postgres -c "CREATE DATABASE vastgoed;"
psql -U postgres -d vastgoed -f sql/01_schema.sql
psql -U postgres -d vastgoed -f sql/02_seed.sql

# Dependencies
pip install psycopg2-binary

# Server starten
python serve.py
```

## URLs

| Pagina | URL |
|--------|-----|
| Booking Engine | http://localhost:8088 |
| Admin Panel | http://localhost:8088/admin.html |

## API Endpoints

| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/panden` | Lijst appartementen (paginatie) |
| GET | `/api/panden/<id>` | Enkel appartement |
| POST | `/api/woningen` | Nieuw pand toevoegen |
| PUT | `/api/panden/<id>` | Pand bijwerken |
| DELETE | `/api/woningen/<id>` | Pand verwijderen |
| POST | `/api/panden/<id>/onderhoud` | Onderhoudstaak toevoegen |
| GET | `/api/beschikbaarheid` | Beschikbaarheid checken |
| POST | `/api/reservering` | Boeking aanmaken (wizard) |
| GET | `/api/reserveringen` | Lijst reserveringen |
| PUT | `/api/reserveringen/<id>` | Reservering bijwerken |
| DELETE | `/api/reserveringen/<id>` | Reservering annuleren |
| GET | `/api/betalingen` | Lijst betalingen |
| POST | `/api/betalingen` | Betaling registreren |
| POST | `/api/betalingen/<id>/refund` | Terugbetaling |
| GET | `/api/kalender` | Kalenderdata |
| GET | `/api/stats` | Dashboard statistieken |

## Database Tabellen

- `woningen` - Panden met details, amenities, tarieven, foto's
- `reserveringen` - Boekingen met gasten, datums, tarieven
- `betalingen` - Betaalhistorie (iDEAL, creditcard, bank)
- `beschikbaarheid_blokkades` - Geblokkeerde datums per pand
