---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: ['.ignore/brd.md']
workflowType: 'research'
lastStep: 4
research_type: 'technical'
research_topic: 'Open-Source Collaborative Editor Stack for ZachAI'
research_goals: 'Identify the best open-source tech stack for a Google Docs-like collaborative editor with rich styling, version management, and bidirectional audio synchronization, ensuring full on-premise sovereignty.'
user_name: 'Josué HUNNAKEY'
date: '2026-03-19'
web_research_enabled: true
source_verification: true
---

# Research Report: technical

**Date:** 2026-03-19
**Author:** Josué HUNNAKEY
**Research Type:** technical

---

## Research Overview

## Technical Research Scope Confirmation

**Research Topic:** Open-Source Collaborative Editor Stack for ZachAI
**Research Goals:** Identify the best open-source tech stack for a Google Docs-like collaborative editor with rich styling, version management, and bidirectional audio synchronization, ensuring full on-premise sovereignty.

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights

**Scope Confirmed:** 2026-03-19

---

## Technology Stack Analysis

### Programming Languages

The collaborative editor ecosystem in 2026 is dominated by **TypeScript** and **Node.js**. TypeScript is essential for managing the complex shared types required by CRDTs (Conflict-free Replicated Data Types) and ensuring type safety across the frontend editor and the backend signaling server.
_Popular Languages: TypeScript, JavaScript (Node.js)_
_Emerging Languages: Rust (via Yrs/WASM for high-performance CRDT operations)_
_Language Evolution: Shift towards strict typing for complex state management_
_Performance Characteristics: TypeScript/Node.js provides the low-latency I/O necessary for real-time WebSockets._
_Source: [dev.to](https://dev.to/lexical), [lexical.dev](https://lexical.dev)_

### Development Frameworks and Libraries

For ZachAI, the "Headless" approach is the most robust choice.
_Major Frameworks: **Tiptap** (Headless, built on ProseMirror) and **Lexical** (Meta's performance engine)._
_Micro-frameworks: **Yjs** (the gold standard for CRDT synchronization)._
_Evolution Trends: Headless editors are replacing "batteries-included" editors like CKEditor for custom workflows._
_Ecosystem Maturity: Tiptap/Yjs have massive community support and pre-built extensions for collaboration._
_Source: [tiptap.dev](https://tiptap.dev), [yjs.dev](https://yjs.dev)_

### Database and Storage Technologies

Collaboration requires two types of storage: ephemeral signaling and persistent snapshots.
_Relational Databases: **PostgreSQL** for storing Yjs update blobs and document metadata._
_NoSQL Databases: **Redis** for real-time signaling, presence indicators (avatars), and horizontal scaling._
_In-Memory Databases: Redis is mandatory for the Hocuspocus/Y-websocket signaling layer._
_Data Warehousing: **MinIO** (S3-compatible) for storing long-term version snapshots and audio files._
_Source: [hocuspocus.tiptap.dev](https://hocuspocus.tiptap.dev)_

### Development Tools and Platforms

_IDE and Editors: VS Code with TypeScript/ESLint plugins._
_Version Control: Git._
_Build Systems: Vite (Frontend) and TS-Node/Docker (Backend)._
_Testing Frameworks: Playwright for E2E collaborative testing (testing two users in one session)._
_Source: [playwright.dev](https://playwright.dev)_

### Cloud Infrastructure and Deployment (On-Premise Focus)

ZachAI mandates a 100% On-Premise sovereign stack.
_Major Providers: N/A (Self-hosted on physical/private-cloud servers)._
_Container Technologies: **Docker** and **Docker Compose** for easy on-premise orchestration._
_Serverless Platforms: N/A (Persistent WebSocket connections require dedicated containers)._
_CDN and Edge Computing: Self-hosted **Nginx** or **Traefik** as reverse proxies for WebSocket management._
_Source: [docker.com](https://docker.com)_

### Technology Adoption Trends

_Migration Patterns: Moving from Operational Transformation (OT) to CRDT (Yjs) for easier scaling._
_Emerging Technologies: **Local-first** architectures where the editor works offline and syncs when back online._
_Legacy Technology: Traditional `contenteditable` hacks and heavy "Word-clone" editors._
_Community Trends: Strong preference for headless editors that allow total UI control (essential for ZachAI)._
_Source: [yjs.dev](https://yjs.dev)_

---

## Integration Patterns Analysis

### API Design Patterns

For real-time collaboration, traditional RESTful APIs are replaced by a **State-Sync Protocol** over WebSockets.
_RESTful APIs: Used for initial document discovery, project metadata, and generating "Collaboration Tickets" for WebSocket handshakes._
_GraphQL APIs: N/A (Standard WebSockets are preferred for the CRDT sync layer)._
_RPC and gRPC: Potential for high-performance internal communication between the Gateway and Hocuspocus._
_Webhook Patterns: **Mandatory** for triggering snapshots in MinIO and notifying Camunda workflows when a version is "Finalized."_
_Source: [hocuspocus.tiptap.dev](https://hocuspocus.tiptap.dev)_

### Communication Protocols

The backbone of the ZachAI editor is a persistent, binary-encoded stream.
_HTTP/HTTPS Protocols: Used only for the initial handshake and static asset delivery._
_WebSocket Protocols: **WSS (Secure WebSockets)** is used for the continuous Yjs sync stream._
_Message Queue Protocols: **Redis Pub/Sub** is used internally by Hocuspocus to sync state across multiple server instances._
_Source: [yjs.dev](https://yjs.dev)_

### Data Formats and Standards

Efficiency is critical for the < 50ms latency target.
_JSON and XML: Used only for non-real-time metadata exchange._
_Protobuf and MessagePack: Yjs uses a similar **run-length encoded binary format** (V1/V2) which is 10x smaller than JSON for document updates._
_Custom Data Formats: **Timestamp-Text Mappings** are stored as custom CRDT shared types to ensure audio sync remains consistent across collaborators._
_Source: [github.com/yjs/yjs](https://github.com/yjs/yjs)_

### System Interoperability Approaches

ZachAI must bridge the gap between the ML pipeline and the Human-in-the-Loop editor.
_API Gateway Patterns: A **Unified Gateway** (FastAPI) handles OIDC authentication and routes users to the correct Hocuspocus document instance._
_Service Mesh: Not required for initial MVP; standard Docker networking is sufficient._
_Enterprise Service Bus: N/A (Camunda 8 acts as the orchestrator)._
_Source: [docs.camunda.io](https://docs.camunda.io)_

### Event-Driven Integration

_Publish-Subscribe Patterns: Real-time cursor presence and "is typing" indicators use the **Yjs Awareness Protocol**._
_Event Sourcing: Yjs updates are essentially an event log of document changes._
_Message Broker Patterns: Redis handles the live distribution of editor events._
_Source: [tiptap.dev/docs/collaboration](https://tiptap.dev/docs/collaboration)_

### Integration Security Patterns (Critical for GDPR)

_OAuth 2.0 and JWT: **Short-lived Ticket Pattern** — The user exchanges a Keycloak JWT for a one-time WebSocket ticket to avoid passing tokens in URLs._
_API Key Management: Used for service-to-service communication (e.g., Camunda to MinIO)._
_Mutual TLS: Recommended for on-premise service communication within the private network._
_Data Encryption: **AES-256** at rest in MinIO; **TLS 1.3** in transit for WebSockets._
_Source: [keycloak.org](https://www.keycloak.org)_

---

## Architectural Patterns and Design

### System Architecture Patterns

The ZachAI editor follows a **Headless CRDT-based Architecture**.
- **Engine**: ProseMirror provides the foundational toolkit for managing an immutable document tree.
- **Synchronization**: **Yjs** implements the CRDT logic, ensuring that all collaborators eventually converge to the same state without a central authority.
- **Signaling**: **Hocuspocus** acts as the WebSocket relay, using an event-driven model to broadcast binary updates.
_Source: [tiptap.dev/docs/collaboration](https://tiptap.dev/docs/collaboration), [yjs.dev](https://yjs.dev)_

### Design Principles and Best Practices

- **Separation of Concerns**: The document model (ProseMirror) is strictly decoupled from the synchronization layer (Yjs).
- **Immutable State**: Editor states are treated as immutable values, enabling reliable undo/redo and time-travel debugging.
- **Intent Preservation**: Formatting is treated as "spans" (via the Peritext algorithm in modern CRDTs) to ensure that concurrent edits to the same paragraph preserve the user's intended styling.
_Source: [prosemirror.net](https://prosemirror.net), [loro.dev](https://loro.dev)_

### Scalability and Performance Patterns

To meet the **< 50ms latency** target:
- **Redis Pub/Sub**: Enables horizontal scaling of Hocuspocus instances across on-premise nodes while keeping all sessions in sync.
- **Binary Framing**: Uses `lib0` variable-length encoding to minimize the size of WebSocket packets.
- **Incremental Updates**: Only changes (deltas) are transmitted, not the full document state.
_Source: [github.com/dmonad/lib0](https://github.com/dmonad/lib0)_

### Integration and Communication Patterns

- **Short-Lived Ticket Pattern**: Bridges the OIDC/JWT authentication gap for WebSockets.
- **Webhook Snapshots**: Hocuspocus triggers immuable snapshots in MinIO after a debounced period of inactivity (e.g., 5s).
- **Event-Driven Flywheel**: Modification events trigger LoRA training jobs once the 100-entry threshold is met.
_Source: [hocuspocus.tiptap.dev](https://hocuspocus.tiptap.dev)_

### Security Architecture Patterns (Zero Trust)

- **Identity-Aware Proxy**: An on-premise gateway (e.g., Traefik or Pomerium) enforces OIDC policies before traffic reaches the editor services.
- **Micro-segmentation**: The editor containers are isolated in a dedicated Docker network, communicating with MinIO only via internal APIs.
- **End-to-End Encryption (E2EE)**: While not mandatory for MVP, the Yjs stack supports E2EE for high-sensitivity ministerial content.
_Source: [pomerium.com/zta](https://pomerium.com)_

### Data Architecture Patterns

- **Hybrid Persistence**: Live updates are stored as binary blobs in PostgreSQL/Redis; finalized versions are exported as JSON/SRT/DOCX to MinIO.
- **Schema Composition**: A modular schema allows the easy addition of "Ministerial Styles" (e.g., specific marks for biblical citations) without breaking standard rich-text compatibility.
_Source: [prosemirror.net/docs/guide/#schema](https://prosemirror.net/docs/guide/#schema)_

---

<!-- Content will be appended sequentially through research workflow steps -->



