-- Migration 015 : efface toutes les valeurs de scouter_rating
-- Le calcul est dynamique dans l'API (compute_scouter_dynamic), pas en BDD.
UPDATE fighters SET scouter_rating = NULL;
