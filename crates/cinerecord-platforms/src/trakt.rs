use anyhow::{Context, Result, anyhow, bail};
use chrono::{DateTime, Duration, Utc};
use cinerecord_core::{
    AppConfig, FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult,
    SyncExecutionItem, SyncPreviewItem, TraktConfig, TraktDeviceCode, TraktDevicePollResult,
    WishlistRecord,
};
use reqwest::Client;
use serde_json::{Value, json};

pub const DEFAULT_TRAKT_CLIENT_ID: &str =
    "a66d3a863b9f1d07c093630f9d984534fce6e60ec87fa67ef9b240ffab4564c2";

#[derive(Clone)]
pub struct TraktClient {
    client: Client,
    pub client_id: String,
    pub client_secret: Option<String>,
    pub access_token: Option<String>,
}

impl TraktClient {
    pub fn new(
        client_id: String,
        client_secret: Option<String>,
        access_token: Option<String>,
    ) -> Self {
        let client = Client::builder()
            .user_agent("CineRecord/2.0")
            .timeout(std::time::Duration::from_secs(15))
            .build()
            .unwrap_or_else(|_| Client::new());
        Self {
            client,
            client_id,
            client_secret,
            access_token,
        }
    }

    pub async fn start_device_flow(&self) -> Result<TraktDeviceCode> {
        let url = "https://api.trakt.tv/oauth/device/code";
        let resp = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .json(&json!({ "client_id": self.client_id }))
            .send()
            .await
            .context("failed to send Trakt device code request")?;

        let status = resp.status();
        if !status.is_success() {
            let body = resp.text().await.unwrap_or_default();
            bail!("Trakt 设备授权请求失败 (HTTP {status}): {body}");
        }

        let resp: Value = resp.json().await.context("failed to parse Trakt device code response")?;

        Ok(TraktDeviceCode {
            device_code: resp
                .get("device_code")
                .and_then(|v| v.as_str())
                .context("missing device_code")?
                .to_string(),
            user_code: resp
                .get("user_code")
                .and_then(|v| v.as_str())
                .context("missing user_code")?
                .to_string(),
            verification_url: resp
                .get("verification_url")
                .and_then(|v| v.as_str())
                .unwrap_or("https://trakt.tv/activate")
                .to_string(),
            expires_in: resp.get("expires_in").and_then(|v| v.as_i64()).unwrap_or(600),
            interval: resp.get("interval").and_then(|v| v.as_i64()).unwrap_or(5),
        })
    }

    pub async fn poll_device_flow(
        &self,
        device_code: &str,
        client_secret: &str,
    ) -> Result<TraktDevicePollResult> {
        let url = "https://api.trakt.tv/oauth/device/token";
        let resp = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .json(&json!({
                "code": device_code,
                "client_id": self.client_id,
                "client_secret": client_secret,
            }))
            .send()
            .await?;

        let status = resp.status();
        if status.as_u16() == 400 {
            return Ok(TraktDevicePollResult {
                status: "pending".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("等待用户在浏览器完成授权".to_string()),
                profile: None,
            });
        }
        if status.as_u16() == 404 {
            return Ok(TraktDevicePollResult {
                status: "not_found".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("Device Code 未找到或无效".to_string()),
                profile: None,
            });
        }
        if status.as_u16() == 409 {
            return Ok(TraktDevicePollResult {
                status: "already_used".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("该 Device Code 已被使用".to_string()),
                profile: None,
            });
        }
        if status.as_u16() == 410 {
            return Ok(TraktDevicePollResult {
                status: "expired".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("授权已超时，请重新发起".to_string()),
                profile: None,
            });
        }
        if status.as_u16() == 418 {
            return Ok(TraktDevicePollResult {
                status: "denied".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("用户拒绝了授权申请".to_string()),
                profile: None,
            });
        }
        if status.as_u16() == 429 {
            return Ok(TraktDevicePollResult {
                status: "slow_down".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("轮询过频，请减慢轮询".to_string()),
                profile: None,
            });
        }

        if status.is_success() {
            let body: Value = resp.json().await?;
            let access_token = body
                .get("access_token")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned);
            let refresh_token = body
                .get("refresh_token")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned);
            let expires_in = body.get("expires_in").and_then(|v| v.as_i64()).unwrap_or(7776000);
            let token_expires = Some(Utc::now() + Duration::seconds(expires_in));

