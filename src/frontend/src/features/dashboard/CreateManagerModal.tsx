import { useEffect, useState } from "react";
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

export function CreateManagerModal({ isOpen, onClose, token, onSuccess }: CreateManagerModalProps) {
  const { notify } = useNotifications();
  const initialFormData: Omit<UserCreate, "role"> = {
    username: "",
    email: "",
    firstName: "",
    lastName: "",
    enabled: true,
    password: "",
  };
  const [formData, setFormData] = useState<Omit<UserCreate, "role">>({
    ...initialFormData,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen) {
      setFormData(initialFormData);
      setError("");
      setLoading(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const pwd = formData.password?.trim();
      const res = await createUser(
        {
          ...formData,
          role: "Manager",
          password: pwd || undefined,
        },
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
    setFormData(initialFormData);
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
          <input
            name="password"
            type="password"
            value={formData.password ?? ""}
            onChange={handleChange}
            className="za-input"
            autoComplete="new-password"
            placeholder="Laisser vide = mot de passe généré par le serveur"
          />
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
          <button type="submit" className="za-btn za-btn--primary" disabled={loading}>
            {loading ? "Création..." : "Créer Manager"}
          </button>
        </div>
      </form>
    </GlassModal>
  );
}
