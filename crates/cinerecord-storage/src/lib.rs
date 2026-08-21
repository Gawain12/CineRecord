pub mod aggregation;
pub mod backup;
pub mod cache;
pub mod db;
pub mod legacy_csv;

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use chrono::Utc;
use cinerecord_core::AppConfig;
use tokio::fs;

pub use aggregation::*;
pub use backup::*;
pub use cache::*;
pub use db::*;
pub use legacy_csv::*;

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
