import { useEffect, useState, useCallback } from "react";
import { GlassModal } from "../../shared/ui/Modals";
import { createUser, type UserCreate } from "./dashboardApi";
import { useNotifications } from "../../shared/notifications/NotificationContext";

type TeamRole = "Transcripteur" | "Expert";

interface InviteTeamMemberModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onSuccess: () => void;
}

const initialFormData: Omit<UserCreate, "role"> = {
  username: "",
  email: "",
  firstName: "",
  lastName: "",
  enabled: true,
};

export function InviteTeamMemberModal({ isOpen, onClose, token, onSuccess }: InviteTeamMemberModalProps) {
  const { notify } = useNotifications();
  const [formData, setFormData] = useState<Omit<UserCreate, "role">>(() => ({ ...initialFormData }));
  const [role, setRole] = useState<TeamRole>("Transcripteur");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const resetForm = useCallback(() => {
    setFormData({ ...initialFormData });
    setRole("Transcripteur");
    setError("");
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen, resetForm]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || loading) return;

    setLoading(true);
    setError("");

    const sanitizedData = {
      username: formData.username.trim(),
      email: formData.email.trim(),
      firstName: formData.firstName.trim(),
      lastName: formData.lastName.trim(),
      enabled: formData.enabled,
    };

    try {
      await createUser({ ...sanitizedData, role }, token);
      notify({
        tier: "informational",
        title: "Succès",
        body: `Utilisateur ${sanitizedData.username} (${role}) invité avec succès.`,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création");
      setLoading(false);
    }
    // Note: finally { setLoading(false) } is omitted because resetForm or setError handle it, 
    // avoiding redundant state updates after onClose().
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleClose = () => {
    if (loading) return;
    onClose();
  };

  return (
    <GlassModal isOpen={isOpen} onClose={handleClose} title="Inviter un membre d'équipe">
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "var(--spacing-4)" }}>
        {error ? <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p> : null}

        <fieldset style={{ border: "none", padding: 0, margin: 0, display: "grid", gap: "var(--spacing-2)" }}>
          <legend className="za-label" style={{ marginBottom: "var(--spacing-2)" }}>Rôle</legend>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-4)" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "var(--spacing-2)", cursor: "pointer" }}>
              <input
                type="radio"
                name="teamRole"
                checked={role === "Transcripteur"}
                onChange={() => setRole("Transcripteur")}
                disabled={loading}
              />
              Transcripteur
            </label>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "var(--spacing-2)", cursor: "pointer" }}>
              <input 
                type="radio" 
                name="teamRole" 
                checked={role === "Expert"} 
                onChange={() => setRole("Expert")}
                disabled={loading}
              />
              Expert
            </label>
          </div>
          {role === "Expert" ? (
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
              Les experts peuvent ouvrir leurs projets Label Studio depuis le tableau de bord Expert.
            </p>
          ) : null}
        </fieldset>

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
            disabled={loading}
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
            disabled={loading}
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
              disabled={loading}
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
              disabled={loading}
            />
          </div>
        </div>

        <div style={{ marginTop: "var(--spacing-4)", display: "flex", justifyContent: "flex-end", gap: "var(--spacing-3)" }}>
          <button type="button" onClick={handleClose} className="za-btn za-btn--ghost" disabled={loading}>
            Annuler
          </button>
          <button type="submit" className="za-btn za-btn--primary" disabled={loading || !token}>
            {loading ? "Création..." : "Créer le compte"}
          </button>
        </div>
      </form>
    </GlassModal>
  );
}
