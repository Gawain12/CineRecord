use aes::Aes256;
use anyhow::{Context, Result, anyhow};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use cbc::cipher::{BlockDecryptMut, KeyIvInit, block_padding::Pkcs7};
use chrono::{DateTime, Duration, Utc};
use cinerecord_core::{
    AppConfig, FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult, SyncExecuteResult,
    SyncExecutionItem, SyncPreviewItem, SyncPreviewRequest, SyncPreviewResult, TraktDeviceCode,
    TraktDevicePollResult, WishlistRecord,
};
use reqwest::{Client, Method, StatusCode};
use scraper::{Html, Selector};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashMap};
use std::sync::OnceLock;
use tokio::process::Command;
use uuid::Uuid;

const DEFAULT_TMDB_API_KEY: &str = "8ffaf38032c0f85f4f421fb0cc1241a5";
const COOKIECLOUD_ALLOWED_DOUBAN: &[&str] = &["dbcl2", "ck", "ap_v", "bid", "push_noty_num", "push_doumail_num"];
const COOKIECLOUD_REQUIRED_DOUBAN: &[&str] = &["dbcl2"];
const COOKIECLOUD_ALLOWED_IMDB: &[&str] = &[
    "ubid-main",
    "at-main",
    "sess-at-main",
    "session-id",
    "session-id-time",
    "session-token",
    "x-main",
    "csm-hit",
    "uu",
    "lc-main",
];
const COOKIECLOUD_REQUIRED_IMDB: &[&str] = &["ubid-main", "at-main", "session-token"];
static DOUBAN_IMDB_CACHE: OnceLock<HashMap<String, String>> = OnceLock::new();
static TMDB_LEGACY_CACHE: OnceLock<HashMap<String, HashMap<String, String>>> = OnceLock::new();

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudImportedPlatform {
    pub platform: String,
    pub matched_count: usize,
    pub cookie_names: Vec<String>,
    pub user_id: Option<String>,
    pub imported_without_validation: bool,
    pub validation: PlatformValidationResult,
}

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudSkippedPlatform {
    pub platform: String,
    pub matched_count: usize,
    pub cookie_names: Vec<String>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudSyncResult {
    pub imported: Vec<CookieCloudImportedPlatform>,
    pub skipped: Vec<CookieCloudSkippedPlatform>,
    pub missing: Vec<String>,
}

pub async fn start_trakt_device_auth(config: &AppConfig) -> Result<TraktDeviceCode> {
    trakt_client(&config.platforms.trakt)?
        .start_device_auth()
        .await
}

pub async fn poll_trakt_device_auth(config: &AppConfig, device_code: &str) -> Result<TraktDevicePollResult> {
    trakt_client(&config.platforms.trakt)?
        .poll_device_auth(device_code)
        .await
}

pub async fn refresh_trakt_access_token(config: &AppConfig) -> Result<TraktDevicePollResult> {
    trakt_client(&config.platforms.trakt)?
        .refresh_access_token()
        .await
}

pub async fn start_tmdb_auth(config: &AppConfig) -> Result<Value> {
    let client = tmdb_client(&config.platforms.tmdb)?;
    let request_token = client.create_request_token().await?;
    Ok(json!({
        "request_token": request_token,
        "auth_url": format!("https://www.themoviedb.org/authenticate/{request_token}"),
    }))
}

pub async fn complete_tmdb_auth(config: &AppConfig) -> Result<Value> {
    let client = tmdb_client(&config.platforms.tmdb)?;
    let request_token = config
        .platforms
        .tmdb
        .request_token
        .clone()
        .context("TMDB request_token is required. Start auth first.")?;
    let session_id = client.create_session(&request_token).await?;
    let account = client.fetch_account_with_session(&session_id).await?;
    let account_id = account.get("id").and_then(|v| v.as_i64());
    let username = account.get("username").and_then(|v| v.as_str()).map(ToOwned::to_owned);
    Ok(json!({
        "session_id": session_id,
        "account_id": account_id.map(|v| v.to_string()),
        "username": username,
        "profile": account,
    }))
}

pub async fn test_platform(platform: &str, config: &AppConfig) -> Result<PlatformValidationResult> {
    match platform {
        "tmdb" => test_tmdb(&config.platforms.tmdb).await,
        "trakt" => test_trakt(&config.platforms.trakt).await,
        "imdb" => test_cookie_platform("imdb", &config.platforms.imdb).await,
        "douban" => test_cookie_platform("douban", &config.platforms.douban).await,
        "letterboxd" => Ok(PlatformValidationResult {
            platform: "letterboxd".to_string(),
            success: true,
            message: "Letterboxd import/export is file-based and will be implemented incrementally".to_string(),
            profile: None,
        }),
        other => Err(anyhow!("unsupported platform: {other}")),
    }
}

pub async fn validate_cookie_platform(
    platform: &str,
    cookie_header: &str,
    user_id: Option<&str>,
) -> Result<PlatformValidationResult> {
    let cookie_names = cookie_names_from_header(cookie_header);
    let required = required_cookie_names(platform);
    let missing_required = required
        .iter()
        .filter(|name| !cookie_names.iter().any(|item| item == **name))
        .map(|name| (*name).to_string())
        .collect::<Vec<_>>();

    if !missing_required.is_empty() {
        return Ok(PlatformValidationResult {
            platform: platform.to_string(),
            success: false,
            message: format!("缺少关键 Cookie：{}", missing_required.join(", ")),
            profile: Some(json!({
                "cookie_names": cookie_names,
                "missing_required": missing_required
            })),
        });
    }

    match platform {
        "douban" => validate_douban_cookie(cookie_header, user_id, cookie_names).await,
        "imdb" => validate_imdb_cookie(cookie_header, user_id, cookie_names).await,
        other => Err(anyhow!("unsupported cookie platform: {other}")),
    }
}

pub async fn sync_cookiecloud(
    config: &mut AppConfig,
    host_override: Option<String>,
    uuid_override: Option<String>,
    password_override: Option<String>,
) -> Result<CookieCloudSyncResult> {
    let host = host_override
        .or_else(|| config.cookiecloud.host.clone())
        .map(|value| normalize_cookiecloud_host(&value))
        .transpose()?
        .context("CookieCloud host is required")?;
    let uuid = uuid_override
        .or_else(|| config.cookiecloud.uuid.clone())
        .filter(|value| !value.trim().is_empty())
        .context("CookieCloud UUID is required")?;
    let password = password_override
        .or_else(|| config.cookiecloud.password.clone())
        .context("CookieCloud password is required")?;

    config.cookiecloud.host = Some(host.clone());
    config.cookiecloud.uuid = Some(uuid.clone());
    config.cookiecloud.password = Some(password.clone());

    let payload = request_cookiecloud_payload(&host, &uuid, &password).await?;
    let cookie_data = extract_cookie_data(&payload)?;
    let mut result = CookieCloudSyncResult {
        imported: Vec::new(),
        skipped: Vec::new(),
        missing: Vec::new(),
    };

    for platform in ["douban", "imdb"] {
        let allowed = allowed_cookie_names(platform);
        let domain_keywords = platform_domain_keywords(platform);
        let (cookie, matched_count) = build_cookie_header(&cookie_data, &domain_keywords, allowed);
        let cookie_names = cookie_names_from_header(&cookie);

        if cookie.is_empty() {
            result.missing.push(platform.to_string());
            continue;
        }

        let validation = validate_cookie_platform(
            platform,
            &cookie,
            current_platform_cookie_config(config, platform)
                .user_id
                .as_deref(),
        )
        .await?;

        if validation.success || !validation.message.contains("缺少关键 Cookie") {
            let user_id = validation
                .profile
                .as_ref()
                .and_then(|profile| profile.get("user_id"))
                .and_then(|value| value.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| current_platform_cookie_config(config, platform).user_id.clone());

            let target = current_platform_cookie_config_mut(config, platform)?;
            target.cookie = Some(cookie);
            if user_id.is_some() {
                target.user_id = user_id.clone();
            }

            result.imported.push(CookieCloudImportedPlatform {
                platform: platform.to_string(),
                matched_count,
                cookie_names,
                user_id,
                imported_without_validation: !validation.success,
                validation: if validation.success {
                    validation
                } else {
                    PlatformValidationResult {
                        platform: validation.platform,
                        success: false,
                        message: format!("关键 Cookie 已导入，但在线校验未通过：{}", validation.message),
                        profile: validation.profile,
                    }
                },
            });
        } else {
            result.skipped.push(CookieCloudSkippedPlatform {
                platform: platform.to_string(),
                matched_count,
                cookie_names,
                reason: validation.message,
            });
        }
    }

    Ok(result)
}

pub async fn fetch_platform(platform: &str, config: &AppConfig) -> Result<(FetchResult, Vec<MovieRecord>)> {
    match platform {
        "tmdb" => fetch_tmdb_rated_movies(&config.platforms.tmdb).await,
        "trakt" => fetch_trakt_movies(&config.platforms.trakt).await,
        "imdb" => fetch_imdb_rated_movies(&config.platforms.imdb).await,
        "douban" => fetch_douban_movies(&config.platforms.douban).await,
        "letterboxd" => stub_fetch(platform),
        other => Err(anyhow!("unsupported platform: {other}")),
    }
}

pub async fn fetch_platform_wishlist(platform: &str, config: &AppConfig) -> Result<(Value, Vec<WishlistRecord>)> {
    match platform {
        "tmdb" => fetch_tmdb_watchlist(&config.platforms.tmdb).await,
        "trakt" => fetch_trakt_watchlist(&config.platforms.trakt).await,
        "imdb" => fetch_imdb_watchlist(&config.platforms.imdb).await,
        "douban" => fetch_douban_wishlist(&config.platforms.douban).await,
        _ => Ok((
            json!({
                "platform": platform,
                "items": [],
                "item_count": 0,
                "stored_count": 0,
                "implemented": false
            }),
            Vec::new(),
        )),
    }
}

pub fn build_sync_preview(
    source: &str,
    target: &str,
    source_items: &[MovieRecord],
    target_items: &[MovieRecord],
    request: &SyncPreviewRequest,
) -> Result<SyncPreviewResult> {
    if !supports_sync_pair(source, target) {
        return Err(anyhow!("暂不支持 {source} -> {target} 同步"));
    }

    let mut sorted_source = source_items.to_vec();
    sorted_source.sort_by(|a, b| b.rated_at.cmp(&a.rated_at).then_with(|| a.title.cmp(&b.title)));
    if request.recent_limit > 0 && sorted_source.len() > request.recent_limit {
        sorted_source.truncate(request.recent_limit);
    }

    let mut target_index = std::collections::HashSet::new();
    let mut target_lookup = std::collections::HashMap::<String, &MovieRecord>::new();
    for target_item in target_items {
        for key in identifier_keys(target_item) {
            target_index.insert(key.clone());
            target_lookup.entry(key).or_insert(target_item);
        }
    }

    let mut preview_items = Vec::new();

    for item in sorted_source {
        let item_keys = identifier_keys(&item);
        let matched_target = item_keys
            .iter()
            .find_map(|key| target_lookup.get(key).copied());
        let found_in_target = item_keys.iter().any(|key| target_index.contains(key));

        if request.only_new && !request.overwrite && found_in_target {
            continue;
        }

        let mut source_rating = item.rating;
        let target_existing_rating = matched_target.and_then(|target| target.rating);
        let target_linking_id = matched_target
            .and_then(|target_item| resolve_target_linking_id(target, &target_item.identifiers))
            .or_else(|| resolve_target_linking_id(target, &item.identifiers));
        let mut reason = None;
        let mut action = if found_in_target && request.overwrite {
            "overwrite".to_string()
        } else if found_in_target {
            "keep".to_string()
        } else {
            "new".to_string()
        };

        if target_linking_id.is_none() {
            reason = Some("No linking identifier available for target platform".to_string());
        }

        if target == "tmdb" && !is_valid_rating(source_rating) {
            if let Some(default_rating) = request.default_rating.filter(|rating| *rating > 0.0) {
                source_rating = Some(default_rating);
            } else {
                reason = Some("TMDB does not support watched-only sync without a rating".to_string());
            }
        }

        if found_in_target && request.overwrite {
            if is_valid_rating(target_existing_rating) && !is_valid_rating(source_rating) {
                action = "keep".to_string();
                reason = Some(format!(
                    "目标平台已有评分 {}，源平台未评分；为避免覆盖，已跳过",
                    format_rating(target_existing_rating)
                ));
            } else if is_valid_rating(target_existing_rating)
                && is_valid_rating(source_rating)
                && ratings_match(source_rating, target_existing_rating)
            {
                action = "keep".to_string();
                reason = Some(format!(
                    "目标平台评分已是 {}，无需重复覆盖",
                    format_rating(target_existing_rating)
                ));
            }
        } else if found_in_target && !request.overwrite {
            action = "keep".to_string();
            reason = Some("目标平台已有对应条目；开启覆盖后才会更新已有评分".to_string());
        }

        preview_items.push(SyncPreviewItem {
            title: item.title.clone(),
            year: item.year,
            source_platform: source.to_string(),
            target_platform: target.to_string(),
            source_rating,
            target_existing_rating,
            source_url: item.source_url.clone(),
            target_linking_id,
            identifiers: item.identifiers.clone(),
            action,
            reason,
        });
    }

    Ok(SyncPreviewResult {
        direction: format!("{source}-to-{target}"),
        source_count: source_items.len(),
        target_count: target_items.len(),
        preview_count: preview_items.len(),
        items: preview_items,
    })
}

pub async fn execute_sync(config: &AppConfig, preview: &SyncPreviewResult) -> Result<SyncExecuteResult> {
    let (source, target) = parse_direction(&preview.direction)?;
    if !supports_sync_pair(source, target) {
        return Err(anyhow!("暂不支持 {} 同步", preview.direction));
    }

    let mut results = Vec::new();
    let mut success_count = 0;
    let mut failed_count = 0;
    let mut skipped_count = 0;

    match target {
        "trakt" => {
            let client = trakt_client(&config.platforms.trakt)?;
            for item in &preview.items {
                if item.reason.is_some() {
                    skipped_count += 1;
                    results.push(skipped_item(item, item.reason.clone()));
                    continue;
                }
                match sync_item_to_trakt(&client, item).await {
                    Ok(result) => {
                        if result.status == "success" {
                            success_count += 1;
                        } else if result.status == "skipped" {
                            skipped_count += 1;
                        } else {
                            failed_count += 1;
                        }
                        results.push(result);
                    }
                    Err(error) => {
                        failed_count += 1;
                        results.push(failed_item(item, error.to_string()));
                    }
                }
            }
        }
        "tmdb" => {
            let client = tmdb_client(&config.platforms.tmdb)?;
            for item in &preview.items {
                if item.reason.is_some() {
                    skipped_count += 1;
                    results.push(skipped_item(item, item.reason.clone()));
                    continue;
                }
                match sync_item_to_tmdb(&client, item).await {
                    Ok(result) => {
                        if result.status == "success" {
                            success_count += 1;
                        } else if result.status == "skipped" {
                            skipped_count += 1;
                        } else {
                            failed_count += 1;
                        }
                        results.push(result);
                    }
                    Err(error) => {
                        failed_count += 1;
                        results.push(failed_item(item, error.to_string()));
                    }
                }
            }
        }
        "imdb" => {
            let cookie = config
                .platforms
                .imdb
                .cookie
                .as_deref()
                .filter(|value| !value.trim().is_empty())
                .context("IMDb Cookie is required for sync target")?;
            for item in &preview.items {
                if item.reason.is_some() {
                    skipped_count += 1;
                    results.push(skipped_item(item, item.reason.clone()));
                    continue;
                }
                match sync_item_to_imdb(cookie, item).await {
                    Ok(result) => {
                        if result.status == "success" {
                            success_count += 1;
                        } else if result.status == "skipped" {
                            skipped_count += 1;
                        } else {
                            failed_count += 1;
                        }
                        results.push(result);
                    }
                    Err(error) => {
                        failed_count += 1;
                        results.push(failed_item(item, error.to_string()));
                    }
                }
            }
        }
        "douban" => {
            let cookie = config
                .platforms
                .douban
                .cookie
                .as_deref()
                .filter(|value| !value.trim().is_empty())
                .context("Douban Cookie is required for sync target")?;
            for item in &preview.items {
                if item.reason.is_some() {
                    skipped_count += 1;
                    results.push(skipped_item(item, item.reason.clone()));
                    continue;
                }
                match sync_item_to_douban(cookie, item).await {
                    Ok(result) => {
                        if result.status == "success" {
                            success_count += 1;
                        } else if result.status == "skipped" {
                            skipped_count += 1;
                        } else {
                            failed_count += 1;
                        }
                        results.push(result);
                    }
                    Err(error) => {
                        failed_count += 1;
                        results.push(failed_item(item, error.to_string()));
                    }
                }
            }
        }
        _ => return Err(anyhow!("sync target {target} is not implemented")),
    }

    Ok(SyncExecuteResult {
        direction: preview.direction.clone(),
        success_count,
        failed_count,
        skipped_count,
        items: results,
    })
}

pub fn supports_sync_pair(source: &str, target: &str) -> bool {
    source != target
        && matches!(source, "tmdb" | "trakt" | "imdb" | "douban")
        && matches!(target, "tmdb" | "trakt" | "imdb" | "douban")
}

async fn test_tmdb(config: &cinerecord_core::TmdbConfig) -> Result<PlatformValidationResult> {
    let client = tmdb_client(config)?;
    let auth = client.validate_api_key().await?;
    if !auth.get("success").and_then(|v| v.as_bool()).unwrap_or(false) {
        return Ok(PlatformValidationResult {
            platform: "tmdb".to_string(),
            success: false,
            message: auth
                .get("status_message")
                .and_then(|v| v.as_str())
                .unwrap_or("TMDB 校验失败")
                .to_string(),
            profile: Some(auth),
        });
    }

    let profile = if client.session_id.is_some() {
        if let Ok(account) = client.fetch_account().await {
            let account_id = account.get("id").and_then(|value| value.as_i64());
            let username = account
                .get("username")
                .and_then(|value| value.as_str())
                .map(ToOwned::to_owned);
            let avatar = extract_tmdb_avatar(&account);
            let rated_payload = match account_id {
                Some(account_id) => client.get_account_rated_movies(account_id, 1).await.ok(),
                None => None,
            };
            let watchlist_payload = match account_id {
                Some(account_id) => client.get_account_watchlist(account_id, 1).await.ok(),
                None => None,
            };
            let rated_total = rated_payload
                .as_ref()
                .and_then(|value| value.get("total_results"))
                .and_then(|value| value.as_i64());
            let watchlist_total = watchlist_payload
                .as_ref()
                .and_then(|value| value.get("total_results"))
                .and_then(|value| value.as_i64());
            let sample_title = rated_payload
                .as_ref()
                .and_then(|value| value.get("results"))
                .and_then(|value| value.as_array())
                .and_then(|items| items.first())
                .and_then(|item| item.get("title"))
                .and_then(|value| value.as_str())
                .map(ToOwned::to_owned);
            Some(json!({
                "account": account,
                "fetch_verified": rated_payload.is_some(),
                "user_id": account_id.map(|value| value.to_string()),
                "display_name": username,
                "avatar": avatar,
                "rated_total": rated_total,
                "watchlist_total": watchlist_total,
                "ratings": rated_total,
                "watchlist": watchlist_total,
                "sample_title": sample_title,
                "profile_link": username.as_ref().map(|name| format!("https://www.themoviedb.org/u/{name}"))
            }))
        } else {
            None
        }
    } else {
        None
    };

    Ok(PlatformValidationResult {
        platform: "tmdb".to_string(),
        success: true,
        message: if let Some(profile) = &profile {
            let username = profile
                .get("account")
                .and_then(|account| account.get("username"))
                .and_then(|value| value.as_str());
            let rated_total = profile.get("rated_total").and_then(|value| value.as_i64()).unwrap_or(0);
            match username {
                Some(username) => format!("TMDB 已验证 · 用户 {username} · 可读取评分数据 ({rated_total} 条)"),
                None => format!("TMDB API Key 和 Session 校验通过 · 可读取评分数据 ({rated_total} 条)"),
            }
        } else {
            "TMDB API Key 校验通过；补充 Session 后即可抓取和同步评分".to_string()
        },
        profile,
    })
}

async fn test_trakt(config: &cinerecord_core::TraktConfig) -> Result<PlatformValidationResult> {
    if config.client_id.as_deref().is_none_or(|value| value.trim().is_empty())
        || config.client_secret.as_deref().is_none_or(|value| value.trim().is_empty())
    {
        return Ok(PlatformValidationResult {
            platform: "trakt".to_string(),
            success: false,
            message: "先填写 Trakt client_id 和 client_secret，再开始设备授权".to_string(),
            profile: None,
        });
    }
    let client = trakt_client(config)?;
    if client.access_token.is_none() {
        return Ok(PlatformValidationResult {
            platform: "trakt".to_string(),
            success: false,
            message: "Trakt 基础配置已完成，但还没有 access token，请先在 CineRecord 页面完成设备授权".to_string(),
            profile: None,
        });
    }

    let profile = client.get_user_profile().await?;
    let stats = client.get_user_stats("me").await?;
    let ratings_probe = client
        .get(
            "/users/me/ratings/movies",
            Some(&[
                ("page", "1".to_string()),
                ("limit", "1".to_string()),
                ("extended", "full".to_string()),
            ]),
        )
        .await?;
    let sample_title = ratings_probe
        .as_array()
        .and_then(|items| items.first())
        .and_then(|item| item.get("movie"))
        .and_then(|movie| movie.get("title"))
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned);
    let username = profile
        .get("username")
        .and_then(|value| value.as_str())
        .or_else(|| profile.get("ids").and_then(|ids| ids.get("slug")).and_then(|value| value.as_str()));
    let ratings_total = stats
        .get("movies")
        .and_then(|value| value.get("ratings"))
        .and_then(|value| value.as_i64())
        .or_else(|| stats.get("ratings").and_then(|value| value.get("total")).and_then(|value| value.as_i64()))
        .unwrap_or(0);
    let watchlist_total = stats
        .get("watchlist")
        .and_then(|value| value.get("movies"))
        .and_then(|value| value.as_i64());
    Ok(PlatformValidationResult {
        platform: "trakt".to_string(),
        success: true,
        message: match username {
            Some(username) => format!("Trakt 已验证 · 用户 {username} · 可读取评分数据 ({ratings_total} 条)"),
            None => format!("Trakt OAuth token 校验通过 · 可读取评分数据 ({ratings_total} 条)"),
        },
        profile: Some(json!({
            "profile": profile,
            "stats": stats,
            "fetch_verified": true,
            "user_id": username,
            "display_name": profile.get("name").and_then(|value| value.as_str()).or(username),
            "avatar": extract_trakt_avatar(&profile),
            "ratings_total": ratings_total,
            "watchlist_total": watchlist_total,
            "watched": stats.get("movies").and_then(|value| value.get("watched")).and_then(|value| value.as_i64()),
            "ratings": ratings_total,
            "watchlist": watchlist_total,
            "sample_title": sample_title
        })),
    })
}

