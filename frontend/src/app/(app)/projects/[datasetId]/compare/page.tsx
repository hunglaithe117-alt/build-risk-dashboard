'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import {
    ArrowLeftRight,
    CheckCircle2,
    FileUp,
    Loader2,
    Minus,
    Plus,
    Upload,
    XCircle
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { Progress } from '@/components/ui/progress';
import { comparisonApi, ComparableDataset, CompareResponse, CompareExternalResponse } from '@/lib/comparison-api';

export default function ComparePage() {
    const params = useParams();
    const datasetId = params?.datasetId as string;
    const { toast } = useToast();

    // State
    const [mode, setMode] = useState<'internal' | 'external'>('internal');
    const [loading, setLoading] = useState(false);
    const [comparing, setComparing] = useState(false);
    const [datasets, setDatasets] = useState<ComparableDataset[]>([]);

    // Internal comparison selections
    const [baseDatasetId, setBaseDatasetId] = useState<string>('');
    const [baseVersionId, setBaseVersionId] = useState<string>('');
    const [targetDatasetId, setTargetDatasetId] = useState<string>('');
    const [targetVersionId, setTargetVersionId] = useState<string>('');

    // External comparison
    const [internalVersionId, setInternalVersionId] = useState<string>('');
    const [externalFile, setExternalFile] = useState<File | null>(null);

    // Results
    const [result, setResult] = useState<CompareResponse | CompareExternalResponse | null>(null);

    // Load comparable datasets
    useEffect(() => {
        loadDatasets();
    }, []);

    // Auto-select current dataset
    useEffect(() => {
        if (datasets.length > 0 && datasetId) {
            setBaseDatasetId(datasetId);
            const currentDataset = datasets.find(d => d.dataset_id === datasetId);
            if (currentDataset?.versions.length > 0) {
                setInternalVersionId(currentDataset.versions[0].version_id);
            }
        }
    }, [datasets, datasetId]);

    const loadDatasets = async () => {
        setLoading(true);
        try {
            const data = await comparisonApi.getComparableDatasets();
            setDatasets(data.datasets);
        } catch (error) {
            toast({ title: 'Failed to load datasets', variant: 'destructive' });
        } finally {
            setLoading(false);
        }
    };

    const handleCompareInternal = async () => {
        if (!baseDatasetId || !baseVersionId || !targetDatasetId || !targetVersionId) {
            toast({ title: 'Please select both versions', variant: 'destructive' });
            return;
        }

        setComparing(true);
        try {
            const response = await comparisonApi.compareInternal({
                base_dataset_id: baseDatasetId,
                base_version_id: baseVersionId,
                target_dataset_id: targetDatasetId,
                target_version_id: targetVersionId,
            });
            setResult(response);
        } catch (error) {
            toast({ title: 'Comparison failed', variant: 'destructive' });
        } finally {
            setComparing(false);
        }
    };

    const handleCompareExternal = async () => {
        if (!internalVersionId || !externalFile) {
            toast({ title: 'Please select version and upload file', variant: 'destructive' });
            return;
        }

        setComparing(true);
        try {
            const response = await comparisonApi.compareExternal(
                datasetId,
                internalVersionId,
                externalFile
            );
            setResult(response);
        } catch (error) {
            toast({ title: 'Comparison failed', variant: 'destructive' });
        } finally {
            setComparing(false);
        }
    };

    const getBaseVersions = () => {
        return datasets.find(d => d.dataset_id === baseDatasetId)?.versions || [];
    };

    const getTargetVersions = () => {
        return datasets.find(d => d.dataset_id === targetDatasetId)?.versions || [];
    };

    const getInternalVersions = () => {
        return datasets.find(d => d.dataset_id === datasetId)?.versions || [];
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-[400px]">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="container mx-auto py-8 px-4 max-w-6xl">
            <div className="mb-8">
                <h1 className="text-3xl font-bold flex items-center gap-3">
                    <ArrowLeftRight className="h-8 w-8" />
                    Dataset Comparison
                </h1>
                <p className="text-muted-foreground mt-2">
                    Compare enriched versions with other datasets or external references.
                </p>
            </div>

            <Tabs value={mode} onValueChange={(v) => { setMode(v as 'internal' | 'external'); setResult(null); }}>
                <TabsList className="grid w-full grid-cols-2 max-w-md mb-6">
                    <TabsTrigger value="internal">Internal Comparison</TabsTrigger>
                    <TabsTrigger value="external">External CSV</TabsTrigger>
                </TabsList>

                {/* Internal Comparison Tab */}
                <TabsContent value="internal" className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Select Versions to Compare</CardTitle>
                            <CardDescription>
                                Compare two versions from the same or different datasets.
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                {/* Base Version */}
                                <div className="space-y-4">
                                    <h3 className="font-semibold text-blue-600">Base Version</h3>
                                    <div className="space-y-2">
                                        <Label>Dataset</Label>
                                        <Select value={baseDatasetId} onValueChange={(v) => { setBaseDatasetId(v); setBaseVersionId(''); }}>
                                            <SelectTrigger><SelectValue placeholder="Select dataset" /></SelectTrigger>
                                            <SelectContent>
                                                {datasets.map(d => (
                                                    <SelectItem key={d.dataset_id} value={d.dataset_id}>
                                                        {d.dataset_name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Version</Label>
                                        <Select value={baseVersionId} onValueChange={setBaseVersionId} disabled={!baseDatasetId}>
                                            <SelectTrigger><SelectValue placeholder="Select version" /></SelectTrigger>
                                            <SelectContent>
                                                {getBaseVersions().map(v => (
                                                    <SelectItem key={v.version_id} value={v.version_id}>
                                                        {v.version_name} ({v.total_rows} rows, {v.feature_count} features)
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                {/* Target Version */}
                                <div className="space-y-4">
                                    <h3 className="font-semibold text-green-600">Target Version</h3>
                                    <div className="space-y-2">
                                        <Label>Dataset</Label>
                                        <Select value={targetDatasetId} onValueChange={(v) => { setTargetDatasetId(v); setTargetVersionId(''); }}>
                                            <SelectTrigger><SelectValue placeholder="Select dataset" /></SelectTrigger>
                                            <SelectContent>
                                                {datasets.map(d => (
                                                    <SelectItem key={d.dataset_id} value={d.dataset_id}>
                                                        {d.dataset_name}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Version</Label>
                                        <Select value={targetVersionId} onValueChange={setTargetVersionId} disabled={!targetDatasetId}>
                                            <SelectTrigger><SelectValue placeholder="Select version" /></SelectTrigger>
                                            <SelectContent>
                                                {getTargetVersions().map(v => (
                                                    <SelectItem key={v.version_id} value={v.version_id}>
                                                        {v.version_name} ({v.total_rows} rows, {v.feature_count} features)
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </div>

                            <div className="mt-6 flex justify-center">
                                <Button onClick={handleCompareInternal} disabled={comparing || !baseVersionId || !targetVersionId}>
                                    {comparing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowLeftRight className="mr-2 h-4 w-4" />}
                                    Compare Versions
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* External Comparison Tab */}
                <TabsContent value="external" className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Compare with External CSV</CardTitle>
                            <CardDescription>
                                Upload a reference dataset (e.g., TravisTorrent original) to compare.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="space-y-2">
                                <Label>Internal Version</Label>
                                <Select value={internalVersionId} onValueChange={setInternalVersionId}>
                                    <SelectTrigger><SelectValue placeholder="Select version to compare" /></SelectTrigger>
                                    <SelectContent>
                                        {getInternalVersions().map(v => (
                                            <SelectItem key={v.version_id} value={v.version_id}>
                                                {v.version_name} ({v.total_rows} rows, {v.feature_count} features)
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="space-y-2">
                                <Label>External CSV File</Label>
                                <div className="border-2 border-dashed rounded-lg p-6 text-center">
                                    <input
                                        type="file"
                                        accept=".csv"
                                        className="hidden"
                                        id="csv-upload"
                                        onChange={(e) => setExternalFile(e.target.files?.[0] || null)}
                                    />
                                    <label htmlFor="csv-upload" className="cursor-pointer">
                                        {externalFile ? (
                                            <div className="flex items-center justify-center gap-2 text-green-600">
                                                <FileUp className="h-5 w-5" />
                                                <span>{externalFile.name}</span>
                                            </div>
                                        ) : (
                                            <div className="text-muted-foreground">
                                                <Upload className="h-8 w-8 mx-auto mb-2" />
                                                <p>Click to upload CSV file</p>
                                            </div>
                                        )}
                                    </label>
                                </div>
                            </div>

                            <div className="flex justify-center">
                                <Button onClick={handleCompareExternal} disabled={comparing || !internalVersionId || !externalFile}>
                                    {comparing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ArrowLeftRight className="mr-2 h-4 w-4" />}
                                    Compare with CSV
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* Results */}
            {result && (
                <div className="mt-8 space-y-6">
                    <h2 className="text-2xl font-bold">Comparison Results</h2>

                    {/* Summary Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm text-blue-600">Base</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-lg font-semibold">{result.base.dataset_name}</p>
                                <p className="text-sm text-muted-foreground">{result.base.version_name}</p>
                                <div className="mt-2 text-sm">
                                    <span>{result.base.total_rows} rows</span>
                                    <span className="mx-2">•</span>
                                    <span>{result.base.total_features} features</span>
                                </div>
                                <Progress value={result.base.completeness_pct} className="mt-2" />
                                <p className="text-xs text-muted-foreground mt-1">{result.base.completeness_pct}% complete</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm text-green-600">Target</CardTitle>
                            </CardHeader>
                            <CardContent>
                                {'target' in result && result.target ? (
                                    <>
                                        <p className="text-lg font-semibold">{result.target.dataset_name}</p>
                                        <p className="text-sm text-muted-foreground">{result.target.version_name}</p>
                                        <div className="mt-2 text-sm">
                                            <span>{result.target.total_rows} rows</span>
                                            <span className="mx-2">•</span>
                                            <span>{result.target.total_features} features</span>
                                        </div>
                                        <Progress value={result.target.completeness_pct} className="mt-2" />
                                        <p className="text-xs text-muted-foreground mt-1">{result.target.completeness_pct}% complete</p>
                                    </>
                                ) : 'external_target' in result && result.external_target ? (
                                    <>
                                        <p className="text-lg font-semibold">{result.external_target.filename}</p>
                                        <p className="text-sm text-muted-foreground">External CSV</p>
                                        <div className="mt-2 text-sm">
                                            <span>{result.external_target.total_rows} rows</span>
                                            <span className="mx-2">•</span>
                                            <span>{result.external_target.total_columns} columns</span>
                                        </div>
                                    </>
                                ) : null}
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm">Quality Diff</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    <div className="flex justify-between">
                                        <span className="text-sm">Completeness</span>
                                        <span className={`font-semibold ${result.quality_comparison.completeness_diff >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                            {result.quality_comparison.completeness_diff >= 0 ? '+' : ''}{result.quality_comparison.completeness_diff.toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-sm">Base Null Rate</span>
                                        <span>{result.quality_comparison.base_avg_null_pct.toFixed(1)}%</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-sm">Target Null Rate</span>
                                        <span>{result.quality_comparison.target_avg_null_pct.toFixed(1)}%</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Feature Comparison */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Feature Comparison</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div>
                                    <h4 className="font-semibold text-sm mb-2 flex items-center gap-2">
                                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                                        Common ({result.feature_comparison.common_features.length})
                                    </h4>
                                    <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                                        {result.feature_comparison.common_features.slice(0, 20).map(f => (
                                            <div key={f} className="bg-green-50 dark:bg-green-900/20 px-2 py-1 rounded">{f}</div>
                                        ))}
                                        {result.feature_comparison.common_features.length > 20 && (
                                            <p className="text-muted-foreground">+{result.feature_comparison.common_features.length - 20} more</p>
                                        )}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="font-semibold text-sm mb-2 flex items-center gap-2">
                                        <Minus className="h-4 w-4 text-blue-600" />
                                        Base Only ({result.feature_comparison.base_only_features.length})
                                    </h4>
                                    <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                                        {result.feature_comparison.base_only_features.slice(0, 20).map(f => (
                                            <div key={f} className="bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded">{f}</div>
                                        ))}
                                        {result.feature_comparison.base_only_features.length > 20 && (
                                            <p className="text-muted-foreground">+{result.feature_comparison.base_only_features.length - 20} more</p>
                                        )}
                                    </div>
                                </div>
                                <div>
                                    <h4 className="font-semibold text-sm mb-2 flex items-center gap-2">
                                        <Plus className="h-4 w-4 text-orange-600" />
                                        Target Only ({result.feature_comparison.target_only_features.length})
                                    </h4>
                                    <div className="max-h-48 overflow-y-auto space-y-1 text-sm">
                                        {result.feature_comparison.target_only_features.slice(0, 20).map(f => (
                                            <div key={f} className="bg-orange-50 dark:bg-orange-900/20 px-2 py-1 rounded">{f}</div>
                                        ))}
                                        {result.feature_comparison.target_only_features.length > 20 && (
                                            <p className="text-muted-foreground">+{result.feature_comparison.target_only_features.length - 20} more</p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Row Overlap (only for internal comparison) */}
                    {'row_overlap' in result && result.row_overlap && (
                        <Card>
                            <CardHeader>
                                <CardTitle>Row Overlap (by commit_sha)</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                                    <div>
                                        <p className="text-2xl font-bold text-blue-600">{result.row_overlap.base_total_rows}</p>
                                        <p className="text-sm text-muted-foreground">Base Rows</p>
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold text-green-600">{result.row_overlap.target_total_rows}</p>
                                        <p className="text-sm text-muted-foreground">Target Rows</p>
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold">{result.row_overlap.overlapping_rows}</p>
                                        <p className="text-sm text-muted-foreground">Overlapping</p>
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold">{result.row_overlap.overlap_pct}%</p>
                                        <p className="text-sm text-muted-foreground">Overlap Rate</p>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>
            )}
        </div>
    );
}
