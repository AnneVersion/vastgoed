-- ============================================================
-- DataConsultants Stays - Seed Data
-- Run after 01_schema.sql
-- ============================================================

-- ── WONINGEN (Properties) ────────────────────────────────────

INSERT INTO woningen (extern_id, naam, type, categorie, beschrijving, adres, postcode, stad, lat, lng,
    oppervlakte_m2, kamers, slaapkamers, max_gasten, huurprijs, nachtprijs, schoonmaakkosten,
    energielabel, amenities, kenmerken, tarieven, foto_urls, notities, beschikbaar, beschikbaar_vanaf,
    huurder, onderhoud)
VALUES
-- 1. Grachtenpand Deluxe
('a1b2c3d4-e5f6-7890-abcd-ef1234567801',
 'Grachtenpand Deluxe', 'appartement', 'Luxe Appartement',
 'Luxueus appartement aan de iconische Keizersgracht met originele details, hoge plafonds en uitzicht op het water. Volledig uitgerust voor een comfortabel verblijf in het hart van Amsterdam.',
 'Keizersgracht 274', '1016 EV', 'Amsterdam', 52.36760000, 4.88460000,
 92, 4, 2, 4, 1850.00, 185.00, 85.00, 'A',
 ARRAY['wifi','keuken','wasmachine','vaatwasser','airco','TV','handdoeken','beddengoed','lift'],
 ARRAY['balkon','lift','CV','vaatwasser','parketvloer'],
 '{"flexibel": 210, "standaard": 185, "niet_restitueerbaar": 160}'::jsonb,
 ARRAY['gradient-luxury-1','gradient-luxury-2','gradient-luxury-3'],
 'Hoekwoning aan de gracht, populaire locatie', true, '2026-01-01',
 NULL,
 '[{"id":"m001","datum":"2025-11-15","beschrijving":"CV-ketel jaarlijks onderhoud","kosten":185.00,"status":"afgerond"}]'::jsonb),

-- 2. Studio Lombok
('b2c3d4e5-f6a7-8901-bcde-f12345678902',
 'Studio Lombok', 'studio', 'Gezellige Studio',
 'Compacte en sfeervolle studio in de levendige wijk Lombok. Ideaal voor stellen of solo-reizigers die Utrecht willen ontdekken. Op loopafstand van het centrum.',
 'Kanaalstraat 87', '3531 CJ', 'Utrecht', 52.09380000, 5.10030000,
 38, 1, 0, 2, 895.00, 95.00, 45.00, 'C',
 ARRAY['wifi','keuken','wasmachine','TV','handdoeken','beddengoed'],
 ARRAY['open keuken','laminaat','gemeenschappelijke tuin'],
 '{"flexibel": 115, "standaard": 95, "niet_restitueerbaar": 79}'::jsonb,
 ARRAY['gradient-cozy-1','gradient-cozy-2'],
 'Geschikt voor starters, dichtbij station', true, '2026-04-01',
 NULL, '[]'::jsonb),

-- 3. Herenhuis Statenkwartier
('c3d4e5f6-a7b8-9012-cdef-123456789003',
 'Herenhuis Statenkwartier', 'woonhuis', 'Stadsvilla',
 'Ruim en stijlvol herenhuis in het gewilde Statenkwartier. Met 4 slaapkamers, tuin en garage is dit de perfecte keuze voor families of groepen die Den Haag willen verkennen.',
 'Frankenslag 42', '2582 HZ', 'Den Haag', 52.09240000, 4.28780000,
 145, 6, 4, 8, 2200.00, 275.00, 120.00, 'B',
 ARRAY['wifi','keuken','wasmachine','droger','vaatwasser','TV','handdoeken','beddengoed','parkeren','tuin','open_haard'],
 ARRAY['tuin','garage','CV','open haard','kelder','zolder'],
 '{"flexibel": 315, "standaard": 275, "niet_restitueerbaar": 235}'::jsonb,
 ARRAY['gradient-villa-1','gradient-villa-2','gradient-villa-3'],
 'Monumentaal pand, extra aandacht voor onderhoud', true, '2026-01-01',
 NULL,
 '[{"id":"m002","datum":"2026-01-20","beschrijving":"Dakgoot reparatie","kosten":340.00,"status":"afgerond"}]'::jsonb),

