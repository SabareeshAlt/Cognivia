import { describe, expect, it, beforeEach } from "vitest";

import { authStorage } from "@/lib/auth";

describe("authStorage", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("stores user in localStorage", () => {
    authStorage.setUser({ id: 1, email: "user@example.com", name: "User" });
    expect(authStorage.getUser()).toEqual({ id: 1, email: "user@example.com", name: "User" });
  });

  it("stores tokens in sessionStorage", () => {
    authStorage.setTokens({ access: "a", refresh: "r" });
    expect(sessionStorage.getItem("rag_tokens")).toContain("\"access\":\"a\"");
    expect(authStorage.getTokens()).toEqual({ access: "a", refresh: "r" });
  });

  it("clearAll removes persisted auth and chat keys", () => {
    authStorage.setUser({ id: 1, email: "user@example.com", name: "User" });
    authStorage.setTokens({ access: "a", refresh: "r" });
    localStorage.setItem("rag_chats", "[]");

    authStorage.clearAll();

    expect(authStorage.getUser()).toBeNull();
    expect(authStorage.getTokens()).toBeNull();
    expect(localStorage.getItem("rag_chats")).toBeNull();
  });
});