            let profile = if let Some(ref token) = access_token {
                let temp_client = TraktClient::new(self.client_id.clone(), Some(client_secret.to_string()), Some(token.clone()));
                temp_client.fetch_profile().await.ok()
            } else {
                None
            };

            return Ok(TraktDevicePollResult {
                status: "success".to_string(),
                access_token,
                refresh_token,
                token_expires,
                message: Some("授权成功".to_string()),
                profile,
            });
        }

        Err(anyhow!("unhandled status from Trakt poll: {status}"))
    }

    pub async fn refresh_token(
        &self,
        refresh_token: &str,
        client_secret: &str,
    ) -> Result<Value> {
        let url = "https://api.trakt.tv/oauth/token";
        let resp: Value = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .json(&json!({
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "refresh_token",
            }))
            .send()
            .await?
            .json()
            .await?;
        Ok(resp)
    }

    pub async fn fetch_profile(&self) -> Result<Value> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required for Trakt profile")?;
        let url = "https://api.trakt.tv/users/me?extended=full";
        let resp: Value = self
            .client
            .get(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await?
            .json()
            .await?;
        Ok(resp)
    }

    pub async fn fetch_watched_movies(&self) -> Result<Vec<Value>> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required")?;
        let url = "https://api.trakt.tv/sync/watched/movies?extended=full";
        let res = self
            .client
            .get(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await?;
        if !res.status().is_success() {
            let status = res.status();
            let text = res.text().await.unwrap_or_default();
            anyhow::bail!("Trakt API error (status {status}): {text}");
        }
        let resp: Vec<Value> = res.json().await?;
        Ok(resp)
    }

    pub async fn fetch_ratings_movies(&self) -> Result<Vec<Value>> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required")?;
        let url = "https://api.trakt.tv/sync/ratings/movies";
        let res = self
            .client
            .get(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await?;
        if !res.status().is_success() {
            let status = res.status();
            let text = res.text().await.unwrap_or_default();
            anyhow::bail!("Trakt API error (status {status}): {text}");
        }
        let resp: Vec<Value> = res.json().await?;
        Ok(resp)
    }

    pub async fn fetch_watchlist(&self) -> Result<Vec<Value>> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required")?;
        let url = "https://api.trakt.tv/sync/watchlist/movies?extended=full";
        let res = self
            .client
            .get(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .send()
            .await?;
        if !res.status().is_success() {
            let status = res.status();
            let text = res.text().await.unwrap_or_default();
            anyhow::bail!("Trakt API error (status {status}): {text}");
        }
        let resp: Vec<Value> = res.json().await?;
        Ok(resp)
    }

    pub async fn sync_history(&self, movie_body: Value) -> Result<Value> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required")?;
        let url = "https://api.trakt.tv/sync/history";
        let resp: Value = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .json(&json!({ "movies": [movie_body] }))
            .send()
            .await?
            .json()
            .await?;
        Ok(resp)
    }

    pub async fn sync_ratings(&self, movie_rating_body: Value) -> Result<Value> {
        let token = self
            .access_token
            .as_deref()
            .context("access_token required")?;
        let url = "https://api.trakt.tv/sync/ratings";
        let resp: Value = self
            .client
            .post(url)
            .header("Content-Type", "application/json")
            .header("trakt-api-version", "2")
            .header("trakt-api-key", &self.client_id)
            .header("Authorization", format!("Bearer {token}"))
            .json(&json!({ "movies": [movie_rating_body] }))
            .send()
            .await?
            .json()
            .await?;
        Ok(resp)
    }
}

