// SPDX-License-Identifier: AGPL-3.0-or-later
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { isAuthError, useMe } from "./api/queries.ts";
import { ErrorState, LoadingBlock } from "./components/Feedback.tsx";
import { Toaster } from "./components/toast.tsx";
import { Desktop } from "./os/Desktop.tsx";
import { makeQueryClient } from "./utils/queryClient.ts";
import { LoginPage } from "./views/auth/LoginPage.tsx";

function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <LoadingBlock rows={4} />;
  if (me.isError) {
    if (isAuthError(me.error))
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    return <ErrorState error={me.error} onRetry={() => void me.refetch()} />;
  }
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Desktop />
          </RequireAuth>
        }
      />
    </Routes>
  );
}

export default function App({ client = makeQueryClient() }: { client?: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
