import { useEffect, useState } from "react";
import { GlassModal } from "../../shared/ui/Modals";
import { createUser, type UserCreate } from "./dashboardApi";

interface CreateManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  onSuccess: () => void;
}

export function CreateManagerModal({ isOpen, onClose, token, onSuccess }: CreateManagerModalProps) {
  const initialFormData: Omit<UserCreate, "role"> = {
    username: "",
    email: "",
    firstName: "",
    lastName: "",
    enabled: true,
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
      await createUser({ ...formData, role: "Manager" }, token);
      onSuccess();
      onClose();
    } catch (err: any) {
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
    setError("");
    setLoading(false);
    onClose();
  };

  return (
    <GlassModal isOpen={isOpen} onClose={handleClose} title="Créer un nouveau Manager">
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: "var(--spacing-4)" }}>
        {error && <p style={{ color: "var(--color-error)", fontSize: "0.85rem", margin: 0 }}>{error}</p>}
        
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
