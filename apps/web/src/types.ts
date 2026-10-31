export interface HealthResponse {
  status: string;
  database: string;
}

export type ProviderCapability = "script" | "image" | "video";

export interface LLMProvider {
  id: number;
  name: string;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  capabilities: ProviderCapability[];
  created_at: string;
  updated_at: string;
}

export interface CreateProviderInput {
  name: string;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  capabilities: ProviderCapability[];
}

export interface ProviderRoute {
  role: ProviderCapability;
  provider_id: number;
}

export type StageStatus = "pending" | "running" | "done" | "failed" | "waiting_confirmation" | "outdated";
export type RetryableStage = "outline" | "script" | "characters" | "storyboard";

export interface ProjectStage {
  stage: string;
  status: StageStatus;
  completed_items: number;
  total_items: number;
  attempt_count: number;
  requires_attention: boolean;
  error: string | null;
}

export interface ProjectSummary {
  id: number;
  title: string;
  source_filename: string;
  source_media_type: string;
  provider_id: number;
  created_at: string;
  stages: ProjectStage[];
  provider_routes: ProviderRoute[];
}

export interface ProjectDetail extends ProjectSummary {
  novel_json: {
    title: string;
    chapters: { index: number; title: string; text: string }[];
  };
}

export interface ProjectStatus {
  project_id: number;
  stages: ProjectStage[];
}

export interface CastMember {
  name: string;
  role: string;
  weight: number;
}

export interface EpisodeBeat {
  episode: number;
  summary: string;
  payoff_type: string;
  payoff_intensity: number;
}

export interface Outline {
  synopsis: string;
  cast: CastMember[];
  episode_beat: EpisodeBeat[];
  asset_list: string[];
}

export interface ActionBeat {
  order: number;
  text: string;
}

export interface ScriptLine {
  order: number;
  character: string;
  emotion: string;
  text: string;
}

export interface Scene {
  index: number;
  heading: string;
  action_beats: ActionBeat[];
  lines: ScriptLine[];
}

export interface Episode {
  episode: number;
  estimated_duration_s: number;
  scenes: Scene[];
}

export interface Script {
  cast: CastMember[];
  episodes: Episode[];
}

export interface CharacterImage {
  id: number;
  label: string;
  status: string;
  path: string | null;
  width: number | null;
  height: number | null;
  format: string | null;
  workflow_id: string | null;
  error: string | null;
}

export interface Character {
  id: number;
  name: string;
  biography: string;
  prompt_zh: string;
  prompt_en: string;
  voice_prompt: string;
  anchor_features: string[];
  anchor_confirmed: boolean;
  images: CharacterImage[];
}

export interface CharacterAsset {
  characters: Character[];
}

export interface LineRef {
  scene: number;
  order: number;
}

export interface KeyframeImage {
  path: string;
  width: number;
  height: number;
  format: string;
  workflow_id: string;
}

export interface Cut {
  index: number;
  duration_s: number;
  characters: string[];
  prompt: string;
  camera: string;
  line_refs: LineRef[];
  scene_ref: string | null;
  keyframe_image: KeyframeImage | null;
}

export interface Segment {
  index: number;
  duration_s: number;
  cuts: Cut[];
}

export interface EpisodeBoard {
  episode: number;
  segments: Segment[];
}

export interface Storyboard {
  episodes: EpisodeBoard[];
}

export type VideoProviderKind = "wan" | "seedance" | "minimax_h3";

export interface VideoProvider {
  id: number;
  name: string;
  kind: VideoProviderKind;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  config_json: Record<string, unknown>;
}

export interface CreateVideoProviderInput {
  name: string;
  kind: VideoProviderKind;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  config_json: Record<string, unknown>;
}

export interface RenderClipProgress {
  index: number;
  status: string;
  attempt_count: number;
  provider_id: number | null;
  clip_path: string | null;
  error: string | null;
}

export interface RenderSegmentProgress {
  index: number;
  status: string;
  completed_cuts: number;
  total_cuts: number;
  cuts: RenderClipProgress[];
}

export interface RenderProgress {
  project_id: number;
  episode: number;
  status: string;
  error: string | null;
  completed_cuts: number;
  total_cuts: number;
  segments: RenderSegmentProgress[];
}

export interface EpisodeExport {
  episode: number;
  status: string;
  burned_path: string;
  clean_path: string;
  srt_path: string;
  vtt_path: string;
  duration_s: number;
  width: number;
  height: number;
}