-- 4. Appartement Kralingen
('d4e5f6a7-b8c9-0123-defa-234567890104',
 'Appartement Kralingen', 'appartement', 'Modern Appartement',
 'Modern ingericht appartement nabij de Kralingse Plas. Licht en ruim met twee comfortabele slaapkamers. Perfecte uitvalsbasis voor het ontdekken van Rotterdam.',
 'Oudedijk 158', '3062 AP', 'Rotterdam', 51.92700000, 4.51030000,
 68, 3, 2, 4, 1350.00, 135.00, 65.00, 'A',
 ARRAY['wifi','keuken','wasmachine','vaatwasser','TV','handdoeken','beddengoed','balkon','lift'],
 ARRAY['balkon','lift','CV','inbouwkeuken'],
 '{"flexibel": 159, "standaard": 135, "niet_restitueerbaar": 115}'::jsonb,
 ARRAY['gradient-modern-1','gradient-modern-2'],
 'Rustige buurt nabij Kralingse Plas', true, '2026-05-01',
 NULL, '[]'::jsonb),

-- 5. Studio Haarlem
('e5f6a7b8-c9d0-1234-efab-345678901205',
 'Studio Haarlem', 'studio', 'Gezellige Studio',
 'Volledig gemeubileerde studio, ideaal voor korte en langere verblijven. Alles wat je nodig hebt is aanwezig. Uitstekende bereikbaarheid met OV.',
 'Engelandlaan 200', '2034 NA', 'Haarlem', 52.37280000, 4.64220000,
 32, 1, 0, 2, 825.00, 85.00, 40.00, 'D',
 ARRAY['wifi','keuken','wasmachine','TV','handdoeken','beddengoed'],
 ARRAY['gemeubileerd','laminaat','berging'],
 '{"flexibel": 105, "standaard": 85, "niet_restitueerbaar": 69}'::jsonb,
 ARRAY['gradient-cozy-3'],
 'Volledig gemeubileerd, ideaal voor expats', true, '2026-04-15',
 NULL, '[]'::jsonb),

-- 6. Woning Oud-Zuid
('f6a7b8c9-d0e1-2345-fabc-456789012306',
 'Woning Oud-Zuid', 'woonhuis', 'Luxe Appartement',
 'Prachtige woning in het prestigieuze Oud-Zuid. Met 3 ruime slaapkamers, een mooie tuin en parketvloeren. Dichtbij het Vondelpark en de museumstrip.',
 'Beethovenstraat 55', '1077 HN', 'Amsterdam', 52.35050000, 4.87820000,
 120, 5, 3, 6, 2100.00, 225.00, 95.00, 'B',
 ARRAY['wifi','keuken','wasmachine','vaatwasser','TV','handdoeken','beddengoed','tuin','parkeren'],
 ARRAY['tuin','CV','vaatwasser','wasmachine aansluiting','parketvloer'],
 '{"flexibel": 259, "standaard": 225, "niet_restitueerbaar": 195}'::jsonb,
 ARRAY['gradient-luxury-4','gradient-luxury-5'],
 'Premium locatie bij Vondelpark', true, '2026-01-01',
 NULL, '[]'::jsonb),

-- 7. Penthouse Wilhelminapier
('a7b8c9d0-e1f2-3456-abcd-567890123407',
 'Penthouse Wilhelminapier', 'appartement', 'Premium Penthouse',
 'Spectaculair penthouse met panoramisch uitzicht over de Maas en de skyline van Rotterdam. Voorzien van een ruim dakterras en luxe afwerking.',
 'Wilhelminakade 68', '3072 AR', 'Rotterdam', 51.90550000, 4.48700000,
 105, 4, 2, 4, 1950.00, 245.00, 95.00, 'A',
 ARRAY['wifi','keuken','wasmachine','droger','vaatwasser','airco','TV','handdoeken','beddengoed','lift','parkeren','balkon'],
 ARRAY['dakterras','lift','CV','panoramisch uitzicht','inbouwkeuken','parkeergelegenheid'],
 '{"flexibel": 285, "standaard": 245, "niet_restitueerbaar": 210}'::jsonb,
 ARRAY['gradient-penthouse-1','gradient-penthouse-2','gradient-penthouse-3'],
 'Premium locatie met uitzicht over de Maas', true, '2026-01-01',
 NULL, '[]'::jsonb),

-- 8. Appartement Domtoren
('b8c9d0e1-f2a3-4567-bcde-678901234508',
 'Appartement Domtoren', 'appartement', 'Modern Appartement',
 'Charmant appartement op loopafstand van de Domtoren en het stadscentrum van Utrecht. Ideaal voor citytrips en zakenreizen.',
 'Wittevrouwenstraat 12', '3512 CS', 'Utrecht', 52.09440000, 5.12660000,
 62, 3, 1, 3, 1275.00, 125.00, 55.00, 'C',
 ARRAY['wifi','keuken','wasmachine','TV','handdoeken','beddengoed','balkon','fiets'],
 ARRAY['balkon','CV','laminaat','fietsenstalling'],
 '{"flexibel": 149, "standaard": 125, "niet_restitueerbaar": 105}'::jsonb,
 ARRAY['gradient-modern-3'],
 'Centrum locatie, loopafstand naar Domtoren', true, '2026-06-01',
 NULL, '[]'::jsonb),

