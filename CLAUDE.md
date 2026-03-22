# Vastgoed - Luxury Short-Stay Rental Platform

## 1. Project Overview

| Item | Waarde |
|------|--------|
| **Locatie** | `E:\scripts\webscraper\CBSbuurt\vastgoed\` |
| **URL** | `http://localhost:8088` |
| **GitHub** | AnneVersion/vastgoed |
| **Stack** | Python (ThreadingHTTPServer + psycopg2) + PostgreSQL |
| **Doelgroep** | Expats, zakelijke reizigers, relocating professionals |
| **Verblijfsduur** | 1 week tot 2 jaar |

Geen Flask. Gebruikt standaard `http.server.ThreadingHTTPServer` met psycopg2 connection pool (min=2, max=10).
Design: luxury cream/gold theme (#B8860B), Verdana font.

## 2. Starten

```bash
# 1. Database aanmaken (eenmalig)
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -c "CREATE DATABASE vastgoed;"

# 2. Schema + seed + migratie uitvoeren (volgorde belangrijk)
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -d vastgoed -f sql/01_schema.sql
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -d vastgoed -f sql/02_seed.sql
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -d vastgoed -f sql/03_short_stay_migration.sql

# 3. Optioneel: echte panden laden (vervangt demo data met 4 Darosa-panden)
PGPASSWORD=postgres "C:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h localhost -d vastgoed -f sql/04_real_properties.sql

# 4. Server starten
python serve.py  # http://localhost:8088
```

**Vereisten**: Python 3, PostgreSQL 18 draaiend, `pip install psycopg2-binary>=2.9.9`

## 3. Branch-strategie

- **main** = stabiel/productie
- **develop** = dagelijkse ontwikkeling (standaard werkbranch)
- **feature/*** = nieuwe features, maak aan vanuit develop

## 4. Architectuur

```
vastgoed/
  index.html        # Booking engine (5-staps wizard, ~66 KB)
  admin.html         # Admin panel (7 tabs, ~31 KB)
  serve.py           # HTTP server + REST API + contract/factuur generatie (~88 KB)
  requirements.txt   # psycopg2-binary>=2.9.9
  sql/
    01_schema.sql    # Basis tabellen: woningen, reserveringen, betalingen, blokkades
    02_seed.sql      # 9 demo properties
    03_short_stay_migration.sql  # Short-stay kolommen + contracten/facturen tabellen + luxury updates
    04_real_properties.sql       # 4 echte Darosa Beheer panden (vervangt demo data)
  data/
    panden.json          # Legacy JSON data (niet meer primair)
    reserveringen.json   # Legacy JSON data
    betalingen.json      # Legacy JSON data
```

**Server architectuur**:
- `serve.py` is een single-file server: ThreadingHTTPServer + psycopg2 connection pool
- Static files (index.html, admin.html) worden direct geserveerd
- Alle `/api/*` routes worden via een router pattern afgehandeld
- Input validatie voor email, datum, telefoon, statussen
- Serialisatie helper voor Decimal, date, datetime types
- Paginatie support via `?page=&per_page=` op lijst-endpoints

## 5. Key Features

### 3 Luxury Residences (via 03_short_stay_migration.sql)
1. **The Keizersgracht Suite** - Amsterdam, Studio, 65m2, EUR 2.500/maand
2. **The Statenkwartier Residence** - Den Haag, 2 slaapkamers, 110m2, EUR 3.500/maand
3. **The Wilhelmina Penthouse** - Rotterdam, 3 slaapkamers, 155m2, EUR 5.000/maand

### 4 Echte Darosa-panden (via 04_real_properties.sql)
1. **City Apartment Leidseplein** - Amsterdam, 45m2, EUR 1.800/maand
2. **Beach Apartment Zandvoort** - Zandvoort, 55m2, EUR 1.400/maand
3. **Studio A Rosendaalsestraat** - Arnhem, 22m2, EUR 650/maand
4. **Studio B Rosendaalsestraat** - Arnhem, 22m2, EUR 650/maand

### Booking Wizard (index.html)
5-stappen wizard: Periode selectie -> Gastgegevens -> Contract bekijken -> iDEAL betaling -> Bevestiging

### Contracten
- Nederlandse huurovereenkomst naar Nederlands recht (HTML, printbaar)
- Contract nummering: CON-YYYY-XXXX
- Ondertekening tracking (datum + boolean)

### Facturen
- HTML factuur met BTW berekening
- BTW: 21% over huur + servicekosten
- Factuurnummer: DC-YYYY-XXXX
- Vervaldatum: 14 dagen na generatie
- Statussen: openstaand, betaald, verlopen

### iDEAL Simulatie
Mollie-style UI met 9 Nederlandse banken. Geen echte PSP-koppeling.

### iCal Sync
- Export: `/api/woningen/<id>/ical` genereert .ics bestand
- Import: `/api/woningen/<id>/ical-import` haalt externe iCal URL op
- Sync: `/api/woningen/<id>/ical-sync` hersynct geconfigureerde URL
- Blokkades worden opgeslagen in `beschikbaarheid_blokkades` tabel

### Admin Dashboard (admin.html, 7 tabs)
1. **Dashboard** - KPI's: woningen, reserveringen, bezettingsgraad, omzet, check-ins/outs vandaag
2. **Residences** - CRUD woningen, amenities, onderhoud
3. **Reserveringen** - Lijst, status wijzigen, verwijderen
4. **Betalingen** - Overzicht, terugbetalingen
5. **Contracten** - Lijst, bekijken, ondertekenen
6. **Facturen** - Lijst, status wijzigen
7. **Kalender** - Maandoverzicht beschikbaarheid per woning

### Pricing
- Maandprijs (weekprijs voor verblijf < 2 weken)
- Staffelkorting: 3+ mnd = -10%, 6+ mnd = -15%, 12+ mnd = -20%
- Servicekosten per maand (EUR 150-300)
- Borg = 1x maandprijs
- BTW: 21% over huur + servicekosten
- Short-stay regels: Amsterdam geen nieuwe vergunningen (sinds 2014), Arnhem soepeler

## 6. Database Schema

**PostgreSQL** database `vastgoed`, user `postgres`, pw `postgres`.

### Tabellen

**woningen** (properties)
- id, extern_id, naam, type, categorie, beschrijving
- adres, postcode, stad, lat, lng
- oppervlakte_m2, kamers, slaapkamers, badkamers, max_gasten
- huurprijs, nachtprijs, schoonmaakkosten
- maandprijs, weekprijs, borg (short-stay)
- min_verblijf_dagen (default 7), max_verblijf_dagen (default 730)
- servicekosten_maand (default 150)
- energielabel, amenities[], kenmerken[], tarieven (JSONB), foto_urls[]
- beschikbaar, beschikbaar_vanaf, actief
- airbnb_url, ical_url, ical_last_sync
- rating, recensies, huurder (JSONB), onderhoud (JSONB)
- created_at, updated_at (auto-trigger)

**reserveringen** (bookings)
- id, extern_id (RES-YYYY-XXX), pand_id (FK), pand_extern_id, pand_naam
- gast_naam, gast_email, gast_telefoon, gast_adres, gast_bedrijf, gast_bsn
- check_in, check_out, gasten, gasten_volwassen, gasten_kinderen
- tarief_type, nachtprijs, nachten, schoonmaakkosten, servicekosten, korting, totaal
- status (pending/bevestigd/geannuleerd/voltooid)
- betaalstatus (openstaand/betaald/terugbetaald)
- betaal_methode, opmerkingen, promo_code
- reden_verblijf, verblijfsduur_type, maandprijs, borg (short-stay)
- appartement_id, boekingnummer, checkin, checkout (booking engine velden)
- created_at, updated_at (auto-trigger)

**betalingen** (payments)
- id, extern_id (PAY-YYYY-XXX), reservering_id (FK), reservering_extern_id
- gast_naam, bedrag, methode (iDEAL/creditcard/bank), bank
- status (pending/voltooid/mislukt/terugbetaald), transactie_id, beschrijving
- datum, created_at, updated_at (auto-trigger)

**contracten**
- id, reservering_id (FK), contract_nr (CON-YYYY-XXXX)
- contract_html, ondertekend, ondertekend_datum, created_at

**facturen**
- id, factuur_nr (DC-YYYY-XXXX), reservering_id (FK), reservering_extern_id
- bedrag_excl_btw, btw_percentage (21.00), btw_bedrag, totaal
- status (openstaand/betaald/verlopen), vervaldatum, factuur_html, created_at

**beschikbaarheid_blokkades**
- id, woning_id (FK), datum_start, datum_einde, reden, created_at

### SQL Migratie Volgorde
1. `sql/01_schema.sql` - Basis tabellen + indexes + update triggers
2. `sql/02_seed.sql` - 9 demo properties met testdata
3. `sql/03_short_stay_migration.sql` - Short-stay kolommen + contracten/facturen tabellen + 3 luxury properties
4. `sql/04_real_properties.sql` - (optioneel) Vervangt alle data met 4 echte Darosa-panden + 2 voorbeeldreserveringen + betalingen

## 7. API Endpoints

### Health
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/health` | Database status + tellingen |

### Panden (woningen)
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/panden` | Lijst woningen (paginatie: `?page=&per_page=`) |
| GET | `/api/panden/<id>` | Enkel pand op extern_id |
| POST | `/api/woningen` | Nieuw pand aanmaken |
| PUT | `/api/panden/<id>` of `/api/woningen/<id>` | Pand bijwerken |
| DELETE | `/api/woningen/<id>` | Pand verwijderen |
| POST | `/api/panden/<id>/onderhoud` | Onderhoud toevoegen |

### Reserveringen
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/reserveringen` | Lijst (paginatie) |
| POST | `/api/reserveringen` | Nieuwe reservering (admin) |
| PUT | `/api/reserveringen/<id>` | Bijwerken |
| DELETE | `/api/reserveringen/<id>` | Verwijderen |

### Booking Engine
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/beschikbaarheid?checkin=&checkout=` | Beschikbare woningen |
| POST | `/api/reservering` | Boeking vanuit wizard |

### Betalingen
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/betalingen` | Lijst (paginatie) |
| POST | `/api/betalingen` | Nieuwe betaling |
| POST | `/api/betalingen/<id>/refund` | Terugbetaling |

### Contracten
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| POST | `/api/contract/generate` | Genereer huurovereenkomst |
| GET | `/api/contract/<id>` | Bekijk contract als HTML |
| GET | `/api/contracten` | Lijst alle contracten |
| PUT | `/api/contracten/<id>/sign` | Markeer als ondertekend |

### Facturen
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| POST | `/api/factuur/generate` | Genereer factuur |
| GET | `/api/factuur/<id>` | Bekijk factuur als HTML |
| GET | `/api/facturen` | Lijst alle facturen |
| PUT | `/api/facturen/<id>/status` | Update status (openstaand/betaald/verlopen) |

### iCal
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/woningen/<id>/ical` | Export als .ics bestand |
| POST | `/api/woningen/<id>/ical-import` | Importeer externe iCal URL |
| POST | `/api/woningen/<id>/ical-sync` | Hersync geconfigureerde URL |

### Kalender & Stats
| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/api/kalender?maand=&jaar=` | Maandoverzicht beschikbaarheid |
| GET | `/api/stats` | Dashboard statistieken |

## 8. Startup Checklist

### Database setup
- [ ] PostgreSQL draait op localhost
- [ ] Database `vastgoed` bestaat
- [ ] SQL scripts uitgevoerd in volgorde: 01 -> 02 -> 03 (optioneel 04)
- [ ] `python serve.py` start zonder errors, meldt "Database connection OK"

### Booking Engine (index.html)
- [ ] Open `http://localhost:8088` - luxury landing page laadt
- [ ] Selecteer data (check-in/check-out) in stap 1
- [ ] Beschikbare woningen worden getoond
- [ ] Selecteer een woning en ga naar stap 2 (gastgegevens)
- [ ] Vul naam, email, telefoon in
- [ ] Stap 3: contract wordt gegenereerd en getoond (printbaar)
- [ ] Stap 4: iDEAL bank selectie (9 banken), betaling simuleren
- [ ] Stap 5: bevestigingspagina met boekingnummer
- [ ] Controleer staffelkorting: selecteer 3+ maanden en check of -10% wordt berekend
- [ ] Controleer BTW: 21% wordt correct berekend over huur + servicekosten
- [ ] Controleer borg: gelijk aan 1x maandprijs

### Admin Panel (admin.html)
- [ ] Open `http://localhost:8088/admin.html`
- [ ] Login met wachtwoord: `admin`
- [ ] **Tab Dashboard**: KPI's laden (woningen, reserveringen, bezettingsgraad, omzet)
- [ ] **Tab Residences**: woningen worden getoond, klik op een woning voor details
- [ ] **Tab Residences**: voeg onderhoud toe aan een woning
- [ ] **Tab Reserveringen**: lijst laadt, status wijzigen werkt
- [ ] **Tab Betalingen**: lijst laadt, terugbetaling werkt
- [ ] **Tab Contracten**: lijst laadt, contract bekijken opent HTML, ondertekenen werkt
- [ ] **Tab Facturen**: lijst laadt, status wijzigen (openstaand/betaald/verlopen) werkt
- [ ] **Tab Kalender**: maandoverzicht toont beschikbaarheid per woning

### Contracten
- [ ] `POST /api/contract/generate` genereert HTML contract
- [ ] `GET /api/contract/<id>` toont contract als printbare HTML pagina
- [ ] Contract bevat Nederlandse huurovereenkomst tekst
- [ ] Contract nummer formaat: CON-YYYY-XXXX

### Facturen
- [ ] `POST /api/factuur/generate` genereert factuur met BTW 21%
- [ ] `GET /api/factuur/<id>` toont factuur als printbare HTML pagina
- [ ] Factuurnummer formaat: DC-YYYY-XXXX
- [ ] Vervaldatum = 14 dagen na generatie
- [ ] BTW berekening: subtotaal (huur + servicekosten) * 0.21

### iCal Sync
- [ ] `GET /api/woningen/<extern_id>/ical` downloadt .ics bestand
- [ ] Het .ics bestand bevat VCALENDAR met VEVENT entries per reservering
- [ ] `POST /api/woningen/<extern_id>/ical-import` importeert externe URL
- [ ] Geimporteerde events worden opgeslagen als beschikbaarheid_blokkades
- [ ] `POST /api/woningen/<extern_id>/ical-sync` hersynct met eerder geconfigureerde URL

### API Endpoints
- [ ] `GET /api/health` retourneert `{"status": "healthy"}` met woningen/reserveringen tellingen
- [ ] `GET /api/panden` retourneert lijst van woningen
- [ ] `GET /api/beschikbaarheid?checkin=2026-05-01&checkout=2026-05-10` toont beschikbare woningen
- [ ] `POST /api/reserveringen` maakt reservering aan (admin route)
- [ ] `POST /api/betalingen` maakt betaling aan
- [ ] `GET /api/stats` retourneert dashboard statistieken
- [ ] `GET /api/kalender?maand=3&jaar=2026` retourneert kalender data

## 9. TODO

- [ ] Flask migratie overwegen (huidige server is standaard http.server)
- [ ] Echte Mollie/iDEAL integratie (nu simulatie)
- [ ] E-mail notificaties bij boeking/betaling
- [ ] PDF generatie voor contracten en facturen (nu HTML)
- [ ] Foto upload en gallery per woning
- [ ] Multi-language support (nu alleen Nederlands)
- [ ] Rate limiting op API endpoints
- [ ] Authentication/authorization op admin panel (nu alleen simpel wachtwoord)
- [ ] Automated testing

## 10. Belangrijke Notities

- **Port**: 8088
- **Database moet draaien** voordat de server start, anders stopt serve.py direct
- **Admin wachtwoord**: `admin`
- **Geen Flask**: gebruikt `http.server.ThreadingHTTPServer` (standaard library)
- **iDEAL**: simulatie, geen echte PSP koppeling
- **BTW**: 21% (verhoogd van 9% per 1 jan 2026)
- **04_real_properties.sql** verwijdert alle demo data en laadt 4 echte Darosa-panden. Let op: wist betalingen, reserveringen en woningen tabellen.
- **Contracten/facturen tabellen** worden aangemaakt door `03_short_stay_migration.sql`, niet door `01_schema.sql`
- **Dubbele datum-velden** in reserveringen: `check_in`/`check_out` (admin) en `checkin`/`checkout` (booking engine). Beide worden gecontroleerd bij beschikbaarheid.
- **Legacy data**: `data/` map bevat JSON bestanden uit eerdere versie, niet meer primair gebruikt.
