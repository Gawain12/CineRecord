use anyhow::{Context, Result, anyhow};
use chrono::{DateTime, Utc};
use cinerecord_core::{
    CookiePlatformConfig, FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult,
    SyncExecutionItem, SyncPreviewItem, WishlistRecord,
};
use reqwest::Client;
use serde_json::{Value, json};

pub fn browser_user_agent() -> &'static str {
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

pub async fn validate_imdb_cookie(
    config: &CookiePlatformConfig,
) -> Result<PlatformValidationResult> {
    let cookie = config
        .cookie
        .as_deref()
        .context("IMDb cookie is required")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let url = "https://www.imdb.com/profile/";
    let resp = client
        .get(url)
        .header("User-Agent", browser_user_agent())
        .header("Cookie", cookie)
        .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        .send()
        .await
        .with_context(|| format!("failed to connect to IMDb at {url}"))?;

    let status = resp.status();
    let final_url = resp.url().to_string();
    if !status.is_success() || final_url.contains("/registration/") || final_url.contains("/signin") {
        return Ok(PlatformValidationResult {
            platform: "imdb".to_string(),
            success: false,
            message: "IMDb Cookie 校验未通过，请重新抓取或同步 Cookie".to_string(),
            profile: None,
        });
    }

    let text = resp.text().await.unwrap_or_default();
    let user_id = extract_imdb_user_id_from_html(&text);
    let display_name = extract_imdb_display_name_from_html(&text);
    let avatar = extract_imdb_avatar_from_html(&text);

    let profile_data = json!({
        "user_id": user_id,
        "display_name": display_name,
        "avatar": avatar,
        "profile_link": user_id.as_ref().map(|id| format!("https://www.imdb.com/user/{id}/")),
    });

    let display_user = display_name
        .as_deref()
        .or(user_id.as_deref())
        .unwrap_or("IMDb 用户");

    Ok(PlatformValidationResult {
        platform: "imdb".to_string(),
        success: true,
        message: format!("IMDb Cookie 已验证 · 用户: {display_user}"),
        profile: Some(profile_data),
    })
}

fn extract_imdb_user_id_from_html(html: &str) -> Option<String> {
    if let Some(pos) = html.find("/user/ur") {
        let after = &html[pos + 6..];
        let end = after.find(|c: char| !c.is_ascii_alphanumeric()).unwrap_or(after.len());
        let id = &after[..end];
        if id.starts_with("ur") && id.len() > 4 {
            return Some(id.to_string());
        }
    }
    None
}

fn extract_imdb_display_name_from_html(html: &str) -> Option<String> {
    if let Some(pos) = html.find(r#"class="imdb-header__account-toggle""#) {
        let slice = &html[pos..pos + 200.min(html.len() - pos)];
        if let Some(t_pos) = slice.find(r#"aria-label=""#) {
            let after = &slice[t_pos + 12..];
            if let Some(end) = after.find('"') {
                let name = &after[..end];
                if !name.trim().is_empty() {
                    return Some(name.trim().to_string());
                }
            }
        }
    }
    None
}

fn extract_imdb_avatar_from_html(html: &str) -> Option<String> {
    if let Some(pos) = html.find(r#"data-testid="profile-avatar""#) {
        let slice = &html[pos..pos + 300.min(html.len() - pos)];
        if let Some(src_pos) = slice.find(r#"src=""#) {
            let after = &slice[src_pos + 5..];
            if let Some(end) = after.find('"') {
                return Some(after[..end].to_string());
            }
        }
    }
    None
}

