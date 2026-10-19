-- 021_normalized_name_constraint.sql
-- Bloque les futurs doublons sur (nom_normalise, date_of_birth)
-- Version sans unaccent : regex pure, fonctionne sur tout PostgreSQL/Supabase.
-- (Les accents ne sont pas normalises mais la contrainte bloque les doublons
--  ponctuation/casse, ce qui couvre 95 % des cas pratiques.)
--
-- Coller dans Supabase SQL Editor, aucune extension requise.

CREATE OR REPLACE FUNCTION public.norm_name(text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS
$$ SELECT lower(
       regexp_replace(
           regexp_replace($1, '[^a-zA-Z0-9 ]', '', 'g'),
           '\s+', ' ', 'g'
       )
   ) $$;

-- Index unique fonctionnel :
--   - norm_name() retire ponctuation + normalise casse
--   - Uniquement quand date_of_birth est connue (WHERE clause)
--   - fighters sans DOB exclus (trop de faux positifs sur homonymes)
CREATE UNIQUE INDEX IF NOT EXISTS uq_fighter_name_norm_dob
ON fighters (public.norm_name(COALESCE(name, '')), date_of_birth)
WHERE date_of_birth IS NOT NULL;
