export interface AuthUser {
  id: number;
  email: string;
  name: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

const USER_KEY = "rag_user";
const TOKENS_KEY = "rag_tokens";

export const authStorage = {
  getUser(): AuthUser | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  },
  setUser(user: AuthUser): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clearUser(): void {
    localStorage.removeItem(USER_KEY);
  },
  getTokens(): AuthTokens | null {
    const raw = sessionStorage.getItem(TOKENS_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthTokens;
    } catch {
      return null;
    }
  },
  setTokens(tokens: AuthTokens): void {
    sessionStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  },
  clearTokens(): void {
    sessionStorage.removeItem(TOKENS_KEY);
  },
  clearAll(): void {
    this.clearUser();
    this.clearTokens();
  },
};
