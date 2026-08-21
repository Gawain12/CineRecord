use std::{
    collections::HashMap,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use cinerecord_core::{AppConfig, MovieIdentifiers, MovieRecord};
use serde::{Deserialize, Serialize};
use sqlx::SqlitePool;
use tokio::fs;

use crate::{StoragePaths, replace_library_items};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LibrarySnapshot {
    pub platform: String,
    pub item_count: usize,
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

pub fn parse_legacy_csv(path: &Path, platform: &str) -> Result<Vec<MovieRecord>> {
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