pub async fn fetch_imdb_rated_movies(
    config: &CookiePlatformConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let cookie = config
        .cookie
        .as_deref()
        .context("IMDb cookie is required")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;

    let url = "https://api.graphql.imdb.com/";
    let mut after_cursor: Option<String> = None;
    let mut all_records = Vec::new();

    loop {
        let variables = json!({
            "first": 250,
            "after": after_cursor
        });

        let query_body = json!({
            "operationName": "userRatings",
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
                }
            }
        });

        let resp = client
            .post(url)
            .header("User-Agent", browser_user_agent())
            .header("Cookie", cookie)
            .header("Content-Type", "application/json")
            .header("x-imdb-client-name", "imdb-web-next-localized")
            .json(&query_body)
            .send()
            .await?;

        let body: Value = resp.json().await?;
        let user_ratings = body
            .get("data")
            .and_then(|d| d.get("userRatings"));

        let edges = user_ratings
            .and_then(|r| r.get("edges"))
            .and_then(|e| e.as_array())
            .cloned()
            .unwrap_or_default();

        if edges.is_empty() {
            break;
        }

        for edge in edges {
            let node = match edge.get("node") {
                Some(n) => n,
                None => continue,
            };
            let title_obj = match node.get("title") {
                Some(t) => t,
                None => continue,
            };

            let imdb_id = match title_obj.get("id").and_then(|v| v.as_str()) {
                Some(id) if !id.is_empty() => id.to_string(),
                _ => continue,
            };
            let title = title_obj
                .get("titleText")
                .and_then(|v| v.get("text"))
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown")
                .to_string();
            let year = title_obj
                .get("releaseYear")
                .and_then(|v| v.get("year"))
                .and_then(|v| v.as_i64())
                .map(|y| y as i32);
            let user_rating = node.get("userRating");
            let rating = user_rating.and_then(|v| v.get("value")).and_then(|v| v.as_f64());
            let rated_at = user_rating
                .and_then(|v| v.get("date"))
                .and_then(|v| v.as_str())
                .and_then(|s| parse_imdb_rating_date(s));

            all_records.push(MovieRecord {
                id: format!("imdb:{imdb_id}"),
                platform: "imdb".to_string(),
                title: title.clone(),
                year,
                rating,
                rated_at,
                external_id: Some(imdb_id.clone()),
                source_url: Some(format!("https://www.imdb.com/title/{imdb_id}/")),
                identifiers: MovieIdentifiers {
                    imdb: Some(imdb_id),
                    ..MovieIdentifiers::default()
                },
                raw_json: node.clone(),
            });
        }

        let page_info = user_ratings.and_then(|r| r.get("pageInfo"));
        let has_next = page_info
            .and_then(|p| p.get("hasNextPage"))
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

        if !has_next {
            break;
        }

        after_cursor = page_info
            .and_then(|p| p.get("endCursor"))
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned);

        if after_cursor.is_none() {
            break;
        }
    }

    let count = all_records.len();
    Ok((
        FetchResult {
            platform: "imdb".to_string(),
            item_count: count,
            stored_count: count,
        },
        all_records,
    ))
}

fn parse_imdb_rating_date(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            chrono::NaiveDate::parse_from_str(value.trim(), "%Y-%m-%d")
                .ok()
                .and_then(|d| d.and_hms_opt(0, 0, 0))
                .map(|d| DateTime::<Utc>::from_naive_utc_and_offset(d, Utc))
        })
}

pub async fn fetch_imdb_watchlist(
    config: &CookiePlatformConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let cookie = config
        .cookie
        .as_deref()
        .context("IMDb cookie is required")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;

    let url = "https://www.imdb.com/watchlist/";
    let resp = client
        .get(url)
        .header("User-Agent", browser_user_agent())
        .header("Cookie", cookie)
        .send()
        .await?;

    let html = resp.text().await.unwrap_or_default();
    let next_data = extract_imdb_next_data(&html);
    let records = if let Some(ref data) = next_data {
        extract_imdb_watchlist_records(data)
    } else {
        Vec::new()
    };

    let count = records.len();
    Ok((
        json!({
            "platform": "imdb",
            "item_count": count,
            "stored_count": count,
            "implemented": true
        }),
        records,
    ))
}

pub fn extract_imdb_next_data(html: &str) -> Option<Value> {
    if let Some(pos) = html.find(r#"id="__NEXT_DATA__""#) {
        let after = &html[pos..];
        if let Some(start) = after.find('>') {
            let json_slice = &after[start + 1..];
            if let Some(end) = json_slice.find("</script>") {
                let json_str = &json_slice[..end];
                return serde_json::from_str(json_str).ok();
            }
        }
    }
    None
}

