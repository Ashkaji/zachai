# ZachAI: UX Design Specifications (Azure Flow)

## 1. Executive Summary
L'expérience utilisateur de ZachAI, baptisée **"Azure Flow"**, est conçue pour transformer la transcription ministérielle en une expérience collaborative fluide, sereine et visuellement dynamique. Elle repose sur une interface **aérée**, dominée par des nuances de **bleu**, intégrant des outils **Open-Source** (Tiptap/Yjs) pour égaler la puissance de Google Docs tout en garantissant une souveraineté totale.

## 2. Design Philosophy
- **Clarté & Sérénité** : Utilisation de l'espace blanc (ou vide) pour réduire la fatigue cognitive.
- **Réactivité Visuelle (Effets "Néon/Halo")** : Utilisation de dégradés et de lueurs bleues pour indiquer l'activité en temps réel et les changements de version.
- **Synchronisation Organique** : Le lien entre l'audio et le texte n'est pas une simple interface, c'est un flux unique.

## 3. Visual Identity & Palette
Le design supporte nativement le **Mode Clair** et le **Mode Sombre**.

| Élément | Mode Clair | Mode Sombre | Usage |
| :--- | :--- | :--- | :--- |
| **Fond Principal** | `#FFFFFF` | `#0A0E14` (Noir Abyssal) | Surface de travail |
| **Accent Primaire** | `#007BFF` (Bleu Cobalt) | `#3D9BFF` (Bleu Électrique) | Boutons, Actions |
| **Collaboration** | `#E3F2FD` (Bleu Ciel) | `#1E2A3B` (Bleu Nuit) | Zones de sélection, Cursors |
| **Versioning** | `#BBDEFB` (Transparence) | `#263238` (Ghost Blue) | Texte supprimé/modifié |
| **Validation** | `#28A745` | `#34D399` | Succès, Transcription validée |

## 4. Layout & Structure (Aéré & Long-form)
- **Top Bar (Azure Header)** : 
    - À gauche : Nom du document + État d'enregistrement (Cloud Sync icon).
    - Au centre : Barre d'outils flottante (Toolbar) Tiptap.
    - À droite : Avatars des collaborateurs avec **halo lumineux bleu** pour les utilisateurs actifs.
- **Main Canvas** : 
    - Support natif des documents **long-form** (plusieurs dizaines de pages) avec scroll fluide et virtualisation.
    - Marges larges (80px+) pour un focus central, évitant la fatigue visuelle.
    - Police : Sans-serif moderne (Inter ou Geist), taille 16px, interlignage 1.6 (Aéré).
- **Side Panel (Changelog & History)** : 
    - Escamotable à droite. 
    - Timeline verticale avec des "nœuds" bleus représentant les Snapshots MinIO.
- **Bottom Dock (Audio Control Hub)** : 
    - Barre flottante en bas de l'écran. Waveform audio stylisée en dégradé bleu.

## 5. Core Experiences (Interactive Patterns)

### A. Collaboration Google Docs-like
- **Cursors Dynamiques** : Chaque collaborateur a un curseur coloré avec un **tooltip** (nom) et une légère **aura bleue** qui pulse lors de la frappe.
- **Sélections Partagées** : Les blocs de texte sélectionnés par d'autres apparaissent avec un fond bleu translucide (Opacité 20%).

### B. Versioning & "Ghost Mode"
- **Visual Diff** : En mode "Historique", les modifications apparaissent avec un effet **"Ghost Text"**. Le texte supprimé devient bleu spectral et s'estompe, tandis que les ajouts brillent doucement.
- **Preview Hover** : Survoler un Snapshot dans la timeline affiche un aperçu rapide des changements majeurs en superposition (Overlay).

### C. Audio-Text Sync (Magnetic Playhead & Karaoke)
- **Smart Click** : Cliquer sur n'importe quel mot déclenche l'audio à ce timestamp précis (précision < 50ms).
- **Active Word Highlight (Karaoke Style)** : 
    - Le mot en cours de lecture est mis en évidence par un **halo bleu néon** et un soulignement animé.
    - La phrase active est légèrement contrastée (fond bleu très pâle en mode clair, lueur subtile en mode sombre).
    - Cette synchronisation visuelle permet à l'opérateur de repérer instantanément les erreurs de transcription de Whisper.
- **Feedback Loop Interaction** : Toute correction manuelle effectuée sur un mot surligné capture automatiquement le segment audio source pour alimenter le réentraînement du modèle (Golden Set).
- **Floating Context Menu** : Sélectionner un texte affiche 3 bulles : 🎧 (Play), ✅ (Valider), 📖 (Style Verset).

### D. Intelligence Linguistique (Grammar Check)
- **Visual Feedback** : 
    - Les fautes d'orthographe sont soulignées par une ligne **ondulée rouge** discrète.
    - Les erreurs de grammaire et de style sont soulignées par une ligne **ondulée jaune/orange**.
- **Correction Contextuelle** : Faire un clic droit (ou un clic gauche sur mobile) sur un mot souligné ouvre un menu flottant "Azure Menu" proposant :
    - La suggestion de correction.
    - Une explication brève de l'erreur (via LanguageTool).
    - Un bouton "Tout ignorer" pour ce document.
- **Toggle de Visibilité** : Un bouton "L" (Linguistique) dans la toolbar permet de masquer les soulignements pour un focus maximal pendant la lecture audio "Karaoké".

## 6. Component Strategy (Open-Source Stack)
- **Framework** : React / TypeScript.
- **Styling** : **Vanilla CSS** (Variables CSS pour le switch Dark/Light).
- **Editor Core** : **Tiptap** (Extensions: Collaboration, FloatingMenu, Highlight, BubbleMenu).
- **Real-time** : **Yjs** (Hocuspocus provider).
- **Icons** : Lucide React (Strokewidth 1.5 pour un look moderne).

## 7. User Journeys
1. **Édition** : L'utilisateur ouvre un document -> Rejoint la session WebSocket -> Voit les avatars s'illuminer -> Édite avec styles Google Docs.
2. **Correction Audio** : Lit le texte -> Entend une erreur -> Clique sur le mot -> L'audio joue -> Corrige -> Le système capture le "diff" pour le Golden Set.
3. **Restauration** : Ouvre le panneau latéral -> Parcourt la timeline bleue -> Clique sur un snapshot -> Le document revient à l'état précédent.
