use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::OnceLock,
};

use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use cinerecord_core::{
    AppConfig, MovieIdentifiers, MovieRecord, PlatformDescriptor, PlatformStatus, ScheduledTask,
    ScheduledTaskLog, SyncTask, TaskKind, TaskStatus, UnifiedMediaItem, UnifiedSourceEntry,
    WishlistRecord,
};
use serde::{Deserialize, Serialize};
use sqlx::{
    ConnectOptions, Row, SqlitePool,
    sqlite::{SqliteConnectOptions, SqlitePoolOptions},
};
use tokio::fs;

static DOUBAN_IMDB_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();
const LIBRARY_PLATFORMS: [&str; 5] = ["douban", "imdb", "trakt", "letterboxd", "tmdb"];

#[derive(Debug, Clone)]
pub struct StoragePaths {
    pub root: PathBuf,
    pub config_path: PathBuf,
    pub data_dir: PathBuf,
    pub platforms_dir: PathBuf,
    pub exports_dir: PathBuf,
    pub backups_dir: PathBuf,
    pub db_path: PathBuf,
    pub log_path: PathBuf,
}

impl StoragePaths {
    pub fn from_repo_root(root: impl AsRef<Path>) -> Self {
        let root = root.as_ref().to_path_buf();
        let config_path = root.join("config").join("v2").join("config.toml");
        let data_dir = root.join("data").join("v2");
        let platforms_dir = data_dir.join("platforms");
        let exports_dir = data_dir.join("exports");
        let backups_dir = data_dir.join("backups");
        let db_path = data_dir.join("app.db");
        let log_path = root.join("logs").join("v2").join("server.log");
        Self {
            root,
            config_path,
            data_dir,
            platforms_dir,
            exports_dir,
            backups_dir,
            db_path,
            log_path,
        }
    }

    pub async fn ensure_dirs(&self) -> Result<()> {
        fs::create_dir_all(self.config_path.parent().context("config dir missing")?).await?;
        fs::create_dir_all(&self.data_dir).await?;
        fs::create_dir_all(&self.platforms_dir).await?;
        fs::create_dir_all(&self.exports_dir).await?;
        fs::create_dir_all(&self.backups_dir).await?;
        fs::create_dir_all(self.log_path.parent().context("log dir missing")?).await?;
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriendBackup {
    pub id: String,
    pub platform: String,
    pub user_id: String,
    pub watched: Vec<MovieRecord>,
    pub wishlist: Vec<WishlistRecord>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriendBackupSummary {
    pub id: String,
    pub platform: String,
    pub user_id: String,
    pub watched_count: usize,
    pub wishlist_count: usize,
    pub created_at: DateTime<Utc>,
}

impl From<&FriendBackup> for FriendBackupSummary {
    fn from(value: &FriendBackup) -> Self {
        Self {
            id: value.id.clone(),
            platform: value.platform.clone(),
            user_id: value.user_id.clone(),
            watched_count: value.watched.len(),
            wishlist_count: value.wishlist.len(),
            created_at: value.created_at,
        }
    }
}

pub async fn save_friend_backup(paths: &StoragePaths, backup: &FriendBackup) -> Result<()> {
    paths.ensure_dirs().await?;
    validate_backup_id(&backup.id)?;
    let content = serde_json::to_vec_pretty(backup)?;
    fs::write(
        paths.backups_dir.join(format!("{}.json", backup.id)),
        content,
    )
    .await?;
    Ok(())
}

pub async fn list_friend_backups(paths: &StoragePaths) -> Result<Vec<FriendBackupSummary>> {
    paths.ensure_dirs().await?;
    let mut entries = fs::read_dir(&paths.backups_dir).await?;
    let mut backups = Vec::new();
    while let Some(entry) = entries.next_entry().await? {
        if entry.path().extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let content = fs::read(entry.path()).await?;
        if let Ok(backup) = serde_json::from_slice::<FriendBackup>(&content) {
            backups.push(FriendBackupSummary::from(&backup));
        }
    }
    backups.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    Ok(backups)
}

pub async fn get_friend_backup(
    paths: &StoragePaths,
    backup_id: &str,
) -> Result<Option<FriendBackup>> {
    validate_backup_id(backup_id)?;
    let path = paths.backups_dir.join(format!("{backup_id}.json"));
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read(path).await?;
    Ok(Some(serde_json::from_slice(&content)?))
}

pub async fn delete_friend_backup(paths: &StoragePaths, backup_id: &str) -> Result<bool> {
    validate_backup_id(backup_id)?;
    let path = paths.backups_dir.join(format!("{backup_id}.json"));
    if !path.exists() {
        return Ok(false);
    }
    fs::remove_file(path).await?;
    Ok(true)
}

fn validate_backup_id(backup_id: &str) -> Result<()> {
    if backup_id.is_empty()
        || !backup_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-')
    {
        anyhow::bail!("invalid backup id");
    }
    Ok(())
}

pub async fn load_or_init_config(paths: &StoragePaths) -> Result<AppConfig> {
    paths.ensure_dirs().await?;
    if !paths.config_path.exists() {
        let mut default_config = AppConfig::default();
        hydrate_legacy_platform_auth(paths, &mut default_config).await?;
        hydrate_legacy_download_sites(paths, &mut default_config).await?;
        save_config(paths, &default_config).await?;
        return Ok(default_config);
    }

    let content = fs::read_to_string(&paths.config_path)
        .await
        .with_context(|| format!("failed reading {}", paths.config_path.display()))?;
    let mut config: AppConfig = toml::from_str(&content)?;
    hydrate_legacy_platform_auth(paths, &mut config).await?;
    hydrate_legacy_download_sites(paths, &mut config).await?;
    Ok(config)
}

pub async fn save_config(paths: &StoragePaths, config: &AppConfig) -> Result<()> {
    let content = toml::to_string_pretty(config)?;
    fs::write(&paths.config_path, content).await?;
    Ok(())
}

async fn hydrate_legacy_download_sites(paths: &StoragePaths, config: &mut AppConfig) -> Result<()> {
    if !config.download_sites_enabled.is_empty()
        || !config.download_sites_custom.is_empty()
        || !config.download_sites_deleted.is_empty()
    {
        return Ok(());
    }
    let legacy_path = paths.root.join("config").join("config.json");
    if !legacy_path.exists() {
        return Ok(());
    }
    let content = fs::read_to_string(&legacy_path).await?;
    let value: serde_json::Value = serde_json::from_str(&content)?;
    config.download_sites_enabled = value
        .get("download_sites_enabled")
        .and_then(|items| items.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(ToOwned::to_owned))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    config.download_sites_deleted = value
        .get("download_sites_deleted")
        .and_then(|items| items.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(ToOwned::to_owned))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    config.download_sites_custom = value
        .get("download_sites_custom")
        .and_then(|items| items.as_array())
        .map(|items| {
            items
                .iter()
                .filter_map(|item| serde_json::from_value(item.clone()).ok())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if !config.download_sites_enabled.is_empty()
        || !config.download_sites_custom.is_empty()
        || !config.download_sites_deleted.is_empty()
    {
        save_config(paths, config).await?;
    }
    Ok(())
}

async fn hydrate_legacy_platform_auth(paths: &StoragePaths, config: &mut AppConfig) -> Result<()> {
    let legacy_path = paths.root.join("config").join("config.json");
    if !legacy_path.exists() {
        return Ok(());
    }

    let content = fs::read_to_string(&legacy_path).await?;
    let value: serde_json::Value = serde_json::from_str(&content)?;
    let mut changed = false;

    if config
        .media_server_url
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(url) = value
            .get("media_server_url")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.media_server_url = Some(url.to_string());
            changed = true;
        }
    }
    if config
        .media_server_api_key
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(key) = value
            .get("media_server_api_key")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.media_server_api_key = Some(key.to_string());
            changed = true;
        }
    }

    if config
        .platforms
        .tmdb
        .api_key
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(api_key) = value
            .get("tmdb_api_key")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.tmdb.api_key = Some(api_key.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .tmdb
        .session_id
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(session_id) = value
            .get("tmdb_session_id")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.tmdb.session_id = Some(session_id.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .tmdb
        .request_token
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(request_token) = value
            .get("tmdb_request_token")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.tmdb.request_token = Some(request_token.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .tmdb
        .account_id
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(account_id) = value
            .get("tmdb_account_id")
            .and_then(|item| item.as_i64())
            .map(|item| item.to_string())
            .or_else(|| {
                value
                    .get("tmdb_account_id")
                    .and_then(|item| item.as_str())
                    .map(ToOwned::to_owned)
            })
        {
            config.platforms.tmdb.account_id = Some(account_id);
            changed = true;
        }
    }
    if config
        .platforms
        .tmdb
        .username
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(username) = value
            .get("tmdb_username")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.tmdb.username = Some(username.to_string());
            changed = true;
        }
    }

    if config
        .platforms
        .trakt
        .client_id
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(client_id) = value
            .get("trakt_client_id")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.trakt.client_id = Some(client_id.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .trakt
        .client_secret
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(client_secret) = value
            .get("trakt_client_secret")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.trakt.client_secret = Some(client_secret.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .trakt
        .access_token
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(access_token) = value
            .get("trakt_access_token")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.trakt.access_token = Some(access_token.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .trakt
        .refresh_token
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(refresh_token) = value
            .get("trakt_refresh_token")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.trakt.refresh_token = Some(refresh_token.to_string());
            changed = true;
        }
    }
    if config.platforms.trakt.token_expires_at.is_none() {
        if let Some(expires_at) = value
            .get("trakt_token_expires")
            .and_then(|item| item.as_str())
            .and_then(|item| chrono::DateTime::parse_from_rfc3339(item).ok())
            .map(|item| item.with_timezone(&Utc))
        {
            config.platforms.trakt.token_expires_at = Some(expires_at);
            changed = true;
        }
    }

    if config
        .platforms
        .douban
        .user_id
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(user_id) = value
            .get("douban_user_id")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.douban.user_id = Some(user_id.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .douban
        .cookie
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(cookie) = value
            .get("douban_cookie")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.douban.cookie = Some(cookie.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .imdb
        .user_id
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(user_id) = value
            .get("imdb_user_id")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.imdb.user_id = Some(user_id.to_string());
            changed = true;
        }
    }
    if config
        .platforms
        .imdb
        .cookie
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(cookie) = value
            .get("imdb_cookie")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.platforms.imdb.cookie = Some(cookie.to_string());
            changed = true;
        }
    }

