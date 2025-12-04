// Custom Dataset Builder Types

export interface FeatureDefinition {
  id: string;  // MongoDB ObjectId
  slug: string;  // Unique name like 'tr_log_tests_run_sum'
  name: string;  // Display name
  description: string;
  category: string;
  data_type: string;
  is_ml_feature: boolean;
  dependencies: string[];  // List of feature IDs
  extractor_node: string;
  requires_clone: boolean;
  requires_log: boolean;
}

export interface FeatureCategory {
  category: string;
  display_name: string;
  features: FeatureDefinition[];
}

export interface AvailableFeaturesResponse {
  categories: FeatureCategory[];
  total_features: number;
  ml_features_count: number;
  default_features: string[];  // Features always included (not shown in UI)
  features_requiring_source_languages: string[];  // Features that need source_languages
}

export interface ResolvedDependenciesResponse {
  selected_feature_ids: string[];
  resolved_feature_ids: string[];
  resolved_feature_names: string[];
  required_nodes: string[];
  requires_clone: boolean;
  requires_log_collection: boolean;
  requires_source_languages: boolean;  // Whether source_languages must be set
  features_needing_source_languages: string[];  // Which features need it
}

export interface DatasetJobCreateRequest {
  repo_url: string;
  max_builds?: number | null;
  feature_ids: string[];  // Use feature IDs instead of names
  source_languages?: string[] | null;  // Required when selecting features that need language info
}

export interface DatasetJobCreatedResponse {
  job_id: string;
  message: string;
  status: string;
  estimated_time_minutes?: number | null;
}

export type DatasetJobStatus = 
  | "pending"
  | "fetching_runs"
  | "processing"
  | "exporting"
  | "completed"
  | "failed"
  | "cancelled";

export interface DatasetJob {
  id: string;
  user_id: string;
  repo_url: string;
  max_builds?: number | null;
  selected_features: string[];
  resolved_features: string[];
  required_nodes: string[];
  status: DatasetJobStatus;
  current_phase: string;
  total_builds: number;
  processed_builds: number;
  failed_builds: number;
  progress_percent: number;
  output_file_path?: string | null;
  output_file_size?: number | null;
  output_row_count?: number | null;
  download_count: number;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
}

export interface DatasetJobListResponse {
  items: DatasetJob[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface DatasetStats {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  pending_jobs: number;
  processing_jobs: number;
  total_rows_generated: number;
  total_downloads: number;
}
