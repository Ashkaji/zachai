import { useEffect, useMemo, useState } from "react";
import { useAuth } from "react-oidc-context";
import { bearerForApi } from "../../auth/api-client";
import { Card, Badge } from "../../shared/ui/Primitives";
import { 
  Download, 
  Trash2, 
  User, 
  RefreshCcw, 
  AlertTriangle,
} from "lucide-react";
import { 
  fetchMyProfile, 
  updateMyConsents, 
  requestAccountDeletion, 
  cancelAccountDeletion, 
  exportMyData,
  type UserProfile
} from "./ProfileApi";
import { useNotifications } from "../../shared/notifications/NotificationContext";

// --- Local UI Components ---

function Toggle({ 
  label, 
  checked, 
  onChange, 
  disabled = false 
}: { 
  label: string, 
  checked: boolean, 
  onChange: (v: boolean) => void,
  disabled?: boolean
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0" }}>
      <span style={{ fontSize: "0.95rem", fontWeight: 600 }}>{label}</span>
      <button
        onClick={() => !disabled && onChange(!checked)}
        disabled={disabled}
        style={{
          width: "44px",
          height: "24px",
          borderRadius: "12px",
          background: checked ? "var(--color-primary)" : "var(--color-surface-vhi)",
          position: "relative",
          border: "none",
          cursor: disabled ? "not-allowed" : "pointer",
          transition: "all 0.2s ease",
          opacity: disabled ? "0.5" : 1,
          boxShadow: checked ? "var(--glow-primary)" : "inset 0 2px 4px rgba(0,0,0,0.1)"
        }}
      >
        <div style={{
          width: "18px",
          height: "18px",
          borderRadius: "50%",
          background: "#fff",
          position: "absolute",
          top: "3px",
          left: checked ? "23px" : "3px",
          transition: "left 0.2s ease",
          boxShadow: "0 2px 4px rgba(0,0,0,0.2)"
        }} />
      </button>
    </div>
  );
}

function SectionTitle({ icon: Icon, title }: { icon: any, title: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "var(--spacing-4)" }}>
      <div style={{ 
        width: "36px", 
        height: "36px", 
        borderRadius: "var(--radius-sm)", 
        background: "var(--color-primary-soft)", 
        color: "var(--color-primary)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center"
      }}>
        <Icon size={20} strokeWidth={2} />
      </div>
      <h4 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 800 }}>{title}</h4>
    </div>
  );
}

// --- Main Feature Component ---

