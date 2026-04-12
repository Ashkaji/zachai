import { describe, it, expect, vi, beforeEach } from "vitest";
import { 
  fetchMyProfile, 
  updateMyConsents, 
  requestAccountDeletion, 
  cancelAccountDeletion 
} from "./ProfileApi";

vi.stubGlobal('fetch', vi.fn());

describe("ProfileApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockResponse = (data: any) => ({
    ok: true,
    text: () => Promise.resolve(JSON.stringify(data)),
  });

  it("fetchMyProfile calls correct endpoint", async () => {
    (fetch as any).mockResolvedValue(mockResponse({ 
      sub: "user-1", 
      name: "Test User", 
      roles: ["Transcripteur"], 
      consents: {} 
    }));
    
    const res = await fetchMyProfile("dummy-token");
    expect(fetch).toHaveBeenCalledWith("/v1/me/profile", expect.anything());
    
    const init = (fetch as any).mock.calls[0][1];
    expect(init.headers.get("Authorization")).toBe("Bearer dummy-token");
    expect(res.sub).toBe("user-1");
  });

  it("updateMyConsents calls PUT with body", async () => {
    (fetch as any).mockResolvedValue(mockResponse({ 
      ml_usage: true, 
      biometric_data: false 
    }));
    
    const res = await updateMyConsents(true, false, "token");
    expect(fetch).toHaveBeenCalledWith("/v1/me/consents", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ ml_usage: true, biometric_data: false })
    }));
    
    const init = (fetch as any).mock.calls[0][1];
    expect(init.headers.get("Authorization")).toBe("Bearer token");
    expect(res.ml_usage).toBe(true);
  });

  it("requestAccountDeletion calls DELETE", async () => {
    (fetch as any).mockResolvedValue(mockResponse({ 
      deletion_pending: true 
    }));
    
    const res = await requestAccountDeletion("token");
    expect(fetch).toHaveBeenCalledWith("/v1/me/account", expect.objectContaining({
      method: "DELETE"
    }));
    expect(res.deletion_pending).toBe(true);
  });

  it("cancelAccountDeletion calls POST", async () => {
    (fetch as any).mockResolvedValue(mockResponse({ 
      deletion_pending: false 
    }));
    
    const res = await cancelAccountDeletion("token");
    expect(fetch).toHaveBeenCalledWith("/v1/me/delete-cancel", expect.objectContaining({
      method: "POST"
    }));
    expect(res.deletion_pending).toBe(false);
  });
});
