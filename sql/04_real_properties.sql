-- ============================================================
-- Darosa Beheer B.V. - Echte panden migratie
-- Vervangt demo properties met 4 echte verhuurbare units
-- Run na 01_schema.sql
-- ============================================================

-- Verwijder demo data
DELETE FROM betalingen;
DELETE FROM reserveringen;
DELETE FROM woningen;

-- Reset sequences
ALTER SEQUENCE IF EXISTS woningen_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS reserveringen_id_seq RESTART WITH 1;
ALTER SEQUENCE IF EXISTS betalingen_id_seq RESTART WITH 1;

-- ── ECHTE WONINGEN ────────────────────────────────────────

INSERT INTO woningen (extern_id, naam, type, categorie, beschrijving, adres, postcode, stad, lat, lng,
    oppervlakte_m2, kamers, slaapkamers, max_gasten, huurprijs, nachtprijs, schoonmaakkosten,
    energielabel, amenities, kenmerken, tarieven, foto_urls, notities, beschikbaar, beschikbaar_vanaf,
    huurder, onderhoud)
VALUES

-- 1. Amsterdam - Korte Leidsedwarsstraat 169a
('darosa-ams-leidseplein-001',
 'City Apartment Leidseplein', 'appartement', 'City Apartment',
 'Volledig gemeubileerd appartement in het hart van Amsterdam, op loopafstand van het Leidseplein, Vondelpark en de musea. Ideaal voor expats, zakelijke reizigers en toeristen.',
 'Korte Leidsedwarsstraat 169a', '1017 PZ', 'Amsterdam', 52.36390, 4.88280,
 45, 2, 1, 2, 1800.00, 125.00, 75.00, 'C',
 ARRAY['wifi','keuken','wasmachine','TV','handdoeken','beddengoed','airco'],
 ARRAY['centrum','gemeubileerd','laminaat','dubbel glas'],
 '{"flexibel": 145, "standaard": 125, "niet_restitueerbaar": 105}'::jsonb,
 ARRAY['gradient-city-1'],
 'Toplocatie centrum Amsterdam, bij Leidseplein', true, '2026-01-01',
 NULL, '[]'::jsonb),

-- 2. Zandvoort - Favaugeplein 21 F24
('darosa-zvt-favaugeplein-001',
 'Beach Apartment Zandvoort', 'appartement', 'Beach Apartment',
 'Licht en modern appartement nabij het strand van Zandvoort. Op loopafstand van het strand, het centrum en het NS station. Inclusief parkeerplaats.',
 'Favaugeplein 21 F24', '2042 BA', 'Zandvoort', 52.37410, 4.53240,
 55, 2, 1, 3, 1400.00, 100.00, 65.00, 'B',
 ARRAY['wifi','keuken','wasmachine','TV','handdoeken','beddengoed','parkeren','balkon'],
 ARRAY['strand','parkeerplaats','balkon','gemeubileerd','dubbel glas'],
 '{"flexibel": 120, "standaard": 100, "niet_restitueerbaar": 85}'::jsonb,
 ARRAY['gradient-beach-1'],
 'Nabij strand en centrum Zandvoort, inclusief parkeerplaats', true, '2026-01-01',
 NULL, '[]'::jsonb),

-- 3. Arnhem Studio A - Rosendaalsestraat 129
('darosa-arn-rosendaal-001',
 'Studio A Rosendaalsestraat', 'studio', 'Gedeelde Studio',
 'Compacte gemeubileerde studio in het centrum van Arnhem. Gedeelde badkamer met Studio B. Op loopafstand van station, binnenstad en Park Sonsbeek. Ideaal voor starters of expats.',
 'Rosendaalsestraat 129', '6824 CK', 'Arnhem', 51.98550, 5.91930,
 22, 1, 1, 1, 650.00, 55.00, 40.00, 'D',
 ARRAY['wifi','keuken','TV','handdoeken','beddengoed'],
 ARRAY['gemeubileerd','centrum','gedeelde badkamer','laminaat'],
 '{"flexibel": 65, "standaard": 55, "niet_restitueerbaar": 45}'::jsonb,
 ARRAY['gradient-studio-1'],
 'Studio A - gedeelde badkamer met Studio B', true, '2026-01-01',
 NULL, '[]'::jsonb),

