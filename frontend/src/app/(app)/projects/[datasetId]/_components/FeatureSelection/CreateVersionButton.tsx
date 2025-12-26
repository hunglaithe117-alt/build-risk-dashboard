"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Sparkles, AlertTriangle } from "lucide-react";

interface CreateVersionButtonProps {
    datasetId: string;
    disabled?: boolean;
    hasActiveVersion?: boolean;
}

/**
 * Button to navigate to the full-page Create Version Wizard.
 * Replaces the old modal-based approach for better UX.
 */
export function CreateVersionButton({
    datasetId,
    disabled,
    hasActiveVersion,
}: CreateVersionButtonProps) {
    const router = useRouter();

    const handleClick = () => {
        router.push(`/projects/${datasetId}/versions/new`);
    };

    if (hasActiveVersion) {
        return (
            <Button disabled className="gap-2">
                <AlertTriangle className="h-4 w-4" />
                Version Processing...
            </Button>
        );
    }

    return (
        <Button onClick={handleClick} disabled={disabled} className="gap-2">
            <Sparkles className="h-4 w-4" />
            Create New Version
        </Button>
    );
}
