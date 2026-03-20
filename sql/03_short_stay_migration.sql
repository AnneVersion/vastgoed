-- ============================================================
-- Short-Stay Migration - Luxury Rental Platform
-- Run after 01_schema.sql and 02_seed.sql
-- ============================================================

-- Add short-stay pricing columns to woningen
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS maandprijs DECIMAL(10,2);
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS weekprijs DECIMAL(10,2);
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS borg DECIMAL(10,2);
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS min_verblijf_dagen INTEGER DEFAULT 7;
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS max_verblijf_dagen INTEGER DEFAULT 730;
ALTER TABLE woningen ADD COLUMN IF NOT EXISTS servicekosten_maand DECIMAL(10,2) DEFAULT 150.00;

-- Add guest details to reserveringen for short-stay
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS gast_bedrijf VARCHAR(255);
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS gast_bsn VARCHAR(20);
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS reden_verblijf VARCHAR(255);
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS verblijfsduur_type VARCHAR(50);
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS maandprijs DECIMAL(10,2);
ALTER TABLE reserveringen ADD COLUMN IF NOT EXISTS borg DECIMAL(10,2);

-- Contracten table
CREATE TABLE IF NOT EXISTS contracten (
    id SERIAL PRIMARY KEY,
    reservering_id INTEGER REFERENCES reserveringen(id),
    contract_nr VARCHAR(20) UNIQUE,
    contract_html TEXT,
    ondertekend BOOLEAN DEFAULT FALSE,
    ondertekend_datum TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Facturen table
CREATE TABLE IF NOT EXISTS facturen (
    id SERIAL PRIMARY KEY,
    factuur_nr VARCHAR(20) UNIQUE,
    reservering_id INTEGER REFERENCES reserveringen(id),
    reservering_extern_id VARCHAR(20),
    bedrag_excl_btw DECIMAL(10,2),
    btw_percentage DECIMAL(4,2) DEFAULT 21.00,
    btw_bedrag DECIMAL(10,2),
    totaal DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'openstaand',
    vervaldatum DATE,
    factuur_html TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contracten_reservering ON contracten(reservering_id);
CREATE INDEX IF NOT EXISTS idx_facturen_reservering ON facturen(reservering_id);
CREATE INDEX IF NOT EXISTS idx_facturen_status ON facturen(status);

-- Update existing properties with luxury short-stay pricing
-- Property 1: Grachtenpand Deluxe -> Luxury Studio/1BR
UPDATE woningen SET
    naam = 'The Keizersgracht Suite',
    type = 'appartement',
    categorie = 'Luxe Studio',
    beschrijving = 'Een verfijnd gemeubileerd appartement aan de iconische Keizersgracht. Hoge plafonds, originele details en panoramisch uitzicht over het water. Volledig uitgerust met premium keukenapparatuur, Auping bed en ruime inloopkast. Ideaal voor professionals en expats die het beste van Amsterdam willen ervaren.',
    maandprijs = 2500.00,
    weekprijs = 750.00,
    borg = 2500.00,
    min_verblijf_dagen = 7,
    max_verblijf_dagen = 730,
    servicekosten_maand = 150.00,
    slaapkamers = 1,
    badkamers = 1,
    max_gasten = 2,
    oppervlakte_m2 = 65,
    amenities = ARRAY['wifi','volledig uitgeruste keuken','wasmachine','droger','vaatwasser','airco','smart TV','Nespresso','Auping bed','luxe beddengoed','handdoeken','werkplek','lift'],
    kenmerken = ARRAY['grachtzicht','hoge plafonds','originele details','parketvloer','lift','inloopkast']
WHERE extern_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567801';

-- Property 2: Herenhuis Statenkwartier -> 2BR Apartment
UPDATE woningen SET
    naam = 'The Statenkwartier Residence',
    type = 'appartement',
    categorie = 'Premium Appartement',
    beschrijving = 'Ruim en stijlvol twee-slaapkamer appartement in het gewilde Statenkwartier van Den Haag. Gerenoveerd met oog voor detail: marmeren badkamer, Bulthaup keuken en een zonnig balkon. Op loopafstand van het strand van Scheveningen en de internationale organisaties.',
    adres = 'Frankenslag 42',
    stad = 'Den Haag',
    maandprijs = 3500.00,
    weekprijs = 1050.00,
    borg = 3500.00,
    min_verblijf_dagen = 7,
    max_verblijf_dagen = 730,
    servicekosten_maand = 200.00,
    slaapkamers = 2,
    badkamers = 2,
    max_gasten = 4,
    oppervlakte_m2 = 110,
    amenities = ARRAY['wifi','Bulthaup keuken','wasmachine','droger','vaatwasser','airco','smart TV','Nespresso','luxe beddengoed','handdoeken','werkplek','balkon','parkeerplaats','fiets'],
    kenmerken = ARRAY['marmeren badkamer','balkon','parkeerplaats','CV','vaatwasser','eiken vloer','dubbel glas']
WHERE extern_id = 'c3d4e5f6-a7b8-9012-cdef-123456789003';

-- Property 3: Penthouse Wilhelminapier -> 3BR Penthouse
UPDATE woningen SET
    naam = 'The Wilhelmina Penthouse',
    type = 'penthouse',
    categorie = 'Exclusief Penthouse',
    beschrijving = 'Spectaculair drie-slaapkamer penthouse met adembenemend panoramisch uitzicht over de Maas en de skyline van Rotterdam. Voorzien van een ruim dakterras, open haard, en luxe afwerking op het hoogste niveau. Twee parkeerplaatsen en 24/7 conciergerie. De ultieme woonervaring voor veeleisende professionals.',
    maandprijs = 5000.00,
    weekprijs = 1500.00,
    borg = 5000.00,
    min_verblijf_dagen = 7,
    max_verblijf_dagen = 730,
    servicekosten_maand = 300.00,
    slaapkamers = 3,
    badkamers = 2,
    max_gasten = 6,
    oppervlakte_m2 = 155,
    amenities = ARRAY['wifi','Gaggenau keuken','wasmachine','droger','vaatwasser','airco','smart TV','Sonos','Nespresso','luxe beddengoed','handdoeken','werkplek','dakterras','2x parkeerplaats','lift','open haard','conciergerie'],
    kenmerken = ARRAY['panoramisch uitzicht','dakterras','open haard','2 parkeerplaatsen','lift','marmer','eiken vloer','walk-in closet','gastentoilet']
WHERE extern_id = 'a7b8c9d0-e1f2-3456-abcd-567890123407';
