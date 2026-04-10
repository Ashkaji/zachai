export type AppRole = "admin" | "manager" | "transcriber" | "expert";

function readRoleCandidates(profile: Record<string, unknown>): string[] {
  const roles: string[] = [];
  const realmAccess = profile.realm_access;
  if (realmAccess && typeof realmAccess === "object") {
    const candidate = (realmAccess as Record<string, unknown>).roles;
    if (Array.isArray(candidate)) {
      roles.push(...candidate.filter((value): value is string => typeof value === "string"));
    }
  }

  const resourceAccess = profile.resource_access;
  if (resourceAccess && typeof resourceAccess === "object") {
    for (const clientEntry of Object.values(resourceAccess as Record<string, unknown>)) {
      if (!clientEntry || typeof clientEntry !== "object") {
        continue;
      }
      const candidate = (clientEntry as Record<string, unknown>).roles;
      if (Array.isArray(candidate)) {
        roles.push(...candidate.filter((value): value is string => typeof value === "string"));
      }
    }
  }

  return roles;
}

export function resolveAppRole(profile: Record<string, unknown> | undefined): AppRole {
  if (!profile) {
    return "transcriber";
  }

  const roles = readRoleCandidates(profile).map((role) => role.toLowerCase());
  if (roles.some((role) => role.includes("admin"))) return "admin";
  if (roles.some((role) => role.includes("manager"))) return "manager";
  if (roles.some((role) => role.includes("expert"))) return "expert";
  if (roles.some((role) => role.includes("transcrip"))) return "transcriber";
  return "transcriber";
}
