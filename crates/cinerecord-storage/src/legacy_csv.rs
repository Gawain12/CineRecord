use std::{
    collections::HashMap,
    io::Read,
    path::{Path, PathBuf},
};

use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use cinerecord_core::{AppConfig, MovieIdentifiers, MovieRecord, WishlistRecord};
use serde::{Deserialize, Serialize};
use sqlx::SqlitePool;
use tokio::fs;

use crate::{
    StoragePaths, normalize_title, replace_library_items, replace_wishlist_items,
    update_platform_local_counts,
};

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

/// Imports a Letterboxd export uploaded from the browser (`diary.csv`, `ratings.csv`
/// or `watched.csv` for the library, `watchlist.csv` for the wishlist).
pub async fn import_letterboxd_upload(
    pool: &SqlitePool,
    kind: &str,
    content: String,
) -> Result<LibrarySnapshot> {
    match kind {
        "watchlist" => {
            let items = parse_letterboxd_watchlist(content.as_bytes())?;
            replace_wishlist_items(pool, "letterboxd", &items).await?;
            update_platform_local_counts(pool, "letterboxd", None, Some(items.len())).await?;
            Ok(LibrarySnapshot {
                platform: "letterboxd".to_string(),
                item_count: items.len(),
            })
        }
        "library" | "diary" => {
            let items = dedupe_rewatches(parse_legacy_csv_reader(content.as_bytes(), "letterboxd")?);
            replace_library_items(pool, "letterboxd", &items).await?;
            update_platform_local_counts(pool, "letterboxd", Some(items.len()), None).await?;
            Ok(LibrarySnapshot {
                platform: "letterboxd".to_string(),
                item_count: items.len(),
            })
        }
        other => anyhow::bail!("unsupported Letterboxd import kind: {other}"),
    }
}

/// Diary exports list every rewatch as its own row; keep only the latest entry per film.
fn dedupe_rewatches(items: Vec<MovieRecord>) -> Vec<MovieRecord> {
    let mut latest: HashMap<(String, Option<i32>), MovieRecord> = HashMap::new();
    for item in items {
        let key = (normalize_title(&item.title), item.year);
        match latest.get(&key) {
            Some(existing) if existing.rated_at >= item.rated_at => {}
            _ => {
                latest.insert(key, item);
            }
        }
    }
    let mut items = latest.into_values().collect::<Vec<_>>();
    items.sort_by(|a, b| b.rated_at.cmp(&a.rated_at));
    items
}

pub fn parse_letterboxd_watchlist(reader: impl Read) -> Result<Vec<WishlistRecord>> {
    let mut reader = csv::Reader::from_reader(reader);
    let headers = reader
        .headers()?
        .iter()
        .map(|header| header.trim_start_matches('\u{feff}').to_owned())
        .collect::<Vec<_>>();
    if !headers.iter().any(|header| header == "Name") {
        anyhow::bail!("not a Letterboxd watchlist CSV (missing Name column)");
    }
    let mut items = Vec::new();
    for row in reader.records() {
        let row = row?;
        let map = headers
            .iter()
            .cloned()
            .zip(row.iter().map(ToOwned::to_owned))
            .collect::<HashMap<_, _>>();
        let Some(title) = first_value(&map, &["Name", "Title"]) else {
            continue;
        };
        let uri = first_value(&map, &["Letterboxd URI"]);
        items.push(WishlistRecord {
            id: uuid::Uuid::new_v4().to_string(),
            platform: "letterboxd".to_string(),
            title,
            year: first_value(&map, &["Year"]).and_then(|value| value.parse::<i32>().ok()),
            external_id: uri.clone(),
            source_url: uri.clone(),
            identifiers: MovieIdentifiers {
                letterboxd: uri,
                ..MovieIdentifiers::default()
            },
            created_at: first_value(&map, &["Date"]).and_then(|value| parse_legacy_datetime(&value)),
            raw_json: serde_json::to_value(&map)?,
        });
    }
    Ok(items)
}

pub fn parse_legacy_csv(path: &Path, platform: &str) -> Result<Vec<MovieRecord>> {
    parse_legacy_csv_reader(std::fs::File::open(path)?, platform)
}

pub fn parse_legacy_csv_reader(reader: impl Read, platform: &str) -> Result<Vec<MovieRecord>> {
    let mut reader = csv::Reader::from_reader(reader);
    let headers = reader
        .headers()?
        .iter()
        .map(|header| header.trim_start_matches('\u{feff}').to_owned())
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
            .and_then(|value| value.parse::<f64>().ok())
            // Letterboxd rates on a 0.5–5 star scale; everything else here is out of 10.
            .map(|value| if platform == "letterboxd" { value * 2.0 } else { value });
        let rated_at = first_value(
            &map,
            &["Date Rated", "Watched Date", "watched_at", "rated_at", "Date"],
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn letterboxd_diary_ratings_are_scaled_and_rewatches_deduped() {
        let csv = "Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n\
2024-01-02,Heat,1995,https://boxd.it/a,4.5,,,2024-01-01\n\
2024-03-02,Heat,1995,https://boxd.it/b,5,Yes,,2024-03-01\n\
2024-02-02,Alien,1979,https://boxd.it/c,3,,,2024-02-01\n";
        let items = dedupe_rewatches(parse_legacy_csv_reader(csv.as_bytes(), "letterboxd").unwrap());
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].title, "Heat");
        assert_eq!(items[0].rating, Some(10.0));
        assert_eq!(items[1].rating, Some(6.0));
    }

    #[test]
    fn letterboxd_watchlist_parses_rows() {
        let csv = "\u{feff}Date,Name,Year,Letterboxd URI\n2024-05-01,Paris Texas,1984,https://boxd.it/x\n";
        let items = parse_letterboxd_watchlist(csv.as_bytes()).unwrap();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].year, Some(1984));
        assert_eq!(items[0].identifiers.letterboxd.as_deref(), Some("https://boxd.it/x"));
        assert!(parse_letterboxd_watchlist("a,b\n1,2\n".as_bytes()).is_err());
    }
}
