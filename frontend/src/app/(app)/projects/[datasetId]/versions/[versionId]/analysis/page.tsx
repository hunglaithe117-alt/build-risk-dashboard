"use client";

import { useParams } from "next/navigation";
import { AnalysisSection } from "../_components";

export default function VersionAnalysisPage() {
    const params = useParams<{ datasetId: string; versionId: string }>();
    const datasetId = params.datasetId;
    const versionId = params.versionId;

    return (
        <AnalysisSection
            datasetId={datasetId}
            versionId={versionId}
            versionStatus="processed"
        />
    );
}
