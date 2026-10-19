-- 016_fix_nationality_chimaev.sql
-- Corrige la nationalité de Khamzat Chimaev : UFC-FR dit "Émirats arabes unis"
-- mais Tapology (birth country = Russia/Chechnya) avait écrasé la valeur.
-- Après ce patch, relancer un scrape UFC-FR pour tout fighter concerné maintiendra
-- automatiquement la bonne valeur (Tapology n'est plus autoritaire pour nationality).

UPDATE fighters
SET nationality = 'United Arab Emirates'
WHERE name = 'Khamzat Chimaev'
  AND nationality = 'Russia';

-- Vérification (doit renvoyer 1 ligne avec UAE) :
-- SELECT id, name, nationality FROM fighters WHERE name = 'Khamzat Chimaev';
