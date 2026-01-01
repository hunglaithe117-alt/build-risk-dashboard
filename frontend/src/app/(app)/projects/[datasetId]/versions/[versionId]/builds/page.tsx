import { redirect } from "next/navigation";

interface PageProps {
    params: { datasetId: string; versionId: string };
}

export default function BuildsPage({ params }: PageProps) {
    // Redirect to default sub-tab (ingestion)
    redirect(`/projects/${params.datasetId}/versions/${params.versionId}/builds/ingestion`);
}
