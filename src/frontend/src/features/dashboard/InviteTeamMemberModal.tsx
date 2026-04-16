import { useEffect, useState } from "react";
import { GlassModal } from "../../shared/ui/Modals";
import { createUser, type UserCreate } from "./dashboardApi";

type TeamRole = "Transcripteur" | "Expert";

interface InviteTeamMemberModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onSuccess: () => void;
}

export function InviteTeamMemberModal({ isOpen, onClose, token, onSuccess }: InviteTeamMemberModalProps) {
  const initialFormData: Omit<UserCreate, "role"> = {
    username: "",
    email: "",
    firstName: "",
    lastName: "",
    enabled: true,
  };
  const [formData, setFormData] = useState<Omit<UserCreate, "role">>({ ...initialFormData });
  const [role, setRole] = useState<TeamRole>("Transcripteur");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) {
      setFormData(initialFormData);
      setRole("Transcripteur");
      setError("");
      setLoading(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await createUser({ ...formData, role }, token);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création");
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleClose = () => {
    setFormData(initialFormData);
    setRole("Transcripteur");
    setError("");
    setLoading(false);
    onClose();
  };

  return (
    <GlassModal isOpen={isOpen} onClose={handleClose} title="Inviter un membre d'équipe">
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "var(--spacing-4)" }}>
        {error ? <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p> : null}

        <div style={{ display: "grid", gap: "var(--spacing-2)" }}>
          <span className="za-label">Rôle</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-4)" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "var(--spacing-2)", cursor: "pointer" }}>
              <input
                type="radio"
                name="teamRole"
                checked={role === "Transcripteur"}
                onChange={() => setRole("Transcripteur")}
              />
              Transcripteur
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "var(--spacing-2)", cursor: "pointer" }}>
              <input type="radio" name="teamRole" checked={role === "Expert"} onChange={() => setRole("Expert")} />
              Expert
            </label>
          </div>
          {role === "Expert" ? (
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
              L’accès projet Label Studio pour les experts sera branché dans une prochaine livraison (story 16.6).
            </p>
          ) : null}
        </div>

        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <label className="za-label" htmlFor="invite-username">
            Nom d'utilisateur
          </label>
          <input
            id="invite-username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
            className="za-input"
            autoComplete="off"
          />
        </div>

        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <label className="za-label" htmlFor="invite-email">
            Email
          </label>
          <input
            id="invite-email"
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            required
            className="za-input"
            autoComplete="off"
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label className="za-label" htmlFor="invite-firstName">
              Prénom
            </label>
            <input
              id="invite-firstName"
              name="firstName"
              value={formData.firstName}
              onChange={handleChange}
              required
              className="za-input"
              autoComplete="off"
            />
          </div>
          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label className="za-label" htmlFor="invite-lastName">
              Nom
            </label>
            <input
              id="invite-lastName"
              name="lastName"
              value={formData.lastName}
              onChange={handleChange}
              required
              className="za-input"
              autoComplete="off"
            />
          </div>
        </div>

        <div style={{ marginTop: "var(--spacing-4)", display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)" }}>
          <button type="button" onClick={handleClose} className="za-btn za-btn--ghost" disabled={loading}>
            Annuler
          </button>
          <button type="submit" className="za-btn za-btn--primary" disabled={loading}>
            {loading ? "Création..." : "Créer le compte"}
          </button>
        </div>
      </form>
    </GlassModal>
  );
}