pub fn extract_imdb_watchlist_records(next_data: &Value) -> Vec<WishlistRecord> {
    let mut records = Vec::new();
    traverse_imdb_watchlist_value(next_data, &mut records);
    records
}

fn traverse_imdb_watchlist_value(val: &Value, out: &mut Vec<WishlistRecord>) {
    if let Some(obj) = val.as_object() {
        if let Some(item) = imdb_watchlist_record_from_value(val) {
            out.push(item);
            return;
        }
        for (_, v) in obj {
            traverse_imdb_watchlist_value(v, out);
        }
    } else if let Some(arr) = val.as_array() {
        for v in arr {
            traverse_imdb_watchlist_value(v, out);
        }
    }
}

fn imdb_watchlist_record_from_value(val: &Value) -> Option<WishlistRecord> {
    let title_obj = val.get("title").or(Some(val))?;
    let id = title_obj.get("id").and_then(|v| v.as_str())?;
    if !id.starts_with("tt") {
        return None;
    }
    let title = title_obj
        .get("titleText")
        .and_then(|v| v.get("text"))
        .and_then(|v| v.as_str())
        .or_else(|| title_obj.get("title").and_then(|v| v.as_str()))?;
    let year = title_obj
        .get("releaseYear")
        .and_then(|v| v.get("year"))
        .and_then(|v| v.as_i64())
        .map(|y| y as i32);

    Some(WishlistRecord {
        id: format!("imdb:{id}"),
        platform: "imdb".to_string(),
        title: title.to_string(),
        year,
        external_id: Some(id.to_string()),
        source_url: Some(format!("https://www.imdb.com/title/{id}/")),
        identifiers: MovieIdentifiers {
            imdb: Some(id.to_string()),
            ..MovieIdentifiers::default()
        },
        raw_json: val.clone(),
        created_at: None,
    })
}

pub async fn rate_imdb_title(
    cookie_header: &str,
    imdb_id: &str,
    rating: i32,
) -> Result<()> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let url = "https://api.graphql.imdb.com/";
    let rating_val = rating.clamp(1, 10);

    let query_body = json!({
        "operationName": "UpdateTitleRating",
        "query": r#"
            mutation UpdateTitleRating($rating: Int!, $titleId: ID!) {
                rateTitle(input: {rating: $rating, titleId: $titleId}) {
                    rating {
                        value
                    }
                }
            }
        "#,
        "variables": {
            "titleId": imdb_id,
            "rating": rating_val,
        }
    });

    let resp = client
        .post(url)
        .header("User-Agent", browser_user_agent())
        .header("Cookie", cookie_header)
        .header("Content-Type", "application/json")
        .header("Referer", format!("https://www.imdb.com/title/{imdb_id}/"))
        .header("Origin", "https://www.imdb.com")
        .header("x-imdb-client-name", "imdb-web-next-localized")
        .json(&query_body)
        .send()
        .await?;

    let status = resp.status();
    if !status.is_success() {
        return Err(anyhow!("IMDb rating mutation HTTP failed: {status}"));
    }

    let body: Value = resp.json().await?;
    if let Some(errors) = body.get("errors") {
        return Err(anyhow!("IMDb GraphQL returned errors: {errors:?}"));
    }

    Ok(())
}

pub async fn sync_item_to_imdb(
    config: &CookiePlatformConfig,
    item: &SyncPreviewItem,
) -> Result<SyncExecutionItem> {
    let cookie = config
        .cookie
        .as_deref()
        .context("IMDb cookie is required")?;

    let imdb_id = item
        .target_linking_id
        .as_deref()
        .or_else(|| item.identifiers.imdb.as_deref())
        .context("IMDb ID (tt...) is required to sync to IMDb")?;

    let rating_float = item
        .source_rating
        .context("source rating is required for IMDb sync")?;

    let rating_int = rating_float.round() as i32;
    rate_imdb_title(cookie, imdb_id, rating_int).await?;

    Ok(SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: Some(imdb_id.to_string()),
        target_url: Some(format!("https://www.imdb.com/title/{imdb_id}/")),
        status: "success".to_string(),
        reason: None,
    })
}
