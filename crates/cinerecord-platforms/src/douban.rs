use anyhow::{Context, Result, anyhow, bail};
use chrono::{DateTime, Utc};
use cinerecord_core::{
    CookiePlatformConfig, FetchResult, MovieIdentifiers, MovieRecord, PlatformValidationResult,
    SyncExecutionItem, SyncPreviewItem, WishlistRecord,
};
use reqwest::Client;
use scraper::{Html, Selector};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashSet;

use crate::imdb::browser_user_agent;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DoubanPublicSnapshot {
    pub user_id: String,
    pub display_name: Option<String>,
    pub avatar: Option<String>,
    pub watched_count: Option<usize>,
    pub wishlist_count: Option<usize>,
    pub sample_title: Option<String>,
}

#[derive(Debug, Clone)]
pub struct DoubanInterestProbe {
    pub total: Option<i64>,
    pub sample_title: Option<String>,
}

pub fn douban_ck_from_cookie(cookie: &str) -> Option<String> {
    cookie.split(';').find_map(|part| {
        let (k, v) = part.split_once('=')?;
        if k.trim() == "ck" {
            Some(v.trim().trim_matches('"').to_string())
        } else {
            None
        }
    })
}

pub fn extract_douban_user_id_from_cookie(cookie: &str) -> Option<String> {
    cookie.split(';').find_map(|part| {
        let (k, v) = part.split_once('=')?;
        let k_trim = k.trim();
        if k_trim == "dbcl2" || k_trim == "id" {
            let v_trim = v.trim().trim_matches('"');
            let id = v_trim.split(':').next().unwrap_or(v_trim);
            if !id.is_empty() {
                return Some(id.to_string());
            }
        }
        None
    })
}

pub fn is_douban_protection_error(err_str: &str) -> bool {
    let lower = err_str.to_lowercase();
    lower.contains("403")
        || lower.contains("sec.douban.com")
        || lower.contains("blocked")
        || lower.contains("captcha")
        || lower.contains("protection")
        || lower.contains("login_jump")
}

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};

pub fn extract_douban_profile_from_cookie(cookie: &str) -> (Option<String>, Option<String>, Option<String>) {
    let mut user_id = extract_douban_user_id_from_cookie(cookie);
    let mut display_name = None;
    let mut avatar = None;

    for part in cookie.split(';') {
        let Some((k, v)) = part.split_once('=') else { continue };
        let k = k.trim();
        let v = v.trim().trim_matches('"');
        if k == "talionusr" {
            if let Ok(bytes) = BASE64.decode(v) {
                if let Ok(val) = serde_json::from_slice::<Value>(&bytes) {
                    if let Some(id) = val.get("id").and_then(|i| i.as_str()) {
                        if user_id.is_none() {
                            user_id = Some(id.to_string());
                        }
                    }
                    if let Some(name) = val.get("name").and_then(|n| n.as_str()) {
                        display_name = Some(name.to_string());
                    }
                    if let Some(icon) = val.get("icon").and_then(|i| i.as_str()) {
                        avatar = Some(icon.to_string());
                    }
                }
            }
        }
    }

    if avatar.is_none() {
        if let Some(ref id) = user_id {
            avatar = Some(format!("https://img1.doubanio.com/icon/u{id}-1.jpg"));
        }
    }

    (user_id, display_name, avatar)
}