async fn fetch_tmdb_rated_movies(config: &cinerecord_core::TmdbConfig) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let client = tmdb_client(config)?;
    let account = client.fetch_account().await?;
    let account_id = account
        .get("id")
        .and_then(|v| v.as_i64())
        .context("TMDB account id missing")?;

    let mut page = 1_i64;
    let mut total_pages = 1_i64;
    let mut records = Vec::new();
    let legacy_cache = tmdb_legacy_cache();

    while page <= total_pages {
        let payload = client.get_account_rated_movies(account_id, page).await?;
        total_pages = payload.get("total_pages").and_then(|v| v.as_i64()).unwrap_or(1);

        for item in payload
            .get("results")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default()
        {
            let tmdb_id = item.get("id").and_then(|v| v.as_i64()).context("TMDB movie id missing")?;
            let tmdb_key = tmdb_id.to_string();
            let legacy = legacy_cache.get(&tmdb_key);
            let imdb_id = legacy.and_then(|row| legacy_row_value(row, &["imdb_id", "IMDb ID", "IMDB ID"]));
            let release_year = item
                .get("release_date")
                .and_then(|v| v.as_str())
                .and_then(parse_year)
                .or_else(|| legacy.and_then(|row| legacy_row_value(row, &["Year", "year"])).and_then(|value| value.parse::<i32>().ok()));
            let rated_at = item
                .get("rated_at")
                .and_then(|v| v.as_str())
                .and_then(parse_datetime)
                .or_else(|| legacy.and_then(|row| legacy_row_value(row, &["Date Rated", "date"])).and_then(parse_datetime));
            let mut raw_json = item.clone();
            if let Some(row) = legacy {
                for (source_key, target_key) in [
                    ("imdb_id", "imdb_id"),
                    ("IMDb ID", "IMDb ID"),
                    ("Cover URL", "Cover URL"),
                    ("Genres", "Genres"),
                    ("Overview", "Overview"),
                    ("URL", "URL"),
                ] {
                    if raw_json.get(target_key).is_none() {
                        if let Some(value) = row.get(source_key).filter(|value| !value.trim().is_empty()) {
                            raw_json[target_key] = json!(value);
                        }
                    }
                }
            }

            records.push(MovieRecord {
                id: Uuid::new_v4().to_string(),
                platform: "tmdb".to_string(),
                title: item
                    .get("title")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Unknown title")
                    .to_string(),
                year: release_year,
                rating: item.get("rating").and_then(|v| v.as_f64()),
                rated_at,
                external_id: Some(tmdb_id.to_string()),
                source_url: Some(format!("https://www.themoviedb.org/movie/{tmdb_id}")),
                identifiers: MovieIdentifiers {
                    imdb: imdb_id.map(ToOwned::to_owned),
                    tmdb: Some(tmdb_id.to_string()),
                    trakt: None,
                    douban: None,
                    letterboxd: None,
                },
                raw_json,
            });
        }

        page += 1;
    }

    let count = records.len();
    Ok((
        FetchResult {
            platform: "tmdb".to_string(),
            item_count: count,
            stored_count: count,
        },
        records,
    ))
}

async fn fetch_tmdb_watchlist(config: &cinerecord_core::TmdbConfig) -> Result<(Value, Vec<WishlistRecord>)> {
    let client = tmdb_client(config)?;
    let account = client.fetch_account().await?;
    let account_id = account
        .get("id")
        .and_then(|v| v.as_i64())
        .context("TMDB account id missing")?;

    let payload = client.get_account_watchlist(account_id, 1).await?;
    let results = payload
        .get("results")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let items = results
        .iter()
        .map(|item| {
            let tmdb_id = item.get("id").and_then(|value| value.as_i64()).map(|value| value.to_string());
            WishlistRecord {
                id: Uuid::new_v4().to_string(),
                platform: "tmdb".to_string(),
                title: item
                    .get("title")
                    .or_else(|| item.get("name"))
                    .and_then(|value| value.as_str())
                    .unwrap_or("Unknown title")
                    .to_string(),
                year: item
                    .get("release_date")
                    .and_then(|value| value.as_str())
                    .and_then(parse_year),
                external_id: tmdb_id.clone(),
                source_url: tmdb_id
                    .as_ref()
                    .map(|id| format!("https://www.themoviedb.org/movie/{id}")),
                identifiers: MovieIdentifiers {
                    imdb: None,
                    tmdb: tmdb_id,
                    trakt: None,
                    douban: None,
                    letterboxd: None,
                },
                raw_json: item.clone(),
            }
        })
        .collect::<Vec<_>>();
    Ok((
        json!({
            "platform": "tmdb",
            "items": results,
            "item_count": items.len(),
            "stored_count": items.len(),
            "implemented": true
        }),
        items,
    ))
}

async fn fetch_trakt_movies(config: &cinerecord_core::TraktConfig) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let client = trakt_client(config)?;
    let items = client.get_all_movies_with_ratings("me").await?;
    let records = items
        .into_iter()
        .map(|item| {
            let trakt_ids = item.get("ids").cloned().unwrap_or_else(|| json!({}));
            let trakt_id = trakt_ids.get("trakt").and_then(|v| v.as_i64()).map(|v| v.to_string());
            let tmdb_id = trakt_ids.get("tmdb").and_then(|v| v.as_i64()).map(|v| v.to_string());
            let imdb_id = trakt_ids.get("imdb").and_then(|v| v.as_str()).map(ToOwned::to_owned);
            let movie = item.get("movie").cloned().unwrap_or_else(|| json!({}));
            let title = movie
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown title")
                .to_string();
            let year = movie
                .get("year")
                .and_then(|v| v.as_i64())
                .map(|v| v as i32);
            let rated_at = item.get("rated_at").and_then(|v| v.as_str()).and_then(parse_datetime);
            let watched_at = item.get("watched_at").and_then(|v| v.as_str()).and_then(parse_datetime);
            let source_url = trakt_ids
                .get("slug")
                .and_then(|v| v.as_str())
                .map(|slug| format!("https://trakt.tv/movies/{slug}"));
            MovieRecord {
                id: Uuid::new_v4().to_string(),
                platform: "trakt".to_string(),
                title,
                year,
                rating: item.get("rating").and_then(|v| v.as_f64()),
                rated_at: rated_at.or(watched_at),
                external_id: trakt_id.clone(),
                source_url,
                identifiers: MovieIdentifiers {
                    imdb: imdb_id,
                    tmdb: tmdb_id,
                    trakt: trakt_id,
                    douban: None,
                    letterboxd: None,
                },
                raw_json: item,
            }
        })
        .collect::<Vec<_>>();

    let count = records.len();
    Ok((
        FetchResult {
            platform: "trakt".to_string(),
            item_count: count,
            stored_count: count,
        },
        records,
    ))
}

async fn fetch_trakt_watchlist(config: &cinerecord_core::TraktConfig) -> Result<(Value, Vec<WishlistRecord>)> {
    let client = trakt_client(config)?;
    let response = client.get("users/me/watchlist/movies", None).await?;
    let records = response
        .as_array()
        .into_iter()
        .flatten()
        .map(|item| {
            let movie = item.get("movie").cloned().unwrap_or_else(|| json!({}));
            let ids = movie.get("ids").cloned().unwrap_or_else(|| json!({}));
            let trakt_id = ids.get("trakt").and_then(|value| value.as_i64()).map(|value| value.to_string());
            let tmdb_id = ids.get("tmdb").and_then(|value| value.as_i64()).map(|value| value.to_string());
            let imdb_id = ids.get("imdb").and_then(|value| value.as_str()).map(ToOwned::to_owned);
            let source_url = ids
                .get("slug")
                .and_then(|value| value.as_str())
                .map(|slug| format!("https://trakt.tv/movies/{slug}"));
            WishlistRecord {
                id: Uuid::new_v4().to_string(),
                platform: "trakt".to_string(),
                title: movie
                    .get("title")
                    .and_then(|value| value.as_str())
                    .unwrap_or("Unknown title")
                    .to_string(),
                year: movie.get("year").and_then(|value| value.as_i64()).map(|value| value as i32),
                external_id: trakt_id.clone(),
                source_url,
                identifiers: MovieIdentifiers {
                    imdb: imdb_id,
                    tmdb: tmdb_id,
                    trakt: trakt_id,
                    douban: None,
                    letterboxd: None,
                },
                raw_json: item.clone(),
            }
        })
        .collect::<Vec<_>>();
    Ok((
        json!({
            "platform": "trakt",
            "items": response,
            "item_count": records.len(),
            "stored_count": records.len(),
            "implemented": true
        }),
        records,
    ))
}

