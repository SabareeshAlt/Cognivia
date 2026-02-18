import { Navigate, type ReactNode } from "react-router-dom";

import { authStorage } from "@/lib/auth";

interface ProtectedRouteProps {
  children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const user = authStorage.getUser();
  const tokens = authStorage.getTokens();

  if (!user || !tokens?.access) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
