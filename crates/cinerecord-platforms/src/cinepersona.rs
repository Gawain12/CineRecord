use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Utc};
use cinerecord_core::{
    CinePersonaConfig, FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult,
    WishlistRecord,
};
use reqwest::Client;
use serde_json::{Value, json};

pub async fn test_cinepersona(config: &CinePersonaConfig) -> Result<PlatformValidationResult> {
    let base_url = match config.base_url.as_deref() {
        Some(url) if !url.trim().is_empty() => url,
        _ => {
            return Ok(PlatformValidationResult {
                platform: "cinepersona".to_string(),
                success: false,
                message: "未配置 Base URL".to_string(),
                profile: None,
            });
        }
    };
    let api_key = match config.api_key.as_deref() {
        Some(key) if !key.trim().is_empty() => key,
        _ => {
            return Ok(PlatformValidationResult {
                platform: "cinepersona".to_string(),
                success: false,
                message: "未配置 API Key".to_string(),
                profile: None,
            });
        }
    };

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(6))
        .build()?;
    let trimmed_base = base_url.trim().trim_end_matches('/');
    let url = format!("{trimmed_base}/api/v1/auth/me");

    let resp_res = client
        .get(&url)
        .header("Authorization", format!("Bearer {api_key}"))
        .header("Content-Type", "application/json")
        .send()
        .await;

    let resp = match resp_res {
        Ok(r) => r,
        Err(e) => {
            return Ok(PlatformValidationResult {
                platform: "cinepersona".to_string(),
                success: false,
                message: format!("连接失败: 无法访问服务 ({e})"),
                profile: None,
            });
        }
    };

    let status = resp.status();
    if !status.is_success() {
        return Ok(PlatformValidationResult {
            platform: "cinepersona".to_string(),
            success: false,
            message: format!("连接失败: HTTP {status}"),
            profile: None,
        });
    }

    let body: Value = resp.json().await.unwrap_or(json!({}));
    let user_id = body.get("id").and_then(|v| v.as_str());
    let username = body.get("username").and_then(|v| v.as_str());
    let email = body.get("email").and_then(|v| v.as_str());

    let profile_data = json!({
        "user_id": user_id,
        "username": username,
        "display_name": username.or(email),
        "email": email,
        "profile": body,
    });

    let display_name = username.or(email).unwrap_or("CinePersona 用户");
    Ok(PlatformValidationResult {
        platform: "cinepersona".to_string(),
        success: true,
        message: format!("CinePersona 已连接 · 用户: {display_name}"),
        profile: Some(profile_data),
    })
}

pub async fn fetch_cinepersona_movies(
    config: &CinePersonaConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let base_url = config
        .base_url
        .as_deref()
        .context("CinePersona base_url is required")?;
    let api_key = config
        .api_key
        .as_deref()
        .context("CinePersona api_key is required")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let trimmed_base = base_url.trim().trim_end_matches('/');
    let url = format!("{trimmed_base}/api/v1/ratings?limit=10000");

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {api_key}"))
        .send()
        .await
        .with_context(|| format!("failed to fetch CinePersona ratings from {url}"))?;

    let status = resp.status();
    if !status.is_success() {
        return Err(anyhow!("CinePersona ratings fetch failed: HTTP {status}"));
    }

    let items: Vec<Value> = resp.json().await?;
    let mut records = Vec::new();

    for item in items {
        let movie = match item.get("movie") {
            Some(m) => m,
            None => continue,
        };
        let title = movie.get("title").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
        let year = movie.get("year").and_then(|v| v.as_i64()).map(|y| y as i32);
        let imdb_id = movie.get("imdbId").and_then(|v| v.as_str()).map(ToOwned::to_owned);
        let tmdb_id = movie.get("tmdbId").and_then(|v| v.as_i64()).map(|v| v.to_string())
            .or_else(|| movie.get("tmdbId").and_then(|v| v.as_str()).map(ToOwned::to_owned));
        let rating = item.get("score").and_then(|v| v.as_f64());
        let rated_at = item.get("createdAt").and_then(|v| v.as_str())
            .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
            .map(|dt| dt.with_timezone(&Utc));

        let id = item.get("id").and_then(|v| v.as_str()).unwrap_or_default().to_string();

        records.push(MovieRecord {
            id: format!("cinepersona:{id}"),
            platform: "cinepersona".to_string(),
            title: title.clone(),
            year,
            rating,
            rated_at,
            external_id: Some(id),
            source_url: None,
            identifiers: MovieIdentifiers {
                imdb: imdb_id,
                tmdb: tmdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: item,
        });
    }

    let count = records.len();
    Ok((
        FetchResult {
            platform: "cinepersona".to_string(),
            item_count: count,
            stored_count: count,
        },
        records,
    ))
}

pub async fn fetch_cinepersona_wishlist(
    config: &CinePersonaConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let base_url = config
        .base_url
        .as_deref()
        .context("CinePersona base_url is required")?;
    let api_key = config
        .api_key
        .as_deref()
        .context("CinePersona api_key is required")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let trimmed_base = base_url.trim().trim_end_matches('/');
    let url = format!("{trimmed_base}/api/v1/watchlist?limit=10000");

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {api_key}"))
        .send()
        .await
        .with_context(|| format!("failed to fetch CinePersona watchlist from {url}"))?;

    let status = resp.status();
    if !status.is_success() {
        return Err(anyhow!("CinePersona watchlist fetch failed: HTTP {status}"));
    }

    let items: Vec<Value> = resp.json().await?;
    let mut records = Vec::new();

    for item in items {
        let movie = match item.get("movie") {
            Some(m) => m,
            None => continue,
        };
        let title = movie.get("title").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
        let year = movie.get("year").and_then(|v| v.as_i64()).map(|y| y as i32);
        let imdb_id = movie.get("imdbId").and_then(|v| v.as_str()).map(ToOwned::to_owned);
        let tmdb_id = movie.get("tmdbId").and_then(|v| v.as_i64()).map(|v| v.to_string())
            .or_else(|| movie.get("tmdbId").and_then(|v| v.as_str()).map(ToOwned::to_owned));
        let created_at = item.get("createdAt").and_then(|v| v.as_str())
            .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
            .map(|dt| dt.with_timezone(&Utc));

        let id = item.get("id").and_then(|v| v.as_str()).unwrap_or_default().to_string();

        records.push(WishlistRecord {
            id: format!("cinepersona:{id}"),
            platform: "cinepersona".to_string(),
            title: title.clone(),
            year,
            external_id: Some(id),
            source_url: None,
            identifiers: MovieIdentifiers {
                imdb: imdb_id,
                tmdb: tmdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: item,
            created_at,
        });
    }

    let count = records.len();
    Ok((
        json!({
            "platform": "cinepersona",
            "item_count": count,
            "stored_count": count,
            "implemented": true
        }),
        records,
    ))
}
