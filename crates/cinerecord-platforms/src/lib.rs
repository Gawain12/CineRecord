pub mod cinepersona;
pub mod cookiecloud;
pub mod douban;
pub mod imdb;
pub mod media_server;
pub mod preview;
pub mod sync;
pub mod tmdb;
pub mod trakt;

use anyhow::{Context, Result, bail};
use cinerecord_core::{
    AppConfig, FetchResult, MovieRecord, PlatformValidationResult, WishlistRecord,
};

pub use cinepersona::*;
pub use cookiecloud::*;
pub use douban::*;
pub use imdb::*;
pub use media_server::*;
pub use preview::*;
pub use sync::*;
pub use tmdb::*;
pub use trakt::*;

pub async fn test_platform(
    platform: &str,
    config: &AppConfig,
) -> Result<PlatformValidationResult> {
    match platform {
        "tmdb" => test_tmdb(&config.platforms.tmdb).await,
        "trakt" => test_trakt(&config.platforms.trakt).await,
        "imdb" => validate_imdb_cookie(&config.platforms.imdb).await,
        "douban" => {
            if let Some(_cookie) = config.platforms.douban.cookie.as_deref().filter(|c| !c.trim().is_empty()) {
                validate_douban_cookie(&config.platforms.douban).await
            } else if let Some(user_id) = config.platforms.douban.user_id.as_deref().filter(|u| !u.trim().is_empty()) {
                validate_douban_public_profile(user_id).await
            } else {
                Ok(PlatformValidationResult {
                    platform: "douban".to_string(),
                    success: false,
                    message: "豆瓣未配置 Cookie 或用户 ID".to_string(),
                    profile: None,
                })
            }
        }
        "letterboxd" => Ok(PlatformValidationResult {
            platform: "letterboxd".to_string(),
            success: true,
            message: "Letterboxd 支持通过 CSV 导入观影历史".to_string(),
            profile: None,
        }),
        "cinepersona" => test_cinepersona(&config.cinepersona).await,
        other => bail!("unsupported platform for validation: {other}"),
    }
}

pub async fn fetch_platform(
    platform: &str,
    config: &AppConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    match platform {
        "tmdb" => fetch_tmdb_rated_movies(&config.platforms.tmdb).await,
        "trakt" => fetch_trakt_movies(&config.platforms.trakt).await,
        "imdb" => fetch_imdb_rated_movies(&config.platforms.imdb).await,
        "douban" => fetch_douban_movies(&config.platforms.douban).await,
        "cinepersona" => fetch_cinepersona_movies(&config.cinepersona).await,
        other => bail!("unsupported platform for movie fetching: {other}"),
    }
}

pub async fn fetch_platform_wishlist(
    platform: &str,
    config: &AppConfig,
) -> Result<(serde_json::Value, Vec<WishlistRecord>)> {
    match platform {
        "tmdb" => fetch_tmdb_watchlist(&config.platforms.tmdb).await,
        "trakt" => fetch_trakt_watchlist(&config.platforms.trakt).await,
        "imdb" => fetch_imdb_watchlist(&config.platforms.imdb).await,
        "douban" => fetch_douban_wishlist(&config.platforms.douban).await,
        "cinepersona" => fetch_cinepersona_wishlist(&config.cinepersona).await,
        other => bail!("unsupported platform for wishlist fetching: {other}"),
    }
}