pub async fn validate_douban_cookie(
    config: &CookiePlatformConfig,
) -> Result<PlatformValidationResult> {
    let cookie = config
        .cookie
        .as_deref()
        .context("Douban cookie is required")?;

    let (extracted_id, display_name, avatar) = extract_douban_profile_from_cookie(cookie);
    let user_id = config
        .user_id
        .clone()
        .or(extracted_id)
        .unwrap_or_else(|| "people".to_string());

    let has_ck = douban_ck_from_cookie(cookie).is_some();
    let has_dbcl2 = extract_douban_user_id_from_cookie(cookie).is_some();
    let write_ready = has_ck || has_dbcl2;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let probe = fetch_douban_interest_probe(&client, cookie, &user_id, "done").await;
    match probe {
        Ok(info) => {
            let total = info.total.unwrap_or(0);
            let profile_data = json!({
                "user_id": user_id,
                "display_name": display_name.or_else(|| config.user_id.clone()),
                "avatar": avatar,
                "write_ready": write_ready,
                "watched": total,
                "watched_total": total,
                "sample_title": info.sample_title,
                "profile_link": format!("https://movie.douban.com/people/{user_id}/"),
            });
            Ok(PlatformValidationResult {
                platform: "douban".to_string(),
                success: true,
                message: "豆瓣已连接".to_string(),
                profile: Some(profile_data),
            })
        }
        Err(e) => {
            let msg = e.to_string();
            if is_douban_protection_error(&msg) {
                Ok(PlatformValidationResult {
                    platform: "douban".to_string(),
                    success: false,
                    message: "豆瓣安全风控拦截，请等待片刻后重试或更新 Cookie".to_string(),
                    profile: None,
                })
            } else {
                Ok(PlatformValidationResult {
                    platform: "douban".to_string(),
                    success: false,
                    message: format!("豆瓣 Cookie 校验失败: {msg}"),
                    profile: None,
                })
            }
        }
    }
}

pub async fn validate_douban_public_profile(
    user_id: &str,
) -> Result<PlatformValidationResult> {
    let snapshot = fetch_douban_public_snapshot(user_id).await?;
    let profile_data = json!({
        "user_id": snapshot.user_id,
        "display_name": snapshot.display_name,
        "avatar": snapshot.avatar,
        "watched": snapshot.watched_count,
        "watched_total": snapshot.watched_count,
        "wish": snapshot.wishlist_count,
        "wish_total": snapshot.wishlist_count,
        "sample_title": snapshot.sample_title,
        "profile_link": format!("https://movie.douban.com/people/{user_id}/"),
    });
    let name = snapshot.display_name.as_deref().unwrap_or(user_id);
    let count_msg = format!("{} 部看过，{} 部想看", snapshot.watched_count.unwrap_or(0), snapshot.wishlist_count.unwrap_or(0));
    Ok(PlatformValidationResult {
        platform: "douban".to_string(),
        success: true,
        message: format!("豆瓣公开主页已识别 · 用户 {name} · 可读取 {count_msg}"),
        profile: Some(profile_data),
    })
}

pub async fn fetch_douban_public_snapshot(user_id: &str) -> Result<DoubanPublicSnapshot> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;
    let url = format!("https://movie.douban.com/people/{user_id}/collect");
    let resp = client
        .get(&url)
        .header("User-Agent", browser_user_agent())
        .send()
        .await?;

    let html = resp.text().await.unwrap_or_default();
    Ok(parse_douban_public_snapshot_html(user_id, &html))
}

fn parse_douban_public_snapshot_html(user_id: &str, html: &str) -> DoubanPublicSnapshot {
    let document = Html::parse_document(html);

    let title_sel = Selector::parse("h1").ok();
    let display_name = title_sel.and_then(|s| {
        document
            .select(&s)
            .next()
            .map(|e| e.text().collect::<String>().trim().to_string())
    });

    let nav_sel = Selector::parse(".nav-items a").ok();
    let mut watched_count = None;
    let mut wishlist_count = None;

    if let Some(sel) = nav_sel {
        for a in document.select(&sel) {
            let t = a.text().collect::<String>();
            if t.contains("看过") {
                watched_count = extract_number_in_parens(&t);
            } else if t.contains("想看") {
                wishlist_count = extract_number_in_parens(&t);
            }
        }
    }

    let item_sel = Selector::parse(".item .title a").ok();
    let sample_title = item_sel.and_then(|s| {
        document
            .select(&s)
            .next()
            .map(|e| e.text().collect::<String>().trim().to_string())
    });

    DoubanPublicSnapshot {
        user_id: user_id.to_string(),
        display_name,
        avatar: None,
        watched_count,
        wishlist_count,
        sample_title,
    }
}