-- 9. Strandwoning Zandvoort
('c9d0e1f2-a3b4-5678-cdef-789012345609',
 'Strandwoning Zandvoort', 'woonhuis', 'Stadsvilla',
 'Sfeervolle woning op steenworp afstand van het strand van Zandvoort. Met 3 slaapkamers en een zonnige tuin. Ideaal voor een ontspannen vakantie aan zee.',
 'Boulevard Barnaart 15', '2041 JA', 'Zandvoort', 52.37450000, 4.53300000,
 98, 4, 3, 6, 1650.00, 195.00, 85.00, 'B',
 ARRAY['wifi','keuken','wasmachine','droger','TV','handdoeken','beddengoed','tuin','parkeren','fiets'],
 ARRAY['tuin','berging','CV','dubbel glas','zonnepanelen'],
 '{"flexibel": 229, "standaard": 195, "niet_restitueerbaar": 169}'::jsonb,
 ARRAY['gradient-beach-1','gradient-beach-2'],
 'Nabij strand, zeer gewild bij gezinnen', true, '2026-01-01',
 NULL, '[]'::jsonb)
ON CONFLICT (extern_id) DO NOTHING;


-- ── RESERVERINGEN (Bookings) ─────────────────────────────────

INSERT INTO reserveringen (extern_id, pand_id, pand_extern_id, pand_naam,
    gast_naam, gast_email, gast_telefoon,
    check_in, check_out, gasten, tarief_type, nachtprijs, nachten,
    schoonmaakkosten, totaal, status, betaalstatus, betaal_methode,
    opmerkingen, aangemaakt)
