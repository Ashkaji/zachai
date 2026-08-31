# ZachAI — Kit de handoff Figma

Ce dossier accompagne la proposition de refonte visuelle des 4 parcours (10 écrans).
Objectif : obtenir un fichier Figma **propre et éditable** (variables + composants), pas un import aplati.

- **Maquette de référence (artifact)** : https://claude.ai/code/artifact/d3cb37e5-84a1-4276-9c77-adf13c9d886a
- **Tokens** : [`zachai-tokens.json`](./zachai-tokens.json) — format Tokens Studio (dark + light)
- **Source de vérité code** : `src/frontend/src/theme/theme.css`

---

## 1. Importer les tokens dans Figma

1. Installer le plugin **Tokens Studio for Figma** (gratuit).
2. Plugin → onglet **Settings** → laisser le stockage local.
3. Onglet principal → menu (⋯) → **Load** / **Import** → coller le contenu de `zachai-tokens.json`.
4. Trois *token sets* apparaissent : `global` (type, spacing, radius, poids), `light`, `dark`.
5. **Créer les thèmes** : Themes → `Light` = global + light ; `Dark` = global + dark.
6. Bouton **Create Variables / Export to Figma Variables** → génère les Figma Variables natives
   avec **deux modes** (Light / Dark) sur la collection couleur.

> Résultat : chaque composant stylé via une variable bascule automatiquement entre nuit et jour,
> exactement comme `data-theme` dans le code.

---

## 2. Barème de tokens (référence rapide)

### Couleurs — action & surfaces
| Token | Light | Dark | Usage |
|---|---|---|---|
| `color.bg` | `#f9f9f9` | `#0a0e14` | fond page |
| `color.surface` | `#ffffff` | `#0e131b` | cartes |
| `color.surface-hi` | `#eeeeee` | `#151a21` | panneaux internes |
| `color.text` | `#1a1c1c` | `#f1f3fc` | texte |
| `color.text-muted` | `#5a6072` | `#a8abb3` | secondaire |
| `color.primary` | `#005bc0` | `#74b1ff` | **action** (boutons, liens) |
| `color.outline` | `rgba(20,30,60,.1)` | `rgba(255,255,255,.1)` | bordures |

### Couleurs — statut sémantique (le cœur de la refonte)
> Réservées à **l'état du pipeline**. Ne jamais utiliser `primary` pour un statut.

| Statut | Light | Dark | Sens |
|---|---|---|---|
| `status.uploaded` | `#8a93ad` | `#7f889f` | déposé |
| `status.assigned` | `#6f6bff` | `#8f8bff` | assigné |
| `status.in-progress` | `#0091c2` | `#35b6e6` | en cours |
| `status.transcribed` | `#d98a00` | `#f0a72e` | à valider |
| `status.validated` | `#17936b` | `#46c295` | validé |
| `status.critical` | `#c02b2b` | `#ff6b6b` | erreur |

### Type · Spacing · Radius
- **Display** : Manrope (700 / 800). **Body** : Inter (400 / 600). **Mono/données** : tabular-nums.
- Échelle : eyebrow 12 · caption 13 · body 15 · sectionTitle 17 · pageTitle 20 · metric 27 · display 48.
- Spacing (px) : 4 · 8 · 12 · 16 · 20 · 24 · 32.
- Radius : sm 10 · md 12 · lg 16 · pill 100.

---

## 3. Composants à créer (avec variantes)

Construire ces composants une fois, avec variables + variantes, puis composer les 10 écrans.

### StatusChip
- Point 7px + label. Fond = `status.*` à 14–16 % d'opacité, texte = `status.*` plein.
- **Variantes** : `uploaded · assigned · in-progress · transcribed · validated · critical`.
- Padding 4×10, radius pill, poids 700, taille 12.

### MetricTile
- Fond `surface-hi`, radius md, padding 14×15.
- Slots : label (label/12/muted), valeur (metric/27, tabular-nums), tendance (▲/▼ + `status.validated`/`critical`), sparkline optionnelle.
- **Variantes** : `default · positive · attention · demo` (le mode `demo` ajoute un badge « DÉMO »).

### PipelineBar
- Barre segmentée, hauteur 9, radius pill, fond `surface-vhi`.
- Segments proportionnels colorés par `status.*` + légende chiffrée dessous.

### TaskCard (transcripteur)
- Ligne : forme d'onde 84×34 → nom fichier (bold 15) + projet (muted 12) → StatusChip → boutons `Reprendre` (primary sm) / `Aide` (ghost sm).
- **État** : `assigné · en cours · entraide demandée` (drapeau `status.transcribed`).

### EmptyState
- Icône 44 dans carré `primary-soft`, titre (display 15), description (muted 13, ≤42ch), CTA optionnel.

### Autres
- **Button** : `primary · ghost · danger` × `md · sm`.
- **Toggle** (RGPD) : off = `surface-vhi`, on = `status.validated`.
- **Modal** : scrim + carte `surface`, header + body, `warn-box` pour l'avertissement de normalisation.
- **Stepper** : done (`validated`) · active (`primary` + halo) · à venir (`surface-vhi`).
- **DiffPane** : volet gauche muted (machine), droite pleine ; `.del` = `critical` 20 %, `.ins` = `validated` 22 %.

---

## 4. Écrans à composer (frames)

Desktop 1280 de large, deux modes (Light/Dark) :

1. Connexion (Keycloak)
2. Dashboard Admin
3. Dashboard Manager (portefeuille)
4. Wizard Nouveau projet — étape Audios (+ étape Assignation)
5. Détail projet + modale d'assignation
6. Dashboard Transcripteur (Mes tâches / Libre service)
7. Éditeur de transcription
8. Dashboard Expert
9. Réconciliation / Golden Set
10. Profil & Sécurité (RGPD)

---

## 5. Alternative — import direct de la maquette
Plugin **html.to.design** → coller l'URL de l'artifact pour obtenir des frames éditables rapidement,
puis rebrancher les calques sur les variables importées à l'étape 1. Pratique pour démarrer,
mais moins propre que de reconstruire à partir des composants ci-dessus.