pub async fn sync_cookiecloud(
    config: &mut AppConfig,
    host: Option<&str>,
    uuid: Option<&str>,
    password: Option<&str>,
) -> Result<CookieCloudSyncResult> {
    let host = host
        .or(config.cookiecloud.host.as_deref())
        .context("CookieCloud host is required")?;
    let uuid = uuid
        .or(config.cookiecloud.uuid.as_deref())
        .context("CookieCloud uuid is required")?;
    let password = password
        .or(config.cookiecloud.password.as_deref())
        .context("CookieCloud password is required")?;

    let norm_host = normalize_cookiecloud_host(host)?;
    let payload = request_cookiecloud_payload(&norm_host, uuid, password).await?;
    let cookie_data = extract_cookie_data(&payload)?;

    let mut imported = Vec::new();
    let mut skipped = Vec::new();
    let mut missing = Vec::new();

    let platforms = ["douban", "imdb"];

    for platform in platforms {
        let keywords = platform_domain_keywords(platform);
        let allowed = allowed_cookie_names(platform);
        let required = required_cookie_names(platform);

        let (header, count) = build_cookie_header(&cookie_data, &keywords, allowed);
        let found_names = cookie_names_from_header(&header);

        let has_required = required.iter().all(|req| found_names.iter().any(|name| name == req));

        if count == 0 {
            missing.push(platform.to_string());
            continue;
        }

        if !has_required {
            skipped.push(CookieCloudSkippedPlatform {
                platform: platform.to_string(),
                matched_count: count,
                cookie_names: found_names,
                reason: format!("缺少关键 Cookie: {:?}", required),
            });
            continue;
        }

        // Apply cookie to config
        let cfg = current_platform_cookie_config_mut(config, platform)?;
        cfg.cookie = Some(header.clone());

        let validation = test_platform(platform, config).await?;
        let user_id = validation
            .profile
            .as_ref()
            .and_then(|p| p.get("user_id"))
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned);

        if let Some(ref uid) = user_id {
            if let Ok(cfg) = current_platform_cookie_config_mut(config, platform) {
                cfg.user_id = Some(uid.clone());
            }
        }

        imported.push(CookieCloudImportedPlatform {
            platform: platform.to_string(),
            matched_count: count,
            cookie_names: found_names,
            user_id,
            imported_without_validation: false,
            validation,
        });
    }

    Ok(CookieCloudSyncResult {
        imported,
        skipped,
        missing,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use cinerecord_core::{MovieIdentifiers, SyncPreviewRequest};
    use serde_json::json;

    #[test]
    fn detects_douban_login_jump_as_protection_page() {
        assert!(is_douban_protection_error("HTTP 403 Forbidden"));
        assert!(is_douban_protection_error("https://sec.douban.com/something"));
        assert!(is_douban_protection_error("captcha required"));
        assert!(!is_douban_protection_error("connection reset by peer"));
    }

    #[test]
    fn preview_builds_imdb_to_tmdb_candidates() {
        let source_items = vec![MovieRecord {
            id: "imdb:tt0111161".to_string(),
            platform: "imdb".to_string(),
            title: "The Shawshank Redemption".to_string(),
            year: Some(1994),
            rating: Some(9.3),
            rated_at: None,
            external_id: Some("tt0111161".to_string()),
            source_url: None,
            identifiers: MovieIdentifiers {
                imdb: Some("tt0111161".to_string()),
                tmdb: Some("278".to_string()),
                ..MovieIdentifiers::default()
            },
            raw_json: json!({}),
        }];
        let target_items = Vec::new();

        let req = SyncPreviewRequest {
            source_platform: "imdb".to_string(),
            target_platform: "tmdb".to_string(),
            recent_limit: 10,
            only_new: true,
            overwrite: false,
            default_rating: None,
            refresh_before_sync: false,
        };

        let preview = build_sync_preview(
            "imdb",
            "tmdb",
            &source_items,
            &target_items,
            &req,
        )
        .unwrap();

        assert_eq!(preview.items.len(), 1);
        assert_eq!(preview.items[0].action, "new");
        assert_eq!(preview.items[0].target_linking_id, Some("278".to_string()));
        assert_eq!(preview.preview_count, 1);
    }

    #[test]
    fn preview_skips_existing_movies_when_only_new() {
        let item = MovieRecord {
            id: "tmdb:278".to_string(),
            platform: "tmdb".to_string(),
            title: "The Shawshank Redemption".to_string(),
            year: Some(1994),
            rating: Some(9.0),
            rated_at: None,
            external_id: Some("278".to_string()),
            source_url: None,
            identifiers: MovieIdentifiers {
                tmdb: Some("278".to_string()),
                imdb: Some("tt0111161".to_string()),
                ..MovieIdentifiers::default()
            },
            raw_json: json!({}),
        };

        let req = SyncPreviewRequest {
            source_platform: "tmdb".to_string(),
            target_platform: "trakt".to_string(),
            recent_limit: 10,
            only_new: true,
            overwrite: false,
            default_rating: None,
            refresh_before_sync: false,
        };

        let preview = build_sync_preview(
            "tmdb",
            "trakt",
            &[item.clone()],
            &[item],
            &req,
        )
        .unwrap();

        assert_eq!(preview.items.len(), 1);
        assert_eq!(preview.items[0].action, "skip");
        assert_eq!(preview.preview_count, 0);
    }

    #[test]
    fn preview_skips_overwrite_when_target_already_has_same_rating() {
        let source_item = MovieRecord {
            id: "imdb:tt0111161".to_string(),
            platform: "imdb".to_string(),
            title: "The Shawshank Redemption".to_string(),
            year: Some(1994),
            rating: Some(9.0),
            rated_at: None,
            external_id: Some("tt0111161".to_string()),
            source_url: None,
            identifiers: MovieIdentifiers {
                imdb: Some("tt0111161".to_string()),
                ..MovieIdentifiers::default()
            },
            raw_json: json!({}),
        };
        let target_item = MovieRecord {
            id: "tmdb:278".to_string(),
            platform: "tmdb".to_string(),
            title: "The Shawshank Redemption".to_string(),
            year: Some(1994),
            rating: Some(9.0),
            rated_at: None,
            external_id: Some("278".to_string()),
            source_url: None,
            identifiers: MovieIdentifiers {
                imdb: Some("tt0111161".to_string()),
                tmdb: Some("278".to_string()),
                ..MovieIdentifiers::default()
            },
            raw_json: json!({}),
        };

        let req = SyncPreviewRequest {
            source_platform: "imdb".to_string(),
            target_platform: "tmdb".to_string(),
            recent_limit: 10,
            only_new: false,
            overwrite: true,
            default_rating: None,
            refresh_before_sync: false,
        };

        let preview = build_sync_preview(
            "imdb",
            "tmdb",
            &[source_item],
            &[target_item],
            &req,
        )
        .unwrap();

        assert_eq!(preview.items.len(), 1);
        assert_eq!(preview.items[0].action, "skip");
        assert_eq!(
            preview.items[0].reason.as_deref(),
            Some("目标平台已存在相同评分")
        );
    }
}