VALUES
-- RES-2026-001
('RES-2026-001',
 (SELECT id FROM woningen WHERE extern_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567801'),
 'a1b2c3d4-e5f6-7890-abcd-ef1234567801', 'Grachtenpand Deluxe',
 'Jan de Vries', 'jan.devries@email.nl', '+31 6 12345678',
 '2026-03-15', '2026-03-20', 2, 'standaard', 185.00, 5,
 85.00, 1010.00, 'bevestigd', 'betaald', 'iDEAL',
 'Late check-in rond 22:00', '2026-03-01T10:30:00'),

-- RES-2026-002
('RES-2026-002',
 (SELECT id FROM woningen WHERE extern_id = 'c3d4e5f6-a7b8-9012-cdef-123456789003'),
 'c3d4e5f6-a7b8-9012-cdef-123456789003', 'Herenhuis Statenkwartier',
 'Sophie van Dijk', 'sophie.vandijk@gmail.com', '+31 6 98765432',
 '2026-03-19', '2026-03-26', 6, 'flexibel', 315.00, 7,
 120.00, 2325.00, 'bevestigd', 'betaald', 'iDEAL',
 'Familie vakantie, extra bedden nodig', '2026-03-05T14:20:00'),

-- RES-2026-003
('RES-2026-003',
 (SELECT id FROM woningen WHERE extern_id = 'b2c3d4e5-f6a7-8901-bcde-f12345678902'),
 'b2c3d4e5-f6a7-8901-bcde-f12345678902', 'Studio Lombok',
 'Thomas Bakker', 't.bakker@outlook.com', '+31 6 55443322',
 '2026-03-22', '2026-03-25', 1, 'niet_restitueerbaar', 79.00, 3,
 45.00, 282.00, 'pending', 'openstaand', '',
 '', '2026-03-18T09:15:00'),

-- RES-2026-004
('RES-2026-004',
 (SELECT id FROM woningen WHERE extern_id = 'a7b8c9d0-e1f2-3456-abcd-567890123407'),
 'a7b8c9d0-e1f2-3456-abcd-567890123407', 'Penthouse Wilhelminapier',
 'Emma Jansen', 'emma.jansen@hotmail.com', '+31 6 11223344',
 '2026-03-25', '2026-03-30', 3, 'standaard', 245.00, 5,
 95.00, 1320.00, 'bevestigd', 'betaald', 'iDEAL',
 'Verjaardag verrassing voor partner', '2026-03-10T16:45:00'),

-- RES-2026-005
('RES-2026-005',
 (SELECT id FROM woningen WHERE extern_id = 'd4e5f6a7-b8c9-0123-defa-234567890104'),
 'd4e5f6a7-b8c9-0123-defa-234567890104', 'Appartement Kralingen',
 'Pieter Mol', 'p.mol@ziggo.nl', '+31 6 77889900',
 '2026-04-01', '2026-04-05', 4, 'flexibel', 155.00, 4,
 65.00, 685.00, 'bevestigd', 'openstaand', '',
 'Zakelijke reis met collega''s', '2026-03-12T11:00:00'),

-- RES-2026-006
('RES-2026-006',
 (SELECT id FROM woningen WHERE extern_id = 'c9d0e1f2-a3b4-5678-cdef-789012345609'),
 'c9d0e1f2-a3b4-5678-cdef-789012345609', 'Strandwoning Zandvoort',
 'Lisa Vermeer', 'lisa.vermeer@email.nl', '+31 6 33445566',
 '2026-03-10', '2026-03-14', 2, 'standaard', 195.00, 4,
 75.00, 855.00, 'geannuleerd', 'terugbetaald', 'iDEAL',
 'Geannuleerd wegens ziekte', '2026-02-28T08:30:00'),

-- RES-2026-007
('RES-2026-007',
 (SELECT id FROM woningen WHERE extern_id = 'f6a7b8c9-d0e1-2345-fabc-456789012306'),
 'f6a7b8c9-d0e1-2345-fabc-456789012306', 'Woning Oud-Zuid',
 'Mark van den Berg', 'm.vandenberg@gmail.com', '+31 6 99887766',
 '2026-03-19', '2026-03-22', 2, 'standaard', 225.00, 3,
 85.00, 760.00, 'bevestigd', 'betaald', 'iDEAL',
 'Weekend getaway', '2026-03-14T13:20:00'),

-- RES-2026-008
('RES-2026-008',
 (SELECT id FROM woningen WHERE extern_id = 'e5f6a7b8-c9d0-1234-efab-345678901205'),
 'e5f6a7b8-c9d0-1234-efab-345678901205', 'Studio Haarlem',
 'Anna Smit', 'anna.smit@live.nl', '+31 6 22334455',
 '2026-04-10', '2026-04-14', 1, 'niet_restitueerbaar', 72.00, 4,
 40.00, 328.00, 'pending', 'openstaand', '',
 'Solo trip, vroege check-in gewenst', '2026-03-17T15:10:00')
ON CONFLICT (extern_id) DO NOTHING;


-- ── BETALINGEN (Payments) ────────────────────────────────────

INSERT INTO betalingen (extern_id, reservering_id, reservering_extern_id,
    gast_naam, bedrag, methode, bank, status, datum, beschrijving)
VALUES
('PAY-2026-001',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-001'),
 'RES-2026-001', 'Jan de Vries', 1010.00, 'iDEAL', 'ING', 'voltooid',
 '2026-03-01T10:35:00', 'Betaling Grachtenpand Deluxe - 5 nachten'),

('PAY-2026-002',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-002'),
 'RES-2026-002', 'Sophie van Dijk', 2325.00, 'iDEAL', 'Rabobank', 'voltooid',
 '2026-03-05T14:28:00', 'Betaling Herenhuis Statenkwartier - 7 nachten'),

('PAY-2026-003',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-004'),
 'RES-2026-004', 'Emma Jansen', 1320.00, 'iDEAL', 'ABN AMRO', 'voltooid',
 '2026-03-10T16:52:00', 'Betaling Penthouse Wilhelminapier - 5 nachten'),

('PAY-2026-004',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-006'),
 'RES-2026-006', 'Lisa Vermeer', 855.00, 'iDEAL', 'ING', 'terugbetaald',
 '2026-02-28T08:35:00', 'Betaling Strandwoning Zandvoort - 4 nachten (terugbetaald)'),

('PAY-2026-005',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-007'),
 'RES-2026-007', 'Mark van den Berg', 760.00, 'iDEAL', 'Rabobank', 'voltooid',
 '2026-03-14T13:28:00', 'Betaling Woning Oud-Zuid - 3 nachten'),

('PAY-2026-006',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-003'),
 'RES-2026-003', 'Thomas Bakker', 282.00, 'iDEAL', '', 'pending',
 '2026-03-18T09:15:00', 'Betaling Studio Lombok - 3 nachten (wacht op betaling)'),

('PAY-2026-007',
 (SELECT id FROM reserveringen WHERE extern_id = 'RES-2026-005'),
 'RES-2026-005', 'Pieter Mol', 685.00, 'iDEAL', '', 'pending',
 '2026-03-12T11:05:00', 'Betaling Appartement Kralingen - 4 nachten (wacht op betaling)')
ON CONFLICT (extern_id) DO NOTHING;