async fn sync_item_to_trakt(client: &TraktClient, item: &SyncPreviewItem) -> Result<SyncExecutionItem> {
    let mut ids = serde_json::Map::new();
    if let Some(imdb) = &item.identifiers.imdb {
        ids.insert("imdb".to_string(), json!(imdb));
    }
    if let Some(trakt) = &item.identifiers.trakt {
        ids.insert("trakt".to_string(), json!(trakt.parse::<i64>().unwrap_or_default()));
    }
    if let Some(tmdb) = &item.identifiers.tmdb {
        ids.insert("tmdb".to_string(), json!(tmdb.parse::<i64>().unwrap_or_default()));
    }
    if ids.is_empty() {
        return Ok(skipped_item(
            item,
            Some("No IMDb/Trakt/TMDB identifier available for Trakt sync".to_string()),
        ));
    }

    post_trakt_sync_with_retry(
        client,
        "/sync/history",
        json!({
            "movies": [{
                "ids": ids.clone()
            }]
        }),
    )
    .await?;

    if is_valid_rating(item.source_rating) {
        post_trakt_sync_with_retry(
            client,
            "/sync/ratings",
            json!({
                "movies": [{
                    "ids": ids,
                    "rating": item.source_rating.unwrap().round() as i64
                }]
            }),
        )
        .await?;
    }

    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.target_linking_id.clone(),
        target_url: item
            .identifiers
            .imdb
            .as_ref()
            .map(|imdb| format!("https://trakt.tv/search/imdb/{imdb}")),
        status: "success".to_string(),
        reason: None,
    })
}

async fn sync_item_to_tmdb(client: &TmdbClient, item: &SyncPreviewItem) -> Result<SyncExecutionItem> {
    let rating = item
        .source_rating
        .filter(|value| *value > 0.0)
        .context("TMDB requires a positive rating")?;
    let target_id = item
        .target_linking_id
        .clone()
        .context("Missing TMDB target identifier")?;
    let (tmdb_id, media_type) = if target_id.starts_with("tt") {
        client.find_by_imdb(&target_id).await?
    } else {
        (target_id.parse::<i64>()?, "movie".to_string())
    };

    let success = match media_type.as_str() {
        "tv" => client.rate_tv(tmdb_id, rating).await?,
        _ => client.rate_movie(tmdb_id, rating).await?,
    };
    if !success {
        return Ok(failed_item(item, "TMDB rating API returned unsuccessful response".to_string()));
    }

    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: Some(tmdb_id.to_string()),
        target_url: Some(format!(
            "https://www.themoviedb.org/{}/{tmdb_id}",
            if media_type == "tv" { "tv" } else { "movie" }
        )),
        status: "success".to_string(),
        reason: None,
    })
}

async fn sync_item_to_imdb(cookie_header: &str, item: &SyncPreviewItem) -> Result<SyncExecutionItem> {
    let rating = item
        .source_rating
        .filter(|value| *value > 0.0)
        .context("IMDb requires a positive rating")?;
    let imdb_id = item
        .target_linking_id
        .clone()
        .or_else(|| item.identifiers.imdb.clone())
        .context("Missing IMDb target identifier")?;
    rate_imdb_title(cookie_header, &imdb_id, rating).await?;
    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: Some(imdb_id.clone()),
        target_url: Some(format!("https://www.imdb.com/title/{imdb_id}/")),
        status: "success".to_string(),
        reason: None,
    })
}

async fn sync_item_to_douban(cookie_header: &str, item: &SyncPreviewItem) -> Result<SyncExecutionItem> {
    let douban_id = if let Some(target_id) = item.target_linking_id.clone() {
        if target_id.starts_with("tt") {
            search_douban_id_by_imdb(cookie_header, &target_id).await?
        } else {
            target_id
        }
    } else if let Some(douban_id) = item.identifiers.douban.clone() {
        douban_id
    } else if let Some(imdb_id) = item.identifiers.imdb.clone() {
        search_douban_id_by_imdb(cookie_header, &imdb_id).await?
    } else {
        return Ok(skipped_item(
            item,
            Some("No Douban or IMDb identifier available for Douban sync".to_string()),
        ));
    };

    mark_douban_collect(cookie_header, &douban_id, item.source_rating).await?;
    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: Some(douban_id.clone()),
        target_url: Some(format!("https://movie.douban.com/subject/{douban_id}/")),
        status: "success".to_string(),
        reason: None,
    })
}

fn trakt_client(config: &cinerecord_core::TraktConfig) -> Result<TraktClient> {
    Ok(TraktClient {
        client: Client::new(),
        client_id: config
            .client_id
            .clone()
            .filter(|value| !value.trim().is_empty())
            .context("Trakt client_id is required")?,
        client_secret: config
            .client_secret
            .clone()
            .filter(|value| !value.trim().is_empty())
            .context("Trakt client_secret is required")?,
        access_token: config.access_token.clone(),
        refresh_token: config.refresh_token.clone(),
    })
}

fn tmdb_client(config: &cinerecord_core::TmdbConfig) -> Result<TmdbClient> {
    Ok(TmdbClient {
        client: Client::new(),
        api_key: config
            .api_key
            .clone()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| DEFAULT_TMDB_API_KEY.to_string()),
        session_id: config.session_id.clone(),
    })
}

async fn test_cookie_platform(
    platform: &str,
    config: &cinerecord_core::CookiePlatformConfig,
) -> Result<PlatformValidationResult> {
    if platform == "douban" {
        if let Some(user_id) = config.user_id.as_deref().filter(|value| !value.trim().is_empty()) {
            if let Some(cookie) = config.cookie.as_deref().filter(|value| !value.trim().is_empty()) {
                return match validate_cookie_platform("douban", cookie, Some(user_id)).await {
                    Ok(result) => Ok(result),
                    Err(_) => validate_douban_public_profile(user_id, None).await,
                };
            }
            return validate_douban_public_profile(user_id, None).await;
        }
        if config.cookie.as_deref().is_none_or(|value| value.trim().is_empty()) {
            return Ok(PlatformValidationResult {
                platform: "douban".to_string(),
                success: false,
                message: "请填写 Douban User ID，Cookie 只在需要写入/同步到豆瓣时才必需".to_string(),
                profile: None,
            });
        }
    }
    let Some(cookie) = config.cookie.as_deref().filter(|value| !value.trim().is_empty()) else {
        return Ok(PlatformValidationResult {
            platform: platform.to_string(),
            success: false,
            message: if platform == "imdb" {
                format!("{} cookie 未配置", platform_display_name(platform))
            } else {
                "请填写 Douban User ID 或 Cookie".to_string()
            },
            profile: None,
        });
    };
    validate_cookie_platform(platform, cookie, config.user_id.as_deref()).await
}

async fn validate_douban_public_profile(user_id: &str, cookie: Option<&str>) -> Result<PlatformValidationResult> {
    let snapshot = fetch_douban_public_snapshot(user_id, cookie).await?;
    let display_name = snapshot.display_name.clone().unwrap_or_else(|| user_id.to_string());
    let success = snapshot.watched_total.is_some() || snapshot.wish_total.is_some();
    Ok(PlatformValidationResult {
        platform: "douban".to_string(),
        success,
        message: if success {
            format!(
                "豆瓣已验证 · 用户 {display_name} · 可读取公开数据（看过 {} · 想看 {}）",
                snapshot.watched_total.unwrap_or(0),
                snapshot.wish_total.unwrap_or(0)
            )
        } else {
            format!("豆瓣页面当前返回受限内容，暂时没能读取到 {display_name} 的电影统计")
        },
        profile: Some(json!({
            "user_id": user_id,
            "display_name": snapshot.display_name,
            "avatar": snapshot.avatar,
            "fetch_verified": true,
            "watched_total": snapshot.watched_total,
            "wish_total": snapshot.wish_total,
            "watched": snapshot.watched_total,
            "wish": snapshot.wish_total,
            "sample_title": snapshot.sample_title,
            "profile_link": format!("https://movie.douban.com/people/{user_id}/"),
            "read_mode": if cookie.is_some() { "public+cookie" } else { "public" },
            "write_cookie_required": true
        })),
    })
}

async fn validate_douban_cookie(
    cookie_header: &str,
    user_id: Option<&str>,
    cookie_names: Vec<String>,
) -> Result<PlatformValidationResult> {
    let client = Client::new();
    let response = client
        .get("https://www.douban.com/mine/")
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .send()
        .await?;
    let final_url = response.url().to_string();
    let body = response.text().await.unwrap_or_default();
    let resolved_user_id = extract_douban_user_id(&final_url)
        .or_else(|| extract_douban_user_id(&body))
        .or_else(|| user_id.map(ToOwned::to_owned));
    let login_ok = final_url.contains("/people/") && !final_url.contains("passport/login") && !final_url.contains("/sorry");
    let mut display_name = extract_douban_display_name(&body);
    let mut watched_total = None::<i64>;
    let mut wish_total = None::<i64>;
    let mut sample_title = None::<String>;
    let mut profile_link = resolved_user_id
        .as_ref()
        .map(|user_id| format!("https://movie.douban.com/people/{user_id}/"));
    let mut avatar = extract_douban_avatar(&body);
    let mut fetch_verified = false;

    if login_ok {
        if let Some(user_id) = resolved_user_id.as_deref() {
            if let Ok(profile_response) = client
                .get(format!("https://www.douban.com/people/{user_id}/"))
                .header("Cookie", cookie_header)
                .header("User-Agent", browser_user_agent())
                .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                .send()
                .await
            {
                let profile_html = profile_response.text().await.unwrap_or_default();
                display_name = display_name.or_else(|| extract_douban_display_name(&profile_html));
                avatar = avatar.or_else(|| extract_douban_avatar(&profile_html));
            }

            if let Ok(movie_response) = client
                .get(format!("https://movie.douban.com/people/{user_id}/"))
                .header("Cookie", cookie_header)
                .header("User-Agent", browser_user_agent())
                .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
                .send()
                .await
            {
                let movie_html = movie_response.text().await.unwrap_or_default();
                watched_total = extract_html_counter(&movie_html, "/collect").or(watched_total);
                wish_total = extract_html_counter(&movie_html, "/wish").or(wish_total);
            }

            if profile_link.is_none() {
                profile_link = Some(format!("https://movie.douban.com/people/{user_id}/"));
            }
        }
    }

    if let Some(user_id) = resolved_user_id.as_deref() {
        if let Ok(probe) = fetch_douban_interest_probe(&client, cookie_header, user_id, "done").await {
            watched_total = probe.total.or(watched_total);
            sample_title = probe.sample_title.or(sample_title);
            fetch_verified = true;
        }
        if let Ok(probe) = fetch_douban_interest_probe(&client, cookie_header, user_id, "mark").await {
            wish_total = probe.total.or(wish_total);
            fetch_verified = true;
        }
        if profile_link.is_none() {
            profile_link = Some(format!("https://movie.douban.com/people/{user_id}/"));
        }
    }

    let public_snapshot = if let Some(user_id) = resolved_user_id.as_deref() {
        fetch_douban_public_snapshot(user_id, Some(cookie_header)).await.ok()
    } else {
        None
    };
    watched_total = public_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.watched_total)
        .or(watched_total);
    wish_total = public_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.wish_total)
        .or(wish_total);
    display_name = public_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.display_name.clone())
        .or(display_name);
    avatar = public_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.avatar.clone())
        .or(avatar);
    sample_title = public_snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.sample_title.clone())
        .or(sample_title);

    if display_name
        .as_deref()
        .is_some_and(|value| value.contains("禁止访问") || value.contains("访问受限"))
    {
        display_name = resolved_user_id.clone();
    }
    if avatar
        .as_deref()
        .is_some_and(|value| value.contains("new_menu.gif"))
    {
        avatar = None;
    }

    let public_fetch_verified = watched_total.is_some() || wish_total.is_some();
    let success = public_fetch_verified || (login_ok && fetch_verified);
    let identity = display_name
        .clone()
        .or_else(|| resolved_user_id.clone())
        .unwrap_or_else(|| "当前账户".to_string());
    let message = if success {
        format!(
            "豆瓣已验证 · 用户 {identity} · 可读取数据（看过 {} · 想看 {}）",
            watched_total.unwrap_or(0),
            wish_total.unwrap_or(0)
        )
    } else if fetch_verified {
        "豆瓣 Cookie 可读取电影数据，但主页请求被限制；抓取仍可继续".to_string()
    } else if login_ok {
        "豆瓣登录已建立，但还没验证到可读取电影数据；请确认 Cookie 和账号页权限".to_string()
    } else {
        format!("豆瓣 Cookie 无效或已过期 · final_url={final_url}")
    };

    Ok(PlatformValidationResult {
        platform: "douban".to_string(),
        success,
        message,
        profile: Some(json!({
            "user_id": resolved_user_id,
            "final_url": final_url,
            "display_name": display_name,
            "avatar": avatar,
            "cookie_names": cookie_names,
            "fetch_verified": success,
            "watched_total": watched_total,
            "wish_total": wish_total,
            "watched": watched_total,
            "wish": wish_total,
            "sample_title": sample_title,
            "profile_link": profile_link,
            "read_mode": "public+cookie",
            "write_cookie_required": true
        })),
    })
}

async fn validate_imdb_cookie(
    cookie_header: &str,
    user_id: Option<&str>,
    cookie_names: Vec<String>,
) -> Result<PlatformValidationResult> {
    let client = Client::new();
    let payload = json!({
        "operationName": "userRatings",
        "variables": { "first": 1, "after": null },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
            }
        }
    });
    let response = client
        .post("https://api.graphql.imdb.com/")
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept-Language", "en-US,en;q=0.9")
        .json(&payload)
        .send()
        .await?;
    let status = response.status();
    let data: Value = response.json().await.unwrap_or_else(|_| json!({}));
    let ratings_total = data
        .get("data")
        .and_then(|value| value.get("userRatings"))
        .and_then(|value| value.get("total"))
        .and_then(|value| value.as_i64());
    let sample_rating = data
        .get("data")
        .and_then(|value| value.get("userRatings"))
        .and_then(|value| value.get("edges"))
        .and_then(|value| value.as_array())
        .and_then(|items| items.first())
        .and_then(|edge| edge.get("node"))
        .and_then(|node| node.get("rating"))
        .and_then(|value| value.as_f64());
    let sample_title = data
        .get("data")
        .and_then(|value| value.get("userRatings"))
        .and_then(|value| value.get("edges"))
        .and_then(|value| value.as_array())
        .and_then(|items| items.first())
        .and_then(extract_imdb_title_from_edge);

    let mut resolved_user_id = user_id
        .map(ToOwned::to_owned)
        .or_else(|| extract_imdb_user_id_from_cookie(cookie_header));
    let mut profile_url = None::<String>;
    let mut watchlist_total = None::<i64>;
    let mut display_name = None::<String>;
    let mut avatar = None::<String>;
    if resolved_user_id.is_none() {
        let page = client
            .get("https://www.imdb.com/list/watchlist/")
            .header("Cookie", cookie_header)
            .header("User-Agent", browser_user_agent())
            .header("Accept-Language", "en-US,en;q=0.9")
            .send()
            .await?;
        let final_url = page.url().to_string();
        let body = page.text().await.unwrap_or_default();
        resolved_user_id = extract_imdb_user_id(&final_url).or_else(|| extract_imdb_user_id(&body));
        profile_url = Some(final_url);
        watchlist_total = extract_number_before_keyword(&body, "titles");
    }

    if let Some(user_id) = resolved_user_id.as_deref() {
        let profile_page = client
            .get(format!("https://www.imdb.com/user/{user_id}/"))
            .header("Cookie", cookie_header)
            .header("User-Agent", browser_user_agent())
            .header("Accept-Language", "en-US,en;q=0.9")
            .send()
            .await;
        if let Ok(response) = profile_page {
            let final_url = response.url().to_string();
            let body = response.text().await.unwrap_or_default();
            profile_url = Some(final_url);
            display_name = extract_imdb_display_name(&body);
            avatar = extract_imdb_avatar(&body);
        }

        let watchlist_page = client
            .get(format!("https://www.imdb.com/user/{user_id}/watchlist/"))
            .header("Cookie", cookie_header)
            .header("User-Agent", browser_user_agent())
            .header("Accept-Language", "en-US,en;q=0.9")
            .send()
            .await;
        if let Ok(response) = watchlist_page {
            let body = response.text().await.unwrap_or_default();
            watchlist_total = extract_number_before_keyword(&body, "titles").or(watchlist_total);
        }
    }

    let fetch_verified = status == StatusCode::OK && ratings_total.is_some();
    let success = fetch_verified;
    let identity = display_name
        .clone()
        .or_else(|| resolved_user_id.clone())
        .unwrap_or_else(|| "当前账户".to_string());
    let message = if success {
        match ratings_total {
            Some(total) => format!("IMDb 已验证 · 用户 {identity} · 可读取评分数据 ({total} 条)"),
            None => format!("IMDb 已验证 · 用户 {identity}"),
        }
    } else {
        format!("IMDb Cookie 无效或未能读取评分数据 · graphql status={status}")
    };

    Ok(PlatformValidationResult {
        platform: "imdb".to_string(),
        success,
        message,
        profile: Some(json!({
            "user_id": resolved_user_id,
            "ratings_total": ratings_total,
            "sample_title": sample_title,
            "sample_rating": sample_rating,
            "cookie_names": cookie_names,
            "profile_url": profile_url,
            "profile_link": profile_url,
            "display_name": display_name,
            "avatar": avatar,
            "watchlist_total": watchlist_total,
            "ratings": ratings_total,
            "watchlist": watchlist_total,
            "fetch_verified": fetch_verified
        })),
    })
}

