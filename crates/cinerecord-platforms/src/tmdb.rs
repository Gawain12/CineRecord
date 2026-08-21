use anyhow::{Context, Result, anyhow};
use cinerecord_core::{
    FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult, SyncExecutionItem,
    SyncPreviewItem, TmdbConfig, WishlistRecord,
};
use reqwest::Client;
use serde_json::{Value, json};

pub const DEFAULT_TMDB_API_KEY: &str = "8ffaf38032c0f85f4f421fb0cc1241a5";

#[derive(Clone)]
pub struct TmdbClient {
    client: Client,
    pub api_key: String,
    pub session_id: Option<String>,
}

impl TmdbClient {
    pub fn new(api_key: String, session_id: Option<String>) -> Self {
        Self {
            client: Client::new(),
            api_key,
            session_id,
        }
    }

    pub async fn validate_api_key(&self) -> Result<Value> {
        let url = format!(
            "https://api.themoviedb.org/3/authentication?api_key={}",
            self.api_key
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        Ok(resp)
    }

    pub async fn create_request_token(&self) -> Result<String> {
        let url = format!(
            "https://api.themoviedb.org/3/authentication/token/new?api_key={}",
            self.api_key
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        resp.get("request_token")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned)
            .context("failed to obtain TMDB request_token")
    }

    pub async fn create_session(&self, request_token: &str) -> Result<String> {
        let url = format!(
            "https://api.themoviedb.org/3/authentication/session/new?api_key={}",
            self.api_key
        );
        let resp: Value = self
            .client
            .post(&url)
            .json(&json!({ "request_token": request_token }))
            .send()
            .await?
            .json()
            .await?;
        resp.get("session_id")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned)
            .context("failed to create TMDB session_id")
    }

    pub async fn fetch_account(&self) -> Result<Value> {
        let session_id = self
            .session_id
            .as_deref()
            .context("session_id is required to fetch account")?;
        self.fetch_account_with_session(session_id).await
    }

