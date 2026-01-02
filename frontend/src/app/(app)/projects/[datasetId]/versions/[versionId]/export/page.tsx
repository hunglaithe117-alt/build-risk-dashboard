"use client";

import { useParams } from "next/navigation";
import { ExportSection } from "../_components";

export default function VersionExportPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    return (
        <ExportSection
            datasetId={datasetId}
            versionId={versionId}
            versionStatus="processed"
        />
    );
}

