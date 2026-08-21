use anyhow::{Result, bail};
use cinerecord_core::{
    MovieIdentifiers, MovieRecord, SyncPreviewItem, SyncPreviewRequest, SyncPreviewResult,
};
use std::collections::HashMap;

pub fn supports_sync_pair(source: &str, target: &str) -> bool {
    let valid_sources = ["tmdb", "trakt", "imdb", "douban", "letterboxd"];
    let valid_targets = ["tmdb", "trakt", "imdb", "douban", "cinepersona"];
    source != target
        && valid_sources.contains(&source)
        && valid_targets.contains(&target)
}

pub fn identifier_keys(
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
) -> Vec<String> {
    let mut keys = Vec::new();
    let mut imdb = identifiers.imdb.as_deref().filter(|s| !s.trim().is_empty()).map(ToOwned::to_owned);
    let mut douban = identifiers.douban.as_deref().filter(|s| !s.trim().is_empty()).map(ToOwned::to_owned);
    let mut tmdb = identifiers.tmdb.as_deref().filter(|s| !s.trim().is_empty()).map(ToOwned::to_owned);

    if imdb.is_none() {
        if let Some(ref d) = douban {
            imdb = cinerecord_storage::lookup_cached_imdb_for_douban(d);
        } else if let Some(ref tm) = tmdb {
            imdb = cinerecord_storage::lookup_cached_imdb_for_tmdb(tm);
        }
    }
    if douban.is_none() {
        if let Some(ref im) = imdb {
            douban = cinerecord_storage::lookup_cached_douban_for_imdb(im);
        } else if let Some(ref tm) = tmdb {
            douban = cinerecord_storage::lookup_cached_douban_for_tmdb(tm);
        }
    }
    if tmdb.is_none() {
        if let Some(ref im) = imdb {
            tmdb = cinerecord_storage::lookup_cached_tmdb_for_imdb(im);
        } else if let Some(ref d) = douban {
            tmdb = cinerecord_storage::lookup_cached_tmdb_for_douban(d);
        }
    }

    if let Some(ref im) = imdb {
        keys.push(format!("imdb:{im}"));
    }
    if let Some(ref tm) = tmdb {
        keys.push(format!("tmdb:{tm}"));
    }
    if let Some(trakt) = identifiers.trakt.as_deref().filter(|s| !s.trim().is_empty()) {
        keys.push(format!("trakt:{trakt}"));
    }
    if let Some(ref d) = douban {
        keys.push(format!("douban:{d}"));
    }
    if let Some(letterboxd) = identifiers.letterboxd.as_deref().filter(|s| !s.trim().is_empty()) {
        keys.push(format!("letterboxd:{letterboxd}"));
    }
    if !title.trim().is_empty() {
        let normalized = cinerecord_storage::normalize_title(title);
        if !normalized.is_empty() {
            keys.push(format!("title:{normalized}:{}", year.unwrap_or_default()));
        }
    }
    keys
}

pub fn resolve_target_linking_id(
    target: &str,
    identifiers: &MovieIdentifiers,
    target_item: Option<&MovieRecord>,
) -> Option<String> {
    if let Some(target_record) = target_item {
        if let Some(ref ext) = target_record.external_id {
            if target != "imdb" || ext.starts_with("tt") {
                return Some(ext.clone());
            }
        }
        if target == "imdb" {
            if let Some(ref im) = target_record.identifiers.imdb {
                if !im.trim().is_empty() {
                    return Some(im.clone());
                }
            }
        }
        if target == "tmdb" {
            if let Some(ref tm) = target_record.identifiers.tmdb {
                if !tm.trim().is_empty() {
                    return Some(tm.clone());
                }
            }
        }
        if target == "douban" {
            if let Some(ref d) = target_record.identifiers.douban {
                if !d.trim().is_empty() {
                    return Some(d.clone());
                }
            }
        }
    }
    match target {
        "tmdb" => identifiers
            .tmdb
            .clone()
            .or_else(|| {
                identifiers
                    .imdb
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_tmdb_for_imdb)
            })
            .or_else(|| {
                identifiers
                    .douban
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_tmdb_for_douban)
            }),
        "trakt" => identifiers.trakt.clone().or_else(|| identifiers.imdb.clone()),
        "imdb" => identifiers
            .imdb
            .clone()
            .or_else(|| {
                identifiers
                    .douban
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_imdb_for_douban)
            })
            .or_else(|| {
                identifiers
                    .tmdb
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_imdb_for_tmdb)
            }),
        "douban" => identifiers
            .douban
            .clone()
            .or_else(|| {
                identifiers
                    .imdb
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_douban_for_imdb)
            })
            .or_else(|| {
                identifiers
                    .tmdb
                    .as_deref()
                    .and_then(cinerecord_storage::lookup_cached_douban_for_tmdb)
            }),
        _ => None,
    }
}