fn extract_number_in_parens(text: &str) -> Option<usize> {
    let start = text.find('(')?;
    let end = text.find(')')?;
    text[start + 1..end].trim().parse::<usize>().ok()
}

pub async fn fetch_douban_movies(
    config: &CookiePlatformConfig,
) -> Result<(FetchResult, Vec<MovieRecord>)> {
    let cookie = config.cookie.as_deref().filter(|c| !c.trim().is_empty());
    let user_id = config.user_id.as_deref().context("Douban user_id is required")?;

    let records = if let Some(cookie_str) = cookie {
        fetch_douban_interest_movie_records(user_id, cookie_str, "done").await?
    } else {
        fetch_douban_public_items(user_id).await?
    };

    let count = records.len();
    Ok((
        FetchResult {
            platform: "douban".to_string(),
            item_count: count,
            stored_count: count,
        },
        records,
    ))
}

pub async fn fetch_douban_wishlist(
    config: &CookiePlatformConfig,
) -> Result<(Value, Vec<WishlistRecord>)> {
    let cookie = config.cookie.as_deref().filter(|c| !c.trim().is_empty());
    let user_id = config.user_id.as_deref().context("Douban user_id is required")?;

    let records = if let Some(cookie_str) = cookie {
        fetch_douban_interest_wishlist_records(user_id, cookie_str, "mark").await?
    } else {
        fetch_douban_public_wishlist_items(user_id).await?
    };

    let count = records.len();
    Ok((
        json!({
            "platform": "douban",
            "item_count": count,
            "stored_count": count,
            "implemented": true
        }),
        records,
    ))
}

pub async fn fetch_douban_interest_probe(
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
        .header(
            "Referer",
            format!("https://movie.douban.com/people/{user_id}/"),
        )
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
        .header(
            "Referer",
            format!("https://movie.douban.com/people/{user_id}/"),
        )
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

pub async fn fetch_douban_interest_movie_records(
    user_id: &str,
    cookie_header: &str,
    status: &str,
) -> Result<Vec<MovieRecord>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()?;
    let mut start = 0usize;
    let mut records = Vec::new();
    let mut seen = HashSet::new();
    loop {
        let payload =
            fetch_douban_interest_page(&client, cookie_header, user_id, status, start, 50).await?;
        let total = payload.get("total").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
        let interests = payload
            .get("interests")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if interests.is_empty() {
            break;
        }
        let batch_len = interests.len();
        for interest in &interests {
            let Some(record) = douban_movie_record_from_interest(interest) else {
                continue;
            };
            let Some(key) = record
                .external_id
                .clone()
                .or_else(|| record.identifiers.douban.clone())
            else {
                continue;
            };
            if seen.insert(key) {
                records.push(record);
            }
        }
        start += batch_len;
        if batch_len == 0 || (total > 0 && start >= total) {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(150)).await;
    }
    Ok(records)
}

pub async fn fetch_douban_interest_wishlist_records(
    user_id: &str,
    cookie_header: &str,
    status: &str,
) -> Result<Vec<WishlistRecord>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()?;
    let mut start = 0usize;
    let mut records = Vec::new();
    let mut seen = HashSet::new();
    loop {
        let payload =
            fetch_douban_interest_page(&client, cookie_header, user_id, status, start, 50).await?;
        let total = payload.get("total").and_then(|v| v.as_u64()).unwrap_or(0) as usize;
        let interests = payload
            .get("interests")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if interests.is_empty() {
            break;
        }
        let batch_len = interests.len();
        for interest in &interests {
            let Some(record) = douban_wishlist_record_from_interest(interest) else {
                continue;
            };
            let Some(key) = record
                .external_id
                .clone()
                .or_else(|| record.identifiers.douban.clone())
            else {
                continue;
            };
            if seen.insert(key) {
                records.push(record);
            }
        }
        start += batch_len;
        if batch_len == 0 || (total > 0 && start >= total) {
            break;
        }
        tokio::time::sleep(std::time::Duration::from_millis(150)).await;
    }
    Ok(records)
}