    if config
        .cookiecloud
        .host
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(host) = value
            .get("cookiecloud_host")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cookiecloud.host = Some(host.to_string());
            changed = true;
        }
    }
    if config
        .cookiecloud
        .uuid
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(uuid) = value
            .get("cookiecloud_uuid")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cookiecloud.uuid = Some(uuid.to_string());
            changed = true;
        }
    }
    if config
        .cookiecloud
        .password
        .as_deref()
        .is_none_or(|value| value.trim().is_empty())
    {
        if let Some(password) = value
            .get("cookiecloud_password")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cookiecloud.password = Some(password.to_string());
            changed = true;
        }
    }
    if config
        .cinepersona
        .base_url
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(base_url) = value
            .get("cinepersona_base_url")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cinepersona.base_url = Some(base_url.to_string());
            changed = true;
        }
    }
    if config
        .cinepersona
        .api_key
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(api_key) = value
            .get("cinepersona_api_key")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cinepersona.api_key = Some(api_key.to_string());
            changed = true;
        }
    }
    if config
        .cinepersona
        .username
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(username) = value
            .get("cinepersona_username")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cinepersona.username = Some(username.to_string());
            changed = true;
        }
    }
    if config
        .cinepersona
        .email
        .as_deref()
        .is_none_or(|v| v.trim().is_empty())
    {
        if let Some(email) = value
            .get("cinepersona_email")
            .and_then(|item| item.as_str())
            .filter(|item| !item.trim().is_empty())
        {
            config.cinepersona.email = Some(email.to_string());
            changed = true;
        }
    }

    if changed {
        save_config(paths, config).await?;
    }
    Ok(())
}

pub async fn connect(paths: &StoragePaths) -> Result<SqlitePool> {
    paths.ensure_dirs().await?;
    let options = SqliteConnectOptions::new()
        .filename(&paths.db_path)
        .create_if_missing(true);
    let pool = SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(options.disable_statement_logging())
        .await?;
    init_schema(&pool).await?;
    recover_incomplete_tasks(&pool).await?;
    Ok(pool)
}