-- 4. Arnhem Studio B - Rosendaalsestraat 129
('darosa-arn-rosendaal-002',
 'Studio B Rosendaalsestraat', 'studio', 'Gedeelde Studio',
 'Compacte gemeubileerde studio in het centrum van Arnhem. Gedeelde badkamer met Studio A. Op loopafstand van station, binnenstad en Park Sonsbeek. Ideaal voor starters of expats.',
 'Rosendaalsestraat 129', '6824 CK', 'Arnhem', 51.98550, 5.91930,
 22, 1, 1, 1, 650.00, 55.00, 40.00, 'D',
 ARRAY['wifi','keuken','TV','handdoeken','beddengoed'],
 ARRAY['gemeubileerd','centrum','gedeelde badkamer','laminaat'],
 '{"flexibel": 65, "standaard": 55, "niet_restitueerbaar": 45}'::jsonb,
 ARRAY['gradient-studio-2'],
 'Studio B - gedeelde badkamer met Studio A', true, '2026-01-01',
 NULL, '[]'::jsonb)

ON CONFLICT (extern_id) DO NOTHING;

-- ── VOORBEELD RESERVERINGEN ────────────────────────────────

INSERT INTO reserveringen (extern_id, pand_id, pand_extern_id, pand_naam,
    gast_naam, gast_email, gast_telefoon,
    check_in, check_out, gasten, tarief_type, nachtprijs, nachten,
    schoonmaakkosten, totaal, status, betaalstatus, betaal_methode,
    opmerkingen, aangemaakt)
VALUES
('RES-2026-001',
 (SELECT id FROM woningen WHERE extern_id = 'darosa-ams-leidseplein-001'),
 'darosa-ams-leidseplein-001', 'City Apartment Leidseplein',
 'Thomas Mueller', 't.mueller@gmail.com', '+49 170 1234567',
 '2026-04-01', '2026-04-15', 2, 'standaard', 125.00, 14,
 75.00, 1825.00, 'bevestigd', 'betaald', 'iDEAL',
 'Duitse expat, 2 weken zakelijk verblijf', '2026-03-15T10:30:00'),

('RES-2026-002',
 (SELECT id FROM woningen WHERE extern_id = 'darosa-zvt-favaugeplein-001'),
 'darosa-zvt-favaugeplein-001', 'Beach Apartment Zandvoort',
 'Sophie van Dijk', 'sophie.vandijk@outlook.com', '+31 6 98765432',
 '2026-04-20', '2026-04-27', 3, 'standaard', 100.00, 7,
 65.00, 765.00, 'bevestigd', 'betaald', 'iDEAL',
 'Voorjaarsvakantie met gezin', '2026-03-20T14:20:00')

ON CONFLICT (extern_id) DO NOTHING;

-- ── BETALINGEN ─────────────────────────────────────────────

INSERT INTO betalingen (extern_id, reservering_id, reservering_extern_id,
    gast_naam, bedrag, methode, bank, status, datum, beschrijving)
VALUES
('PAY-2026-001',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-001'),
 'RES-2026-001', 'Thomas Mueller', 1825.00, 'iDEAL', 'ING', 'voltooid',
 '2026-03-15T10:35:00', 'Betaling City Apartment Leidseplein - 14 nachten'),

('PAY-2026-002',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-002'),
 'RES-2026-002', 'Sophie van Dijk', 765.00, 'iDEAL', 'Rabobank', 'voltooid',
 '2026-03-20T14:28:00', 'Betaling Beach Apartment Zandvoort - 7 nachten')

ON CONFLICT (extern_id) DO NOTHING;