export function ProfileCenter() {
  const auth = useAuth();
  const token = useMemo(() => bearerForApi(auth.user), [auth.user]);
  const { notify } = useNotifications();
  
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadProfile = async () => {
    if (!token) return;
    try {
      setLoading(true);
      const data = await fetchMyProfile(token);
      setProfile(data);
    } catch (e: any) {
      setError(e.message || "Erreur de chargement du profil");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, [token]);

  const handleToggleConsent = async (key: 'ml_usage' | 'biometric_data', value: boolean) => {
    if (!token || !profile) return;
    try {
      setBusy(true);
      const newMl = key === 'ml_usage' ? value : profile.consents.ml_usage;
      const newBio = key === 'biometric_data' ? value : profile.consents.biometric_data;
      
      const newStatus = await updateMyConsents(newMl, newBio, token);
      setProfile({ ...profile, consents: newStatus });
      
      notify({
        tier: "informational",
        title: "Consentements mis à jour",
        body: "Vos préférences RGPD ont été enregistrées.",
      });
    } catch (e: any) {
      notify({
        tier: "critical",
        title: "Erreur",
        body: e.message || "Impossible de mettre à jour les consentements.",
      });
    } finally {
      setBusy(false);
    }
  };

  const handleExport = async () => {
    if (!token) return;
    try {
      setBusy(true);
      await exportMyData(token);
      notify({
        tier: "informational",
        title: "Export prêt",
        body: "Votre archive de données a été générée avec succès.",
      });
    } catch (e: any) {
      notify({
        tier: "critical",
        title: "Erreur d'export",
        body: e.message,
      });
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteRequest = async () => {
    if (!token || !window.confirm("Êtes-vous sûr de vouloir supprimer votre compte ? Toutes vos données seront anonymisées après 48h.")) return;
    try {
      setBusy(true);
      const newStatus = await requestAccountDeletion(token);
      setProfile(p => p ? { ...p, consents: newStatus } : null);
      notify({
        tier: "critical",
        title: "Suppression demandée",
        body: "Votre demande a été prise en compte. Le compte sera supprimé dans 48 heures.",
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleCancelDeletion = async () => {
    if (!token) return;
    try {
      setBusy(true);
      const newStatus = await cancelAccountDeletion(token);
      setProfile(p => p ? { ...p, consents: newStatus } : null);
      notify({
        tier: "informational",
        title: "Suppression annulée",
        body: "Votre demande de suppression de compte a été annulée.",
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div style={{ padding: "var(--spacing-8)" }}><RefreshCcw className="za-spin" /> Chargement du profil...</div>;

  return (
    <div style={{ maxWidth: "1000px", animation: "fade-in 0.4s ease" }}>
      {error && (
        <div style={{ background: "var(--color-error-soft)", color: "var(--color-error)", padding: "16px", borderRadius: "8px", marginBottom: "24px", display: "flex", gap: "12px", alignItems: "center" }}>
          <AlertTriangle size={20} /> {error}
        </div>
      )}

      {profile?.consents.deletion_pending && (
        <div style={{ 
          background: "var(--color-error)", 
          color: "#fff", 
          padding: "20px", 
          borderRadius: "var(--radius-lg)", 
          marginBottom: "32px", 
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center",
          boxShadow: "0 10px 30px rgba(255, 75, 75, 0.3)"
        }}>
          <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
            <Trash2 size={24} />
            <div>
              <div style={{ fontWeight: 800, fontSize: "1.1rem" }}>SUPPRESSION EN COURS</div>
              <div style={{ fontSize: "0.9rem", opacity: 0.9 }}>Votre accès est restreint. Le compte sera définitivement anonymisé sous peu.</div>
            </div>
          </div>
          <button 
            onClick={handleCancelDeletion} 
            className="za-btn" 
            style={{ background: "#fff", color: "var(--color-error)", fontWeight: 700 }}
            disabled={busy}
          >
            Annuler la suppression
          </button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", marginBottom: "32px" }}>
        {/* User Info Card */}
        <Card title="Identité & Rôles">
          <div style={{ display: "flex", alignItems: "center", gap: "20px", marginBottom: "24px" }}>
            <div style={{ 
              width: "64px", 
              height: "64px", 
              borderRadius: "50%", 
              background: "var(--color-primary-soft)", 
              color: "var(--color-primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center"
            }}>
              <User size={32} strokeWidth={1.5} />
            </div>
            <div>
              <div style={{ fontSize: "1.2rem", fontWeight: 800 }}>{profile?.name}</div>
              <div style={{ fontSize: "0.9rem", color: "var(--color-text-muted)" }}>{profile?.email}</div>
            </div>
          </div>
          
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {profile?.roles.map(r => (
              <Badge key={r} tone="primary" glow>{r}</Badge>
            ))}
          </div>
          <div style={{ marginTop: "24px", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
            ID unique : <code style={{ background: "var(--color-surface-hi)", padding: "2px 4px", borderRadius: "4px" }}>{profile?.sub}</code>
          </div>
        </Card>

        {/* Consents Card */}
        <Card title="Confidentialité & Consentements" subtitle="Gérez vos préférences RGPD">
          <Toggle 
            label="Utilisation ML (Amélioration IA)" 
            checked={!!profile?.consents.ml_usage} 
            onChange={(v) => handleToggleConsent('ml_usage', v)}
            disabled={busy || !!profile?.consents.deletion_pending}
          />
          <p style={{ margin: "0 0 16px", fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
            Autorise l'utilisation de vos corrections pour l'entraînement des modèles LoRA. Le retrait purge immédiatement vos contributions du Golden Set.
          </p>
          
          <Toggle 
            label="Données Biométriques (Voix)" 
            checked={!!profile?.consents.biometric_data} 
            onChange={(v) => handleToggleConsent('biometric_data', v)}
            disabled={busy || !!profile?.consents.deletion_pending}
          />
          <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
            Autorise le stockage et l'analyse de caractéristiques vocales spécifiques.
          </p>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Portability Card */}
        <Card title="Portabilité des données">
          <SectionTitle icon={Download} title="Récupérer vos données" />
          <p style={{ fontSize: "0.9rem", marginBottom: "20px" }}>
            Conformément à l'article 20 du RGPD, vous pouvez télécharger l'intégralité de vos données personnelles (profil, tâches, corrections, logs) dans un format structuré (ZIP/JSON).
          </p>
          <button 
            onClick={handleExport}
            className="za-btn za-btn--primary" 
            style={{ width: "100%", justifyContent: "center", gap: "12px" }}
            disabled={busy || !!profile?.consents.deletion_pending}
          >
            <Download size={18} /> Télécharger mon archive (.zip)
          </button>
        </Card>

        {/* Security / Danger Zone */}
        <Card title="Zone de danger">
          <SectionTitle icon={Trash2} title="Droit à l'oubli" />
          <p style={{ fontSize: "0.9rem", marginBottom: "20px" }}>
            La suppression de votre compte anonymisera toutes vos données personnelles. Cette action est irréversible après le délai de grâce de 48h.
          </p>
          {!profile?.consents.deletion_pending ? (
            <button 
              onClick={handleDeleteRequest}
              className="za-btn za-btn--ghost" 
              style={{ width: "100%", justifyContent: "center", color: "var(--color-error)", background: "rgba(255, 75, 75, 0.05)" }}
              disabled={busy}
            >
              <Trash2 size={18} /> Demander la suppression du compte
            </button>
          ) : (
            <Badge tone="error" pulse style={{ width: "100%", justifyContent: "center", padding: "12px" }}>
              SUPPRESSION PROGRAMMÉE
            </Badge>
          )}
        </Card>
      </div>

      <div style={{ marginTop: "40px", textAlign: "center", color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
        Dernière mise à jour de vos préférences : {profile?.consents.updated_at ? new Date(profile.consents.updated_at).toLocaleString() : "--"}
      </div>
    </div>
  );
}
