import { useEffect, useState, useCallback } from "react";
import { GlassModal } from "../../shared/ui/Modals";
import { createUser, type UserCreate } from "./dashboardApi";
import { useNotifications } from "../../shared/notifications/NotificationContext";
import { ApiError } from "../../shared/api/zachaiApi";

function suggestPassword(): string {
  const buf = new Uint8Array(12);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(36)).join("").slice(0, 16);
}

function formatCreateUserError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return err.message || "Ce nom d’utilisateur ou cet e-mail existe déjà.";
    }
    if (err.status === 403) {
      return err.message || "Action interdite (droits insuffisants ou périmètre manager).";
    }
    if (err.status === 502) {
      return (
        err.message ||
        "Keycloak ou la passerelle a renvoyé une erreur (502). Vérifiez les logs des conteneurs fastapi et keycloak."
      );
    }
  }
  return err instanceof Error ? err.message : "Erreur lors de la création";
}

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
  password: "",
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
      const pwd = formData.password?.trim();
      const res = await createUser({ ...sanitizedData, role, password: pwd || undefined }, token);
      const pwdHint = res.initial_password
        ? ` Mot de passe initial : ${res.initial_password}`
        : "";
      notify({
        tier: "informational",
        title: "Succès",
        body: `Utilisateur ${sanitizedData.username} (${role}) créé.${pwdHint}`,
      });
      setLoading(false);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(formatCreateUserError(err));
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
        {error ? (
          <p
            style={{
              color: "var(--color-error)",
              fontSize: "0.85rem",
              margin: 0,
              whiteSpace: "pre-wrap",
              maxHeight: "14rem",
              overflowY: "auto",
            }}
          >
            {error}
          </p>
        ) : null}

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

        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--spacing-2)" }}>
            <label className="za-label" htmlFor="invite-password" style={{ margin: 0 }}>
              Mot de passe initial
            </label>
            <button
              type="button"
              className="za-btn za-btn--ghost"
              style={{ fontSize: "0.8rem", padding: "4px 8px" }}
              onClick={() =>
                setFormData((prev) => ({
                  ...prev,
                  password: suggestPassword(),
                }))
              }
              disabled={loading}
            >
              Générer
            </button>
          </div>
          <input
            id="invite-password"
            name="password"
            type="password"
            value={formData.password ?? ""}
            onChange={handleChange}
            className="za-input"
            disabled={loading}
            autoComplete="new-password"
            placeholder="Vide = généré par le serveur (affiché dans la notification)"
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
