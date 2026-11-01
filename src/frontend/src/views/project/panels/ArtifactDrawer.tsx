// SPDX-License-Identifier: AGPL-3.0-or-later
// The artifact viewer in the right drawer (3D documents, QA report).
import { useTranslation } from "react-i18next";

import { Drawer } from "../../../components/Overlay.tsx";
import { ArtifactViewer } from "./ArtifactViewer.tsx";

export function ArtifactDrawer({
  artifactId,
  onClose,
}: {
  artifactId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Drawer title={t("artifacts.viewer")} onClose={onClose} wide>
      <div className="-m-4">
        <ArtifactViewer artifactId={artifactId} />
      </div>
    </Drawer>
  );
}