async fn fetch_imdb_rated_movies(
    config: &cinerecord_core::CookiePlatformConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let cookie = config
        .cookie
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .context("IMDb Cookie is required for ratings fetch")?;
    let client = Client::new();
    let mut after = None::<String>;
    let mut records = Vec::new();

    loop {
        let payload = imdb_user_ratings_page(&client, cookie, after.as_deref(), 200).await?;
        let ratings = payload
            .get("data")
            .and_then(|value| value.get("userRatings"))
            .cloned()
            .unwrap_or_else(|| json!({}));
        let edges = ratings
            .get("edges")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if edges.is_empty() {
            break;
        }

        for edge in edges {
            let node = edge.get("node").cloned().unwrap_or_else(|| json!({}));
            let title = node.get("title").cloned().unwrap_or_else(|| json!({}));
            let imdb_id = title
                .get("id")
                .and_then(|value| value.as_str())
                .context("IMDb title id missing in ratings edge")?;
            let title_text = title
                .get("titleText")
                .and_then(|value| value.get("text"))
                .and_then(|value| value.as_str())
                .unwrap_or("Unknown title")
                .to_string();
            let year = title
                .get("releaseYear")
                .and_then(|value| value.get("year"))
                .and_then(|value| value.as_i64())
                .map(|value| value as i32);
            let poster = title
                .get("primaryImage")
                .and_then(|value| value.get("url"))
                .and_then(|value| value.as_str())
                .map(ToOwned::to_owned);
            let user_rating = node
                .get("userRating")
                .and_then(|value| value.get("value"))
                .and_then(|value| value.as_f64());
            let rated_at = node
                .get("userRating")
                .and_then(|value| value.get("date"))
                .and_then(|value| value.as_str())
                .and_then(parse_datetime);
            records.push(MovieRecord {
                id: Uuid::new_v4().to_string(),
                platform: "imdb".to_string(),
                title: title_text,
                year,
                rating: user_rating,
                rated_at,
                external_id: Some(imdb_id.to_string()),
                source_url: Some(format!("https://www.imdb.com/title/{imdb_id}/")),
                identifiers: MovieIdentifiers {
                    imdb: Some(imdb_id.to_string()),
                    tmdb: None,
                    trakt: None,
                    douban: None,
                    letterboxd: None,
                },
                raw_json: json!({
                    "Const": imdb_id,
                    "Title": title.get("titleText").and_then(|value| value.get("text")).and_then(|value| value.as_str()),
                    "Year": year,
                    "Cover URL": poster,
                    "primaryImage": title.get("primaryImage"),
                    "Your Rating": user_rating,
                    "Date Rated": node.get("userRating").and_then(|value| value.get("date")).and_then(|value| value.as_str()),
                    "URL": format!("https://www.imdb.com/title/{imdb_id}/")
                }),
            });
        }

        let page_info = ratings.get("pageInfo").cloned().unwrap_or_else(|| json!({}));
        let has_next = page_info
            .get("hasNextPage")
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        after = page_info
            .get("endCursor")
            .and_then(|value| value.as_str())
            .map(ToOwned::to_owned);
        if !has_next || after.is_none() {
            break;
        }
    }

    let count = records.len();
    Ok((
        FetchResult {
            platform: "imdb".to_string(),
            item_count: count,
            stored_count: count,
        },
        records,
    ))
}

async fn imdb_user_ratings_page(client: &Client, cookie_header: &str, after: Option<&str>, first: usize) -> Result<Value> {
    let payload = json!({
        "operationName": "userRatings",
        "variables": { "first": first, "after": after },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
            }
        }
    });
    let response = client
        .post("https://api.graphql.imdb.com/")
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept-Language", "en-US,en;q=0.9")
        .json(&payload)
        .send()
        .await?;
    let status = response.status();
    if status != StatusCode::OK {
        return Err(anyhow!("IMDb ratings graphql returned {status}"));
    }
    Ok(response.json().await.unwrap_or_else(|_| json!({})))
}

async fn fetch_imdb_watchlist(
    config: &cinerecord_core::CookiePlatformConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let cookie = config
        .cookie
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .context("IMDb Cookie is required for watchlist fetch")?;
    let user_id = config.user_id.as_deref().filter(|value| !value.trim().is_empty());
    let mut records = if let Some(user_id) = user_id {
        fetch_imdb_watchlist_from_base(cookie, &format!("https://www.imdb.com/user/{user_id}/watchlist/")).await?
    } else {
        Vec::new()
    };
    if records.is_empty() {
        records = fetch_imdb_watchlist_from_base(cookie, "https://www.imdb.com/list/watchlist/").await?;
    }
    let item_count = records.len();
    Ok((
        json!({
            "platform": "imdb",
            "item_count": item_count,
            "stored_count": item_count,
            "implemented": true
        }),
        records,
    ))
}

async fn fetch_imdb_watchlist_from_base(cookie_header: &str, base_url: &str) -> Result<Vec<WishlistRecord>> {
    let mut page = 1usize;
    let mut records = Vec::new();
    let mut seen = std::collections::HashSet::new();
    loop {
        let url = format!("{base_url}?sort=list_order,asc&mode=detail&page={page}");
        let output = Command::new("curl")
            .arg("-fsSL")
            .arg("--compressed")
            .arg("-A")
            .arg(browser_user_agent())
            .arg("-H")
            .arg(format!("Cookie: {cookie_header}"))
            .arg("-H")
            .arg("Accept-Language: en-US,en;q=0.9")
            .arg("-H")
            .arg("Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            .arg(&url)
            .output()
            .await?;
        if !output.status.success() {
            break;
        }
        let body = String::from_utf8_lossy(&output.stdout).to_string();
        let Some(payload) = extract_imdb_next_data(&body) else {
            break;
        };
        let page_items = extract_imdb_watchlist_records(&payload);
        if page_items.is_empty() {
            break;
        }
        let mut new_count = 0usize;
        for item in page_items {
            let Some(imdb_id) = item.external_id.clone() else {
                continue;
            };
            if !seen.insert(imdb_id) {
                continue;
            }
            new_count += 1;
            records.push(item);
        }
        if new_count == 0 {
            break;
        }
        page += 1;
        if page > 50 {
            break;
        }
    }
    Ok(records)
}

fn extract_imdb_next_data(html: &str) -> Option<Value> {
    let document = Html::parse_document(html);
    let selector = Selector::parse("script#__NEXT_DATA__").ok()?;
    let script = document.select(&selector).next()?;
    let payload = script.text().collect::<Vec<_>>().join("");
    serde_json::from_str(&payload).ok()
}

fn extract_imdb_watchlist_records(payload: &Value) -> Vec<WishlistRecord> {
    let mut records = Vec::new();
    let mut seen = std::collections::HashSet::new();
    traverse_imdb_watchlist_value(payload, &mut records, &mut seen, None, false, true);
    if records.is_empty() {
        traverse_imdb_watchlist_value(payload, &mut records, &mut seen, None, false, false);
    }
    records
}

fn traverse_imdb_watchlist_value(
    value: &Value,
    records: &mut Vec<WishlistRecord>,
    seen: &mut std::collections::HashSet<String>,
    date_added: Option<String>,
    in_list_context: bool,
    require_list_context: bool,
) {
    match value {
        Value::Object(map) => {
            let mut next_date_added = date_added.clone();
            for key in ["listItemCreatedAt", "createdAt", "created", "dateAdded", "addedAt", "listItemCreated"] {
                if let Some(found) = map.get(key).and_then(|item| item.as_str()).filter(|item| !item.trim().is_empty()) {
                    next_date_added = Some(found.trim().to_string());
                    break;
                }
            }

            let list_context = in_list_context
                || [
                    "listItemId",
                    "listItem",
                    "listItemCreatedAt",
                    "listItemCreated",
                    "listItemRanking",
                    "listItemTitle",
                    "listItemRank",
                    "listItemTime",
                ]
                .iter()
                .any(|key| map.contains_key(*key));

            let title_candidate = if map.get("titleText").is_some()
                && (map.get("id").is_some() || map.get("titleId").is_some() || map.get("const").is_some())
            {
                Some(value)
            } else {
                map.get("title")
            };

            if let Some(title_value) = title_candidate {
                if !require_list_context || list_context {
                    if let Some(record) = imdb_watchlist_record_from_value(title_value, next_date_added.as_deref()) {
                        if let Some(imdb_id) = record.external_id.clone() {
                            if seen.insert(imdb_id) {
                                records.push(record);
                            }
                        }
                    }
                }
            }

            for child in map.values() {
                traverse_imdb_watchlist_value(child, records, seen, next_date_added.clone(), list_context, require_list_context);
            }
        }
        Value::Array(items) => {
            for item in items {
                traverse_imdb_watchlist_value(item, records, seen, date_added.clone(), in_list_context, require_list_context);
            }
        }
        _ => {}
    }
}

fn imdb_watchlist_record_from_value(value: &Value, date_added: Option<&str>) -> Option<WishlistRecord> {
    let imdb_id = value
        .get("id")
        .and_then(|item| item.as_str())
        .or_else(|| value.get("titleId").and_then(|item| item.as_str()))
        .or_else(|| value.get("const").and_then(|item| item.as_str()))?
        .to_string();
    let title = value
        .get("titleText")
        .and_then(|item| item.get("text"))
        .and_then(|item| item.as_str())
        .or_else(|| value.get("originalTitleText").and_then(|item| item.get("text")).and_then(|item| item.as_str()))
        .or_else(|| value.get("title").and_then(|item| item.as_str()))
        .unwrap_or("Unknown title")
        .to_string();
    let year = value
        .get("releaseYear")
        .and_then(|item| item.get("year"))
        .and_then(|item| item.as_i64())
        .map(|year| year as i32)
        .or_else(|| value.get("year").and_then(|item| item.as_i64()).map(|year| year as i32));
    let cover_url = value
        .get("primaryImage")
        .and_then(|item| item.get("url"))
        .and_then(|item| item.as_str())
        .or_else(|| value.get("image").and_then(|item| item.get("url")).and_then(|item| item.as_str()));
    let title_type = value
        .get("titleType")
        .map(|item| {
            item.get("id")
                .and_then(|inner| inner.as_str())
                .or_else(|| item.get("text").and_then(|inner| inner.as_str()))
                .or_else(|| item.as_str())
                .unwrap_or("")
                .to_string()
        })
        .filter(|item| !item.trim().is_empty());

    Some(WishlistRecord {
        id: Uuid::new_v4().to_string(),
        platform: "imdb".to_string(),
        title: title.clone(),
        year,
        external_id: Some(imdb_id.clone()),
        source_url: Some(format!("https://www.imdb.com/title/{imdb_id}/")),
        identifiers: MovieIdentifiers {
            imdb: Some(imdb_id.clone()),
            tmdb: None,
            trakt: None,
            douban: None,
            letterboxd: None,
        },
        raw_json: json!({
            "Const": imdb_id,
            "Title": title,
            "Year": year,
            "Cover URL": cover_url,
            "URL": format!("https://www.imdb.com/title/{imdb_id}/"),
            "status": "wish",
            "type": title_type,
            "Date Added": date_added,
        }),
    })
}

#[derive(Debug, Default)]
struct DoubanInterestProbe {
    total: Option<i64>,
    sample_title: Option<String>,
}

async fn fetch_douban_interest_probe(
    client: &Client,
    cookie_header: &str,
    user_id: &str,
    status: &str,
) -> Result<DoubanInterestProbe> {
    let response = client
        .get(format!(
            "https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
        ))
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept", "application/json, text/plain, */*")
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .header("Referer", format!("https://movie.douban.com/people/{user_id}/"))
        .query(&[
            ("type", "movie"),
            ("status", status),
            ("count", "1"),
            ("start", "0"),
            ("for_mobile", "1"),
        ])
        .send()
        .await?
        .error_for_status()?;
    let payload: Value = response.json().await?;
    Ok(DoubanInterestProbe {
        total: payload.get("total").and_then(|value| value.as_i64()),
        sample_title: payload
            .get("interests")
            .and_then(|value| value.as_array())
            .and_then(|items| items.first())
            .and_then(|item| item.get("subject"))
            .and_then(|subject| subject.get("title"))
            .and_then(|value| value.as_str())
            .map(ToOwned::to_owned),
    })
}

async fn fetch_douban_interest_page(
    client: &Client,
    cookie_header: &str,
    user_id: &str,
    status: &str,
    start: usize,
    count: usize,
) -> Result<Value> {
    let response = client
        .get(format!(
            "https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
        ))
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept", "application/json, text/plain, */*")
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .header("Referer", format!("https://movie.douban.com/people/{user_id}/"))
        .query(&[
            ("type", "movie"),
            ("status", status),
            ("count", &count.to_string()),
            ("start", &start.to_string()),
            ("for_mobile", "1"),
        ])
        .send()
        .await?
        .error_for_status()?;
    Ok(response.json().await?)
}

async fn fetch_douban_interest_movie_records(
    user_id: &str,
    cookie_header: &str,
    status: &str,
) -> Result<Vec<MovieRecord>> {
    let client = Client::new();
    let mut start = 0usize;
    let mut records = Vec::new();
    let mut seen = std::collections::HashSet::new();
    loop {
        let payload = fetch_douban_interest_page(&client, cookie_header, user_id, status, start, 50).await?;
        let interests = payload
            .get("interests")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if interests.is_empty() {
            break;
        }
        let mut new_count = 0usize;
        for interest in interests {
            let Some(record) = douban_movie_record_from_interest(&interest) else {
                continue;
            };
            let Some(key) = record.external_id.clone().or_else(|| record.identifiers.douban.clone()) else {
                continue;
            };
            if !seen.insert(key) {
                continue;
            }
            new_count += 1;
            records.push(record);
        }
        if new_count == 0 {
            break;
        }
        start += 50;
    }
    Ok(records)
}

async fn fetch_douban_interest_wishlist_records(
    user_id: &str,
    cookie_header: &str,
    status: &str,
) -> Result<Vec<WishlistRecord>> {
    let client = Client::new();
    let mut start = 0usize;
    let mut records = Vec::new();
    let mut seen = std::collections::HashSet::new();
    loop {
        let payload = fetch_douban_interest_page(&client, cookie_header, user_id, status, start, 50).await?;
        let interests = payload
            .get("interests")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if interests.is_empty() {
            break;
        }
        let mut new_count = 0usize;
        for interest in interests {
            let Some(record) = douban_wishlist_record_from_interest(&interest) else {
                continue;
            };
            let Some(key) = record.external_id.clone().or_else(|| record.identifiers.douban.clone()) else {
                continue;
            };
            if !seen.insert(key) {
                continue;
            }
            new_count += 1;
            records.push(record);
        }
        if new_count == 0 {
            break;
        }
        start += 50;
    }
    Ok(records)
}

fn douban_movie_record_from_interest(interest: &Value) -> Option<MovieRecord> {
    let subject = interest.get("subject")?;
    let subject_id = subject.get("id").and_then(|value| value.as_str()).map(ToOwned::to_owned);
    let title = subject
        .get("title")
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("Unknown title")
        .to_string();
    let year = subject
        .get("year")
        .and_then(|value| value.as_i64())
        .map(|value| value as i32)
        .or_else(|| extract_year_from_text(subject.get("card_subtitle").and_then(|value| value.as_str())));
    let rating = interest
        .get("rating")
        .and_then(|value| value.get("value"))
        .and_then(|value| value.as_f64())
        .map(|value| value * 2.0);
    let date = interest
        .get("create_time")
        .and_then(|value| value.as_str())
        .and_then(parse_date_only)
        .or_else(|| interest.get("create_time").and_then(|value| value.as_str()).and_then(parse_datetime));
    let source_url = subject
        .get("url")
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned)
        .or_else(|| subject_id.as_ref().map(|id| format!("https://movie.douban.com/subject/{id}/")));
    let poster = subject
        .get("pic")
        .and_then(|value| value.get("normal"))
        .and_then(|value| value.as_str())
        .or_else(|| subject.get("pic").and_then(|value| value.get("large")).and_then(|value| value.as_str()));

    Some(MovieRecord {
        id: Uuid::new_v4().to_string(),
        platform: "douban".to_string(),
        title,
        year,
        rating,
        rated_at: date,
        external_id: subject_id.clone(),
        source_url,
        identifiers: MovieIdentifiers {
            imdb: None,
            tmdb: None,
            trakt: None,
            douban: subject_id,
            letterboxd: None,
        },
        raw_json: json!({
            "subject": subject,
            "comment": interest.get("comment"),
            "date": interest.get("create_time"),
            "Your Rating": rating,
            "poster": poster,
            "status": interest.get("status"),
        }),
    })
}

