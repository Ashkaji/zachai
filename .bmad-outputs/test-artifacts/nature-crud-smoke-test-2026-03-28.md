# Rapport de Validation — CRUD Natures & Schémas de Labels (Story 2.1)
**Date :** 2026-03-28
**Testeur :** Gemini CLI

## Résumé des actions effectuées
1.  **Préparation de l'environnement :**
    *   Le service `fastapi` a été reconstruit pour inclure la logique métier de la Story 2.1.
    *   Correction d'un bug identifié lors du smoke test : ajout d'un fallback pour le claim `sub` (Keycloak access tokens 26.x) et forçage de l'expiration de session SQLAlchemy pour garantir des réponses API à jour.

2.  **Démarrage des services :**
    *   `docker compose up -d postgres keycloak fastapi`
    *   Vérification de l'état de santé : Tous les conteneurs sont `healthy`.

3.  **Tests de fumée (Smoke Tests) :**
    *   **Authentification :** Obtention d'un JWT pour l'utilisateur `test-manager` (rôle Manager).
    *   **Création de Nature (POST /v1/natures) :**
        *   Succès : Nature "Camp Biblique" créée avec 3 labels.
        *   Validation DB : Tables `natures` et `label_schemas` automatiquement créées et alimentées dans la base `zachai`.
    *   **Liste des Natures (GET /v1/natures) :**
        *   Succès : Retourne la liste incluant "Camp Biblique" avec son `label_count`.
    *   **Mise à jour des Labels (PUT /v1/natures/1/labels) :**
        *   Succès : Remplacement atomique des labels vérifié par API et par requête SQL directe.
    *   **Schéma Label Studio :**
        *   Le XML généré dynamiquement est correct et conforme aux spécifications pour une intégration future avec Camunda/Label Studio.

## État actuel
*   Layer 1 (Identity - Keycloak) : Opérationnel.
*   Layer 2 (Database - PostgreSQL) : Opérationnel, schéma métier initialisé.
*   Layer 3 (Gateway - FastAPI) : Opérationnel avec persistence réelle.
*   **Conclusion :** La Story 2.1 est validée techniquement en environnement Docker.

## Nettoyage
*   Fichiers temporaires de test (`nature_test.json`, `labels_update_test.json`) prêts à être supprimés.