fn parse_douban_datetime(text: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(text)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            chrono::NaiveDateTime::parse_from_str(text, "%Y-%m-%d %H:%M:%S")
                .ok()
                .map(|ndt| ndt.and_utc())
        })
        .or_else(|| {
            chrono::NaiveDate::parse_from_str(text, "%Y-%m-%d")
                .ok()
                .and_then(|nd| nd.and_hms_opt(0, 0, 0))
                .map(|ndt| ndt.and_utc())
        })
}

fn douban_movie_record_from_interest(interest: &Value) -> Option<MovieRecord> {
    let subject = interest.get("subject")?;
    let douban_id = subject
        .get("id")
        .and_then(|v| v.as_str().map(ToOwned::to_owned).or_else(|| v.as_i64().map(|n| n.to_string())))?;
    let title = subject
        .get("title")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown")
        .to_string();
    let year = subject
        .get("year")
        .and_then(|v| {
            v.as_str()
                .and_then(|y| y.parse::<i32>().ok())
                .or_else(|| v.as_i64().map(|y| y as i32))
        });
    let raw_rating = interest
        .get("rating")
        .and_then(|r| r.get("value"))
        .and_then(|v| v.as_f64());
    // Convert 1..5 star rating to 10-point scale
    let rating = raw_rating.map(|v| if v <= 5.0 { v * 2.0 } else { v });

    let rated_at = interest
        .get("create_time")
        .and_then(|t| t.as_str())
        .and_then(parse_douban_datetime);

    let imdb_id = subject
        .get("imdb_id")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned)
        .or_else(|| cinerecord_storage::lookup_cached_imdb_for_douban(&douban_id));

    Some(MovieRecord {
        id: format!("douban:{douban_id}"),
        platform: "douban".to_string(),
        title,
        year,
        rating,
        rated_at,
        external_id: Some(douban_id.clone()),
        source_url: Some(format!("https://movie.douban.com/subject/{douban_id}/")),
        identifiers: MovieIdentifiers {
            douban: Some(douban_id),
            imdb: imdb_id,
            ..MovieIdentifiers::default()
        },
        raw_json: interest.clone(),
    })
}

fn douban_wishlist_record_from_interest(interest: &Value) -> Option<WishlistRecord> {
    let subject = interest.get("subject")?;
    let douban_id = subject
        .get("id")
        .and_then(|v| v.as_str().map(ToOwned::to_owned).or_else(|| v.as_i64().map(|n| n.to_string())))?;
    let title = subject
        .get("title")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown")
        .to_string();
    let year = subject
        .get("year")
        .and_then(|v| {
            v.as_str()
                .and_then(|y| y.parse::<i32>().ok())
                .or_else(|| v.as_i64().map(|y| y as i32))
        });
    let created_at = interest
        .get("create_time")
        .and_then(|t| t.as_str())
        .and_then(parse_douban_datetime);

    let imdb_id = subject
        .get("imdb_id")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned)
        .or_else(|| cinerecord_storage::lookup_cached_imdb_for_douban(&douban_id));

    Some(WishlistRecord {
        id: format!("douban:{douban_id}"),
        platform: "douban".to_string(),
        title,
        year,
        external_id: Some(douban_id.clone()),
        source_url: Some(format!("https://movie.douban.com/subject/{douban_id}/")),
        identifiers: MovieIdentifiers {
            douban: Some(douban_id),
            imdb: imdb_id,
            ..MovieIdentifiers::default()
        },
        raw_json: interest.clone(),
        created_at,
    })
}

