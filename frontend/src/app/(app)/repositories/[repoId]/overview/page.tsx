"use client";

import { useRepo } from "../repo-context";
import { OverviewTab } from "../_tabs/OverviewTab";

export default function OverviewPage() {
    const {
        repo,
        progress,
        builds,
        handleSync,
        handleRetryIngestion,
        handleStartProcessing,
        handleRetryProcessing,
        syncLoading,
        retryIngestionLoading,
        startProcessingLoading,
        retryProcessingLoading,
    } = useRepo();

    if (!repo) return null;

    return (
        <OverviewTab
            repo={repo}
            progress={progress}
            builds={builds}
            onSync={handleSync}
            onRetryIngestion={handleRetryIngestion}
            onStartProcessing={handleStartProcessing}
            onRetryFailed={handleRetryProcessing}
            syncLoading={syncLoading}
            retryIngestionLoading={retryIngestionLoading}
            startProcessingLoading={startProcessingLoading}
            retryFailedLoading={retryProcessingLoading}
        />
    );
}