pub fn trakt_client(config: &TraktConfig) -> Result<TraktClient> {
    let client_id = config
        .client_id
        .as_deref()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or(DEFAULT_TRAKT_CLIENT_ID)
        .to_string();
    let client_secret = config
        .client_secret
        .as_deref()
        .filter(|v| !v.trim().is_empty())
        .map(ToOwned::to_owned);
    let access_token = config
        .access_token
        .as_deref()
        .filter(|v| !v.trim().is_empty())
        .map(ToOwned::to_owned);

    Ok(TraktClient::new(client_id, client_secret, access_token))
}

pub async fn start_trakt_device_auth(config: &AppConfig) -> Result<TraktDeviceCode> {
    let client = trakt_client(&config.platforms.trakt)?;
    client.start_device_flow().await
}

pub async fn poll_trakt_device_auth(
    config: &AppConfig,
    device_code: &str,
) -> Result<TraktDevicePollResult> {
    let client = trakt_client(&config.platforms.trakt)?;
    let client_secret = config
        .platforms
        .trakt
        .client_secret
        .as_deref()
        .context("Trakt client_secret is required to poll device flow")?;
    client.poll_device_flow(device_code, client_secret).await
}

pub async fn refresh_trakt_access_token(
    config: &AppConfig,
) -> Result<TraktDevicePollResult> {
    let refresh_tok = match &config.platforms.trakt.refresh_token {
        Some(t) if !t.trim().is_empty() => t.clone(),
        _ => {
            return Ok(TraktDevicePollResult {
                status: "expired".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("未找到有效的 refresh_token".to_string()),
                profile: None,
            });
        }
    };
    let secret = match &config.platforms.trakt.client_secret {
        Some(s) if !s.trim().is_empty() => s.clone(),
        _ => {
            return Ok(TraktDevicePollResult {
                status: "failed".to_string(),
                access_token: None,
                refresh_token: None,
                token_expires: None,
                message: Some("未配置 client_secret".to_string()),
                profile: None,
            });
        }
    };

    let client = trakt_client(&config.platforms.trakt)?;
    let resp = client.refresh_token(&refresh_tok, &secret).await?;
    if let Some(access_token) = resp.get("access_token").and_then(|v| v.as_str()) {
        let new_refresh = resp
            .get("refresh_token")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned);
        let expires_in = resp
            .get("expires_in")
            .and_then(|v| v.as_i64())
            .unwrap_or(7776000);
        let token_expires = Some(Utc::now() + Duration::seconds(expires_in));

        return Ok(TraktDevicePollResult {
            status: "success".to_string(),
            access_token: Some(access_token.to_string()),
            refresh_token: new_refresh,
            token_expires,
            message: Some("Token 刷新成功".to_string()),
            profile: None,
        });
    }

    Ok(TraktDevicePollResult {
        status: "expired".to_string(),
        access_token: None,
        refresh_token: None,
        token_expires: None,
        message: Some("Token 刷新失败或已过期".to_string()),
        profile: None,
    })
}