fn parse_douban_public_items_page(html: &str) -> (Vec<MovieRecord>, usize) {
    let document = Html::parse_document(html);
    let item_sel = Selector::parse(".grid-view .item").unwrap();
    let title_sel = Selector::parse(".title a").unwrap();
    let rating_sel = Selector::parse(".date span").unwrap();

    let mut count = 0usize;
    let mut records = Vec::new();

    for item_elem in document.select(&item_sel) {
        count += 1;
        let link_elem = item_elem.select(&title_sel).next();
        let title_raw = link_elem.map(|e| e.text().collect::<String>()).unwrap_or_default();
        let href = link_elem.and_then(|e| e.value().attr("href")).unwrap_or_default();

        let douban_id = href
            .split('/')
            .filter(|s| !s.is_empty())
            .last()
            .unwrap_or_default()
            .to_string();

        let title = title_raw
            .split('/')
            .next()
            .unwrap_or(&title_raw)
            .trim()
            .to_string();

        let rating_class = item_elem
            .select(&rating_sel)
            .next()
            .and_then(|e| e.value().attr("class"));
        let rating = rating_class.and_then(|c| {
            if c.contains("rating5") {
                Some(10.0)
            } else if c.contains("rating4") {
                Some(8.0)
            } else if c.contains("rating3") {
                Some(6.0)
            } else if c.contains("rating2") {
                Some(4.0)
            } else if c.contains("rating1") {
                Some(2.0)
            } else {
                None
            }
        });

        let imdb_id = cinerecord_storage::lookup_cached_imdb_for_douban(&douban_id);

        records.push(MovieRecord {
            id: format!("douban:{douban_id}"),
            platform: "douban".to_string(),
            title,
            year: None,
            rating,
            rated_at: None,
            external_id: Some(douban_id.clone()),
            source_url: Some(href.to_string()),
            identifiers: MovieIdentifiers {
                douban: Some(douban_id),
                imdb: imdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: json!({ "title": title_raw, "href": href, "douban_id": href }),
        });
    }

    (records, count)
}

pub async fn fetch_douban_public_items(user_id: &str) -> Result<Vec<MovieRecord>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;
    let mut start = 0usize;
    let mut records = Vec::new();

    loop {
        let url = format!(
            "https://movie.douban.com/people/{user_id}/collect?start={start}&sort=time&rating=all&filter=all&mode=grid"
        );
        let resp = client
            .get(&url)
            .header("User-Agent", browser_user_agent())
            .send()
            .await?;

        let html = resp.text().await.unwrap_or_default();
        let (page_records, count) = parse_douban_public_items_page(&html);
        records.extend(page_records);

        if count == 0 {
            break;
        }
        start += 30;
        tokio::time::sleep(std::time::Duration::from_millis(800)).await;
    }

    Ok(records)
}

fn parse_douban_public_wishlist_page(html: &str) -> (Vec<WishlistRecord>, usize) {
    let document = Html::parse_document(html);
    let item_sel = Selector::parse(".grid-view .item").unwrap();
    let title_sel = Selector::parse(".title a").unwrap();

    let mut count = 0usize;
    let mut records = Vec::new();

    for item_elem in document.select(&item_sel) {
        count += 1;
        let link_elem = item_elem.select(&title_sel).next();
        let title_raw = link_elem.map(|e| e.text().collect::<String>()).unwrap_or_default();
        let href = link_elem.and_then(|e| e.value().attr("href")).unwrap_or_default();

        let douban_id = href
            .split('/')
            .filter(|s| !s.is_empty())
            .last()
            .unwrap_or_default()
            .to_string();

        let title = title_raw
            .split('/')
            .next()
            .unwrap_or(&title_raw)
            .trim()
            .to_string();

        let imdb_id = cinerecord_storage::lookup_cached_imdb_for_douban(&douban_id);

        records.push(WishlistRecord {
            id: format!("douban:{douban_id}"),
            platform: "douban".to_string(),
            title,
            year: None,
            external_id: Some(douban_id.clone()),
            source_url: Some(href.to_string()),
            identifiers: MovieIdentifiers {
                douban: Some(douban_id),
                imdb: imdb_id,
                ..MovieIdentifiers::default()
            },
            raw_json: json!({ "title": title_raw, "href": href, "douban_id": href }),
            created_at: None,
        });
    }

    (records, count)
}

