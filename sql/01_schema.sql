-- ============================================================
-- DataConsultants Stays - Database Schema
-- Database: vastgoed
-- ============================================================

-- Create database (run separately as superuser if needed):
-- CREATE DATABASE vastgoed;

-- woningen (properties)
CREATE TABLE IF NOT EXISTS woningen (
    id SERIAL PRIMARY KEY,
    extern_id VARCHAR(50) UNIQUE,  -- legacy UUID from JSON migration
    naam VARCHAR(255) NOT NULL,
    type VARCHAR(50),              -- studio, appartement, woonhuis, penthouse
    categorie VARCHAR(100),
    beschrijving TEXT,
    adres VARCHAR(255),
    postcode VARCHAR(10),
    stad VARCHAR(100),
    lat DECIMAL(10,8),
    lng DECIMAL(11,8),
    oppervlakte_m2 INTEGER,
    kamers INTEGER,
    slaapkamers INTEGER,
    badkamers DECIMAL(3,1),
    max_gasten INTEGER,
    huurprijs DECIMAL(10,2),
    nachtprijs DECIMAL(10,2),
    schoonmaakkosten DECIMAL(10,2),
    energielabel VARCHAR(5),
    amenities TEXT[],              -- PostgreSQL array
    kenmerken TEXT[],
    tarieven JSONB,                -- {"flexibel": x, "standaard": y, "niet_restitueerbaar": z}
    foto_urls TEXT[],
    notities TEXT,
    beschikbaar BOOLEAN DEFAULT true,
    beschikbaar_vanaf DATE,
    actief BOOLEAN DEFAULT true,
    airbnb_url VARCHAR(500),
    rating DECIMAL(3,2),
    recensies INTEGER DEFAULT 0,
    huurder JSONB,
    onderhoud JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- reserveringen (bookings)
CREATE TABLE IF NOT EXISTS reserveringen (
    id SERIAL PRIMARY KEY,
    extern_id VARCHAR(20) UNIQUE NOT NULL,   -- e.g. RES-2026-001
    pand_id INTEGER REFERENCES woningen(id),
    pand_extern_id VARCHAR(50),              -- legacy reference
    pand_naam VARCHAR(255),
    gast_naam VARCHAR(255),
    gast_email VARCHAR(255),
    gast_telefoon VARCHAR(50),
    gast_adres TEXT,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    gasten INTEGER DEFAULT 1,
    gasten_volwassen INTEGER,
    gasten_kinderen INTEGER DEFAULT 0,
    tarief_type VARCHAR(50),                 -- flexibel, standaard, niet_restitueerbaar
    nachtprijs DECIMAL(10,2),
    nachten INTEGER,
    schoonmaakkosten DECIMAL(10,2),
    servicekosten DECIMAL(10,2),
    korting DECIMAL(10,2) DEFAULT 0,
    totaal DECIMAL(10,2),
    status VARCHAR(20) DEFAULT 'pending',    -- pending, bevestigd, geannuleerd, voltooid
    betaalstatus VARCHAR(20) DEFAULT 'openstaand',
    betaal_methode VARCHAR(50),
    opmerkingen TEXT,
    promo_code VARCHAR(50),
    -- Fields used by the booking engine
    appartement_id VARCHAR(50),              -- legacy: used by booking engine
    boekingnummer VARCHAR(50),
    checkin VARCHAR(20),                     -- booking engine uses different field names
    checkout VARCHAR(20),
    datum_aangemaakt VARCHAR(50),
    aangemaakt TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- betalingen (payments)
CREATE TABLE IF NOT EXISTS betalingen (
    id SERIAL PRIMARY KEY,
    extern_id VARCHAR(20) UNIQUE NOT NULL,   -- e.g. PAY-2026-001
    reservering_id INTEGER REFERENCES reserveringen(id),
    reservering_extern_id VARCHAR(20),       -- legacy reference
    gast_naam VARCHAR(255),
    bedrag DECIMAL(10,2) NOT NULL,
    methode VARCHAR(50) DEFAULT 'iDEAL',     -- ideal, creditcard, bank
    bank VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',    -- pending, voltooid, mislukt, terugbetaald
    transactie_id VARCHAR(100),
    beschrijving TEXT,
    datum TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- beschikbaarheid_blokkades (availability blocks)
CREATE TABLE IF NOT EXISTS beschikbaarheid_blokkades (
    id SERIAL PRIMARY KEY,
    woning_id INTEGER REFERENCES woningen(id) ON DELETE CASCADE,
    datum_start DATE NOT NULL,
    datum_einde DATE NOT NULL,
    reden VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_woningen_stad ON woningen(stad);
CREATE INDEX IF NOT EXISTS idx_woningen_type ON woningen(type);
CREATE INDEX IF NOT EXISTS idx_woningen_extern_id ON woningen(extern_id);
CREATE INDEX IF NOT EXISTS idx_reserveringen_pand_id ON reserveringen(pand_id);
CREATE INDEX IF NOT EXISTS idx_reserveringen_pand_extern ON reserveringen(pand_extern_id);
CREATE INDEX IF NOT EXISTS idx_reserveringen_check_in ON reserveringen(check_in);
CREATE INDEX IF NOT EXISTS idx_reserveringen_check_out ON reserveringen(check_out);
CREATE INDEX IF NOT EXISTS idx_reserveringen_status ON reserveringen(status);
CREATE INDEX IF NOT EXISTS idx_reserveringen_extern_id ON reserveringen(extern_id);
CREATE INDEX IF NOT EXISTS idx_betalingen_reservering_id ON betalingen(reservering_id);
CREATE INDEX IF NOT EXISTS idx_betalingen_status ON betalingen(status);
CREATE INDEX IF NOT EXISTS idx_blokkades_woning ON beschikbaarheid_blokkades(woning_id);
CREATE INDEX IF NOT EXISTS idx_blokkades_datums ON beschikbaarheid_blokkades(datum_start, datum_einde);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_woningen_updated_at ON woningen;
CREATE TRIGGER trigger_woningen_updated_at
    BEFORE UPDATE ON woningen
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_reserveringen_updated_at ON reserveringen;
CREATE TRIGGER trigger_reserveringen_updated_at
    BEFORE UPDATE ON reserveringen
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trigger_betalingen_updated_at ON betalingen;
CREATE TRIGGER trigger_betalingen_updated_at
    BEFORE UPDATE ON betalingen
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
