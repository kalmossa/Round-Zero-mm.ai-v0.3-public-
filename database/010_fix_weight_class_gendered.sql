-- Migration 010 : Correction de la colonne generee weight_class_gendered
-- Avant : "Women's Flyweight" + gender=F → "Women's Flyweight W" (redondant)
-- Apres : si weight_class_current contient deja "Women" → pas de suffixe
--         sinon → suffixe " W" ou " M" comme avant

ALTER TABLE fighters
DROP COLUMN IF EXISTS weight_class_gendered;

ALTER TABLE fighters
ADD COLUMN weight_class_gendered TEXT GENERATED ALWAYS AS (
    CASE
        WHEN weight_class_current IS NULL
          OR weight_class_current = ''
          OR weight_class_current = 'Unknown'
        THEN COALESCE(weight_class_current, 'Unknown')
        WHEN weight_class_current ILIKE 'Women%'
        THEN weight_class_current   -- deja "Women's X", pas de suffixe
        ELSE weight_class_current
             || ' '
             || CASE gender WHEN 'F' THEN 'W' ELSE 'M' END
    END
) STORED;

-- Verification rapide
SELECT weight_class_current, gender, weight_class_gendered
FROM fighters
WHERE is_ufc_champion = TRUE
ORDER BY weight_class_current;