    pub async fn fetch_account_with_session(&self, session_id: &str) -> Result<Value> {
        let url = format!(
            "https://api.themoviedb.org/3/account?api_key={}&session_id={}",
            self.api_key, session_id
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        if resp.get("id").is_none() {
            return Err(anyhow!("failed to fetch TMDB account: {resp:?}"));
        }
        Ok(resp)
    }

    pub async fn get_account_rated_movies(&self, account_id: i64, page: usize) -> Result<Value> {
        let session_id = self
            .session_id
            .as_deref()
            .context("session_id is required")?;
        let url = format!(
            "https://api.themoviedb.org/3/account/{account_id}/rated/movies?api_key={}&session_id={}&page={page}&language=zh-CN",
            self.api_key, session_id
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        Ok(resp)
    }

    pub async fn get_account_watchlist(&self, account_id: i64, page: usize) -> Result<Value> {
        let session_id = self
            .session_id
            .as_deref()
            .context("session_id is required")?;
        let url = format!(
            "https://api.themoviedb.org/3/account/{account_id}/watchlist/movies?api_key={}&session_id={}&page={page}&language=zh-CN",
            self.api_key, session_id
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        Ok(resp)
    }

    pub async fn rate_movie(&self, tmdb_id: &str, rating: f64) -> Result<()> {
        let session_id = self
            .session_id
            .as_deref()
            .context("session_id is required to rate movie")?;
        let url = format!(
            "https://api.themoviedb.org/3/movie/{tmdb_id}/rating?api_key={}&session_id={}",
            self.api_key, session_id
        );
        let clamped = rating.clamp(0.5, 10.0);
        let resp: Value = self
            .client
            .post(&url)
            .json(&json!({ "value": clamped }))
            .send()
            .await?
            .json()
            .await?;

        let status_code = resp.get("status_code").and_then(|v| v.as_i64()).unwrap_or(0);
        if status_code == 1 || status_code == 12 {
            Ok(())
        } else {
            let msg = resp
                .get("status_message")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown error");
            Err(anyhow!("TMDB rate movie failed: {msg} (code {status_code})"))
        }
    }

    pub async fn find_movie_by_imdb_id(&self, imdb_id: &str) -> Result<Option<String>> {
        let url = format!(
            "https://api.themoviedb.org/3/find/{imdb_id}?api_key={}&external_source=imdb_id",
            self.api_key
        );
        let resp: Value = self.client.get(&url).send().await?.json().await?;
        if let Some(results) = resp.get("movie_results").and_then(|v| v.as_array()) {
            if let Some(first) = results.first() {
                if let Some(id) = first.get("id").and_then(|v| v.as_i64()) {
                    return Ok(Some(id.to_string()));
                }
            }
        }
        if let Some(results) = resp.get("tv_results").and_then(|v| v.as_array()) {
            if let Some(first) = results.first() {
                if let Some(id) = first.get("id").and_then(|v| v.as_i64()) {
                    return Ok(Some(id.to_string()));
                }
            }
        }
        Ok(None)
    }
}

pub fn tmdb_client(config: &TmdbConfig) -> Result<TmdbClient> {
    let api_key = config
        .api_key
        .as_deref()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or(DEFAULT_TMDB_API_KEY)
        .to_string();
    let session_id = config
        .session_id
        .as_deref()
        .filter(|v| !v.trim().is_empty())
        .map(ToOwned::to_owned);
    Ok(TmdbClient::new(api_key, session_id))
}

pub async fn start_tmdb_auth(config: &cinerecord_core::AppConfig) -> Result<Value> {
    let client = tmdb_client(&config.platforms.tmdb)?;
    let request_token = client.create_request_token().await?;
    Ok(json!({
        "request_token": request_token,
        "auth_url": format!("https://www.themoviedb.org/authenticate/{request_token}"),
    }))
}

pub async fn complete_tmdb_auth(config: &cinerecord_core::AppConfig) -> Result<Value> {
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
    let username = account
        .get("username")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    Ok(json!({
        "session_id": session_id,
        "account_id": account_id.map(|v| v.to_string()),
        "username": username,
        "profile": account,
    }))
}

pub async fn test_tmdb(config: &TmdbConfig) -> Result<PlatformValidationResult> {
    let client = tmdb_client(config)?;
    let auth = client.validate_api_key().await?;
    if !auth
        .get("success")
        .and_then(|v| v.as_bool())
        .unwrap_or(false)
    {
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
            "TMDB 已连接".to_string()
        } else {
            "TMDB API Key 校验通过；补充 Session 后即可抓取和同步评分".to_string()
        },
        profile,
    })
}

pub fn extract_tmdb_avatar(account: &Value) -> Option<String> {
    let avatar_path = account
        .get("avatar")
        .and_then(|v| v.get("tmdb"))
        .and_then(|v| v.get("avatar_path"))
        .and_then(|v| v.as_str());
    if let Some(path) = avatar_path {
        return Some(format!("https://image.tmdb.org/t/p/w200{path}"));
    }
    let gravatar_hash = account
        .get("avatar")
        .and_then(|v| v.get("gravatar"))
        .and_then(|v| v.get("hash"))
        .and_then(|v| v.as_str());
    if let Some(hash) = gravatar_hash {
        return Some(format!("https://www.gravatar.com/avatar/{hash}?s=200"));
    }
    None
}

pub async fn fetch_tmdb_rated_movies(
    config: &TmdbConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let client = tmdb_client(config)?;
    let account = client.fetch_account().await?;
    let account_id = account
        .get("id")
        .and_then(|v| v.as_i64())
        .context("TMDB account id missing")?;

    let mut page = 1;
    let mut all_records = Vec::new();

    loop {
        let payload = client.get_account_rated_movies(account_id, page).await?;
        let results = payload
            .get("results")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        if results.is_empty() {
            break;
        }

        for item in results {
            let id = item.get("id").and_then(|v| v.as_i64()).unwrap_or(0);
            let title = item
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown")
                .to_string();
            let release_date = item.get("release_date").and_then(|v| v.as_str());
            let year = release_date.and_then(|s| s.split('-').next()).and_then(|y| y.parse::<i32>().ok());
            let rating = item.get("rating").and_then(|v| v.as_f64());
            let tmdb_id = id.to_string();

            all_records.push(MovieRecord {
                id: format!("tmdb:{tmdb_id}"),
                platform: "tmdb".to_string(),
                title: title.clone(),
                year,
                rating,
                rated_at: None,
                external_id: Some(tmdb_id.clone()),
                source_url: Some(format!("https://www.themoviedb.org/movie/{tmdb_id}")),
                identifiers: MovieIdentifiers {
                    tmdb: Some(tmdb_id),
                    ..MovieIdentifiers::default()
                },
                raw_json: item,
            });
        }

        let total_pages = payload
            .get("total_pages")
            .and_then(|v| v.as_i64())
            .unwrap_or(1);
        if page as i64 >= total_pages {
            break;
        }
        page += 1;
    }

    let count = all_records.len();
    Ok((
        FetchResult {
            platform: "tmdb".to_string(),
            item_count: count,
            stored_count: count,
        },
        all_records,
    ))
}

pub async fn fetch_tmdb_watchlist(
    config: &TmdbConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let client = tmdb_client(config)?;
    let account = client.fetch_account().await?;
    let account_id = account
        .get("id")
        .and_then(|v| v.as_i64())
        .context("TMDB account id missing")?;

    let mut page = 1;
    let mut all_records = Vec::new();

    loop {
        let payload = client.get_account_watchlist(account_id, page).await?;
        let results = payload
            .get("results")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        if results.is_empty() {
            break;
        }

        for item in results {
            let id = item.get("id").and_then(|v| v.as_i64()).unwrap_or(0);
            let title = item
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown")
                .to_string();
            let release_date = item.get("release_date").and_then(|v| v.as_str());
            let year = release_date.and_then(|s| s.split('-').next()).and_then(|y| y.parse::<i32>().ok());
            let tmdb_id = id.to_string();

            all_records.push(WishlistRecord {
                id: format!("tmdb:{tmdb_id}"),
                platform: "tmdb".to_string(),
                title: title.clone(),
                year,
                external_id: Some(tmdb_id.clone()),
                source_url: Some(format!("https://www.themoviedb.org/movie/{tmdb_id}")),
                identifiers: MovieIdentifiers {
                    tmdb: Some(tmdb_id),
                    ..MovieIdentifiers::default()
                },
                raw_json: item,
                created_at: None,
            });
        }

        let total_pages = payload
            .get("total_pages")
            .and_then(|v| v.as_i64())
            .unwrap_or(1);
        if page as i64 >= total_pages {
            break;
        }
        page += 1;
    }

    let count = all_records.len();
    Ok((
        json!({
            "platform": "tmdb",
            "item_count": count,
            "stored_count": count,
            "implemented": true
        }),
        all_records,
    ))
}

pub async fn sync_item_to_tmdb(
    client: &TmdbClient,
    item: &SyncPreviewItem,
) -> Result<SyncExecutionItem> {
    let mut tmdb_id = item
        .target_linking_id
        .clone()
        .or_else(|| item.identifiers.tmdb.clone());

    if tmdb_id.is_none() {
        let imdb_id = item.identifiers.imdb.clone().or_else(|| {
            item.identifiers
                .douban
                .as_deref()
                .and_then(cinerecord_storage::lookup_cached_imdb_for_douban)
        });
        if let Some(im) = imdb_id {
            if let Ok(Some(found_id)) = client.find_movie_by_imdb_id(&im).await {
                tmdb_id = Some(found_id);
            }
        }
    }

    let tmdb_id = tmdb_id.context("TMDB ID is required to sync rating to TMDB")?;

    let rating = item
        .source_rating
        .context("source rating is required for TMDB sync")?;

    client.rate_movie(&tmdb_id, rating).await?;

    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: Some(tmdb_id.clone()),
        target_url: Some(format!("https://www.themoviedb.org/movie/{tmdb_id}")),
        status: "success".to_string(),
        reason: None,
    })
}