pub async fn fetch_douban_public_wishlist_items(user_id: &str) -> Result<Vec<WishlistRecord>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;
    let mut start = 0usize;
    let mut records = Vec::new();

    loop {
        let url = format!(
            "https://movie.douban.com/people/{user_id}/wish?start={start}&sort=time&mode=grid"
        );
        let resp = client
            .get(&url)
            .header("User-Agent", browser_user_agent())
            .send()
            .await?;

        let html = resp.text().await.unwrap_or_default();
        let (page_records, count) = parse_douban_public_wishlist_page(&html);
        records.extend(page_records);

        if count == 0 {
            break;
        }
        start += 30;
        tokio::time::sleep(std::time::Duration::from_millis(800)).await;
    }

    Ok(records)
}

fn parse_douban_search_id_html(html: &str) -> Option<String> {
    let document = Html::parse_document(html);
    let link_sel = Selector::parse(".result .content .title a").unwrap();

    if let Some(a) = document.select(&link_sel).next() {
        if let Some(href) = a.value().attr("href") {
            if let Some(pos) = href.find("subject/") {
                let after = &href[pos + 8..];
                let end = after.find('/').unwrap_or(after.len());
                let id = &after[..end];
                if !id.is_empty() {
                    return Some(id.to_string());
                }
            }
        }
    }
    None
}

pub async fn search_douban_id_by_imdb(imdb_id: &str) -> Result<Option<String>> {
    // 1. Fast O(1) cache check
    if let Some(cached) = cinerecord_storage::lookup_cached_douban_for_imdb(imdb_id) {
        return Ok(Some(cached));
    }

    // 2. Web search fallback
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()?;
    let url = format!("https://www.douban.com/search?cat=1002&q={imdb_id}");
    let resp = client
        .get(&url)
        .header("User-Agent", browser_user_agent())
        .send()
        .await?;

    let html = resp.text().await.unwrap_or_default();
    Ok(parse_douban_search_id_html(&html))
}

pub async fn mark_douban_collect(
    cookie_header: &str,
    douban_id: &str,
    rating_stars: Option<i32>,
) -> Result<()> {
    let ck = douban_ck_from_cookie(cookie_header)
        .context("Douban 'ck' token missing in cookie header")?;

    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let url = format!("https://movie.douban.com/j/subject/{douban_id}/interest");
    let mut form = vec![
        ("ck", ck),
        ("interest", "collect".to_string()),
        ("foldcollect", "F".to_string()),
    ];
    if let Some(stars) = rating_stars {
        let stars_clamped = stars.clamp(1, 5);
        form.push(("rating", stars_clamped.to_string()));
    }

    let resp = client
        .post(&url)
        .header("User-Agent", browser_user_agent())
        .header("Cookie", cookie_header)
        .header("Referer", format!("https://movie.douban.com/subject/{douban_id}/"))
        .form(&form)
        .send()
        .await?;

    let status = resp.status();
    if !status.is_success() {
        return Err(anyhow!("Douban mark collect HTTP failed: {status}"));
    }

    Ok(())
}

pub async fn sync_item_to_douban(
    config: &CookiePlatformConfig,
    item: &SyncPreviewItem,
) -> Result<SyncExecutionItem> {
    let cookie = config
        .cookie
        .as_deref()
        .context("Douban cookie is required")?;

    let douban_id = match &item.target_linking_id {
        Some(id) if !id.is_empty() => id.clone(),
        _ => match &item.identifiers.douban {
            Some(id) if !id.is_empty() => id.clone(),
            _ => {
                if let Some(imdb) = &item.identifiers.imdb {
                    search_douban_id_by_imdb(imdb)
                        .await?
                        .context("could not resolve Douban ID for IMDb ID")?
                } else {
                    bail!("Douban ID or IMDb ID is required to sync to Douban");
                }
            }
        },
    };

    let rating_stars = item.source_rating.map(|r| {
        let rounded = r.round() as i32;
        ((rounded + 1) / 2).clamp(1, 5)
    });

    mark_douban_collect(cookie, &douban_id, rating_stars).await?;

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