fn douban_wishlist_record_from_interest(interest: &Value) -> Option<WishlistRecord> {
    let subject = interest.get("subject")?;
    let subject_id = subject.get("id").and_then(|value| value.as_str()).map(ToOwned::to_owned);
    let title = subject
        .get("title")
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("Unknown title")
        .to_string();
    let year = subject
        .get("year")
        .and_then(|value| value.as_i64())
        .map(|value| value as i32)
        .or_else(|| extract_year_from_text(subject.get("card_subtitle").and_then(|value| value.as_str())));
    let source_url = subject
        .get("url")
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned)
        .or_else(|| subject_id.as_ref().map(|id| format!("https://movie.douban.com/subject/{id}/")));
    let poster = subject
        .get("pic")
        .and_then(|value| value.get("normal"))
        .and_then(|value| value.as_str())
        .or_else(|| subject.get("pic").and_then(|value| value.get("large")).and_then(|value| value.as_str()));

    Some(WishlistRecord {
        id: Uuid::new_v4().to_string(),
        platform: "douban".to_string(),
        title,
        year,
        external_id: subject_id.clone(),
        source_url,
        identifiers: MovieIdentifiers {
            imdb: None,
            tmdb: None,
            trakt: None,
            douban: subject_id,
            letterboxd: None,
        },
        raw_json: json!({
            "subject": subject,
            "comment": interest.get("comment"),
            "date": interest.get("create_time"),
            "poster": poster,
            "status": interest.get("status"),
        }),
    })
}

fn browser_user_agent() -> &'static str {
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

fn douban_ck_from_cookie(cookie_header: &str) -> Option<String> {
    cookie_value_from_header(cookie_header, "ck").map(ToOwned::to_owned)
}

async fn rate_imdb_title(cookie_header: &str, imdb_id: &str, rating: f64) -> Result<()> {
    let normalized = rating.round().clamp(1.0, 10.0) as i64;
    let client = Client::new();
    let payload = json!({
        "query": "mutation UpdateTitleRating($rating: Int!, $titleId: ID!) { rateTitle(input: {rating: $rating, titleId: $titleId}) { rating { value } } }",
        "operationName": "UpdateTitleRating",
        "variables": {
            "rating": normalized,
            "titleId": imdb_id
        }
    });
    let mut last_error = None;
    for attempt in 0..3 {
        let response = client
            .post("https://api.graphql.imdb.com/")
            .header("Cookie", cookie_header)
            .header("User-Agent", browser_user_agent())
            .header("Accept-Language", "en-US,en;q=0.9")
            .header("Origin", "https://www.imdb.com")
            .header("Referer", format!("https://www.imdb.com/title/{imdb_id}/"))
            .json(&payload)
            .send()
            .await;

        match response {
            Ok(response) => {
                let response = response.error_for_status()?;
                let body: Value = response.json().await?;
                if let Some(errors) = body.get("errors").and_then(|value| value.as_array()) {
                    if !errors.is_empty() {
                        return Err(anyhow!("IMDb rateTitle returned GraphQL errors"));
                    }
                }
                return Ok(());
            }
            Err(error) => {
                last_error = Some(anyhow!(error.to_string()));
                if attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_millis(400 * (attempt as u64 + 1))).await;
                }
            }
        }
    }

    Err(last_error.unwrap_or_else(|| anyhow!("IMDb rating request failed")))
}

async fn search_douban_id_by_imdb(cookie_header: &str, imdb_id: &str) -> Result<String> {
    if let Some(cached) = douban_id_from_cache(imdb_id) {
        return Ok(cached);
    }
    let client = Client::new();
    let response = client
        .get("https://m.douban.com/rexxar/api/v2/search")
        .header("Cookie", cookie_header)
        .header("User-Agent", browser_user_agent())
        .header("Accept", "application/json, text/plain, */*")
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .query(&[
            ("query", imdb_id),
            ("type", "movie"),
            ("count", "1"),
        ])
        .send()
        .await?
        .error_for_status()?;
    let payload: Value = response.json().await?;
    payload
        .get("subjects")
        .and_then(|value| value.as_array())
        .and_then(|items| items.first())
        .and_then(|item| item.get("target_id"))
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned)
        .context("Douban search could not resolve target_id from IMDb ID")
}

fn douban_id_from_cache(imdb_id: &str) -> Option<String> {
    douban_imdb_cache()
        .iter()
        .find_map(|(douban_id, cached_imdb)| (cached_imdb == imdb_id).then(|| douban_id.clone()))
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
            let douban_id = row.get("douban_id").map(|value| value.trim()).unwrap_or_default();
            let imdb_id = row.get("imdb").map(|value| value.trim()).unwrap_or_default();
            if !douban_id.is_empty() && !imdb_id.is_empty() {
                map.insert(douban_id.to_string(), imdb_id.to_string());
            }
        }
        map
    })
}

fn tmdb_legacy_cache() -> &'static HashMap<String, HashMap<String, String>> {
    TMDB_LEGACY_CACHE.get_or_init(|| {
        let data_dir = match std::env::current_dir() {
            Ok(cwd) => cwd.join("data"),
            Err(_) => return HashMap::new(),
        };
        let entries = match std::fs::read_dir(data_dir) {
            Ok(entries) => entries,
            Err(_) => return HashMap::new(),
        };
        let mut map = HashMap::new();
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            if !file_name.starts_with("tmdb_") || !file_name.ends_with("_ratings.csv") {
                continue;
            }
            let Ok(mut reader) = csv::Reader::from_path(path) else {
                continue;
            };
            for row in reader.deserialize::<HashMap<String, String>>().flatten() {
                let tmdb_id = legacy_row_value(&row, &["tmdb_id", "TMDB ID"]);
                if let Some(tmdb_id) = tmdb_id.filter(|value| !value.is_empty()) {
                    map.entry(tmdb_id.to_string()).or_insert(row);
                }
            }
        }
        map
    })
}

fn legacy_row_value<'a>(row: &'a HashMap<String, String>, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .filter_map(|key| row.get(*key))
        .map(|value| value.trim())
        .find(|value| !value.is_empty())
}

async fn mark_douban_collect(cookie_header: &str, douban_id: &str, rating: Option<f64>) -> Result<()> {
    let ck = douban_ck_from_cookie(cookie_header).context("Douban ck token missing from cookie")?;
    let client = Client::new();
    let mut form = vec![
        ("ck", ck),
        ("interest", "collect".to_string()),
        ("foldcollect", "F".to_string()),
        ("tags", String::new()),
        ("comment", String::new()),
    ];
    if let Some(rating) = rating.filter(|value| *value > 0.0) {
        let stars = ((rating.round() as i64) + 1) / 2;
        form.push(("rating", stars.clamp(1, 5).to_string()));
    }
    let mut last_error = None;
    for attempt in 0..3 {
        let response = client
            .post(format!("https://movie.douban.com/j/subject/{douban_id}/interest"))
            .header("Cookie", cookie_header)
            .header("User-Agent", browser_user_agent())
            .header("Accept", "application/json, text/plain, */*")
            .header("Referer", format!("https://movie.douban.com/subject/{douban_id}/"))
            .form(&form)
            .send()
            .await;
        match response {
            Ok(response) => {
                let payload: Value = response.error_for_status()?.json().await?;
                let ok = payload.get("r").and_then(|value| value.as_i64()).unwrap_or(-1) == 0;
                if !ok {
                    return Err(anyhow!("Douban interest API returned unsuccessful response"));
                }
                return Ok(());
            }
            Err(error) => {
                last_error = Some(anyhow!(error.to_string()));
                if attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_millis(400 * (attempt as u64 + 1))).await;
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("Douban interest request failed")))
}

async fn post_trakt_sync_with_retry(client: &TraktClient, path: &str, body: Value) -> Result<Value> {
    let mut last_error = None;
    for attempt in 0..3 {
        match client.post(path, body.clone()).await {
            Ok(value) => return Ok(value),
            Err(error) => {
                last_error = Some(error);
                if attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_millis(400 * (attempt as u64 + 1))).await;
                }
            }
        }
    }
    Err(last_error.unwrap_or_else(|| anyhow!("Trakt sync request failed")))
}

fn platform_display_name(platform: &str) -> &'static str {
    match platform {
        "douban" => "Douban",
        "imdb" => "IMDb",
        "tmdb" => "TMDB",
        "trakt" => "Trakt",
        "letterboxd" => "Letterboxd",
        _ => "Platform",
    }
}

fn cookie_names_from_header(cookie_header: &str) -> Vec<String> {
    cookie_header
        .split(';')
        .filter_map(|part| part.split_once('=').map(|(name, _)| name.trim().to_string()))
        .filter(|name| !name.is_empty())
        .collect()
}

fn required_cookie_names(platform: &str) -> &'static [&'static str] {
    match platform {
        "douban" => COOKIECLOUD_REQUIRED_DOUBAN,
        "imdb" => COOKIECLOUD_REQUIRED_IMDB,
        _ => &[],
    }
}

fn allowed_cookie_names(platform: &str) -> Option<&'static [&'static str]> {
    match platform {
        "douban" => Some(COOKIECLOUD_ALLOWED_DOUBAN),
        "imdb" => Some(COOKIECLOUD_ALLOWED_IMDB),
        _ => None,
    }
}

fn platform_domain_keywords(platform: &str) -> Vec<&'static str> {
    match platform {
        "douban" => vec!["douban.com"],
        "imdb" => vec!["imdb.com", "amazon.com"],
        _ => Vec::new(),
    }
}

fn normalize_cookiecloud_host(host: &str) -> Result<String> {
    let host = host.trim();
    if host.is_empty() {
        return Err(anyhow!("CookieCloud host is required"));
    }
    let normalized = if host.starts_with("http://") || host.starts_with("https://") {
        host.to_string()
    } else {
        format!("http://{host}")
    };
    Ok(normalized.trim_end_matches('/').to_string())
}

async fn request_cookiecloud_payload(host: &str, uuid: &str, password: &str) -> Result<Value> {
    let url = format!("{host}/get/{uuid}");
    let response = Client::new()
        .get(url)
        .query(&[("password", password)])
        .send()
        .await?
        .error_for_status()?;
    let data: Value = response.json().await?;

    if data.get("cookie_data").is_some() {
        return Ok(data);
    }
    if let Some(payload) = data.get("data") {
        if payload.get("cookie_data").is_some() {
            return Ok(payload.clone());
        }
    }
    if let Some(encrypted) = data.get("encrypted").and_then(|value| value.as_str()) {
        return decrypt_cookiecloud_blob(uuid, password, encrypted);
    }

    Err(anyhow!("CookieCloud did not return cookie_data"))
}

fn decrypt_cookiecloud_blob(uuid: &str, password: &str, encrypted: &str) -> Result<Value> {
    let raw = BASE64
        .decode(encrypted)
        .map_err(|error| anyhow!("CookieCloud payload is not valid base64: {error}"))?;
    if raw.len() < 16 || &raw[..8] != b"Salted__" {
        return Err(anyhow!("CookieCloud encrypted payload has invalid Salted__ header"));
    }

    let salt = &raw[8..16];
    let ciphertext = &raw[16..];
    let passphrase = format!("{:x}", md5::compute(format!("{uuid}-{password}")))
        .chars()
        .take(16)
        .collect::<String>()
        .into_bytes();
    let (key, iv) = evp_bytes_to_key(&passphrase, salt, 32, 16);
    let mut buf = ciphertext.to_vec();
    let decrypted = cbc::Decryptor::<Aes256>::new_from_slices(&key, &iv)
        .map_err(|error| anyhow!("CookieCloud decrypt init failed: {error}"))?
        .decrypt_padded_mut::<Pkcs7>(&mut buf)
        .map_err(|error| anyhow!("CookieCloud decrypt failed: {error}"))?;
    let value: Value = serde_json::from_slice(decrypted)?;
    Ok(value)
}

fn evp_bytes_to_key(password: &[u8], salt: &[u8], key_len: usize, iv_len: usize) -> (Vec<u8>, Vec<u8>) {
    let mut output = Vec::with_capacity(key_len + iv_len);
    let mut previous = Vec::new();
    while output.len() < key_len + iv_len {
        let mut material = Vec::with_capacity(previous.len() + password.len() + salt.len());
        material.extend_from_slice(&previous);
        material.extend_from_slice(password);
        material.extend_from_slice(salt);
        previous = md5::compute(material).0.to_vec();
        output.extend_from_slice(&previous);
    }
    (output[..key_len].to_vec(), output[key_len..key_len + iv_len].to_vec())
}

fn extract_cookie_data(payload: &Value) -> Result<Value> {
    payload
        .get("cookie_data")
        .cloned()
        .context("CookieCloud payload missing cookie_data")
}

