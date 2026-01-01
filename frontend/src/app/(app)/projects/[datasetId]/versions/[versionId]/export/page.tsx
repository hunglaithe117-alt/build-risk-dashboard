"use client";

import { useParams } from "next/navigation";
import { PreprocessingSection } from "../_components";

export default function VersionExportPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    return (
        <PreprocessingSection
            datasetId={datasetId}
            versionId={versionId}
            versionStatus="processed"
        />
    );
}
