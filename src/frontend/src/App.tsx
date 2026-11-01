// SPDX-License-Identifier: AGPL-3.0-or-later
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { isAuthError, useMe } from "./api/queries.ts";
import { ErrorState, LoadingBlock } from "./components/Feedback.tsx";
import { Toaster } from "./components/toast.tsx";
import { makeQueryClient } from "./utils/queryClient.ts";
import { LoginPage } from "./views/auth/LoginPage.tsx";
import { InboxPage } from "./views/inbox/InboxPage.tsx";
import { AppShell } from "./views/layout/AppShell.tsx";
import { MarketplacePage, PackagesPage } from "./views/packages/PackagesPage.tsx";
import { ProjectPage } from "./views/project/ProjectPage.tsx";
import { NewProjectPage } from "./views/projects/NewProjectPage.tsx";
import { ProjectsPage } from "./views/projects/ProjectsPage.tsx";
import { SettingsPage } from "./views/settings/SettingsPage.tsx";
import { NotFoundPage } from "./views/system/Pages.tsx";

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
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/new" element={<NewProjectPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="/projects/:projectId/:tab" element={<ProjectPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/packages" element={<PackagesPage />} />
        <Route path="/packages/marketplace" element={<MarketplacePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/:section" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
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