fn build_cookie_header(cookie_data: &Value, domain_keywords: &[&str], allowed_names: Option<&[&str]>) -> (String, usize) {
    let allowed = allowed_names.map(|items| items.iter().map(|item| item.to_ascii_lowercase()).collect::<Vec<_>>());
    let mut cookies = BTreeMap::new();
    let mut ordered_names = Vec::<String>::new();
    let mut matched = 0;

    for (domain, item) in iter_cookie_records(cookie_data) {
        let name = item
            .get("name")
            .and_then(|value| value.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        let value = item.get("value").and_then(|value| value.as_str()).unwrap_or_default();
        if name.is_empty() || value.is_empty() {
            continue;
        }

        let actual_domain = item
            .get("domain")
            .and_then(|value| value.as_str())
            .unwrap_or(&domain)
            .trim_start_matches('.')
            .to_ascii_lowercase();
        if !domain_keywords.is_empty() && !domain_keywords.iter().any(|keyword| actual_domain.contains(keyword)) {
            continue;
        }
        if let Some(allowed) = &allowed {
            if !allowed.iter().any(|candidate| candidate == &name.to_ascii_lowercase()) {
                continue;
            }
        }

        matched += 1;
        if !ordered_names.iter().any(|existing| existing == &name) {
            ordered_names.push(name.clone());
        }
        cookies.insert(name, value.to_string());
    }

    let header = ordered_names
        .into_iter()
        .filter_map(|name| cookies.get(&name).map(|value| format!("{name}={value}")))
        .collect::<Vec<_>>()
        .join("; ");
    (header, matched)
}

fn iter_cookie_records(cookie_data: &Value) -> Vec<(String, Value)> {
    match cookie_data {
        Value::Object(map) => map
            .iter()
            .flat_map(|(domain, value)| match value {
                Value::Array(items) => items
                    .iter()
                    .filter(|item| item.is_object())
                    .cloned()
                    .map(|item| (domain.clone(), item))
                    .collect::<Vec<_>>(),
                Value::Object(items) => items
                    .iter()
                    .map(|(name, value)| {
                        (
                            domain.clone(),
                            json!({
                                "name": name,
                                "value": value,
                                "domain": domain
                            }),
                        )
                    })
                    .collect::<Vec<_>>(),
                _ => Vec::new(),
            })
            .collect(),
        Value::Array(items) => items
            .iter()
            .filter_map(|item| {
                item.get("domain")
                    .and_then(|value| value.as_str())
                    .map(|domain| (domain.to_string(), item.clone()))
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn extract_douban_user_id(text: &str) -> Option<String> {
    extract_path_fragment(text, "/people/", &['/', '"', '?', '\''])
}

fn extract_imdb_user_id(text: &str) -> Option<String> {
    extract_path_fragment(text, "/user/", &['/', '"', '?', '\'', '&'])
        .filter(|value| value.starts_with("ur"))
}

fn extract_imdb_user_id_from_cookie(cookie_header: &str) -> Option<String> {
    let encoded = cookie_value_from_header(cookie_header, "uu")?;
    let decoded = BASE64.decode(encoded).ok()?;
    let payload: Value = serde_json::from_slice(&decoded).ok()?;
    payload
        .get("uc")
        .and_then(|value| value.as_str())
        .filter(|value| value.starts_with("ur"))
        .map(ToOwned::to_owned)
}

fn extract_douban_display_name(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    let title = text_for_first_selector(&document, &["title"])?;
    let trimmed = title
        .trim()
        .trim_end_matches("的电影主页")
        .trim_end_matches("的主页")
        .trim_end_matches("的首页")
        .trim();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed.to_string())
    }
}

fn extract_imdb_display_name(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    text_for_first_selector(&document, &["h1 span", "h1"]).map(|value| value.trim().to_string())
}

fn extract_douban_avatar(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    attr_for_first_selector(
        &document,
        &[".userface img", ".side-info-avatar img", ".pic img", "img[alt][src]"],
        "src",
    )
    .map(normalize_image_url)
}

fn extract_imdb_avatar(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    meta_content(
        &document,
        &["meta[property=\"og:image\"]", "meta[name=\"twitter:image\"]"],
        "content",
    )
    .or_else(|| attr_for_first_selector(&document, &["img.ipc-image", "img[srcset]", "img[src]"], "src"))
}

fn extract_trakt_avatar(profile: &Value) -> Option<String> {
    value_at_path(profile, &["images", "avatar", "full"])
        .and_then(|value| value.as_str())
        .or_else(|| value_at_path(profile, &["images", "avatar", "medium"]).and_then(|value| value.as_str()))
        .or_else(|| value_at_path(profile, &["images", "avatar", "thumb"]).and_then(|value| value.as_str()))
        .map(ToOwned::to_owned)
}

fn extract_tmdb_avatar(account: &Value) -> Option<String> {
    if let Some(path) = value_at_path(account, &["avatar", "tmdb", "avatar_path"]).and_then(|value| value.as_str()) {
        return Some(format!("https://image.tmdb.org/t/p/w185{path}"));
    }
    value_at_path(account, &["avatar", "gravatar", "hash"])
        .and_then(|value| value.as_str())
        .map(|hash| format!("https://www.gravatar.com/avatar/{hash}?s=200&d=retro"))
}

fn text_for_first_selector(document: &Html, selectors: &[&str]) -> Option<String> {
    selectors.iter().find_map(|selector| {
        let selector = Selector::parse(selector).ok()?;
        let text = document
            .select(&selector)
            .next()?
            .text()
            .collect::<Vec<_>>()
            .join(" ")
            .trim()
            .to_string();
        if text.is_empty() {
            None
        } else {
            Some(text)
        }
    })
}

fn attr_for_first_selector(document: &Html, selectors: &[&str], attr: &str) -> Option<String> {
    selectors.iter().find_map(|selector| {
        let selector = Selector::parse(selector).ok()?;
        document
            .select(&selector)
            .next()
            .and_then(|element| element.value().attr(attr))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
    })
}

fn meta_content(document: &Html, selectors: &[&str], attr: &str) -> Option<String> {
    attr_for_first_selector(document, selectors, attr)
}

fn normalize_image_url(url: String) -> String {
    if url.starts_with("//") {
        format!("https:{url}")
    } else {
        url
    }
}

fn extract_html_counter(html: &str, marker: &str) -> Option<i64> {
    let start = html.find(marker)?;
    let segment = &html[start..html.len().min(start + 200)];
    let digit_start = segment.find(|character: char| character.is_ascii_digit())?;
    let digits: String = segment[digit_start..]
        .chars()
        .take_while(|character| character.is_ascii_digit())
        .collect();
    digits.parse::<i64>().ok()
}

fn extract_number_before_keyword(text: &str, keyword: &str) -> Option<i64> {
    let keyword_index = text.find(keyword)?;
    let prefix = &text[..keyword_index];
    let digits: String = prefix
        .chars()
        .rev()
        .skip_while(|character| !character.is_ascii_digit())
        .take_while(|character| character.is_ascii_digit())
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    if digits.is_empty() {
        None
    } else {
        digits.parse::<i64>().ok()
    }
}

fn extract_imdb_title_from_edge(edge: &Value) -> Option<String> {
    let node = edge.get("node")?;
    for path in [
        ["title", "titleText", "text"].as_slice(),
        ["title", "primaryText", "text"].as_slice(),
        ["title", "primary_title", "text"].as_slice(),
        ["titleText", "text"].as_slice(),
    ] {
        if let Some(title) = value_at_path(node, path).and_then(|value| value.as_str()) {
            if !title.trim().is_empty() {
                return Some(title.trim().to_string());
            }
        }
    }
    None
}

fn value_at_path<'a>(value: &'a Value, path: &[&str]) -> Option<&'a Value> {
    let mut current = value;
    for segment in path {
        current = current.get(*segment)?;
    }
    Some(current)
}

fn extract_path_fragment(text: &str, marker: &str, terminators: &[char]) -> Option<String> {
    let start = text.find(marker)? + marker.len();
    let rest = &text[start..];
    let end = rest.find(|character| terminators.contains(&character)).unwrap_or(rest.len());
    let value = rest[..end].trim();
    if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

fn cookie_value_from_header<'a>(cookie_header: &'a str, key: &str) -> Option<&'a str> {
    cookie_header.split(';').find_map(|part| {
        let (name, value) = part.trim().split_once('=')?;
        if name.trim() == key {
            Some(value.trim())
        } else {
            None
        }
    })
}

fn current_platform_cookie_config<'a>(config: &'a AppConfig, platform: &str) -> &'a cinerecord_core::CookiePlatformConfig {
    match platform {
        "douban" => &config.platforms.douban,
        "imdb" => &config.platforms.imdb,
        _ => &config.platforms.imdb,
    }
}

fn current_platform_cookie_config_mut<'a>(
    config: &'a mut AppConfig,
    platform: &str,
) -> Result<&'a mut cinerecord_core::CookiePlatformConfig> {
    match platform {
        "douban" => Ok(&mut config.platforms.douban),
        "imdb" => Ok(&mut config.platforms.imdb),
        other => Err(anyhow!("unsupported cookie platform: {other}")),
    }
}

fn identifier_keys(item: &MovieRecord) -> Vec<String> {
    let mut keys = Vec::new();
    if let Some(imdb) = &item.identifiers.imdb {
        keys.push(format!("imdb:{imdb}"));
    }
    if let Some(tmdb) = &item.identifiers.tmdb {
        keys.push(format!("tmdb:{tmdb}"));
    }
    if let Some(trakt) = &item.identifiers.trakt {
        keys.push(format!("trakt:{trakt}"));
    }
    if let Some(douban) = &item.identifiers.douban {
        keys.push(format!("douban:{douban}"));
    }
    if let Some(letterboxd) = &item.identifiers.letterboxd {
        keys.push(format!("letterboxd:{letterboxd}"));
    }
    keys
}

fn resolve_target_linking_id(target: &str, ids: &MovieIdentifiers) -> Option<String> {
    match target {
        "trakt" => ids
            .trakt
            .clone()
            .or_else(|| ids.imdb.clone())
            .or_else(|| ids.tmdb.clone()),
        "tmdb" => ids.tmdb.clone().or_else(|| ids.imdb.clone()),
        "imdb" => ids.imdb.clone(),
        "douban" => ids.douban.clone().or_else(|| ids.imdb.clone()),
        "letterboxd" => ids.letterboxd.clone().or_else(|| ids.imdb.clone()),
        _ => None,
    }
}

fn parse_direction(direction: &str) -> Result<(&str, &str)> {
    direction
        .split_once("-to-")
        .ok_or_else(|| anyhow!("invalid sync direction: {direction}"))
}

fn parse_year(value: &str) -> Option<i32> {
    value.split('-').next()?.parse::<i32>().ok()
}

fn extract_year_from_text(value: Option<&str>) -> Option<i32> {
    let text = value?;
    let chars: Vec<char> = text.chars().collect();
    if chars.len() < 4 {
        return None;
    }
    for index in 0..=chars.len().saturating_sub(4) {
        let candidate = chars[index..index + 4].iter().collect::<String>();
        if let Ok(year) = candidate.parse::<i32>() {
            if (1900..=2100).contains(&year) {
                return Some(year);
            }
        }
    }
    None
}

fn parse_datetime(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            DateTime::parse_from_str(value, "%Y-%m-%dT%H:%M:%S%.fZ")
                .ok()
                .map(|dt| dt.with_timezone(&Utc))
        })
}

fn parse_date_only(value: &str) -> Option<DateTime<Utc>> {
    chrono::NaiveDate::parse_from_str(value.trim(), "%Y-%m-%d")
        .ok()
        .and_then(|date| date.and_hms_opt(0, 0, 0))
        .map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
}

#[derive(Debug, Clone)]
struct DoubanPublicItem {
    title: String,
    year: Option<i32>,
    rating: Option<f64>,
    rated_at: Option<DateTime<Utc>>,
    date: Option<String>,
    intro: Option<String>,
    comment: Option<String>,
    subject_id: Option<String>,
    source_url: Option<String>,
    poster: Option<String>,
}

async fn fetch_douban_public_page_html(
    _client: &Client,
    user_id: &str,
    path: &str,
    start: usize,
    cookie: Option<&str>,
) -> Result<String> {
    let mut url = if path.is_empty() {
        format!("https://movie.douban.com/people/{user_id}/")
    } else {
        format!("https://movie.douban.com/people/{user_id}/{path}")
    };
    if path == "collect" || path == "wish" {
        url = format!("{url}?start={start}&sort=time&rating=all&filter=all&mode=grid");
    }

    let mut command = Command::new("curl");
    command
        .arg("-fsSL")
        .arg("--compressed")
        .arg("-A")
        .arg(browser_user_agent())
        .arg("-H")
        .arg("Accept-Language: zh-CN,zh;q=0.9,en;q=0.8")
        .arg("-H")
        .arg("Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        .arg("-e")
        .arg(format!("https://movie.douban.com/people/{user_id}/"));
    if let Some(cookie) = cookie.filter(|value| !value.trim().is_empty()) {
        command.arg("-H").arg(format!("Cookie: {cookie}"));
    }
    let output = command.arg(&url).output().await?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        if stderr.contains("403") {
            return Err(anyhow!(
                "Douban 公开页面当前触发了 sec.douban.com 风控；按逻辑 user_id 足够读取公开数据，但这个网络环境暂时被拦截"
            ));
        }
        return Err(anyhow!("curl failed for Douban public page: {stderr}"));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

fn parse_douban_public_movies_page(html: &str) -> Result<Vec<DoubanPublicItem>> {
    let document = Html::parse_document(html);
    let item_selector = Selector::parse(".grid-view .item").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let title_selector = Selector::parse("li.title a").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let intro_selector = Selector::parse("li.intro").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let date_selector = Selector::parse("span.date").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let comment_selector = Selector::parse("span.comment").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let poster_selector = Selector::parse(".pic img").map_err(|error| anyhow!("selector parse failed: {error}"))?;
    let rating_selector = Selector::parse("span").map_err(|error| anyhow!("selector parse failed: {error}"))?;

    let mut items = Vec::new();
    for item in document.select(&item_selector) {
        let title_link = item.select(&title_selector).next();
        let title = title_link
            .as_ref()
            .map(|element| element.text().collect::<Vec<_>>().join(" "))
            .map(|value| normalize_whitespace(&value))
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "Unknown title".to_string());
        let source_url = title_link
            .as_ref()
            .and_then(|element| element.value().attr("href"))
            .map(ToOwned::to_owned);
        let subject_id = source_url
            .as_deref()
            .and_then(|url| extract_path_fragment(url, "/subject/", &['/', '?']));
        let intro = item
            .select(&intro_selector)
            .next()
            .map(|element| normalize_whitespace(&element.text().collect::<Vec<_>>().join(" ")));
        let date = item
            .select(&date_selector)
            .next()
            .map(|element| normalize_whitespace(&element.text().collect::<Vec<_>>().join(" ")));
        let comment = item
            .select(&comment_selector)
            .next()
            .map(|element| normalize_whitespace(&element.text().collect::<Vec<_>>().join(" ")));
        let poster = item
            .select(&poster_selector)
            .next()
            .and_then(|element| element.value().attr("src"))
            .map(ToOwned::to_owned);
        let rating = item
            .select(&rating_selector)
            .find_map(|element| element.value().attr("class"))
            .and_then(parse_douban_rating_from_class);

        items.push(DoubanPublicItem {
            title,
            year: intro.as_deref().and_then(extract_first_year),
            rating,
            rated_at: date.as_deref().and_then(parse_date_only),
            date,
            intro,
            comment,
            subject_id,
            source_url,
            poster,
        });
    }
    Ok(items)
}

fn extract_douban_page_total(html: &str) -> Option<i64> {
    let title = extract_between(html, "<title>", "</title>")?;
    extract_number_in_parentheses(&title)
}

fn douban_page_has_next(html: &str) -> bool {
    html.contains("class=\"next\"") && html.contains("href=")
}

fn parse_douban_rating_from_class(class_attr: &str) -> Option<f64> {
    for class_name in class_attr.split_whitespace() {
        if let Some(number) = class_name
            .strip_prefix("rating")
            .and_then(|value| value.strip_suffix("-t"))
            .and_then(|value| value.parse::<i64>().ok())
        {
            return Some((number as f64) * 2.0);
        }
    }
    None
}

fn extract_first_year(text: &str) -> Option<i32> {
    let chars = text.as_bytes();
    for window in chars.windows(4) {
        if window.iter().all(|ch| ch.is_ascii_digit()) {
            let year = std::str::from_utf8(window).ok()?.parse::<i32>().ok()?;
            if (1888..=2099).contains(&year) {
                return Some(year);
            }
        }
    }
    None
}

fn normalize_whitespace(text: &str) -> String {
    text.split_whitespace().collect::<Vec<_>>().join(" ").trim().to_string()
}

fn extract_between(text: &str, start_marker: &str, end_marker: &str) -> Option<String> {
    let start = text.find(start_marker)? + start_marker.len();
    let rest = &text[start..];
    let end = rest.find(end_marker)?;
    Some(normalize_whitespace(&rest[..end]))
}

fn extract_number_in_parentheses(text: &str) -> Option<i64> {
    let start = text.rfind('(')? + 1;
    let end = text[start..].find(')')? + start;
    text[start..end].trim().parse::<i64>().ok()
}

fn is_valid_rating(rating: Option<f64>) -> bool {
    rating.is_some_and(|value| value.is_finite() && value > 0.0)
}

fn ratings_match(left: Option<f64>, right: Option<f64>) -> bool {
    match (left, right) {
        (Some(left), Some(right)) if left.is_finite() && right.is_finite() => (left - right).abs() < 0.001,
        _ => false,
    }
}

fn format_rating(rating: Option<f64>) -> String {
    match rating {
        Some(value) if (value - value.round()).abs() < 0.001 => format!("{}", value.round() as i64),
        Some(value) => format!("{value:.1}"),
        None => "--".to_string(),
    }
}

fn skipped_item(item: &SyncPreviewItem, reason: Option<String>) -> SyncExecutionItem {
    SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.target_linking_id.clone(),
        target_url: target_url_for_preview_item(item),
        status: "skipped".to_string(),
        reason,
    }
}