async fn init_schema(pool: &SqlitePool) -> Result<()> {
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS library_items (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            rating REAL,
            rated_at TEXT,
            external_id TEXT,
            source_url TEXT,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS platform_state (
            platform TEXT PRIMARY KEY,
            configured INTEGER NOT NULL DEFAULT 0,
            last_validated_at TEXT,
            message TEXT,
            profile_json TEXT
        );
        "#,
    )
    .execute(pool)
    .await?;

    ensure_platform_state_profile_column(pool).await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS wishlist_items (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            external_id TEXT,
            source_url TEXT,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_platform TEXT NOT NULL,
            target_platform TEXT NOT NULL,
            schedule TEXT NOT NULL,
            recent_limit INTEGER NOT NULL DEFAULT 100,
            only_new INTEGER NOT NULL DEFAULT 1,
            overwrite INTEGER NOT NULL DEFAULT 0,
            default_rating REAL,
            paused INTEGER NOT NULL DEFAULT 0,
            running INTEGER NOT NULL DEFAULT 0,
            last_run_at TEXT,
            next_run_at TEXT,
            last_status_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS scheduled_task_logs (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            task_name TEXT NOT NULL,
            source_platform TEXT,
            target_platform TEXT,
            log_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    Ok(())
}

async fn recover_incomplete_tasks(pool: &SqlitePool) -> Result<()> {
    sqlx::query(
        "UPDATE tasks SET status = 'failed', payload_json = json_object('error', 'Recovered after previous process stopped'), updated_at = ?1 WHERE status = 'running'",
    )
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    sqlx::query(
        "UPDATE scheduled_tasks SET running = 0, last_status_message = COALESCE(last_status_message, '上次运行被中断，已在启动时恢复'), updated_at = ?1 WHERE running = 1",
    )
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_platforms(
    config: &AppConfig,
    pool: &SqlitePool,
) -> Result<Vec<PlatformDescriptor>> {
    let states = sqlx::query(
        "SELECT platform, configured, last_validated_at, message, profile_json FROM platform_state",
    )
    .fetch_all(pool)
    .await?;

    let mut state_map = std::collections::HashMap::new();
    for row in states {
        let platform: String = row.get("platform");
        let configured_num: i64 = row.get("configured");
        let last_validated_at: Option<String> = row.get("last_validated_at");
        let message: Option<String> = row.get("message");
        let profile_json: Option<String> = row.get("profile_json");
        state_map.insert(
            platform,
            PlatformStatus {
                config_present: false,
                configured: configured_num == 1,
                last_validated_at: last_validated_at
                    .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
                    .map(|dt| dt.with_timezone(&Utc)),
                message,
                profile: profile_json.and_then(|value| serde_json::from_str(&value).ok()),
            },
        );
    }

    let descriptors = vec![
        (
            "tmdb",
            "TMDB",
            "api_key",
            config.platforms.tmdb.api_key.is_some(),
            true,
            true,
        ),
        (
            "trakt",
            "Trakt",
            "oauth",
            config.platforms.trakt.client_id.is_some(),
            true,
            true,
        ),
        (
            "imdb",
            "IMDb",
            "cookie",
            config.platforms.imdb.cookie.is_some(),
            true,
            true,
        ),
        (
            "douban",
            "Douban",
            "cookie",
            config.platforms.douban.cookie.is_some() || config.platforms.douban.user_id.is_some(),
            true,
            true,
        ),
        ("letterboxd", "Letterboxd", "csv", true, true, false),
        (
            "cinepersona",
            "CinePersona",
            "api_key",
            config.cinepersona.api_key.is_some(),
            true,
            true,
        ),
    ];

    Ok(descriptors
        .into_iter()
        .map(
            |(id, name, auth_type, config_present, supports_fetch, supports_sync)| {
                let persisted = state_map.remove(id);
                let status = match persisted {
                    Some(state) => PlatformStatus {
                        config_present,
                        configured: config_present && state.configured,
                        last_validated_at: state.last_validated_at,
                        message: if state
                            .message
                            .as_deref()
                            .is_some_and(|message| !message.trim().is_empty())
                        {
                            state.message
                        } else {
                            None
                        },
                        profile: if config_present { state.profile } else { None },
                    },
                    None => PlatformStatus {
                        config_present,
                        configured: id == "letterboxd" && config_present,
                        last_validated_at: None,
                        message: None,
                        profile: None,
                    },
                };
                PlatformDescriptor {
                    id: id.to_string(),
                    name: name.to_string(),
                    auth_type: auth_type.to_string(),
                    supports_fetch,
                    supports_sync,
                    status,
                }
            },
        )
        .collect())
}

pub async fn upsert_platform_state(
    pool: &SqlitePool,
    platform: &str,
    configured: bool,
    message: Option<&str>,
    profile: Option<&serde_json::Value>,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO platform_state (platform, configured, last_validated_at, message, profile_json)
        VALUES (?1, ?2, ?3, ?4, ?5)
        ON CONFLICT(platform) DO UPDATE SET
            configured = excluded.configured,
            last_validated_at = excluded.last_validated_at,
            message = excluded.message,
            profile_json = excluded.profile_json
        "#,
    )
    .bind(platform)
    .bind(if configured { 1_i64 } else { 0_i64 })
    .bind(Utc::now().to_rfc3339())
    .bind(message)
    .bind(profile.map(|value| value.to_string()))
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn update_platform_local_counts(
    pool: &SqlitePool,
    platform: &str,
    library_count: Option<usize>,
    wishlist_count: Option<usize>,
) -> Result<()> {
    let profile_json = sqlx::query_scalar::<_, Option<String>>(
        "SELECT profile_json FROM platform_state WHERE platform = ?1",
    )
    .bind(platform)
    .fetch_optional(pool)
    .await?
    .flatten();

    let mut profile = profile_json
        .and_then(|value| serde_json::from_str::<serde_json::Value>(&value).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    let Some(profile) = profile.as_object_mut() else {
        return Ok(());
    };

    if let Some(count) = library_count {
        let keys: &[&str] = match platform {
            "douban" => &["watched", "watched_total"],
            "imdb" => &["ratings", "ratings_total"],
            "trakt" => &["watched"],
            "tmdb" => &["ratings", "rated_total"],
            "letterboxd" => &["watched"],
            _ => &[],
        };
        for key in keys {
            profile.insert((*key).to_string(), serde_json::json!(count));
        }
    }

    if let Some(count) = wishlist_count {
        let keys: &[&str] = if platform == "douban" {
            &["wish", "wish_total"]
        } else {
            &["watchlist", "watchlist_total"]
        };
        for key in keys {
            profile.insert((*key).to_string(), serde_json::json!(count));
        }
    }

    sqlx::query("UPDATE platform_state SET profile_json = ?1 WHERE platform = ?2")
        .bind(serde_json::Value::Object(profile.clone()).to_string())
        .bind(platform)
        .execute(pool)
        .await?;
    Ok(())
}

async fn ensure_platform_state_profile_column(pool: &SqlitePool) -> Result<()> {
    let rows = sqlx::query("PRAGMA table_info(platform_state)")
        .fetch_all(pool)
        .await?;
    let has_profile_json = rows
        .iter()
        .filter_map(|row| row.try_get::<String, _>("name").ok())
        .any(|name| name == "profile_json");
    if !has_profile_json {
        sqlx::query("ALTER TABLE platform_state ADD COLUMN profile_json TEXT")
            .execute(pool)
            .await?;
    }
    Ok(())
}

pub async fn insert_task(pool: &SqlitePool, task: &SyncTask) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO tasks (id, name, kind, status, payload_json, created_at, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
        "#,
    )
    .bind(&task.id)
    .bind(&task.name)
    .bind(task_kind_to_str(&task.kind))
    .bind(task_status_to_str(&task.status))
    .bind(task.payload.to_string())
    .bind(task.created_at.to_rfc3339())
    .bind(task.updated_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_tasks(pool: &SqlitePool) -> Result<Vec<SyncTask>> {
    let rows = sqlx::query("SELECT id, name, kind, status, payload_json, created_at, updated_at FROM tasks ORDER BY updated_at DESC")
        .fetch_all(pool)
        .await?;
    rows.into_iter().map(task_from_row).collect()
}

pub async fn get_task(pool: &SqlitePool, task_id: &str) -> Result<Option<SyncTask>> {
    let row = sqlx::query("SELECT id, name, kind, status, payload_json, created_at, updated_at FROM tasks WHERE id = ?1")
        .bind(task_id)
        .fetch_optional(pool)
        .await?;
    row.map(task_from_row).transpose()
}

pub async fn update_task_status(
    pool: &SqlitePool,
    task_id: &str,
    status: TaskStatus,
    payload: serde_json::Value,
) -> Result<()> {
    sqlx::query("UPDATE tasks SET status = ?2, payload_json = ?3, updated_at = ?4 WHERE id = ?1")
        .bind(task_id)
        .bind(task_status_to_str(&status))
        .bind(payload.to_string())
        .bind(Utc::now().to_rfc3339())
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn delete_task(pool: &SqlitePool, task_id: &str) -> Result<()> {
    sqlx::query("DELETE FROM tasks WHERE id = ?1")
        .bind(task_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn replace_library_items(
    pool: &SqlitePool,
    platform: &str,
    items: &[MovieRecord],
) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query("DELETE FROM library_items WHERE platform = ?1")
        .bind(platform)
        .execute(&mut *tx)
        .await?;

    for item in items {
        sqlx::query(
            r#"
            INSERT INTO library_items (id, platform, title, year, rating, rated_at, external_id, source_url, raw_json)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            "#,
        )
        .bind(&item.id)
        .bind(&item.platform)
        .bind(&item.title)
        .bind(item.year)
        .bind(item.rating)
        .bind(item.rated_at.map(|dt| dt.to_rfc3339()))
        .bind(&item.external_id)
        .bind(&item.source_url)
        .bind(item.raw_json.to_string())
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;
    Ok(())
}

pub async fn replace_wishlist_items(
    pool: &SqlitePool,
    platform: &str,
    items: &[WishlistRecord],
) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query("DELETE FROM wishlist_items WHERE platform = ?1")
        .bind(platform)
        .execute(&mut *tx)
        .await?;

    for item in items {
        sqlx::query(
            r#"
            INSERT INTO wishlist_items (id, platform, title, year, external_id, source_url, raw_json)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
            "#,
        )
        .bind(&item.id)
        .bind(&item.platform)
        .bind(&item.title)
        .bind(item.year)
        .bind(&item.external_id)
        .bind(&item.source_url)
        .bind(item.raw_json.to_string())
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;
    Ok(())
}

pub async fn list_library_items(
    pool: &SqlitePool,
    platform: Option<&str>,
) -> Result<Vec<MovieRecord>> {
    list_library_items_paginated(pool, platform, None, None).await
}

pub async fn list_library_items_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<MovieRecord>> {
    let limit = limit.unwrap_or(10_000);
    let offset = offset.unwrap_or(0);
    let rows = if let Some(platform) = platform {
        sqlx::query(
            "SELECT id, platform, title, year, rating, rated_at, external_id, source_url, raw_json FROM library_items WHERE platform = ?1 ORDER BY title ASC LIMIT ?2 OFFSET ?3",
        )
        .bind(platform)
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT id, platform, title, year, rating, rated_at, external_id, source_url, raw_json FROM library_items ORDER BY platform ASC, title ASC LIMIT ?1 OFFSET ?2",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    };

    rows.into_iter().map(movie_from_row).collect()
}

pub async fn count_library_items(pool: &SqlitePool, platform: Option<&str>) -> Result<i64> {
    let row = if let Some(platform) = platform {
        sqlx::query("SELECT COUNT(*) AS count FROM library_items WHERE platform = ?1")
            .bind(platform)
            .fetch_one(pool)
            .await?
    } else {
        sqlx::query("SELECT COUNT(*) AS count FROM library_items")
            .fetch_one(pool)
            .await?
    };
    Ok(row.get("count"))
}

pub async fn list_wishlist_items(
    pool: &SqlitePool,
    platform: Option<&str>,
) -> Result<Vec<WishlistRecord>> {
    list_wishlist_items_paginated(pool, platform, None, None).await
}

pub async fn list_wishlist_items_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<WishlistRecord>> {
    let limit = limit.unwrap_or(10_000);
    let offset = offset.unwrap_or(0);
    let rows = if let Some(platform) = platform {
        sqlx::query(
            "SELECT id, platform, title, year, external_id, source_url, raw_json, created_at FROM wishlist_items WHERE platform = ?1 ORDER BY created_at DESC LIMIT ?2 OFFSET ?3",
        )
        .bind(platform)
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT id, platform, title, year, external_id, source_url, raw_json, created_at FROM wishlist_items ORDER BY created_at DESC LIMIT ?1 OFFSET ?2",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    };

    rows.into_iter().map(wishlist_from_row).collect()
}

pub async fn count_wishlist_items(pool: &SqlitePool, platform: Option<&str>) -> Result<i64> {
    let row = if let Some(platform) = platform {
        sqlx::query("SELECT COUNT(*) AS count FROM wishlist_items WHERE platform = ?1")
            .bind(platform)
            .fetch_one(pool)
            .await?
    } else {
        sqlx::query("SELECT COUNT(*) AS count FROM wishlist_items")
            .fetch_one(pool)
            .await?
    };
    Ok(row.get("count"))
}

fn filter_by_search(items: Vec<UnifiedMediaItem>, search: Option<&str>) -> Vec<UnifiedMediaItem> {
    let Some(q) = search else {
        return items;
    };
    if q.trim().is_empty() {
        return items;
    }
    let q_lower = q.to_lowercase();
    items
        .into_iter()
        .filter(|item| {
            item.title.to_lowercase().contains(&q_lower)
                || item
                    .original_title
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
                || item
                    .directors
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
                || item
                    .actors
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
        })
        .collect()
}

pub async fn list_library_items_aggregated_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let mut items = aggregate_library_records(list_library_items(pool, platform).await?);
    items = filter_by_search(items, search);
    sort_unified_items(&mut items, true);
    Ok(apply_paging(items, limit, offset))
}

pub async fn count_library_groups(
    pool: &SqlitePool,
    platform: Option<&str>,
    search: Option<&str>,
) -> Result<i64> {
    let items = aggregate_library_records(list_library_items(pool, platform).await?);
    let items = filter_by_search(items, search);
    Ok(items.len() as i64)
}

pub async fn list_library_items_view_paginated(
    pool: &SqlitePool,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let mut items = filter_library_view_items(
        aggregate_library_records(list_library_items(pool, None).await?),
        platform_filter,
        selected_platforms,
    );
    items = filter_by_search(items, search);
    sort_unified_items(&mut items, true);
    Ok(apply_paging(items, limit, offset))
}

pub async fn count_library_view_groups(
    pool: &SqlitePool,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
    search: Option<&str>,
) -> Result<i64> {
    let items = filter_library_view_items(
        aggregate_library_records(list_library_items(pool, None).await?),
        platform_filter,
        selected_platforms,
    );
    let items = filter_by_search(items, search);
    Ok(items.len() as i64)
}

pub async fn library_view_counts(
    pool: &SqlitePool,
    selected_platforms: &[String],
) -> Result<HashMap<String, i64>> {
    let items = aggregate_library_records(list_library_items(pool, None).await?);
    let selected = normalized_selected_platforms(selected_platforms);
    let show_union = selected.is_empty();
    let mut counts = HashMap::new();
    let shared_count = if show_union {
        items.len()
    } else {
        items
            .iter()
            .filter(|item| has_all_selected_platforms(item, &selected))
            .count()
    };
    counts.insert("shared".to_string(), shared_count as i64);

    for platform in LIBRARY_PLATFORMS {
        let count = items
            .iter()
            .filter(|item| {
                item.source_platforms
                    .iter()
                    .any(|source| source == platform)
            })
            .filter(|item| show_union || !has_all_selected_platforms(item, &selected))
            .count();
        counts.insert(platform.to_string(), count as i64);
    }
    Ok(counts)
}

pub async fn list_wishlist_items_aggregated_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    media_server_items: Option<&[cinerecord_core::MediaServerItem]>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let library = aggregate_library_records(list_library_items(pool, None).await?);
    let mut items = aggregate_wishlist_records(
        list_wishlist_items(pool, platform).await?,
        &library,
        media_server_items,
    );
    items = filter_by_search(items, search);
    sort_unified_items(&mut items, false);
    Ok(apply_paging(items, limit, offset))
}

pub async fn count_wishlist_groups(
    pool: &SqlitePool,
    platform: Option<&str>,
    media_server_items: Option<&[cinerecord_core::MediaServerItem]>,
    search: Option<&str>,
) -> Result<i64> {
    let library = aggregate_library_records(list_library_items(pool, None).await?);
    let items = aggregate_wishlist_records(
        list_wishlist_items(pool, platform).await?,
        &library,
        media_server_items,
    );
    let items = filter_by_search(items, search);
    Ok(items.len() as i64)
}

pub async fn list_scheduled_tasks(pool: &SqlitePool) -> Result<Vec<ScheduledTask>> {
    let rows = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks ORDER BY paused ASC, next_run_at ASC, updated_at DESC",
    )
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(scheduled_task_from_row).collect()
}

pub async fn get_scheduled_task(pool: &SqlitePool, task_id: &str) -> Result<Option<ScheduledTask>> {
    let row = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks WHERE id = ?1",
    )
    .bind(task_id)
    .fetch_optional(pool)
    .await?;
    row.map(scheduled_task_from_row).transpose()
}

pub async fn upsert_scheduled_task(pool: &SqlitePool, task: &ScheduledTask) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO scheduled_tasks (
            id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating,
            paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            source_platform = excluded.source_platform,
            target_platform = excluded.target_platform,
            schedule = excluded.schedule,
            recent_limit = excluded.recent_limit,
            only_new = excluded.only_new,
            overwrite = excluded.overwrite,
            default_rating = excluded.default_rating,
            paused = excluded.paused,
            running = excluded.running,
            last_run_at = excluded.last_run_at,
            next_run_at = excluded.next_run_at,
            last_status_message = excluded.last_status_message,
            updated_at = excluded.updated_at
        "#,
    )
    .bind(&task.id)
    .bind(&task.name)
    .bind(&task.source_platform)
    .bind(&task.target_platform)
    .bind(&task.schedule)
    .bind(task.recent_limit as i64)
    .bind(if task.only_new { 1_i64 } else { 0_i64 })
    .bind(if task.overwrite { 1_i64 } else { 0_i64 })
    .bind(task.default_rating)
    .bind(if task.paused { 1_i64 } else { 0_i64 })
    .bind(if task.running { 1_i64 } else { 0_i64 })
    .bind(task.last_run_at.map(|value| value.to_rfc3339()))
    .bind(task.next_run_at.map(|value| value.to_rfc3339()))
    .bind(&task.last_status_message)
    .bind(task.created_at.to_rfc3339())
    .bind(task.updated_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn delete_scheduled_task(pool: &SqlitePool, task_id: &str) -> Result<()> {
    sqlx::query("DELETE FROM scheduled_tasks WHERE id = ?1")
        .bind(task_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn claim_due_scheduled_tasks(
    pool: &SqlitePool,
    now: DateTime<Utc>,
) -> Result<Vec<ScheduledTask>> {
    let due = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks WHERE paused = 0 AND running = 0 AND next_run_at IS NOT NULL AND next_run_at <= ?1 ORDER BY next_run_at ASC",
    )
    .bind(now.to_rfc3339())
    .fetch_all(pool)
    .await?;

    let mut tasks = Vec::new();
    for row in due {
        let task = scheduled_task_from_row(row)?;
        let affected = sqlx::query(
            "UPDATE scheduled_tasks SET running = 1, updated_at = ?2 WHERE id = ?1 AND running = 0",
        )
        .bind(&task.id)
        .bind(Utc::now().to_rfc3339())
        .execute(pool)
        .await?
        .rows_affected();
        if affected == 1 {
            tasks.push(ScheduledTask {
                running: true,
                ..task
            });
        }
    }
    Ok(tasks)
}

pub async fn start_scheduled_task_run(pool: &SqlitePool, task_id: &str) -> Result<bool> {
    let affected = sqlx::query(
        "UPDATE scheduled_tasks SET running = 1, updated_at = ?2 WHERE id = ?1 AND running = 0 AND paused = 0",
    )
    .bind(task_id)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?
    .rows_affected();
    Ok(affected == 1)
}

pub async fn complete_scheduled_task_run(
    pool: &SqlitePool,
    task_id: &str,
    next_run_at: Option<DateTime<Utc>>,
    last_status_message: Option<&str>,
) -> Result<()> {
    sqlx::query(
        "UPDATE scheduled_tasks SET running = 0, last_run_at = ?2, next_run_at = ?3, last_status_message = ?4, updated_at = ?5 WHERE id = ?1",
    )
    .bind(task_id)
    .bind(Utc::now().to_rfc3339())
    .bind(next_run_at.map(|value| value.to_rfc3339()))
    .bind(last_status_message)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn mark_scheduled_task_idle(
    pool: &SqlitePool,
    task_id: &str,
    paused: bool,
    next_run_at: Option<DateTime<Utc>>,
    message: Option<&str>,
) -> Result<()> {
    sqlx::query(
        "UPDATE scheduled_tasks SET paused = ?2, running = 0, next_run_at = ?3, last_status_message = ?4, updated_at = ?5 WHERE id = ?1",
    )
    .bind(task_id)
    .bind(if paused { 1_i64 } else { 0_i64 })
    .bind(next_run_at.map(|value| value.to_rfc3339()))
    .bind(message)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn add_scheduled_task_log(pool: &SqlitePool, log: &ScheduledTaskLog) -> Result<()> {
    sqlx::query(
        "INSERT INTO scheduled_task_logs (id, task_id, task_name, source_platform, target_platform, log_type, message, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
    )
    .bind(&log.id)
    .bind(&log.task_id)
    .bind(&log.task_name)
    .bind(&log.source_platform)
    .bind(&log.target_platform)
    .bind(&log.log_type)
    .bind(&log.message)
    .bind(log.created_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_scheduled_task_logs(
    pool: &SqlitePool,
    limit: i64,
) -> Result<Vec<ScheduledTaskLog>> {
    let rows = sqlx::query(
        "SELECT id, task_id, task_name, source_platform, target_platform, log_type, message, created_at FROM scheduled_task_logs ORDER BY created_at DESC LIMIT ?1",
    )
    .bind(limit)
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(scheduled_task_log_from_row).collect()
}

pub async fn platform_item_counts(pool: &SqlitePool, table: &str) -> Result<HashMap<String, i64>> {
    let query = match table {
        "library_items" => {
            "SELECT platform, COUNT(*) AS count FROM library_items GROUP BY platform"
        }
        "wishlist_items" => {
            "SELECT platform, COUNT(*) AS count FROM wishlist_items GROUP BY platform"
        }
        other => anyhow::bail!("unsupported table for counts: {other}"),
    };
    let rows = sqlx::query(query).fetch_all(pool).await?;
    let mut counts = HashMap::new();
    for row in rows {
        counts.insert(row.get::<String, _>("platform"), row.get::<i64, _>("count"));
    }
    Ok(counts)
}

pub async fn import_legacy_csv(
    paths: &StoragePaths,
    platform: &str,
    config: &AppConfig,
    pool: &SqlitePool,
) -> Result<LibrarySnapshot> {
    let csv_path = find_legacy_csv_path(paths, platform, config)
        .await?
        .with_context(|| format!("no legacy CSV found for platform {platform}"))?;
    let platform_name = platform.to_string();
    let items = tokio::task::spawn_blocking(move || parse_legacy_csv(&csv_path, &platform_name))
        .await
        .context("legacy CSV parsing task panicked")??;
    replace_library_items(pool, platform, &items).await?;
    Ok(LibrarySnapshot {
        platform: platform.to_string(),
        item_count: items.len(),
    })
}

fn task_from_row(row: sqlx::sqlite::SqliteRow) -> Result<SyncTask> {
    Ok(SyncTask {
        id: row.get("id"),
        name: row.get("name"),
        kind: task_kind_from_str(row.get::<String, _>("kind").as_str()),
        status: task_status_from_str(row.get::<String, _>("status").as_str()),
        payload: serde_json::from_str(row.get::<String, _>("payload_json").as_str())?,
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
        updated_at: DateTime::parse_from_rfc3339(row.get::<String, _>("updated_at").as_str())?
            .with_timezone(&Utc),
    })
}

fn movie_from_row(row: sqlx::sqlite::SqliteRow) -> Result<MovieRecord> {
    let platform: String = row.get("platform");
    let external_id: Option<String> = row.get("external_id");
    let raw_json: serde_json::Value =
        serde_json::from_str(row.get::<String, _>("raw_json").as_str())?;
    Ok(MovieRecord {
        id: row.get("id"),
        platform: platform.clone(),
        title: row.get("title"),
        year: row.get("year"),
        rating: row.get("rating"),
        rated_at: row
            .get::<Option<String>, _>("rated_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        external_id: external_id.clone(),
        source_url: row.get("source_url"),
        identifiers: infer_identifiers(&platform, external_id.as_deref(), &raw_json),
        raw_json,
    })
}

fn wishlist_from_row(row: sqlx::sqlite::SqliteRow) -> Result<WishlistRecord> {
    let platform: String = row.get("platform");
    let external_id: Option<String> = row.get("external_id");
    let raw_json: serde_json::Value =
        serde_json::from_str(row.get::<String, _>("raw_json").as_str())?;
    let created_at_str: Option<String> = row.try_get("created_at").ok();
    let created_at = created_at_str.and_then(|s| parse_date_string(&s));
    Ok(WishlistRecord {
        id: row.get("id"),
        platform: platform.clone(),
        title: row.get("title"),
        year: row.get("year"),
        external_id: external_id.clone(),
        source_url: row.get("source_url"),
        identifiers: infer_identifiers(&platform, external_id.as_deref(), &raw_json),
        raw_json,
        created_at,
    })
}

fn scheduled_task_from_row(row: sqlx::sqlite::SqliteRow) -> Result<ScheduledTask> {
    Ok(ScheduledTask {
        id: row.get("id"),
        name: row.get("name"),
        source_platform: row.get("source_platform"),
        target_platform: row.get("target_platform"),
        schedule: row.get("schedule"),
        recent_limit: row.get::<i64, _>("recent_limit") as usize,
        only_new: row.get::<i64, _>("only_new") == 1,
        overwrite: row.get::<i64, _>("overwrite") == 1,
        default_rating: row.get("default_rating"),
        paused: row.get::<i64, _>("paused") == 1,
        running: row.get::<i64, _>("running") == 1,
        last_run_at: row
            .get::<Option<String>, _>("last_run_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        next_run_at: row
            .get::<Option<String>, _>("next_run_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        last_status_message: row.get("last_status_message"),
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
        updated_at: DateTime::parse_from_rfc3339(row.get::<String, _>("updated_at").as_str())?
            .with_timezone(&Utc),
    })
}

fn scheduled_task_log_from_row(row: sqlx::sqlite::SqliteRow) -> Result<ScheduledTaskLog> {
    Ok(ScheduledTaskLog {
        id: row.get("id"),
        task_id: row.get("task_id"),
        task_name: row.get("task_name"),
        source_platform: row.get("source_platform"),
        target_platform: row.get("target_platform"),
        log_type: row.get("log_type"),
        message: row.get("message"),
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
    })
}

#[cfg(test)]
mod friend_backup_tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn friend_backup_round_trip_and_delete() {
        let root = std::env::temp_dir().join(format!("cinerecord-backup-test-{}", Uuid::new_v4()));
        let paths = StoragePaths::from_repo_root(&root);
        let backup = FriendBackup {
            id: Uuid::new_v4().to_string(),
            platform: "douban".to_string(),
            user_id: "friend-test".to_string(),
            watched: vec![MovieRecord {
                id: "douban:1".to_string(),
                platform: "douban".to_string(),
                title: "Test Movie".to_string(),
                year: Some(2026),
                rating: Some(8.0),
                rated_at: None,
                external_id: Some("1".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers::default(),
                raw_json: serde_json::json!({}),
            }],
            wishlist: Vec::new(),
            created_at: Utc::now(),
        };

        save_friend_backup(&paths, &backup).await.unwrap();
        let summaries = list_friend_backups(&paths).await.unwrap();
        assert_eq!(summaries.len(), 1);
        assert_eq!(summaries[0].watched_count, 1);
        assert_eq!(
            get_friend_backup(&paths, &backup.id)
                .await
                .unwrap()
                .unwrap()
                .user_id,
            "friend-test"
        );
        assert!(delete_friend_backup(&paths, &backup.id).await.unwrap());
        assert!(
            get_friend_backup(&paths, &backup.id)
                .await
                .unwrap()
                .is_none()
        );
        fs::remove_dir_all(root).await.unwrap();
    }
}

fn infer_identifiers(
    platform: &str,
    external_id: Option<&str>,
    raw_json: &serde_json::Value,
) -> MovieIdentifiers {
    let mut ids = MovieIdentifiers::default();
    match platform {
        "tmdb" => {
            ids.tmdb = external_id.map(ToOwned::to_owned).or_else(|| {
                raw_json
                    .get("id")
                    .and_then(|v| v.as_i64())
                    .map(|v| v.to_string())
            });
            ids.imdb = raw_json
                .get("external_ids")
                .and_then(|v| v.get("imdb_id"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
        }
        "trakt" => {
            let trakt_ids = raw_json
                .get("ids")
                .or_else(|| raw_json.get("movie").and_then(|movie| movie.get("ids")));
            ids.trakt = trakt_ids
                .and_then(|v| v.get("trakt"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    raw_json
                        .get("Trakt ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| external_id.map(ToOwned::to_owned));
            ids.tmdb = trakt_ids
                .and_then(|v| v.get("tmdb"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    raw_json
                        .get("TMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.imdb = trakt_ids
                .and_then(|v| v.get("imdb"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
        }
        "imdb" => {
            ids.imdb = external_id
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("Const")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.douban = raw_json
                .get("douban_id")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_f64())
                        .map(|v| format!("{v:.0}"))
                });
            ids.tmdb = raw_json
                .get("TMDB ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
        }
        "douban" => {
            ids.douban = external_id
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_f64())
                        .map(|v| format!("{v:.0}"))
                })
                .or_else(|| {
                    raw_json
                        .get("movie_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("id"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.imdb = raw_json
                .get("Const")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("imdb"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("imdb_id"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    ids.douban
                        .as_deref()
                        .and_then(lookup_cached_imdb_for_douban)
                });
            ids.tmdb = raw_json
                .get("TMDB ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
            ids.trakt = raw_json
                .get("Trakt ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
        }
        "letterboxd" => {
            ids.letterboxd = external_id.map(ToOwned::to_owned);
        }
        "cinepersona" => {
            let movie = raw_json.get("movie");
            ids.imdb = movie
                .and_then(|m| m.get("imdbId"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    external_id
                        .filter(|id| id.starts_with("tt"))
                        .map(ToOwned::to_owned)
                });
            ids.tmdb = movie
                .and_then(|m| m.get("tmdbId"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    movie
                        .and_then(|m| m.get("tmdbId"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    external_id
                        .filter(|id| !id.starts_with("tt"))
                        .map(ToOwned::to_owned)
                });
        }
        _ => {}
    }
    ids
}

fn lookup_cached_imdb_for_douban(douban_id: &str) -> Option<String> {
    douban_imdb_cache().get(douban_id).cloned()
}

fn douban_imdb_cache() -> &'static HashMap<String, String> {
    DOUBAN_IMDB_CACHE.get_or_init(|| {
        let path = std::env::current_dir()
            .ok()
            .map(|cwd| cwd.join("data").join("db_imdb.csv"));
        let Some(path) = path else {
            return HashMap::new();
        };
        if !path.exists() {
            return HashMap::new();
        }

        let mut reader = match csv::Reader::from_path(path) {
            Ok(reader) => reader,
            Err(_) => return HashMap::new(),
        };
        let mut map = HashMap::new();
        for row in reader.deserialize::<HashMap<String, String>>().flatten() {
            let douban_id = row
                .get("douban_id")
                .map(|value| value.trim())
                .unwrap_or_default();
            let imdb_id = row
                .get("imdb")
                .map(|value| value.trim())
                .unwrap_or_default();
            if !douban_id.is_empty() && !imdb_id.is_empty() {
                map.insert(douban_id.to_string(), imdb_id.to_string());
            }
        }
        map
    })
}

fn aggregate_library_records(records: Vec<MovieRecord>) -> Vec<UnifiedMediaItem> {
    let mut groups = HashMap::<String, UnifiedMediaItem>::new();
    for record in records {
        let key = unified_key(
            &record.identifiers,
            &record.title,
            record.year,
            record.external_id.as_deref(),
            &record.platform,
        );
        let entry = groups
            .entry(key.clone())
            .or_insert_with(|| UnifiedMediaItem {
                id: key.clone(),
                title: record.title.clone(),
                original_title: extract_original_title(&record.raw_json),
                year: record.year,
                media_type: extract_media_type(&record.raw_json),
                poster_url: extract_poster_url(&record.raw_json),
                source_url: record.source_url.clone(),
                identifiers: record.identifiers.clone(),
                personal_rating: record.rating,
                rated_at: record.rated_at,
                public_rating: extract_public_rating(&record.raw_json),
                public_votes: extract_public_votes(&record.raw_json),
                source_platforms: Vec::new(),
                sources: Vec::new(),
                library_matched: true,
                library_url: record.source_url.clone(),
                library_title: Some(record.title.clone()),
                library_year: record.year,
                library_media_path: None,
                library_file_name: None,
                directors: extract_directors(&record.raw_json),
                actors: extract_actors(&record.raw_json),
                genres: extract_genres(&record.raw_json),
                country: extract_country(&record.raw_json),
                duration: extract_duration(&record.raw_json),
            });
        merge_unified_identifiers(&mut entry.identifiers, &record.identifiers);
        fill_unified_defaults(
            entry,
            &record.title,
            record.year,
            &record.raw_json,
            record.source_url.as_deref(),
        );
        merge_library_preference(entry, &record);
        push_unified_source(
            entry,
            UnifiedSourceEntry {
                platform: record.platform.clone(),
                external_id: record.external_id.clone(),
                source_url: record.source_url.clone(),
                rating: record.rating,
                rated_at: record.rated_at,
            },
        );
    }
    groups.into_values().collect()
}

fn normalized_selected_platforms(selected_platforms: &[String]) -> Vec<&str> {
    selected_platforms
        .iter()
        .map(|item| item.trim())
        .filter(|item| LIBRARY_PLATFORMS.contains(item))
        .collect()
}

fn has_all_selected_platforms(item: &UnifiedMediaItem, selected_platforms: &[&str]) -> bool {
    selected_platforms.iter().all(|platform| {
        item.source_platforms
            .iter()
            .any(|source| source == platform)
    })
}

fn filter_library_view_items(
    items: Vec<UnifiedMediaItem>,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
) -> Vec<UnifiedMediaItem> {
    let selected = normalized_selected_platforms(selected_platforms);
    let show_union = selected.is_empty();
    items
        .into_iter()
        .filter(|item| match platform_filter {
            Some(platform) if LIBRARY_PLATFORMS.contains(&platform) => {
                item.source_platforms
                    .iter()
                    .any(|source| source == platform)
                    && (show_union || !has_all_selected_platforms(item, &selected))
            }
            _ if show_union => true,
            _ => has_all_selected_platforms(item, &selected),
        })
        .collect()
}

fn aggregate_wishlist_records(
    records: Vec<WishlistRecord>,
    library: &[UnifiedMediaItem],
    media_server_items: Option<&[cinerecord_core::MediaServerItem]>,
) -> Vec<UnifiedMediaItem> {
    let library_lookup = build_unified_lookup(library);
    let mut groups = HashMap::<String, UnifiedMediaItem>::new();
    for record in records {
        let key = unified_key(
            &record.identifiers,
            &record.title,
            record.year,
            record.external_id.as_deref(),
            &record.platform,
        );
        let mut library_matched = false;
        let mut library_url = None;
        let mut library_title = None;
        let mut library_year = None;
        let mut library_media_path = None;
        let mut library_file_name = None;

        if let Some(media_items) = media_server_items {
            for m_item in media_items {
                let mut id_match = false;
                if let Some(imdb) = &m_item.imdb_id {
                    if let Some(w_imdb) = &record.identifiers.imdb {
                        if imdb == w_imdb {
                            id_match = true;
                        }
                    }
                }
                if !id_match {
                    if let Some(tmdb) = &m_item.tmdb_id {
                        if let Some(w_tmdb) = &record.identifiers.tmdb {
                            if tmdb == w_tmdb {
                                id_match = true;
                            }
                        }
                    }
                }
                if !id_match {
                    if m_item.year == record.year {
                        let m_title = m_item.title.to_lowercase().replace(' ', "");
                        let w_title = record.title.to_lowercase().replace(' ', "");
                        if !m_title.is_empty() && m_title == w_title {
                            id_match = true;
                        }
                    }
                }
                if id_match {
                    library_matched = true;
                    library_url = m_item.library_url.clone();
                    library_title = Some(m_item.title.clone());
                    library_year = m_item.year;
                    library_media_path = m_item.media_path.clone();
                    library_file_name = m_item.file_name.clone();
                    break;
                }
            }
        } else {
            let matched = unified_lookup_match(
                &library_lookup,
                &record.identifiers,
                &record.title,
                record.year,
            );
            if let Some(item) = matched {
                library_matched = true;
                library_url = item.library_url.clone();
                library_title = item.library_title.clone();
                library_year = item.library_year;
                library_media_path = item.library_media_path.clone();
                library_file_name = item.library_file_name.clone();
            }
        }

        let entry = groups
            .entry(key.clone())
            .or_insert_with(|| UnifiedMediaItem {
                id: key.clone(),
                title: record.title.clone(),
                original_title: extract_original_title(&record.raw_json),
                year: record.year,
                media_type: extract_media_type(&record.raw_json),
                poster_url: extract_poster_url(&record.raw_json),
                source_url: record.source_url.clone(),
                identifiers: record.identifiers.clone(),
                personal_rating: None,
                rated_at: extract_date_like(&record.raw_json).or(record.created_at),
                public_rating: extract_public_rating(&record.raw_json),
                public_votes: extract_public_votes(&record.raw_json),
                source_platforms: Vec::new(),
                sources: Vec::new(),
                library_matched,
                library_url: library_url.clone(),
                library_title: library_title.clone(),
                library_year,
                library_media_path: library_media_path.clone(),
                library_file_name: library_file_name.clone(),
                directors: extract_directors(&record.raw_json),
                actors: extract_actors(&record.raw_json),
                genres: extract_genres(&record.raw_json),
                country: extract_country(&record.raw_json),
                duration: extract_duration(&record.raw_json),
            });
        merge_unified_identifiers(&mut entry.identifiers, &record.identifiers);
        fill_unified_defaults(
            entry,
            &record.title,
            record.year,
            &record.raw_json,
            record.source_url.as_deref(),
        );
        if entry.rated_at.is_none() {
            entry.rated_at = extract_date_like(&record.raw_json).or(record.created_at);
        }
        if entry.library_url.is_none() {
            entry.library_url = library_url.clone();
        }
        if entry.library_title.is_none() {
            entry.library_title = library_title.clone();
        }
        if entry.library_year.is_none() {
            entry.library_year = library_year;
        }
        if entry.library_media_path.is_none() {
            entry.library_media_path = library_media_path.clone();
        }
        if entry.library_file_name.is_none() {
            entry.library_file_name = library_file_name.clone();
        }
        entry.library_matched = entry.library_matched || library_matched;
        push_unified_source(
            entry,
            UnifiedSourceEntry {
                platform: record.platform.clone(),
                external_id: record.external_id.clone(),
                source_url: record.source_url.clone(),
                rating: None,
                rated_at: extract_date_like(&record.raw_json),
            },
        );
    }
    groups.into_values().collect()
}

fn merge_library_preference(entry: &mut UnifiedMediaItem, record: &MovieRecord) {
    let newer_rating = match (record.rated_at, entry.rated_at) {
        (Some(new), Some(current)) => new > current,
        (Some(_), None) => true,
        _ => false,
    };
    if entry.rated_at.is_none() || newer_rating {
        entry.personal_rating = record.rating.or(entry.personal_rating);
        entry.rated_at = record.rated_at.or(entry.rated_at);
    }
    if entry.source_url.is_none() {
        entry.source_url = record.source_url.clone();
    }
}

fn fill_unified_defaults(
    entry: &mut UnifiedMediaItem,
    title: &str,
    year: Option<i32>,
    raw_json: &serde_json::Value,
    source_url: Option<&str>,
) {
    if entry.title.trim().is_empty() {
        entry.title = title.to_string();
    }
    if entry.year.is_none() {
        entry.year = year.or_else(|| extract_year(raw_json));
    }
    if entry.original_title.is_none() {
        entry.original_title = extract_original_title(raw_json);
    }
    if entry.media_type.is_none() {
        entry.media_type = extract_media_type(raw_json);
    }
    let extracted_poster = extract_poster_url(raw_json);
    if let Some(new_url) = extracted_poster {
        let is_better = entry
            .poster_url
            .as_ref()
            .map(|curr| {
                let curr_invalid = curr.trim().is_empty()
                    || curr.contains("default_poster")
                    || curr.contains("placeholder");
                let new_is_rich = new_url.contains("doubanio.com")
                    || new_url.contains("tmdb.org")
                    || new_url.contains("image.tmdb.org");
                curr_invalid || (new_is_rich && curr.contains("imdb.com"))
            })
            .unwrap_or(true);
        if is_better {
            entry.poster_url = Some(new_url);
        }
    }
    if entry.source_url.is_none() {
        entry.source_url = source_url.map(ToOwned::to_owned);
    }
    if entry.public_rating.is_none() {
        entry.public_rating = extract_public_rating(raw_json);
    }
    if entry.public_votes.is_none() {
        entry.public_votes = extract_public_votes(raw_json);
    }
    if entry.directors.is_none() {
        entry.directors = extract_directors(raw_json);
    }
    if entry.actors.is_none() {
        entry.actors = extract_actors(raw_json);
    }
    if entry.genres.is_none() {
        entry.genres = extract_genres(raw_json);
    }
    if entry.country.is_none() {
        entry.country = extract_country(raw_json);
    }
    if entry.duration.is_none() {
        entry.duration = extract_duration(raw_json);
    }
}

fn push_unified_source(entry: &mut UnifiedMediaItem, source: UnifiedSourceEntry) {
    if !entry
        .source_platforms
        .iter()
        .any(|platform| platform == &source.platform)
    {
        entry.source_platforms.push(source.platform.clone());
    }
    let duplicate = entry.sources.iter().any(|item| {
        item.platform == source.platform
            && item.external_id == source.external_id
            && item.source_url == source.source_url
    });
    if !duplicate {
        entry.sources.push(source);
    }
}

fn sort_unified_items(items: &mut [UnifiedMediaItem], prefer_date: bool) {
    items.sort_by(|left, right| {
        if prefer_date {
            right
                .rated_at
                .cmp(&left.rated_at)
                .then_with(|| right.year.cmp(&left.year))
                .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
        } else {
            right
                .rated_at
                .cmp(&left.rated_at)
                .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
                .then_with(|| right.year.cmp(&left.year))
        }
    });
}

fn apply_paging<T>(items: Vec<T>, limit: Option<i64>, offset: Option<i64>) -> Vec<T> {
    let offset = offset.unwrap_or(0).max(0) as usize;
    let limit = limit.unwrap_or(10_000).max(0) as usize;
    items.into_iter().skip(offset).take(limit).collect()
}

fn build_unified_lookup(items: &[UnifiedMediaItem]) -> HashMap<String, UnifiedMediaItem> {
    let mut lookup = HashMap::new();
    for item in items {
        for key in unified_lookup_keys(&item.identifiers, &item.title, item.year) {
            lookup.entry(key).or_insert_with(|| item.clone());
        }
    }
    lookup
}

fn unified_lookup_match<'a>(
    lookup: &'a HashMap<String, UnifiedMediaItem>,
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
) -> Option<&'a UnifiedMediaItem> {
    unified_lookup_keys(identifiers, title, year)
        .into_iter()
        .find_map(|key| lookup.get(&key))
}

fn unified_lookup_keys(
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
) -> Vec<String> {
    let mut keys = Vec::new();
    if let Some(imdb) = clean_string(identifiers.imdb.as_deref()) {
        keys.push(format!("imdb:{imdb}"));
    }
    if let Some(tmdb) = clean_string(identifiers.tmdb.as_deref()) {
        keys.push(format!("tmdb:{tmdb}"));
    }
    if let Some(trakt) = clean_string(identifiers.trakt.as_deref()) {
        keys.push(format!("trakt:{trakt}"));
    }
    if let Some(douban) = clean_string(identifiers.douban.as_deref()) {
        keys.push(format!("douban:{douban}"));
    }
    if let Some(letterboxd) = clean_string(identifiers.letterboxd.as_deref()) {
        keys.push(format!("letterboxd:{letterboxd}"));
    }
    if let Some(title_key) = title_year_key(title, year) {
        keys.push(title_key);
    }
    keys
}

fn unified_key(
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
    external_id: Option<&str>,
    platform: &str,
) -> String {
    unified_lookup_keys(identifiers, title, year)
        .into_iter()
        .next()
        .or_else(|| clean_string(external_id).map(|value| format!("{platform}:{value}")))
        .unwrap_or_else(|| format!("{platform}:{}", normalize_title(title)))
}

fn title_year_key(title: &str, year: Option<i32>) -> Option<String> {
    let normalized = normalize_title(title);
    if normalized.is_empty() {
        return None;
    }
    Some(format!("title:{normalized}:{}", year.unwrap_or_default()))
}

fn normalize_title(title: &str) -> String {
    title
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ('\u{4e00}'..='\u{9fff}').contains(&ch) {
                ch.to_ascii_lowercase()
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn clean_string(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn merge_unified_identifiers(target: &mut MovieIdentifiers, source: &MovieIdentifiers) {
    if target.imdb.is_none() {
        target.imdb = source.imdb.clone();
    }
    if target.tmdb.is_none() {
        target.tmdb = source.tmdb.clone();
    }
    if target.trakt.is_none() {
        target.trakt = source.trakt.clone();
    }
    if target.douban.is_none() {
        target.douban = source.douban.clone();
    }
    if target.letterboxd.is_none() {
        target.letterboxd = source.letterboxd.clone();
    }
}

fn extract_original_title(raw_json: &serde_json::Value) -> Option<String> {
    json_string(raw_json, &["original_title", "Original Title", "原名"])
}

fn extract_media_type(raw_json: &serde_json::Value) -> Option<String> {
    let value = json_string(
        raw_json,
        &["Type", "type", "Title Type", "media_type", "titleType"],
    )?;
    let lower = value.to_lowercase();
    if ["tv", "series", "show", "episode", "miniseries"]
        .iter()
        .any(|part| lower.contains(part))
    {
        return Some("tv".to_string());
    }
    Some("movie".to_string())
}

fn extract_poster_url(raw_json: &serde_json::Value) -> Option<String> {
    if let Some(value) = json_string(
        raw_json,
        &["Cover URL", "cover_url", "poster_url", "poster", "Cover"],
    ) {
        return Some(value);
    }
    if let Some(path) = json_string(raw_json, &["poster_path"]) {
        if path.starts_with("http://") || path.starts_with("https://") {
            return Some(path);
        }
        return Some(format!("https://image.tmdb.org/t/p/w500{path}"));
    }
    raw_json
        .get("primaryImage")
        .and_then(|value| value.get("url"))
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned)
}

fn parse_douban_intro(
    intro: &str,
) -> (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
) {
    let parts: Vec<&str> = intro.split('/').map(|s| s.trim()).collect();
    if parts.is_empty() {
        return (None, None, None, None);
    }

    let mut release_dates = Vec::new();
    let mut names = Vec::new();
    let mut countries = Vec::new();
    let mut genres = Vec::new();

    let common_countries = [
        "美国",
        "中国大陆",
        "中国香港",
        "中国台湾",
        "日本",
        "韩国",
        "英国",
        "法国",
        "德国",
        "意大利",
        "西班牙",
        "加拿大",
        "澳大利亚",
        "印度",
        "泰国",
        "新西兰",
        "瑞典",
        "丹麦",
        "俄罗斯",
        "爱尔兰",
        "巴西",
        "中国",
        "香港",
        "台湾",
        "日本",
        "韩国",
        "新加坡",
    ];

    let common_genres = [
        "剧情",
        "喜剧",
        "动作",
        "爱情",
        "科幻",
        "悬疑",
        "惊悚",
        "恐怖",
        "犯罪",
        "同性",
        "音乐",
        "歌舞",
        "传记",
        "历史",
        "战争",
        "西部",
        "奇幻",
        "冒险",
        "灾难",
        "武侠",
        "古装",
        "纪录片",
        "动画",
        "短片",
        "戏曲",
        "家庭",
        "儿童",
        "运动",
        "荒诞",
    ];

    for part in parts {
        if part.chars().next().map_or(false, |c| c.is_ascii_digit()) {
            release_dates.push(part);
            continue;
        }
        if part.contains("分钟") {
            continue;
        }
        if common_countries
            .iter()
            .any(|c| part == *c || part.contains(c))
        {
            countries.push(part);
            continue;
        }
        if common_genres.iter().any(|g| part == *g || part.contains(g)) {
            genres.push(part);
            continue;
        }
        names.push(part);
    }

    let (director, actors) = if names.is_empty() {
        (None, None)
    } else if names.len() == 1 {
        (Some(names[0].to_string()), None)
    } else {
        let dir = names.last().map(|s| s.to_string());
        let acts = names[0..names.len() - 1].join(", ");
        (dir, Some(acts))
    };

    let country = if countries.is_empty() {
        None
    } else {
        Some(countries.join(", "))
    };
    let genre = if genres.is_empty() {
        None
    } else {
        Some(genres.join(", "))
    };

    (director, actors, genre, country)
}

fn get_subject_or_root(raw_json: &serde_json::Value) -> &serde_json::Value {
    if let Some(sub) = raw_json.get("subject") {
        if sub.is_object() {
            return sub;
        }
    }
    raw_json
}

fn extract_directors(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("directors")
        .or_else(|| target.get("Directors"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.get("name")
                    .or_else(|| item.get("text"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.to_string())
            })
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (dir, _, _, _) = parse_douban_intro(intro);
        if dir.is_some() {
            return dir;
        }
    }
    json_string(raw_json, &["Directors", "directors", "director"])
}

fn extract_actors(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("actors")
        .or_else(|| target.get("Actors"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.get("name")
                    .or_else(|| item.get("text"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.to_string())
            })
            .collect();
        if !names.is_empty() {
            let limit = names.len().min(5);
            return Some(names[0..limit].join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, actors, _, _) = parse_douban_intro(intro);
        if actors.is_some() {
            return actors;
        }
    }
    json_string(raw_json, &["Actors", "actors", "actor"])
}

fn extract_genres(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("genres")
        .or_else(|| target.get("Genres"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.as_str().map(|s| s.to_string()).or_else(|| {
                    item.get("name")
                        .and_then(|n| n.as_str())
                        .map(|s| s.to_string())
                })
            })
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, _, genres, _) = parse_douban_intro(intro);
        if genres.is_some() {
            return genres;
        }
    }
    json_string(raw_json, &["Genres", "genres", "genre"])
}

fn extract_country(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("countries")
        .or_else(|| target.get("regions"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| item.as_str().map(|s| s.to_string()))
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(sub) = target.get("card_subtitle").and_then(|v| v.as_str()) {
        let parts: Vec<&str> = sub.split('/').map(|s| s.trim()).collect();
        let common_countries = [
            "美国",
            "中国大陆",
            "中国香港",
            "中国台湾",
            "日本",
            "韩国",
            "英国",
            "法国",
            "德国",
            "意大利",
            "西班牙",
            "加拿大",
            "澳大利亚",
            "印度",
            "泰国",
            "新西兰",
            "瑞典",
            "丹麦",
            "俄罗斯",
            "爱尔兰",
            "巴西",
            "中国",
            "香港",
            "台湾",
        ];
        let matched_countries: Vec<String> = parts
            .iter()
            .filter(|p| common_countries.iter().any(|c| **p == *c || p.contains(c)))
            .map(|s| s.to_string())
            .collect();
        if !matched_countries.is_empty() {
            return Some(matched_countries.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, _, _, country) = parse_douban_intro(intro);
        if country.is_some() {
            return country;
        }
    }
    json_string(raw_json, &["Country", "country", "countries", "region"])
}

fn extract_duration(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target.get("durations").and_then(|v| v.as_array()) {
        if let Some(first) = arr.get(0).and_then(|v| v.as_str()) {
            return Some(first.to_string());
        }
    }
    if let Some(d) = target.get("duration").and_then(|v| v.as_str()) {
        return Some(d.to_string());
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        for part in intro.split('/') {
            let part_trimmed = part.trim();
            if part_trimmed.contains("分钟") || part_trimmed.contains("mins") {
                return Some(part_trimmed.to_string());
            }
        }
    }
    None
}

fn extract_public_rating(raw_json: &serde_json::Value) -> Option<f64> {
    json_number(
        raw_json,
        &[
            "Douban Rating",
            "IMDb Rating",
            "IMDB Rating",
            "vote_average",
            "tmdb_rating",
        ],
    )
}

fn extract_public_votes(raw_json: &serde_json::Value) -> Option<i64> {
    json_number(raw_json, &["Num Votes", "IMDb Votes", "vote_count"])
        .map(|value| value.round() as i64)
}

fn extract_year(raw_json: &serde_json::Value) -> Option<i32> {
    json_string(raw_json, &["Year", "year", "release_date", "上映年份"]).and_then(|value| {
        value
            .chars()
            .take(4)
            .collect::<String>()
            .parse::<i32>()
            .ok()
    })
}

fn extract_date_like(raw_json: &serde_json::Value) -> Option<DateTime<Utc>> {
    json_string(
        raw_json,
        &["Date Added", "Date Rated", "date", "listed_at", "listedAt"],
    )
    .and_then(|value| parse_date_string(&value))
}

fn parse_date_string(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            chrono::NaiveDateTime::parse_from_str(value.trim(), "%Y-%m-%d %H:%M:%S")
                .ok()
                .map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
        })
        .or_else(|| {
            chrono::NaiveDate::parse_from_str(value.trim(), "%Y-%m-%d")
                .ok()
                .and_then(|date| date.and_hms_opt(0, 0, 0))
                .map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
        })
}

fn json_string(raw_json: &serde_json::Value, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| match raw_json.get(*key) {
        Some(serde_json::Value::String(value)) if !value.trim().is_empty() => {
            Some(value.trim().to_string())
        }
        Some(serde_json::Value::Number(value)) => Some(value.to_string()),
        _ => None,
    })
}

fn json_number(raw_json: &serde_json::Value, keys: &[&str]) -> Option<f64> {
    keys.iter().find_map(|key| match raw_json.get(*key) {
        Some(serde_json::Value::Number(value)) => value.as_f64(),
        Some(serde_json::Value::String(value)) => value.trim().replace(',', "").parse::<f64>().ok(),
        _ => None,
    })
}

fn task_kind_to_str(kind: &TaskKind) -> &'static str {
    match kind {
        TaskKind::FetchPlatform => "fetch_platform",
        TaskKind::FetchWishlist => "fetch_wishlist",
        TaskKind::ImportLegacy => "import_legacy",
        TaskKind::SyncPreview => "sync_preview",
        TaskKind::SyncExecute => "sync_execute",
        TaskKind::Maintenance => "maintenance",
    }
}

fn task_kind_from_str(value: &str) -> TaskKind {
    match value {
        "fetch_platform" => TaskKind::FetchPlatform,
        "fetch_wishlist" => TaskKind::FetchWishlist,
        "import_legacy" => TaskKind::ImportLegacy,
        "sync_preview" => TaskKind::SyncPreview,
        "sync_execute" => TaskKind::SyncExecute,
        _ => TaskKind::Maintenance,
    }
}

fn task_status_to_str(status: &TaskStatus) -> &'static str {
    match status {
        TaskStatus::Pending => "pending",
        TaskStatus::Running => "running",
        TaskStatus::Succeeded => "succeeded",
        TaskStatus::Failed => "failed",
        TaskStatus::Cancelled => "cancelled",
    }
}

fn task_status_from_str(value: &str) -> TaskStatus {
    match value {
        "running" => TaskStatus::Running,
        "succeeded" => TaskStatus::Succeeded,
        "failed" => TaskStatus::Failed,
        "cancelled" => TaskStatus::Cancelled,
        _ => TaskStatus::Pending,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LibrarySnapshot {
    pub platform: String,
    pub item_count: usize,
}

async fn find_legacy_csv_path(
    paths: &StoragePaths,
    platform: &str,
    config: &AppConfig,
) -> Result<Option<PathBuf>> {
    let mut candidates = Vec::new();
    let mut dir = fs::read_dir(paths.root.join("data")).await?;
    while let Some(entry) = dir.next_entry().await? {
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("csv") {
            continue;
        }
        let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if matches_platform_csv(name, platform) {
            candidates.push(path);
        }
    }
    if candidates.is_empty() {
        return Ok(None);
    }

    candidates.sort();

    let preferred = match platform {
        "tmdb" => config
            .platforms
            .tmdb
            .username
            .as_ref()
            .map(|username| format!("tmdb_{username}_ratings.csv")),
        "trakt" => None,
        "imdb" => config
            .platforms
            .imdb
            .user_id
            .as_ref()
            .map(|user_id| format!("imdb_{user_id}_ratings.csv")),
        "douban" => config
            .platforms
            .douban
            .user_id
            .as_ref()
            .map(|user_id| format!("douban_{user_id}_ratings.csv")),
        "letterboxd" => Some("letterboxd_diary.csv".to_string()),
        _ => None,
    };

    if let Some(preferred) = preferred {
        if let Some(path) = candidates.iter().find(|path| {
            path.file_name().and_then(|value| value.to_str()) == Some(preferred.as_str())
        }) {
            return Ok(Some(path.clone()));
        }
    }

    Ok(candidates.into_iter().next())
}

fn matches_platform_csv(name: &str, platform: &str) -> bool {
    match platform {
        "tmdb" => name.starts_with("tmdb_") && name.ends_with("_ratings.csv"),
        "trakt" => name.starts_with("trakt_") && name.ends_with("_ratings.csv"),
        "imdb" => name.starts_with("imdb_") && name.ends_with("_ratings.csv"),
        "douban" => name.starts_with("douban_") && name.ends_with("_ratings.csv"),
        "letterboxd" => name == "letterboxd_diary.csv" || name.ends_with("diary.csv"),
        _ => false,
    }
}

fn parse_legacy_csv(path: &Path, platform: &str) -> Result<Vec<MovieRecord>> {
    let mut reader = csv::Reader::from_path(path)?;
    let headers = reader
        .headers()?
        .iter()
        .map(ToOwned::to_owned)
        .collect::<Vec<_>>();
    let mut items = Vec::new();

    for row in reader.records() {
        let row = row?;
        let map = headers
            .iter()
            .cloned()
            .zip(row.iter().map(ToOwned::to_owned))
            .collect::<HashMap<_, _>>();
        let raw_json = serde_json::to_value(&map)?;
        let title = first_value(&map, &["Title", "Name", "Film"])
            .unwrap_or_else(|| "Unknown title".to_string());
        let year = first_value(&map, &["Year", "Release Year"])
            .and_then(|value| value.parse::<i32>().ok());
        let rating = first_value(&map, &["Your Rating", "Rating", "rating"])
            .and_then(|value| value.parse::<f64>().ok());
        let rated_at = first_value(
            &map,
            &["Date Rated", "Watched Date", "watched_at", "rated_at"],
        )
        .and_then(|value| parse_legacy_datetime(&value));
        let identifiers = MovieIdentifiers {
            imdb: first_value(&map, &["Const", "IMDb ID", "imdb_id"]),
            tmdb: first_value(&map, &["TMDB ID", "tmdb_id"]),
            trakt: first_value(&map, &["Trakt ID", "trakt_id"]),
            douban: first_value(&map, &["douban_id", "Subject ID"]),
            letterboxd: first_value(&map, &["Letterboxd URI"]),
        };
        let external_id = match platform {
            "tmdb" => identifiers.tmdb.clone(),
            "trakt" => identifiers.trakt.clone(),
            "imdb" => identifiers.imdb.clone(),
            "douban" => identifiers.douban.clone(),
            "letterboxd" => identifiers.letterboxd.clone(),
            _ => None,
        };

        items.push(MovieRecord {
            id: uuid::Uuid::new_v4().to_string(),
            platform: platform.to_string(),
            title,
            year,
            rating,
            rated_at,
            external_id,
            source_url: first_value(&map, &["URL", "Link", "Subject Link"]),
            identifiers,
            raw_json,
        });
    }

    Ok(items)
}

fn first_value(row: &HashMap<String, String>, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| {
        row.get(*key)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
    })
}

fn parse_legacy_datetime(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            NaiveDate::parse_from_str(value, "%Y-%m-%d")
                .ok()
                .and_then(|date| date.and_hms_opt(0, 0, 0))
                .map(|date| DateTime::<Utc>::from_naive_utc_and_offset(date, Utc))
        })
}
