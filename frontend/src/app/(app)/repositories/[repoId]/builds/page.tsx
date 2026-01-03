"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

import { reposApi } from "@/lib/api";
import { UnifiedBuildsTable } from "../_tabs/builds/UnifiedBuildsTable";

export default function BuildsPage() {
    const params = useParams();
    const repoId = params.repoId as string;

    const [retryIngestionLoading, setRetryIngestionLoading] = useState(false);
    const [retryProcessingLoading, setRetryProcessingLoading] = useState(false);

    const handleRetryIngestion = async () => {
        setRetryIngestionLoading(true);
        try {
            await reposApi.reingestFailed(repoId);
        } catch (err) {
            console.error("Failed to retry ingestion:", err);
        } finally {
            setRetryIngestionLoading(false);
        }
    };

    const handleRetryProcessing = async () => {
        setRetryProcessingLoading(true);
        try {
            await reposApi.reprocessFailed(repoId);
        } catch (err) {
            console.error("Failed to retry processing:", err);
        } finally {
            setRetryProcessingLoading(false);
        }
    };

    return (
        <UnifiedBuildsTable
            repoId={repoId}
            onRetryIngestion={handleRetryIngestion}
            onRetryProcessing={handleRetryProcessing}
            retryIngestionLoading={retryIngestionLoading}
            retryProcessingLoading={retryProcessingLoading}
        />
    );
}