pub async fn test_trakt(config: &TraktConfig) -> Result<PlatformValidationResult> {
    let client = match trakt_client(config) {
        Ok(c) => c,
        Err(e) => {
            return Ok(PlatformValidationResult {
                platform: "trakt".to_string(),
                success: false,
                message: format!("Trakt 客户端初始化失败: {e}"),
                profile: None,
            });
        }
    };
    if client.access_token.is_none() {
        return Ok(PlatformValidationResult {
            platform: "trakt".to_string(),
            success: false,
            message: "未配置 Trakt Access Token，请点击“设备码登录”完成授权".to_string(),
            profile: None,
        });
    }
    let profile = match client.fetch_profile().await {
        Ok(p) => p,
        Err(e) => {
            let msg = e.to_string();
            let expire_info = config
                .token_expires_at
                .map(|dt| format!("（Token 已于 {} 过期）", dt.format("%Y-%m-%d %H:%M")))
                .unwrap_or_default();
            return Ok(PlatformValidationResult {
                platform: "trakt".to_string(),
                success: false,
                message: format!("Trakt 授权已失效{expire_info}，请点击“设备码登录”重新授权: {msg}"),
                profile: None,
            });
        }
    };
    let username = profile.get("username").and_then(|v| v.as_str());
    let name = profile.get("name").and_then(|v| v.as_str());
    let avatar = extract_trakt_avatar(&profile);

    let watched = client.fetch_watched_movies().await.ok();
    let ratings = client.fetch_ratings_movies().await.ok();
    let watchlist = client.fetch_watchlist().await.ok();

    let watched_count = watched.as_ref().map(|v| v.len());
    let rated_count = ratings.as_ref().map(|v| v.len());
    let watchlist_count = watchlist.as_ref().map(|v| v.len());
    let sample_title = watched
        .as_ref()
        .and_then(|items| items.first())
        .and_then(|item| item.get("movie"))
        .and_then(|movie| movie.get("title"))
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);

    let profile_data = json!({
        "profile": profile,
        "user_id": username,
        "display_name": name.or(username),
        "avatar": avatar,
        "watched": watched_count,
        "watched_total": watched_count,
        "ratings": rated_count,
        "ratings_total": rated_count,
        "watchlist": watchlist_count,
        "watchlist_total": watchlist_count,
        "sample_title": sample_title,
        "profile_link": username.map(|u| format!("https://trakt.tv/users/{u}")),
    });

    let display_user = name.or(username).unwrap_or("Trakt 用户");
    let count_msg = format!("{} 部看过，{} 部评分", watched_count.unwrap_or(0), rated_count.unwrap_or(0));

    Ok(PlatformValidationResult {
        platform: "trakt".to_string(),
        success: true,
        message: "Trakt 已连接".to_string(),
        profile: Some(profile_data),
    })
}

pub fn extract_trakt_avatar(profile: &Value) -> Option<String> {
    profile
        .get("images")
        .and_then(|v| v.get("avatar"))
        .and_then(|v| v.get("full"))
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned)
}

