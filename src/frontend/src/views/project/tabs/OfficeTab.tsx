// SPDX-License-Identifier: AGPL-3.0-or-later
import { useTranslation } from "react-i18next";

import { ComingSoon } from "../../../components/Feedback.tsx";
import { useProjectStore } from "../../../store/projectStore.ts";
import { officeDescription } from "../../../store/selectors.ts";

/** Placeholder until E-09: the scene will read `rooms` and `agents` from the same store. */
export function OfficeTab() {
  const { t } = useTranslation();
  const description = useProjectStore(officeDescription);
  return (
    <ComingSoon title={t("office.soon")}>
      <p role="img" aria-label={description}>
        {description}
      </p>
    </ComingSoon>
  );
}
