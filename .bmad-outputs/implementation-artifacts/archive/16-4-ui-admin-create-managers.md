# Story 16.4 : UI Admin — création de Managers

Status: done

<!-- Rétro-document : la story était marquée faite dans sprint-status sans fichier d’artefact ; contenu aligné sur le code et docs/epics-and-stories.md. -->

## Story

**En:** As an Admin, I can create Manager accounts from the web UI without using Keycloak Admin, so that onboarding stays in-product.

**Fr:** En tant qu’Admin, je peux créer des comptes Manager depuis l’interface web sans passer par l’admin Keycloak, pour garder l’onboarding dans le produit.

## Acceptance Criteria / Critères d’Acceptation

1. **Visibilité Admin uniquement** : Le flux « créer un Manager » est proposé sur le tableau de bord Admin (pas sur les vues Manager / Transcripteur / Expert).
2. **Formulaire** : Saisie `username`, `email`, `firstName`, `lastName`, option `enabled` (défaut activé), alignée sur le contrat `UserCreate` de l’API (Story 16.3).
3. **Rôle fixe Manager** : La requête envoie toujours `role: "Manager"` (l’Admin ne choisit pas un autre rôle dans ce flux).
4. **API** : Appel `POST /v1/iam/users` avec le JWT de la session (`createUser` dans `dashboardApi.ts`).
5. **UX** : Modal glass (réutilisation des primitives existantes), états chargement / erreur affichés, fermeture et reset du formulaire à la fermeture du modal.
6. **Tests** : Couverture unitaire du modal (soumission, erreurs) et de `createUser` (corps JSON et propagation des erreurs HTTP).

## Tasks / Subtasks

- [x] **Client API** — `createUser` + type `UserCreate` dans `dashboardApi.ts`.
- [x] **UI** — `CreateManagerModal.tsx` (formulaire + `role: "Manager"`).
- [x] **Intégration** — Bouton « + Créer Manager » et montage du modal dans le dashboard Admin (`RoleDashboards.tsx`).
- [x] **Tests** — `CreateManagerModal.test.tsx`, `dashboardApi.test.ts` (section `createUser`).

## Previous story intelligence (16.3)

- L’Admin peut créer un utilisateur avec n’importe quel rôle côté API ; cette UI ne expose que la création de **Manager** pour respecter le périmètre produit de la story 16.4.
- Erreurs typiques : 403, 409 (conflit), 502 — à surfacer côté UI via le message renvoyé par `apiJson` / couche d’erreur.

## References

- [Source: docs/epics-and-stories.md — Epic 16, Story 16.4]
- [Source: .bmad-outputs/implementation-artifacts/16-3-api-user-provisioning-and-rbac.md]
- [Source: src/frontend/src/features/dashboard/CreateManagerModal.tsx]
- [Source: src/frontend/src/features/dashboard/RoleDashboards.tsx — dashboard Admin]
- [Source: src/frontend/src/features/dashboard/dashboardApi.ts — `createUser`]

## Dev Agent Record (rétroactif)

### Completion Notes List

- [x] Flux Admin « Créer Manager » branché sur `POST /v1/iam/users`.
- [x] Tests frontend associés présents.

### File List

- src/frontend/src/features/dashboard/CreateManagerModal.tsx
- src/frontend/src/features/dashboard/CreateManagerModal.test.tsx
- src/frontend/src/features/dashboard/RoleDashboards.tsx
- src/frontend/src/features/dashboard/dashboardApi.ts
- src/frontend/src/features/dashboard/dashboardApi.test.ts