fn failed_item(item: &SyncPreviewItem, reason: String) -> SyncExecutionItem {
    SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.target_linking_id.clone(),
        target_url: target_url_for_preview_item(item),
        status: "failed".to_string(),
        reason: Some(reason),
    }
}

fn target_url_for_preview_item(item: &SyncPreviewItem) -> Option<String> {
    let target_id = item
        .target_linking_id
        .as_deref()
        .or(item.identifiers.imdb.as_deref())
        .or(item.identifiers.tmdb.as_deref())
        .or(item.identifiers.douban.as_deref())
        .or(item.identifiers.trakt.as_deref())?;

    match item.target_platform.as_str() {
        "imdb" => Some(format!("https://www.imdb.com/title/{target_id}/")),
        "douban" => {
            if target_id.starts_with("tt") {
                None
            } else {
                Some(format!("https://movie.douban.com/subject/{target_id}/"))
            }
        }
        "tmdb" => {
            let tmdb_id = if target_id.starts_with("tt") {
                item.identifiers.tmdb.as_deref()
            } else {
                Some(target_id)
            }?;
            Some(format!("https://www.themoviedb.org/movie/{tmdb_id}"))
        }
        "trakt" => item
            .identifiers
            .imdb
            .as_ref()
            .map(|imdb| format!("https://trakt.tv/search/imdb/{imdb}")),
        _ => None,
    }
}

fn stub_fetch(platform: &str) -> Result<(FetchResult, Vec<MovieRecord>)> {
    Ok((
        FetchResult {
            platform: platform.to_string(),
            item_count: 0,
            stored_count: 0,
        },
        Vec::new(),
    ))
}

#[derive(Debug, Default, Clone)]
struct DoubanPublicSnapshot {
    display_name: Option<String>,
    avatar: Option<String>,
    watched_total: Option<i64>,
    wish_total: Option<i64>,
    sample_title: Option<String>,
}

async fn fetch_douban_movies(
    config: &cinerecord_core::CookiePlatformConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let user_id = config
        .user_id
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .context("Douban User ID is required for public fetch")?;
    let cookie = config.cookie.as_deref().filter(|value| !value.trim().is_empty());
    let items = match fetch_douban_public_items(user_id, "collect", None).await {
        Ok(items) if !items.is_empty() => items,
        _ => {
            if let Some(cookie) = cookie {
                match fetch_douban_public_items(user_id, "collect", Some(cookie)).await {
                    Ok(items) if !items.is_empty() => items,
                    _ => fetch_douban_interest_movie_records(user_id, cookie, "done").await?,
                }
            } else {
                fetch_douban_public_items(user_id, "collect", None).await?
            }
        }
    };
    let count = items.len();
    Ok((
        FetchResult {
            platform: "douban".to_string(),
            item_count: count,
            stored_count: count,
        },
        items,
    ))
}

async fn fetch_douban_wishlist(
    config: &cinerecord_core::CookiePlatformConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let user_id = config
        .user_id
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .context("Douban User ID is required for public wishlist fetch")?;
    let cookie = config.cookie.as_deref().filter(|value| !value.trim().is_empty());
    let (items, read_mode) = match fetch_douban_public_wishlist_items(user_id, None).await {
        Ok(items) if !items.is_empty() => (items, "public"),
        _ => {
            if let Some(cookie) = cookie {
                match fetch_douban_public_wishlist_items(user_id, Some(cookie)).await {
                    Ok(items) if !items.is_empty() => (items, "public+cookie"),
                    _ => (fetch_douban_interest_wishlist_records(user_id, cookie, "mark").await?, "api+cookie"),
                }
            } else {
                (fetch_douban_public_wishlist_items(user_id, None).await?, "public")
            }
        }
    };
    let item_count = items.len();
    Ok((
        json!({
            "platform": "douban",
            "item_count": item_count,
            "stored_count": item_count,
            "implemented": true,
            "read_mode": read_mode
        }),
        items,
    ))
}

async fn fetch_douban_public_snapshot(user_id: &str, cookie: Option<&str>) -> Result<DoubanPublicSnapshot> {
    let client = Client::new();
    let profile_html = fetch_douban_public_page_html(&client, user_id, "", 0, cookie).await?;
    let collect_html = fetch_douban_public_page_html(&client, user_id, "collect", 0, cookie).await?;
    let wish_html = fetch_douban_public_page_html(&client, user_id, "wish", 0, cookie).await?;
    Ok(DoubanPublicSnapshot {
        display_name: extract_douban_display_name(&profile_html)
            .or_else(|| extract_douban_display_name(&collect_html))
            .or_else(|| Some(user_id.to_string())),
        avatar: extract_douban_avatar(&profile_html).or_else(|| extract_douban_avatar(&collect_html)),
        watched_total: extract_douban_page_total(&collect_html),
        wish_total: extract_douban_page_total(&wish_html),
        sample_title: parse_douban_public_movies_page(&collect_html)
            .ok()
            .and_then(|items| items.first().map(|item| item.title.clone())),
    })
}

async fn fetch_douban_public_items(
    user_id: &str,
    path: &str,
    cookie: Option<&str>,
) -> Result<Vec<MovieRecord>> {
    let client = Client::new();
    let mut start = 0usize;
    let page_size = 15usize;
    let mut items = Vec::new();
    let mut seen_subjects = std::collections::HashSet::new();
    loop {
        let html = fetch_douban_public_page_html(&client, user_id, path, start, cookie).await?;
        let page_items = parse_douban_public_movies_page(&html)?;
        if page_items.is_empty() {
            break;
        }
        let mut new_items = 0usize;
        items.extend(page_items.into_iter().filter_map(|item| {
            if let Some(subject_id) = item.subject_id.as_ref() {
                if !seen_subjects.insert(subject_id.clone()) {
                    return None;
                }
            }
            new_items += 1;
            Some(MovieRecord {
            id: Uuid::new_v4().to_string(),
            platform: "douban".to_string(),
            title: item.title,
            year: item.year,
            rating: item.rating,
            rated_at: item.rated_at,
            external_id: item.subject_id.clone(),
            source_url: item.source_url.clone(),
            identifiers: MovieIdentifiers {
                imdb: None,
                tmdb: None,
                trakt: None,
                douban: item.subject_id.clone(),
                letterboxd: None,
            },
            raw_json: json!({
                "intro": item.intro,
                "date": item.date,
                "comment": item.comment,
                "poster": item.poster,
                "public_path": path
            }),
            })
        }));
        start += page_size;
        if new_items == 0 || !douban_page_has_next(&html) || start > 6000 {
            break;
        }
    }
    Ok(items)
}

async fn fetch_douban_public_wishlist_items(
    user_id: &str,
    cookie: Option<&str>,
) -> Result<Vec<WishlistRecord>> {
    let client = Client::new();
    let mut start = 0usize;
    let page_size = 15usize;
    let mut items = Vec::new();
    let mut seen_subjects = std::collections::HashSet::new();
    loop {
        let html = fetch_douban_public_page_html(&client, user_id, "wish", start, cookie).await?;
        let page_items = parse_douban_public_movies_page(&html)?;
        if page_items.is_empty() {
            break;
        }
        let mut new_items = 0usize;
        items.extend(page_items.into_iter().filter_map(|item| {
            if let Some(subject_id) = item.subject_id.as_ref() {
                if !seen_subjects.insert(subject_id.clone()) {
                    return None;
                }
            }
            new_items += 1;
            Some(WishlistRecord {
            id: Uuid::new_v4().to_string(),
            platform: "douban".to_string(),
            title: item.title,
            year: item.year,
            external_id: item.subject_id.clone(),
            source_url: item.source_url.clone(),
            identifiers: MovieIdentifiers {
                imdb: None,
                tmdb: None,
                trakt: None,
                douban: item.subject_id.clone(),
                letterboxd: None,
            },
            raw_json: json!({
                "intro": item.intro,
                "date": item.date,
                "comment": item.comment,
                "poster": item.poster,
                "public_path": "wish"
            }),
            })
        }));
        start += page_size;
        if new_items == 0 || !douban_page_has_next(&html) || start > 6000 {
            break;
        }
    }
    Ok(items)
}

struct TraktClient {
    client: Client,
    client_id: String,
    client_secret: String,
    access_token: Option<String>,
    refresh_token: Option<String>,
}

impl TraktClient {
    async fn start_device_auth(&self) -> Result<TraktDeviceCode> {
        let payload = self
            .post_unauth(
                "/oauth/device/code",
                json!({
                    "client_id": self.client_id
                }),
            )
            .await?;
        Ok(TraktDeviceCode {
            device_code: payload
                .get("device_code")
                .and_then(|v| v.as_str())
                .context("Trakt device_code missing")?
                .to_string(),
            user_code: payload
                .get("user_code")
                .and_then(|v| v.as_str())
                .context("Trakt user_code missing")?
                .to_string(),
            verification_url: payload
                .get("verification_url")
                .and_then(|v| v.as_str())
                .context("Trakt verification_url missing")?
                .to_string(),
            expires_in: payload.get("expires_in").and_then(|v| v.as_i64()).unwrap_or(600),
            interval: payload.get("interval").and_then(|v| v.as_i64()).unwrap_or(5),
        })
    }

    async fn poll_device_auth(&self, device_code: &str) -> Result<TraktDevicePollResult> {
        let response = self
            .request(
                Method::POST,
                "/oauth/device/token",
                false,
                Some(json!({
                    "code": device_code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                })),
            )
            .await?;

        match response.status() {
            StatusCode::OK => {
                let payload: Value = response.json().await?;
                let access_token = payload.get("access_token").and_then(|v| v.as_str()).map(ToOwned::to_owned);
                let refresh_token = payload.get("refresh_token").and_then(|v| v.as_str()).map(ToOwned::to_owned);
                let token_expires = payload
                    .get("expires_in")
                    .and_then(|v| v.as_i64())
                    .map(|seconds| Utc::now() + Duration::seconds(seconds));

                let profile = if let Some(token) = &access_token {
                    self.get_user_profile_with_token(token).await.ok()
                } else {
                    None
                };

                Ok(TraktDevicePollResult {
                    status: "success".to_string(),
                    access_token,
                    refresh_token,
                    token_expires,
                    message: None,
                    profile,
                })
            }
            StatusCode::BAD_REQUEST => {
                let payload: Value = response.json().await.unwrap_or_else(|_| json!({}));
                let error_code = payload.get("error").and_then(|value| value.as_str()).unwrap_or("authorization_pending");
                let error_description = payload
                    .get("error_description")
                    .and_then(|value| value.as_str())
                    .map(ToOwned::to_owned);
                let (status, message) = match error_code {
                    "authorization_pending" => (
                        "pending".to_string(),
                        Some("Trakt is still waiting for you to confirm authorization".to_string()),
                    ),
                    "slow_down" => (
                        "slow_down".to_string(),
                        Some("Trakt asked for slower polling; wait a few seconds and try again".to_string()),
                    ),
                    "access_denied" => (
                        "denied".to_string(),
                        Some("Trakt authorization was denied".to_string()),
                    ),
                    "expired_token" => (
                        "expired".to_string(),
                        Some("Trakt device code expired; please start OAuth again".to_string()),
                    ),
                    "invalid_grant" => (
                        "error".to_string(),
                        Some("Trakt did not accept this device code; please start OAuth again".to_string()),
                    ),
                    _ => (
                        "error".to_string(),
                        Some(format!("Trakt returned {error_code}{}", error_description.as_deref().map(|text| format!(" · {text}")).unwrap_or_default())),
                    ),
                };
                Ok(TraktDevicePollResult {
                    status,
                    access_token: None,
                    refresh_token: None,
                    token_expires: None,
                    message: error_description.or(message),
                    profile: None,
                })
            }
            StatusCode::NOT_FOUND | StatusCode::CONFLICT => Ok(TraktDevicePollResult {
                status: "expired".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("Trakt device code expired or was already used".to_string()),
                profile: None,
            }),
            StatusCode::GONE | StatusCode::IM_A_TEAPOT => Ok(TraktDevicePollResult {
                status: "denied".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("Trakt authorization was denied".to_string()),
                profile: None,
            }),
            StatusCode::TOO_MANY_REQUESTS => Ok(TraktDevicePollResult {
                status: "slow_down".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("Trakt requested slower polling".to_string()),
                profile: None,
            }),
            _ => {
                let status = response.status();
                let body = response.text().await.unwrap_or_default();
                Ok(TraktDevicePollResult {
                    status: "error".to_string(),
                    access_token: None,
                    refresh_token: None,
                    token_expires: None,
                    message: Some(format!("HTTP {}: {}", status, body)),
                    profile: None,
                })
            }
        }
    }

    async fn refresh_access_token(&self) -> Result<TraktDevicePollResult> {
        let refresh_token = self
            .refresh_token
            .as_deref()
            .filter(|value| !value.trim().is_empty())
            .context("Trakt refresh_token missing")?;
        let response = self
            .request(
                Method::POST,
                "/oauth/token",
                false,
                Some(json!({
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob"
                })),
            )
            .await?;

        match response.status() {
            StatusCode::OK => {
                let payload: Value = response.json().await?;
                let access_token = payload.get("access_token").and_then(|v| v.as_str()).map(ToOwned::to_owned);
                let next_refresh_token = payload.get("refresh_token").and_then(|v| v.as_str()).map(ToOwned::to_owned);
                let token_expires = payload
                    .get("expires_in")
                    .and_then(|v| v.as_i64())
                    .map(|seconds| Utc::now() + Duration::seconds(seconds));
                let profile = if let Some(token) = &access_token {
                    self.get_user_profile_with_token(token).await.ok()
                } else {
                    None
                };

                Ok(TraktDevicePollResult {
                    status: "success".to_string(),
                    access_token,
                    refresh_token: next_refresh_token,
                    token_expires,
                    message: Some("Trakt access token refreshed".to_string()),
                    profile,
                })
            }
            StatusCode::BAD_REQUEST | StatusCode::UNAUTHORIZED => {
                let payload: Value = response.json().await.unwrap_or_else(|_| json!({}));
                let error_code = payload.get("error").and_then(|value| value.as_str()).unwrap_or("invalid_grant");
                let error_description = payload
                    .get("error_description")
                    .and_then(|value| value.as_str())
                    .unwrap_or("refresh token is no longer valid");
                Ok(TraktDevicePollResult {
                    status: "expired".to_string(),
                    access_token: None,
                    refresh_token: None,
                    token_expires: None,
                    message: Some(format!("Trakt token refresh failed: {error_code} · {error_description}")),
                    profile: None,
                })
            }
            _ => {
                let status = response.status();
                let body = response.text().await.unwrap_or_default();
                Ok(TraktDevicePollResult {
                    status: "error".to_string(),
                    access_token: None,
                    refresh_token: None,
                    token_expires: None,
                    message: Some(format!("Trakt token refresh failed: HTTP {} · {}", status, body)),
                    profile: None,
                })
            }
        }
    }

