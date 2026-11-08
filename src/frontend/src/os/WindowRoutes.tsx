// SPDX-License-Identifier: AGPL-3.0-or-later
// The pages an app window can show. Each window renders them at its own location, so
// `useParams`/`useLocation` inside a page read the window path, not the browser URL.
import { Route, Routes } from "react-router-dom";

import { InboxPage } from "../views/inbox/InboxPage.tsx";
import { MarketplacePage, PackagesPage } from "../views/packages/PackagesPage.tsx";
import { ProjectPage } from "../views/project/ProjectPage.tsx";
import { NewProjectPage } from "../views/projects/NewProjectPage.tsx";
import { ProjectsPage } from "../views/projects/ProjectsPage.tsx";
import { SettingsPage } from "../views/settings/SettingsPage.tsx";
import { NotFoundPage } from "../views/system/Pages.tsx";

export function WindowRoutes({ location }: { location: string }) {
  return (
    <Routes location={location}>
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
    </Routes>
  );
}
