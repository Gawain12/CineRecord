use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct AppConfig {
    pub app: AppSettings,
    pub platforms: PlatformConfigs,
    pub cookiecloud: CookieCloudConfig,
    pub cinepersona: CinePersonaConfig,
    pub download_sites_enabled: Vec<String>,
    pub download_sites_custom: Vec<DownloadSiteConfig>,
    pub download_sites_deleted: Vec<String>,
    pub media_server_url: Option<String>,
    pub media_server_api_key: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct CinePersonaConfig {
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub username: Option<String>,
    pub email: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AppSettings {
    pub host: String,
    pub port: u16,
    pub timezone: String,
    pub data_dir: String,
    pub database_url: String,
    pub log_path: String,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 18000,
            timezone: "Asia/Shanghai".to_string(),
            data_dir: "data/v2".to_string(),
            database_url: "sqlite://data/v2/app.db".to_string(),
            log_path: "logs/v2/server.log".to_string(),
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PlatformConfigs {
    pub tmdb: TmdbConfig,
    pub trakt: TraktConfig,
    pub imdb: CookiePlatformConfig,
    pub douban: CookiePlatformConfig,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct CookiePlatformConfig {
    pub user_id: Option<String>,
    pub cookie: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct TmdbConfig {
    pub api_key: Option<String>,
    pub request_token: Option<String>,
    pub session_id: Option<String>,
    pub account_id: Option<String>,
    pub username: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct TraktConfig {
    pub client_id: Option<String>,
    pub client_secret: Option<String>,
    pub access_token: Option<String>,
    pub refresh_token: Option<String>,
    pub token_expires_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct CookieCloudConfig {
    pub host: Option<String>,
    pub uuid: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct DownloadSiteConfig {
    pub label: String,
    pub template: String,
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformDescriptor {
    pub id: String,
    pub name: String,
    pub auth_type: String,
    pub supports_fetch: bool,
    pub supports_sync: bool,
    pub status: PlatformStatus,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PlatformStatus {
    pub config_present: bool,
    pub configured: bool,
    pub last_validated_at: Option<DateTime<Utc>>,
    pub last_fetch_at: Option<DateTime<Utc>>,
    pub token_expires_at: Option<DateTime<Utc>>,
    pub message: Option<String>,
    pub profile: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MovieRecord {
    pub id: String,
    pub platform: String,
    pub title: String,
    pub year: Option<i32>,
    pub rating: Option<f64>,
    pub rated_at: Option<DateTime<Utc>>,
    pub external_id: Option<String>,
    pub source_url: Option<String>,
    #[serde(default)]
    pub identifiers: MovieIdentifiers,
    pub raw_json: serde_json::Value,
}

impl MovieRecord {
    pub fn media_type(&self) -> Option<String> {
        let val = &self.raw_json;
        let keys = ["Type", "type", "Title Type", "media_type", "titleType"];
        let mut type_str = None;
        for key in keys {
            if let Some(v) = val.get(key) {
                if let Some(s) = v.as_str() {
                    type_str = Some(s.to_string());
                    break;
                }
            }
        }

        let value = type_str?;
        let lower = value.to_lowercase();
        if ["tv", "show", "episode"]
            .iter()
            .any(|part| lower.contains(part))
            || (lower.contains("series") && !lower.contains("mini"))
        {
            return Some("tv".to_string());
        }
        Some("movie".to_string())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WishlistRecord {
    pub id: String,
    pub platform: String,
    pub title: String,
    pub year: Option<i32>,
    pub external_id: Option<String>,
    pub source_url: Option<String>,
    #[serde(default)]
    pub identifiers: MovieIdentifiers,
    pub raw_json: serde_json::Value,
    #[serde(default)]
    pub created_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MovieIdentifiers {
    pub imdb: Option<String>,
    pub tmdb: Option<String>,
    pub trakt: Option<String>,
    pub douban: Option<String>,
    pub letterboxd: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct UnifiedSourceEntry {
    pub platform: String,
    pub external_id: Option<String>,
    pub source_url: Option<String>,
    pub rating: Option<f64>,
    pub rated_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct UnifiedMediaItem {
    pub id: String,
    pub title: String,
    pub original_title: Option<String>,
    pub year: Option<i32>,
    pub media_type: Option<String>,
    pub poster_url: Option<String>,
    pub source_url: Option<String>,
    pub identifiers: MovieIdentifiers,
    pub personal_rating: Option<f64>,
    pub rated_at: Option<DateTime<Utc>>,
    pub public_rating: Option<f64>,
    pub public_votes: Option<i64>,
    pub source_platforms: Vec<String>,
    pub sources: Vec<UnifiedSourceEntry>,
    pub library_matched: bool,
    pub library_url: Option<String>,
    pub library_title: Option<String>,
    pub library_year: Option<i32>,
    pub library_media_path: Option<String>,
    pub library_file_name: Option<String>,
    pub directors: Option<String>,
    pub actors: Option<String>,
    pub genres: Option<String>,
    pub country: Option<String>,
    pub duration: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncTask {
    pub id: String,
    pub name: String,
    pub kind: TaskKind,
    pub status: TaskStatus,
    pub payload: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskKind {
    FetchPlatform,
    FetchWishlist,
    ImportLegacy,
    SyncPreview,
    SyncExecute,
    Maintenance,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TaskStatus {
    Pending,
    Running,
    Succeeded,
    Failed,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncRun {
    pub id: String,
    pub source_platform: String,
    pub target_platform: String,
    pub dry_run: bool,
    pub status: TaskStatus,
    pub summary: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppEvent {
    pub event_type: String,
    pub task_id: Option<String>,
    pub timestamp: DateTime<Utc>,
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformValidationResult {
    pub platform: String,
    pub success: bool,
    pub message: String,
    pub profile: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FetchResult {
    pub platform: String,
    pub item_count: usize,
    pub stored_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncPreviewRequest {
    pub source_platform: String,
    pub target_platform: String,
    #[serde(default = "default_recent_limit")]
    pub recent_limit: usize,
    #[serde(default = "default_only_new")]
    pub only_new: bool,
    #[serde(default)]
    pub overwrite: bool,
    #[serde(default)]
    pub default_rating: Option<f64>,
    #[serde(default)]
    pub refresh_before_sync: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncPreviewItem {
    pub title: String,
    pub year: Option<i32>,
    pub source_platform: String,
    pub target_platform: String,
    pub source_rating: Option<f64>,
    pub target_existing_rating: Option<f64>,
    pub source_url: Option<String>,
    pub target_linking_id: Option<String>,
    pub identifiers: MovieIdentifiers,
    pub action: String,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncPreviewResult {
    pub direction: String,
    pub source_count: usize,
    pub target_count: usize,
    pub preview_count: usize,
    pub items: Vec<SyncPreviewItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncExecuteRequest {
    pub source_platform: String,
    pub target_platform: String,
    #[serde(default = "default_recent_limit")]
    pub recent_limit: usize,
    #[serde(default = "default_only_new")]
    pub only_new: bool,
    #[serde(default)]
    pub overwrite: bool,
    #[serde(default)]
    pub default_rating: Option<f64>,
    #[serde(default)]
    pub refresh_before_sync: bool,
    #[serde(default, deserialize_with = "deserialize_null_tolerant_vec")]
    pub selected_target_ids: Vec<String>,
}

fn deserialize_null_tolerant_vec<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let opt_vec: Option<Vec<Option<String>>> = Option::deserialize(deserializer)?;
    Ok(opt_vec
        .unwrap_or_default()
        .into_iter()
        .flatten()
        .filter(|s| !s.trim().is_empty())
        .collect())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncExecutionItem {
    pub title: String,
    pub year: Option<i32>,
    pub source_rating: Option<f64>,
    pub source_url: Option<String>,
    pub target_linking_id: Option<String>,
    pub target_url: Option<String>,
    pub status: String,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncExecuteResult {
    pub direction: String,
    pub success_count: usize,
    pub failed_count: usize,
    pub skipped_count: usize,
    pub items: Vec<SyncExecutionItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScheduledTask {
    pub id: String,
    pub name: String,
    pub source_platform: String,
    pub target_platform: String,
    pub schedule: String,
    #[serde(default = "default_recent_limit")]
    pub recent_limit: usize,
    #[serde(default = "default_only_new")]
    pub only_new: bool,
    #[serde(default)]
    pub overwrite: bool,
    #[serde(default)]
    pub default_rating: Option<f64>,
    #[serde(default)]
    pub paused: bool,
    #[serde(default)]
    pub running: bool,
    pub last_run_at: Option<DateTime<Utc>>,
    pub next_run_at: Option<DateTime<Utc>>,
    pub last_status_message: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScheduledTaskLog {
    pub id: String,
    pub task_id: Option<String>,
    pub task_name: String,
    pub source_platform: Option<String>,
    pub target_platform: Option<String>,
    pub log_type: String,
    pub message: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraktDeviceCode {
    pub device_code: String,
    pub user_code: String,
    pub verification_url: String,
    pub expires_in: i64,
    pub interval: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraktDevicePollResult {
    pub status: String,
    pub access_token: Option<String>,
    pub refresh_token: Option<String>,
    pub token_expires: Option<DateTime<Utc>>,
    pub message: Option<String>,
    pub profile: Option<serde_json::Value>,
}

fn default_recent_limit() -> usize {
    100
}

fn default_only_new() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MediaServerItem {
    pub title: String,
    pub year: Option<i32>,
    pub imdb_id: Option<String>,
    pub tmdb_id: Option<String>,
    pub library_url: Option<String>,
    pub media_path: Option<String>,
    pub file_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformDiffItem {
    pub title: String,
    pub year: Option<i32>,
    pub category: String, // "missing" | "mismatch" | "synced"
    pub source_platform: String,
    pub source_rating: Option<f64>,
    pub source_rated_at: Option<DateTime<Utc>>,
    pub source_url: Option<String>,
    pub target_platform: String,
    pub target_rating: Option<f64>,
    pub target_rated_at: Option<DateTime<Utc>>,
    pub target_url: Option<String>,
    pub identifiers: MovieIdentifiers,
    pub target_linking_id: Option<String>,
    pub poster_url: Option<String>,
    pub syncable: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PlatformDiffResult {
    pub source_platform: String,
    pub target_platform: String,
    pub total_source: usize,
    pub total_target: usize,
    pub missing_count: usize,
    pub mismatch_count: usize,
    pub synced_count: usize,
    pub items: Vec<PlatformDiffItem>,
}

