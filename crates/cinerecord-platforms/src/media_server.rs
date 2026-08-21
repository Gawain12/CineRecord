use anyhow::{Context, Result, anyhow};
use cinerecord_core::MediaServerItem;
use reqwest::Client;
use serde_json::Value;

pub async fn test_media_server(url: &str, api_key: Option<&str>) -> Result<bool> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()?;
    let trimmed = url.trim().trim_end_matches('/');
    let key = api_key.unwrap_or("").trim();

    // 1. Try Emby / Jellyfin /System/Info
    let mut req = client.get(format!("{trimmed}/System/Info"));
    if !key.is_empty() {
        req = req.header("X-Emby-Token", key).query(&[("api_key", key)]);
    }
    if let Ok(resp) = req.send().await {
        if resp.status().is_success() {
            return Ok(true);
        }
    }

    // 2. Try Plex /identity
    let mut req_plex = client.get(format!("{trimmed}/identity"));
    if !key.is_empty() {
        req_plex = req_plex.header("X-Plex-Token", key).query(&[("X-Plex-Token", key)]);
    }
    if let Ok(resp) = req_plex.send().await {
        if resp.status().is_success() {
            return Ok(true);
        }
    }

    // 3. Fallback /api/v1/system/status
    let mut req_generic = client.get(format!("{trimmed}/api/v1/system/status"));
    if !key.is_empty() {
        req_generic = req_generic.header("X-Api-Key", key);
    }
    let resp = req_generic.send().await?;
    Ok(resp.status().is_success())
}

pub async fn fetch_media_server_movies(
    url: &str,
    api_key: Option<&str>,
) -> Result<Vec<MediaServerItem>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()?;
    let trimmed = url.trim().trim_end_matches('/');
    let key = api_key.unwrap_or("").trim();

    // Fetch from Emby / Jellyfin /Items endpoint
    let mut items = Vec::new();
    let mut start_index = 0;
    let limit = 500;

    loop {
        let target_url = format!("{trimmed}/Items");
        let mut req = client
            .get(&target_url)
            .query(&[
                ("Recursive", "true"),
                ("IncludeItemTypes", "Movie"),
                ("Fields", "ProviderIds,ProductionYear,OriginalTitle,Path,MediaSources,ServerId"),
                ("StartIndex", &start_index.to_string()),
                ("Limit", &limit.to_string()),
            ]);
        if !key.is_empty() {
            req = req.header("X-Emby-Token", key).query(&[("api_key", key)]);
        }

        let resp = match req.send().await {
            Ok(r) if r.status().is_success() => r,
            Ok(r) => {
                // If /Items failed, maybe generic /api/v1/movies?
                if start_index == 0 {
                    let mut req_gen = client.get(format!("{trimmed}/api/v1/movies"));
                    if !key.is_empty() {
                        req_gen = req_gen.header("X-Api-Key", key);
                    }
                    if let Ok(r_gen) = req_gen.send().await {
                        if r_gen.status().is_success() {
                            let raw: Vec<Value> = r_gen.json().await.unwrap_or_default();
                            for it in raw {
                                items.push(MediaServerItem {
                                    title: it.get("title").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                                    year: it.get("year").and_then(|v| v.as_i64()).map(|y| y as i32),
                                    imdb_id: it.get("imdb_id").and_then(|v| v.as_str()).map(ToOwned::to_owned),
                                    tmdb_id: it.get("tmdb_id").and_then(|v| v.as_str()).map(ToOwned::to_owned)
                                        .or_else(|| it.get("tmdb_id").and_then(|v| v.as_i64()).map(|v| v.to_string())),
                                    library_url: it.get("url").and_then(|v| v.as_str()).map(ToOwned::to_owned),
                                    media_path: it.get("path").and_then(|v| v.as_str()).map(ToOwned::to_owned),
                                    file_name: it.get("file_name").and_then(|v| v.as_str()).map(ToOwned::to_owned),
                                });
                            }
                            return Ok(items);
                        }
                    }
                }
                return Err(anyhow!("media server returned status {}", r.status()));
            }
            Err(e) => return Err(anyhow!("failed to connect to media server: {e}")),
        };

        let data: Value = resp.json().await.with_context(|| "failed to parse media server JSON")?;
        let batch = data.get("Items").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        if batch.is_empty() {
            break;
        }

        let batch_len = batch.len();
        for item in batch {
            let title = item
                .get("Name")
                .or_else(|| item.get("OriginalTitle"))
                .or_else(|| item.get("title"))
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown")
                .to_string();
            let year = item
                .get("ProductionYear")
                .or_else(|| item.get("year"))
                .and_then(|v| v.as_i64())
                .map(|y| y as i32);
            
            let provider_ids = item.get("ProviderIds");
            let imdb_id = provider_ids
                .and_then(|p| p.get("Imdb").or_else(|| p.get("imdb")))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| item.get("imdb_id").and_then(|v| v.as_str()).map(ToOwned::to_owned));
            let tmdb_id = provider_ids
                .and_then(|p| p.get("Tmdb").or_else(|| p.get("tmdb")))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| provider_ids.and_then(|p| p.get("Tmdb").or_else(|| p.get("tmdb"))).and_then(|v| v.as_i64()).map(|v| v.to_string()))
                .or_else(|| item.get("tmdb_id").and_then(|v| v.as_str()).map(ToOwned::to_owned));

            let item_id = item.get("Id").and_then(|v| v.as_str()).unwrap_or("");
            let server_id = item.get("ServerId").and_then(|v| v.as_str()).unwrap_or("");
            let library_url = if !item_id.is_empty() {
                Some(format!("{trimmed}/web/index.html#!/item?id={item_id}&serverId={server_id}"))
            } else {
                item.get("url").and_then(|v| v.as_str()).map(ToOwned::to_owned)
            };

            let media_path = item.get("Path").and_then(|v| v.as_str()).map(ToOwned::to_owned)
                .or_else(|| {
                    item.get("MediaSources")
                        .and_then(|ms| ms.as_array())
                        .and_then(|arr| arr.first())
                        .and_then(|s| s.get("Path"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            
            let file_name = media_path.as_deref().and_then(|p| {
                let norm = p.replace('\\', "/");
                norm.split('/').filter(|s| !s.is_empty()).last().map(ToOwned::to_owned)
            });

            items.push(MediaServerItem {
                title,
                year,
                imdb_id,
                tmdb_id,
                library_url,
                media_path,
                file_name,
            });
        }

        let total_count = data.get("TotalRecordCount").and_then(|v| v.as_i64()).unwrap_or(0) as usize;
        if total_count > 0 && items.len() >= total_count {
            break;
        }
        if batch_len < limit {
            break;
        }
        start_index += batch_len;
    }

    Ok(items)
}