pub async fn fetch_trakt_movies(
    config: &TraktConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let client = trakt_client(config)?;
    let watched = client.fetch_watched_movies().await?;
    let ratings = client.fetch_ratings_movies().await.unwrap_or_default();

    let mut ratings_map = std::collections::HashMap::new();
    for r in ratings {
        if let Some(movie) = r.get("movie") {
            if let Some(trakt_id) = movie.get("ids").and_then(|v| v.get("trakt")).and_then(|v| v.as_i64()) {
                let rating = r.get("rating").and_then(|v| v.as_f64());
                let rated_at = r.get("rated_at").and_then(|v| v.as_str()).and_then(|s| DateTime::parse_from_rfc3339(s).ok()).map(|dt| dt.with_timezone(&Utc));
                ratings_map.insert(trakt_id, (rating, rated_at));
            }
        }
    }

    let mut all_records = Vec::new();
    for w in watched {
        let movie = match w.get("movie") {
            Some(m) => m,
            None => continue,
        };
        let ids = movie.get("ids");
        let trakt_id = ids.and_then(|v| v.get("trakt")).and_then(|v| v.as_i64()).unwrap_or(0);
        let imdb_id = ids.and_then(|v| v.get("imdb")).and_then(|v| v.as_str()).map(ToOwned::to_owned);
        let tmdb_id = ids.and_then(|v| v.get("tmdb")).and_then(|v| v.as_i64()).map(|v| v.to_string());
        let slug = ids.and_then(|v| v.get("slug")).and_then(|v| v.as_str());

        let title = movie.get("title").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
        let year = movie.get("year").and_then(|v| v.as_i64()).map(|y| y as i32);
        let last_watched_at = w.get("last_watched_at").and_then(|v| v.as_str()).and_then(|s| DateTime::parse_from_rfc3339(s).ok()).map(|dt| dt.with_timezone(&Utc));

        let (rating, rated_at) = ratings_map.get(&trakt_id).cloned().unwrap_or((None, None));
        let effective_rated_at = rated_at.or(last_watched_at);

        let trakt_str = trakt_id.to_string();
        all_records.push(MovieRecord {
            id: format!("trakt:{trakt_str}"),
            platform: "trakt".to_string(),
            title: title.clone(),
            year,
            rating,
            rated_at: effective_rated_at,
            external_id: Some(trakt_str.clone()),
            source_url: slug.map(|s| format!("https://trakt.tv/movies/{s}")),
            identifiers: MovieIdentifiers {
                trakt: Some(trakt_str),
                imdb: imdb_id,
                tmdb: tmdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: w,
        });
    }

    let count = all_records.len();
    Ok((
        FetchResult {
            platform: "trakt".to_string(),
            item_count: count,
            stored_count: count,
        },
        all_records,
    ))
}

pub async fn fetch_trakt_watchlist(
    config: &TraktConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let client = trakt_client(config)?;
    let watchlist = client.fetch_watchlist().await?;

    let mut all_records = Vec::new();
    for item in watchlist {
        let movie = match item.get("movie") {
            Some(m) => m,
            None => continue,
        };
        let ids = movie.get("ids");
        let trakt_id = ids.and_then(|v| v.get("trakt")).and_then(|v| v.as_i64()).unwrap_or(0);
        let imdb_id = ids.and_then(|v| v.get("imdb")).and_then(|v| v.as_str()).map(ToOwned::to_owned);
        let tmdb_id = ids.and_then(|v| v.get("tmdb")).and_then(|v| v.as_i64()).map(|v| v.to_string());
        let slug = ids.and_then(|v| v.get("slug")).and_then(|v| v.as_str());

        let title = movie.get("title").and_then(|v| v.as_str()).unwrap_or("Unknown").to_string();
        let year = movie.get("year").and_then(|v| v.as_i64()).map(|y| y as i32);
        let listed_at = item.get("listed_at").and_then(|v| v.as_str()).and_then(|s| DateTime::parse_from_rfc3339(s).ok()).map(|dt| dt.with_timezone(&Utc));

        let trakt_str = trakt_id.to_string();
        all_records.push(WishlistRecord {
            id: format!("trakt:{trakt_str}"),
            platform: "trakt".to_string(),
            title: title.clone(),
            year,
            external_id: Some(trakt_str.clone()),
            source_url: slug.map(|s| format!("https://trakt.tv/movies/{s}")),
            identifiers: MovieIdentifiers {
                trakt: Some(trakt_str),
                imdb: imdb_id,
                tmdb: tmdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: item,
            created_at: listed_at,
        });
    }

    let count = all_records.len();
    Ok((
        json!({
            "platform": "trakt",
            "item_count": count,
            "stored_count": count,
            "implemented": true
        }),
        all_records,
    ))
}

pub async fn sync_item_to_trakt(
    client: &TraktClient,
    item: &SyncPreviewItem,
) -> Result<SyncExecutionItem> {
    let mut ids = json!({});
    if let Some(trakt_id) = &item.identifiers.trakt {
        ids["trakt"] = json!(trakt_id.parse::<i64>().unwrap_or(0));
    }
    if let Some(imdb_id) = &item.identifiers.imdb {
        ids["imdb"] = json!(imdb_id);
    }
    if let Some(tmdb_id) = &item.identifiers.tmdb {
        ids["tmdb"] = json!(tmdb_id.parse::<i64>().unwrap_or(0));
    }

    let movie_obj = json!({
        "title": item.title,
        "year": item.year,
        "ids": ids,
    });

    let _ = client.sync_history(movie_obj.clone()).await?;

    if let Some(rating) = item.source_rating {
        let rating_int = rating.round() as i64;
        let mut rating_obj = movie_obj.clone();
        rating_obj["rating"] = json!(rating_int.clamp(1, 10));
        let _ = client.sync_ratings(rating_obj).await?;
    }

    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.identifiers.trakt.clone(),
        target_url: item.source_url.clone(),
        status: "success".to_string(),
        reason: None,
    })
}
