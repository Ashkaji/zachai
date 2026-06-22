import { useEffect, useState } from "react";
import { GlassModal } from "../../shared/ui/Modals";
import { createUser, type UserCreate } from "./dashboardApi";
import { useNotifications } from "../../shared/notifications/NotificationContext";
import { ApiError } from "../../shared/api/zachaiApi";

function suggestPassword(): string {
  const buf = new Uint8Array(24);
  crypto.getRandomValues(buf);
  return btoa(String.fromCharCode(...buf)).replace(/[+/=]/g, "").slice(0, 16);
}

function formatCreateUserError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return err.message || "Ce nom d’utilisateur ou cet e-mail existe déjà.";
    }
    if (err.status === 403) {
      return err.message || "Action interdite (droits insuffisants ou compte déjà lié à un autre manager).";
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

interface CreateManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onSuccess: () => void;
}

const _initialFormData: Omit<UserCreate, "role"> = {
  username: "",
  email: "",
  firstName: "",
  lastName: "",
  enabled: true,
  password: "",
};

export function CreateManagerModal({ isOpen, onClose, token, onSuccess }: CreateManagerModalProps) {
  const { notify } = useNotifications();
  const [formData, setFormData] = useState<Omit<UserCreate, "role">>({
    ..._initialFormData,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      setFormData({ ..._initialFormData });
      setError("");
      setLoading(false);
      setShowPassword(false);
    }
  }, [isOpen]);

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
      const res = await createUser(
        { ...sanitizedData, role: "Manager", password: pwd || undefined },
        token,
      );
      if (res.initial_password) {
        notify({
          tier: "informational",
          title: "Manager créé",
          body: `Mot de passe initial (copiez-le, aucun e-mail envoyé) : ${res.initial_password}`,
        });
      } else {
        notify({
          tier: "informational",
          title: "Manager créé",
          body: `Compte ${formData.username} prêt avec le mot de passe que vous avez défini.`,
        });
      }
      onSuccess();
      onClose();
    } catch (err: unknown) {
      setError(formatCreateUserError(err));
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
    setFormData({ ..._initialFormData });
    setError("");
    setLoading(false);
    onClose();
  };

  return (
    <GlassModal isOpen={isOpen} onClose={handleClose} title="Créer un nouveau Manager">
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
        
        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <label className="za-label">Nom d'utilisateur</label>
          <input
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
            className="za-input"
            autoComplete="off"
          />
        </div>

        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <label className="za-label">Email</label>
          <input
            name="email"
            type="email"
            value={formData.email}
            onChange={handleChange}
            required
            className="za-input"
            autoComplete="off"
          />
        </div>

        <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--spacing-2)" }}>
            <label className="za-label" style={{ margin: 0 }}>
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
          <div style={{ position: "relative" }}>
            <input
              name="password"
              type={showPassword ? "text" : "password"}
              value={formData.password ?? ""}
              onChange={handleChange}
              className="za-input"
              style={{ paddingRight: "4rem" }}
              autoComplete="new-password"
              placeholder="Laisser vide = mot de passe généré par le serveur"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="za-btn za-btn--ghost"
              style={{
                position: "absolute",
                right: "4px",
                top: "50%",
                transform: "translateY(-50%)",
                fontSize: "0.7rem",
                padding: "4px 8px",
                height: "auto"
              }}
            >
              {showPassword ? "Cacher" : "Afficher"}
            </button>
          </div>
          <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            Sans e-mail transactionnel, renseignez un mot de passe ou laissez vide : il sera affiché dans une notification après création.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-4)" }}>
          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label className="za-label">Prénom</label>
            <input
              name="firstName"
              value={formData.firstName}
              onChange={handleChange}
              required
              className="za-input"
              autoComplete="off"
            />
          </div>
          <div style={{ display: "grid", gap: "var(--spacing-1)" }}>
            <label className="za-label">Nom</label>
            <input
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
          <button type="submit" className="za-btn za-btn--primary" disabled={loading || !token}>
            {loading ? "Création..." : "Créer Manager"}
          </button>
        </div>
      </form>
    </GlassModal>
  );
}