pub fn is_valid_rating(rating: Option<f64>) -> bool {
    matches!(rating, Some(r) if r > 0.0)
}

pub fn ratings_match(source: Option<f64>, target: Option<f64>) -> bool {
    match (source, target) {
        (Some(s), Some(t)) => (s - t).abs() < 0.01,
        (None, None) => true,
        _ => false,
    }
}

pub fn format_rating(rating: Option<f64>) -> String {
    match rating {
        Some(r) => format!("{r:.1}"),
        None => "-".to_string(),
    }
}

pub fn build_sync_preview(
    source_platform: &str,
    target_platform: &str,
    source_items: &[MovieRecord],
    target_items: &[MovieRecord],
    request: &SyncPreviewRequest,
) -> Result<SyncPreviewResult> {
    if !supports_sync_pair(source_platform, target_platform) {
        bail!("unsupported sync pair: {source_platform} -> {target_platform}");
    }

    let mut target_lookup = HashMap::new();
    for item in target_items {
        for key in identifier_keys(&item.identifiers, &item.title, item.year) {
            target_lookup.entry(key).or_insert_with(|| item.clone());
        }
    }

    let mut sorted_sources: Vec<&MovieRecord> = source_items.iter().collect();
    sorted_sources.sort_by(|a, b| match (a.rated_at, b.rated_at) {
        (Some(ra), Some(rb)) => rb.cmp(&ra),
        (Some(_), None) => std::cmp::Ordering::Less,
        (None, Some(_)) => std::cmp::Ordering::Greater,
        (None, None) => b.year.unwrap_or(0).cmp(&a.year.unwrap_or(0)),
    });

    let limit = if request.recent_limit == 0 {
        sorted_sources.len()
    } else {
        request.recent_limit
    };

    let mut window_sources: Vec<&MovieRecord> = sorted_sources.into_iter().take(limit).collect();
    // Sort from oldest to newest so that sync execution follows chronological order
    window_sources.sort_by(|a, b| match (a.rated_at, b.rated_at) {
        (Some(ra), Some(rb)) => ra.cmp(&rb),
        (Some(_), None) => std::cmp::Ordering::Greater,
        (None, Some(_)) => std::cmp::Ordering::Less,
        (None, None) => a.year.unwrap_or(0).cmp(&b.year.unwrap_or(0)),
    });

    let mut items = Vec::new();

    for source_item in window_sources {
        let keys = identifier_keys(
            &source_item.identifiers,
            &source_item.title,
            source_item.year,
        );
        let target_item = keys.iter().find_map(|k| target_lookup.get(k));

        let target_linking_id =
            resolve_target_linking_id(target_platform, &source_item.identifiers, target_item);

        let target_existing_rating = target_item.and_then(|t| t.rating);
        let effective_source_rating = source_item.rating.or(request.default_rating);

        let (action, reason) = if target_item.is_none() {
            if target_platform == "imdb" && target_linking_id.is_none() {
                ("skip".to_string(), Some("未解析到目标 IMDb ID".to_string()))
            } else if !is_valid_rating(effective_source_rating) {
                ("skip".to_string(), Some("源记录无评分且未设置默认评分".to_string()))
            } else {
                ("new".to_string(), None)
            }
        } else if !request.only_new {
            if request.overwrite {
                if is_valid_rating(effective_source_rating) {
                    if ratings_match(effective_source_rating, target_existing_rating) {
                        ("skip".to_string(), Some("目标平台已存在相同评分".to_string()))
                    } else {
                        ("overwrite".to_string(), None)
                    }
                } else {
                    ("skip".to_string(), Some("源平台无评分且未指定默认评分".to_string()))
                }
            } else if target_existing_rating.is_none() && is_valid_rating(effective_source_rating) {
                ("overwrite".to_string(), None)
            } else {
                ("skip".to_string(), Some("目标平台已有评分且未开启覆盖".to_string()))
            }
        } else {
            ("skip".to_string(), Some("目标平台已存在该影视 (仅同步新增已开启)".to_string()))
        };

        items.push(SyncPreviewItem {
            title: source_item.title.clone(),
            year: source_item.year,
            source_platform: source_platform.to_string(),
            target_platform: target_platform.to_string(),
            source_rating: effective_source_rating,
            target_existing_rating,
            source_url: source_item.source_url.clone(),
            target_linking_id,
            identifiers: source_item.identifiers.clone(),
            action,
            reason,
        });
    }

    let preview_count = items
        .iter()
        .filter(|item| item.action != "skip" && item.reason.is_none())
        .count();

    Ok(SyncPreviewResult {
        direction: format!("{source_platform}-to-{target_platform}"),
        source_count: source_items.len(),
        target_count: target_items.len(),
        preview_count,
        items,
    })
}
