// SPDX-License-Identifier: AGPL-3.0-or-later
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { EmptyState } from "../../components/Feedback.tsx";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <EmptyState
      title={t("notFound.title")}
      action={
        <Link to="/projects" className="text-accent underline">
          {t("backToProjects")}
        </Link>
      }
    />
  );
}

export function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <EmptyState
      title={t("forbidden.title")}
      action={
        <Link to="/projects" className="text-accent underline">
          {t("backToProjects")}
        </Link>
      }
    />
  );
}
