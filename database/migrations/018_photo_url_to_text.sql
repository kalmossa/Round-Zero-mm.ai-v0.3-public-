-- 018_photo_url_to_text.sql
-- Passe photo_url et photo_thumbnail_url de VARCHAR(700) -> TEXT.
--
-- POURQUOI : certaines URLs de photo (CDN avec query params, ou data: URIs
-- base64 inline) depassent 700 caracteres. Le scraper plantait alors avec
--   ERROR: value too long for type character varying(700)
-- et le fighter entier n'etait pas inscrit (cf failed_urls.txt : Ramazan
-- Kishev, Aziz Azizov). TEXT n'a pas de limite de longueur -> plus de crash.
--
-- Les data: URIs (blobs base64) sont par ailleurs rejetees cote scraper
-- (_cast dans scrape_mma_supabase.py) : on ne veut pas stocker de blob ici.
--
-- Idempotent : ne fait rien si les colonnes sont deja en TEXT.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fighters'
          AND column_name = 'photo_url'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE fighters ALTER COLUMN photo_url TYPE TEXT;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fighters'
          AND column_name = 'photo_thumbnail_url'
          AND data_type = 'character varying'
    ) THEN
        ALTER TABLE fighters ALTER COLUMN photo_thumbnail_url TYPE TEXT;
    END IF;
END $$;

-- Verification :
-- SELECT column_name, data_type FROM information_schema.columns
--  WHERE table_name = 'fighters' AND column_name LIKE 'photo%';
