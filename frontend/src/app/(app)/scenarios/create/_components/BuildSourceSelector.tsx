"use client";

import { useEffect, useState } from "react";
import { Check, FileText, Loader2, Plus, Upload, X } from "lucide-react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
} from "@/components/ui/command";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { buildSourcesApi, type BuildSourceRecord } from "@/lib/api/build-sources";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface BuildSourceSelectorProps {
    value?: string;
    onChange: (value: string | undefined) => void;
}

interface UploadFormData {
    name: string;
    description?: string;
    file: FileList;
}

export function BuildSourceSelector({ value, onChange }: BuildSourceSelectorProps) {
    const [open, setOpen] = useState(false);
    const [sources, setSources] = useState<BuildSourceRecord[]>([]);
    const [loading, setLoading] = useState(false);

    // Upload Dialog State
    const [uploadOpen, setUploadOpen] = useState(false);
    const [uploading, setUploading] = useState(false);
    const { register, handleSubmit, reset } = useForm<UploadFormData>();

    useEffect(() => {
        void loadSources();
    }, []);

    const loadSources = async () => {
        try {
            setLoading(true);
            const data = await buildSourcesApi.list({ limit: 100 });
            setSources(data.items);
        } catch (error) {
            console.error("Failed to load build sources:", error);
        } finally {
            setLoading(false);
        }
    };

    const onUploadSubmit = async (data: UploadFormData) => {
        if (!data.file || data.file.length === 0) return;

        try {
            setUploading(true);
            const file = data.file[0];
            const newSource = await buildSourcesApi.upload(file, {
                name: data.name,
                description: data.description,
            });

            // Wait for validation to complete? Or just select it?
            // For now, just reload and select
            await loadSources();
            onChange(newSource.id);
            setUploadOpen(false);
            reset();

            // Trigger validation immediately
            if (newSource.validation_status === "pending") {
                await buildSourcesApi.startValidation(newSource.id);
            }
        } catch (error) {
            console.error("Failed to upload build source:", error);
        } finally {
            setUploading(false);
        }
    };

    const selectedSource = sources.find((s) => s.id === value);

    return (
        <div className="flex items-center gap-4">
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={open}
                        className="w-[400px] justify-between"
                    >
                        {selectedSource ? (
                            <div className="flex items-center gap-2 truncate">
                                <FileText className="h-4 w-4 shrink-0 opacity-50" />
                                <span className="truncate">{selectedSource.name}</span>
                                {selectedSource.validation_status === "completed" ? (
                                    <Badge variant="secondary" className="bg-green-100 text-green-800 h-5 text-[10px] px-1">Valid</Badge>
                                ) : (
                                    <Badge variant="outline" className="h-5 text-[10px] px-1">{selectedSource.validation_status}</Badge>
                                )}
                            </div>
                        ) : (
                            "Select a dataset source..."
                        )}
                        <span className="sr-only">Toggle source</span>
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[400px] p-0">
                    <Command>
                        <CommandInput placeholder="Search sources..." />
                        <CommandEmpty>No source found.</CommandEmpty>
                        <CommandGroup>
                            {sources.map((source) => (
                                <CommandItem
                                    key={source.id}
                                    value={source.name}
                                    onSelect={() => {
                                        onChange(source.id === value ? undefined : source.id);
                                        setOpen(false);
                                    }}
                                >
                                    <Check
                                        className={cn(
                                            "mr-2 h-4 w-4",
                                            value === source.id ? "opacity-100" : "opacity-0"
                                        )}
                                    />
                                    <div className="flex flex-col">
                                        <span>{source.name}</span>
                                        <span className="text-xs text-muted-foreground">
                                            {source.rows} rows • {source.validation_status}
                                        </span>
                                    </div>
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </Command>
                </PopoverContent>
            </Popover>

            <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
                <DialogTrigger asChild>
                    <Button variant="outline" className="gap-2">
                        <Upload className="h-4 w-4" />
                        Upload New CSV
                    </Button>
                </DialogTrigger>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Upload Build Source</DialogTitle>
                        <DialogDescription>
                            Upload a CSV file containing build information to be used as a dataset.
                        </DialogDescription>
                    </DialogHeader>

                    <form onSubmit={handleSubmit(onUploadSubmit)} className="space-y-4 py-4">
                        <div className="space-y-2">
                            <Label htmlFor="name">Name</Label>
                            <Input id="name" {...register("name", { required: true })} placeholder="My Dataset Source" />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="description">Description (Optional)</Label>
                            <Textarea id="description" {...register("description")} placeholder="Describe this dataset..." />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="file">CSV File</Label>
                            <Input
                                id="file"
                                type="file"
                                accept=".csv"
                                {...register("file", { required: true })}
                            />
                            <p className="text-xs text-muted-foreground">
                                File must be CSV format.
                            </p>
                        </div>

                        <DialogFooter>
                            <Button type="button" variant="ghost" onClick={() => setUploadOpen(false)}>
                                Cancel
                            </Button>
                            <Button type="submit" disabled={uploading}>
                                {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                Upload & Validate
                            </Button>
                        </DialogFooter>
                    </form>
                </DialogContent>
            </Dialog>
        </div>
    );
}