    async fn get_user_profile(&self) -> Result<Value> {
        self.get_user_profile_with_token(self.access_token.as_deref().context("Trakt access token missing")?)
            .await
    }

    async fn get_user_profile_with_token(&self, token: &str) -> Result<Value> {
        self.request_with_token(Method::GET, "/users/me?extended=full", token, None)
            .await?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn get_user_stats(&self, username: &str) -> Result<Value> {
        self.get(&format!("/users/{username}/stats"), None).await
    }

    async fn get_all_movies_with_ratings(&self, username: &str) -> Result<Vec<Value>> {
        let mut ratings = std::collections::HashMap::new();
        let mut page = 1_i64;
        loop {
            let response = self
                .request_paginated(&format!("/users/{username}/ratings/movies"), page)
                .await?;
            let page_count = response.0;
            let items = response.1;
            if items.is_empty() {
                break;
            }
            for item in items {
                if let Some(trakt_id) = item
                    .get("movie")
                    .and_then(|movie| movie.get("ids"))
                    .and_then(|ids| ids.get("trakt"))
                    .and_then(|v| v.as_i64())
                {
                    ratings.insert(trakt_id, item);
                }
            }
            if page >= page_count {
                break;
            }
            page += 1;
        }

        let mut all_items = Vec::new();
        let mut seen = std::collections::HashSet::new();
        let mut page = 1_i64;
        loop {
            let response = self
                .request_paginated(&format!("/users/{username}/history/movies"), page)
                .await?;
            let page_count = response.0;
            let items = response.1;
            if items.is_empty() {
                break;
            }
            for mut item in items {
                let trakt_id = item
                    .get("movie")
                    .and_then(|movie| movie.get("ids"))
                    .and_then(|ids| ids.get("trakt"))
                    .and_then(|v| v.as_i64());
                if let Some(trakt_id) = trakt_id {
                    if !seen.insert(trakt_id) {
                        continue;
                    }
                    if let Some(rating_item) = ratings.get(&trakt_id) {
                        if let Some(rating) = rating_item.get("rating") {
                            item["rating"] = rating.clone();
                        }
                        if let Some(rated_at) = rating_item.get("rated_at") {
                            item["rated_at"] = rated_at.clone();
                        }
                    }
                }
                all_items.push(item);
            }
            if page >= page_count {
                break;
            }
            page += 1;
        }
        Ok(all_items)
    }

    async fn request_paginated(&self, path: &str, page: i64) -> Result<(i64, Vec<Value>)> {
        let response = self
            .client
            .request(Method::GET, format!("https://api.trakt.tv{path}"))
            .header("Content-Type", "application/json")
            .header("User-Agent", browser_user_agent())
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .bearer_auth(self.access_token.as_deref().context("Trakt access token missing")?)
            .query(&[
                ("page", page.to_string()),
                ("limit", "100".to_string()),
                ("extended", "full".to_string()),
            ])
            .send()
            .await?
            .error_for_status()?;
        let total_pages = response
            .headers()
            .get("X-Pagination-Page-Count")
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(1);
        let items: Vec<Value> = response.json().await?;
        Ok((total_pages, items))
    }

    async fn get(&self, path: &str, query: Option<&[(&str, String)]>) -> Result<Value> {
        let mut request = self
            .client
            .request(Method::GET, format!("https://api.trakt.tv{path}"))
            .header("Content-Type", "application/json")
            .header("User-Agent", browser_user_agent())
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id);
        if let Some(token) = &self.access_token {
            request = request.bearer_auth(token);
        }
        if let Some(query) = query {
            request = request.query(query);
        }
        request.send().await?.error_for_status()?.json().await.map_err(Into::into)
    }

    async fn post(&self, path: &str, body: Value) -> Result<Value> {
        self.request(Method::POST, path, true, Some(body))
            .await?
            .error_for_status()?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn post_unauth(&self, path: &str, body: Value) -> Result<Value> {
        self.request(Method::POST, path, false, Some(body))
            .await?
            .error_for_status()?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn request(&self, method: Method, path: &str, auth_required: bool, body: Option<Value>) -> Result<reqwest::Response> {
        let mut request = self
            .client
            .request(method, format!("https://api.trakt.tv{path}"))
            .header("Content-Type", "application/json")
            .header("User-Agent", browser_user_agent())
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id);
        if auth_required {
            let token = self.access_token.as_deref().context("Trakt access token missing")?;
            request = request.bearer_auth(token);
        }
        if let Some(body) = body {
            request = request.json(&body);
        }
        request.send().await.map_err(Into::into)
    }

    async fn request_with_token(
        &self,
        method: Method,
        path: &str,
        token: &str,
        body: Option<Value>,
    ) -> Result<reqwest::Response> {
        let mut request = self
            .client
            .request(method, format!("https://api.trakt.tv{path}"))
            .header("Content-Type", "application/json")
            .header("User-Agent", browser_user_agent())
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .bearer_auth(token);
        if let Some(body) = body {
            request = request.json(&body);
        }
        request.send().await.map_err(Into::into)
    }
}

struct TmdbClient {
    client: Client,
    api_key: String,
    session_id: Option<String>,
}

impl TmdbClient {
    async fn validate_api_key(&self) -> Result<Value> {
        let mut url = reqwest::Url::parse("https://api.themoviedb.org/3/authentication")?;
        url.query_pairs_mut().append_pair("api_key", &self.api_key);
        self.client.get(url).send().await?.json().await.map_err(Into::into)
    }

    async fn fetch_account(&self) -> Result<Value> {
        let session_id = self.session_id.as_deref().context("TMDB session_id is required")?;
        self.fetch_account_with_session(session_id).await
    }

    async fn fetch_account_with_session(&self, session_id: &str) -> Result<Value> {
        let mut url = reqwest::Url::parse("https://api.themoviedb.org/3/account")?;
        url.query_pairs_mut()
            .append_pair("api_key", &self.api_key)
            .append_pair("session_id", session_id);
        self.client
            .get(url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn create_request_token(&self) -> Result<String> {
        let mut url = reqwest::Url::parse("https://api.themoviedb.org/3/authentication/token/new")?;
        url.query_pairs_mut().append_pair("api_key", &self.api_key);
        let payload: Value = self.client.get(url).send().await?.error_for_status()?.json().await?;
        payload
            .get("request_token")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned)
            .context("TMDB request_token missing")
    }

    async fn create_session(&self, request_token: &str) -> Result<String> {
        let mut url = reqwest::Url::parse("https://api.themoviedb.org/3/authentication/session/new")?;
        url.query_pairs_mut().append_pair("api_key", &self.api_key);
        let payload: Value = self
            .client
            .post(url)
            .json(&json!({ "request_token": request_token }))
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        payload
            .get("session_id")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned)
            .context("TMDB session_id missing")
    }

    async fn get_account_rated_movies(&self, account_id: i64, page: i64) -> Result<Value> {
        let session_id = self.session_id.as_deref().context("TMDB session_id is required")?;
        let mut url = reqwest::Url::parse(&format!(
            "https://api.themoviedb.org/3/account/{account_id}/rated/movies"
        ))?;
        url.query_pairs_mut()
            .append_pair("api_key", &self.api_key)
            .append_pair("session_id", session_id)
            .append_pair("page", &page.to_string())
            .append_pair("sort_by", "created_at.desc");
        self.client
            .get(url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn get_account_watchlist(&self, account_id: i64, page: i64) -> Result<Value> {
        let session_id = self.session_id.as_deref().context("TMDB session_id is required")?;
        let mut url = reqwest::Url::parse(&format!(
            "https://api.themoviedb.org/3/account/{account_id}/watchlist/movies"
        ))?;
        url.query_pairs_mut()
            .append_pair("api_key", &self.api_key)
            .append_pair("session_id", session_id)
            .append_pair("page", &page.to_string());
        self.client
            .get(url)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await
            .map_err(Into::into)
    }

    async fn find_by_imdb(&self, imdb_id: &str) -> Result<(i64, String)> {
        let mut url = reqwest::Url::parse(&format!(
            "https://api.themoviedb.org/3/find/{imdb_id}"
        ))?;
        url.query_pairs_mut()
            .append_pair("api_key", &self.api_key)
            .append_pair("external_source", "imdb_id");
        let payload: Value = self.client.get(url).send().await?.error_for_status()?.json().await?;
        if let Some(id) = payload
            .get("movie_results")
            .and_then(|v| v.as_array())
            .and_then(|items| items.first())
            .and_then(|item| item.get("id"))
            .and_then(|v| v.as_i64())
        {
            return Ok((id, "movie".to_string()));
        }
        if let Some(id) = payload
            .get("tv_results")
            .and_then(|v| v.as_array())
            .and_then(|items| items.first())
            .and_then(|item| item.get("id"))
            .and_then(|v| v.as_i64())
        {
            return Ok((id, "tv".to_string()));
        }
        Err(anyhow!("TMDB could not resolve IMDb ID {imdb_id}"))
    }

    async fn rate_movie(&self, movie_id: i64, rating: f64) -> Result<bool> {
        self.rate("/movie", movie_id, rating).await
    }

    async fn rate_tv(&self, tv_id: i64, rating: f64) -> Result<bool> {
        self.rate("/tv", tv_id, rating).await
    }

    async fn rate(&self, prefix: &str, item_id: i64, rating: f64) -> Result<bool> {
        let session_id = self.session_id.as_deref().context("TMDB session_id is required")?;
        let mut url = reqwest::Url::parse(&format!(
            "https://api.themoviedb.org/3{prefix}/{item_id}/rating"
        ))?;
        url.query_pairs_mut()
            .append_pair("api_key", &self.api_key)
            .append_pair("session_id", session_id);
        let mut last_error = None;
        for attempt in 0..3 {
            let response = self
                .client
                .post(url.clone())
                .json(&json!({ "value": normalize_tmdb_rating(rating) }))
                .send()
                .await;
            match response {
                Ok(response) => {
                    let payload: Value = response.json().await?;
                    return Ok(payload.get("success").and_then(|v| v.as_bool()).unwrap_or(false));
                }
                Err(error) => {
                    last_error = Some(anyhow!(error.to_string()));
                    if attempt < 2 {
                        tokio::time::sleep(std::time::Duration::from_millis(400 * (attempt as u64 + 1))).await;
                    }
                }
            }
        }
        Err(last_error.unwrap_or_else(|| anyhow!("TMDB rating request failed")))
    }
}

fn normalize_tmdb_rating(rating: f64) -> f64 {
    (rating.clamp(0.5, 10.0) * 2.0).round() / 2.0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_movie(platform: &str, title: &str, rating: Option<f64>, ids: MovieIdentifiers) -> MovieRecord {
        MovieRecord {
            id: Uuid::new_v4().to_string(),
            platform: platform.to_string(),
            title: title.to_string(),
            year: Some(2024),
            rating,
            rated_at: Some(Utc::now()),
            external_id: ids
                .tmdb
                .clone()
                .or(ids.trakt.clone())
                .or(ids.imdb.clone())
                .or(ids.douban.clone())
                .or(ids.letterboxd.clone()),
            source_url: Some("https://example.test/item".to_string()),
            identifiers: ids,
            raw_json: json!({}),
        }
    }

    #[test]
    fn preview_builds_tmdb_to_trakt_candidates() {
        let source = vec![sample_movie(
            "tmdb",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                tmdb: Some("101".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = Vec::new();
        let request = SyncPreviewRequest {
            source_platform: "tmdb".to_string(),
            target_platform: "trakt".to_string(),
            recent_limit: 100,
            only_new: true,
            overwrite: false,
            default_rating: None,
        };

        let preview = build_sync_preview("tmdb", "trakt", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert_eq!(preview.items[0].target_linking_id.as_deref(), Some("tt1234567"));
        assert_eq!(preview.items[0].reason, None);
    }

    #[test]
    fn preview_skips_existing_movies_when_only_new() {
        let source = vec![sample_movie(
            "tmdb",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                tmdb: Some("101".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = vec![sample_movie(
            "trakt",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                trakt: Some("9001".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let request = SyncPreviewRequest {
            source_platform: "tmdb".to_string(),
            target_platform: "trakt".to_string(),
            recent_limit: 100,
            only_new: true,
            overwrite: false,
            default_rating: None,
        };

        let preview = build_sync_preview("tmdb", "trakt", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 0);
    }

    #[test]
    fn preview_builds_imdb_to_trakt_candidates() {
        let source = vec![sample_movie(
            "imdb",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = Vec::new();
        let request = SyncPreviewRequest {
            source_platform: "imdb".to_string(),
            target_platform: "trakt".to_string(),
            recent_limit: 100,
            only_new: true,
            overwrite: false,
            default_rating: None,
        };

        let preview = build_sync_preview("imdb", "trakt", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert_eq!(preview.items[0].target_linking_id.as_deref(), Some("tt1234567"));
        assert_eq!(preview.items[0].reason, None);
    }

    #[test]
    fn preview_builds_imdb_to_tmdb_candidates() {
        let source = vec![sample_movie(
            "imdb",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = Vec::new();
        let request = SyncPreviewRequest {
            source_platform: "imdb".to_string(),
            target_platform: "tmdb".to_string(),
            recent_limit: 100,
            only_new: true,
            overwrite: false,
            default_rating: None,
        };

        let preview = build_sync_preview("imdb", "tmdb", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert_eq!(preview.items[0].target_linking_id.as_deref(), Some("tt1234567"));
        assert_eq!(preview.items[0].reason, None);
    }

    #[test]
    fn preview_marks_tmdb_unrated_items_without_default_rating() {
        let source = vec![sample_movie(
            "trakt",
            "No Rating",
            None,
            MovieIdentifiers {
                imdb: Some("tt7654321".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = Vec::new();
        let request = SyncPreviewRequest {
            source_platform: "trakt".to_string(),
            target_platform: "tmdb".to_string(),
            recent_limit: 100,
            only_new: true,
            overwrite: false,
            default_rating: None,
        };

        let preview = build_sync_preview("trakt", "tmdb", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert!(preview.items[0]
            .reason
            .as_deref()
            .unwrap_or_default()
            .contains("TMDB does not support watched-only sync"));
    }

    #[test]
    fn preview_skips_overwrite_when_target_has_rating_but_source_is_unrated() {
        let source = vec![sample_movie(
            "trakt",
            "Flow",
            None,
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                trakt: Some("9001".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = vec![sample_movie(
            "douban",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                douban: Some("1001".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let request = SyncPreviewRequest {
            source_platform: "trakt".to_string(),
            target_platform: "douban".to_string(),
            recent_limit: 100,
            only_new: false,
            overwrite: true,
            default_rating: None,
        };

        let preview = build_sync_preview("trakt", "douban", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert_eq!(preview.items[0].action, "keep");
        assert_eq!(preview.items[0].target_existing_rating, Some(8.0));
        assert!(preview.items[0]
            .reason
            .as_deref()
            .unwrap_or_default()
            .contains("目标平台已有评分"));
    }

    #[test]
    fn preview_skips_overwrite_when_target_already_has_same_rating() {
        let source = vec![sample_movie(
            "trakt",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                trakt: Some("9001".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let target = vec![sample_movie(
            "douban",
            "Flow",
            Some(8.0),
            MovieIdentifiers {
                imdb: Some("tt1234567".to_string()),
                douban: Some("1001".to_string()),
                ..MovieIdentifiers::default()
            },
        )];
        let request = SyncPreviewRequest {
            source_platform: "trakt".to_string(),
            target_platform: "douban".to_string(),
            recent_limit: 100,
            only_new: false,
            overwrite: true,
            default_rating: None,
        };

        let preview = build_sync_preview("trakt", "douban", &source, &target, &request).unwrap();
        assert_eq!(preview.preview_count, 1);
        assert_eq!(preview.items[0].action, "keep");
        assert_eq!(preview.items[0].target_existing_rating, Some(8.0));
        assert!(preview.items[0]
            .reason
            .as_deref()
            .unwrap_or_default()
            .contains("无需重复覆盖"));
    }
}
