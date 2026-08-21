use std::collections::HashMap;

use chrono::{DateTime, Utc};
use cinerecord_core::{
    MediaServerItem, MovieIdentifiers, MovieRecord, PlatformDiffItem, PlatformDiffResult,
    UnifiedMediaItem, UnifiedSourceEntry, WishlistRecord,
};

use crate::cache::{lookup_cached_douban_for_imdb, lookup_cached_imdb_for_douban};

pub const LIBRARY_PLATFORMS: [&str; 6] = ["douban", "imdb", "trakt", "letterboxd", "tmdb", "cinepersona"];



pub fn infer_identifiers(
    platform: &str,
    external_id: Option<&str>,
    raw_json: &serde_json::Value,
) -> MovieIdentifiers {
    let mut ids = MovieIdentifiers::default();
    match platform {
        "tmdb" => {
            ids.tmdb = external_id.map(ToOwned::to_owned).or_else(|| {
                raw_json
                    .get("id")
                    .and_then(|v| v.as_i64())
                    .map(|v| v.to_string())
            });
            ids.imdb = raw_json
                .get("external_ids")
                .and_then(|v| v.get("imdb_id"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
        }
        "trakt" => {
            let trakt_ids = raw_json
                .get("ids")
                .or_else(|| raw_json.get("movie").and_then(|movie| movie.get("ids")));
            ids.trakt = trakt_ids
                .and_then(|v| v.get("trakt"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    raw_json
                        .get("Trakt ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| external_id.map(ToOwned::to_owned));
            ids.tmdb = trakt_ids
                .and_then(|v| v.get("tmdb"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    raw_json
                        .get("TMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.imdb = trakt_ids
                .and_then(|v| v.get("imdb"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
        }
        "imdb" => {
            ids.imdb = external_id
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("Const")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.douban = raw_json
                .get("douban_id")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_f64())
                        .map(|v| format!("{v:.0}"))
                });
            ids.tmdb = raw_json
                .get("TMDB ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
        }
        "douban" => {
            ids.douban = external_id
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("douban_id")
                        .and_then(|v| v.as_f64())
                        .map(|v| format!("{v:.0}"))
                })
                .or_else(|| {
                    raw_json
                        .get("movie_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("id"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                });
            ids.imdb = raw_json
                .get("Const")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("imdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDb ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("IMDB ID")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("imdb"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("subject")
                        .and_then(|v| v.get("imdb_id"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    ids.douban
                        .as_deref()
                        .and_then(lookup_cached_imdb_for_douban)
                });
            ids.tmdb = raw_json
                .get("TMDB ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("tmdb_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
            ids.trakt = raw_json
                .get("Trakt ID")
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    raw_json
                        .get("trakt_id")
                        .and_then(|v| v.as_i64())
                        .map(|v| v.to_string())
                });
        }
        "letterboxd" => {
            ids.letterboxd = external_id.map(ToOwned::to_owned);
        }
        "cinepersona" => {
            let movie = raw_json.get("movie");
            ids.imdb = movie
                .and_then(|m| m.get("imdbId"))
                .and_then(|v| v.as_str())
                .map(ToOwned::to_owned)
                .or_else(|| {
                    external_id
                        .filter(|id| id.starts_with("tt"))
                        .map(ToOwned::to_owned)
                });
            ids.tmdb = movie
                .and_then(|m| m.get("tmdbId"))
                .and_then(|v| v.as_i64())
                .map(|v| v.to_string())
                .or_else(|| {
                    movie
                        .and_then(|m| m.get("tmdbId"))
                        .and_then(|v| v.as_str())
                        .map(ToOwned::to_owned)
                })
                .or_else(|| {
                    external_id
                        .filter(|id| !id.starts_with("tt"))
                        .map(ToOwned::to_owned)
                });
        }
        _ => {}
    }
    ids
}

pub fn filter_by_search(
    items: Vec<UnifiedMediaItem>,
    search: Option<&str>,
) -> Vec<UnifiedMediaItem> {
    let Some(q) = search else {
        return items;
    };
    if q.trim().is_empty() {
        return items;
    }
    let q_lower = q.to_lowercase();
    items
        .into_iter()
        .filter(|item| {
            item.title.to_lowercase().contains(&q_lower)
                || item
                    .original_title
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
                || item
                    .directors
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
                || item
                    .actors
                    .as_ref()
                    .map(|s| s.to_lowercase().contains(&q_lower))
                    .unwrap_or(false)
        })
        .collect()
}

pub fn aggregate_library_records(records: Vec<MovieRecord>) -> Vec<UnifiedMediaItem> {
    let mut groups = Vec::<UnifiedMediaItem>::new();
    let mut key_to_group_idx = HashMap::<String, usize>::new();

    for record in records {
        let mut ids = infer_identifiers(&record.platform, record.external_id.as_deref(), &record.raw_json);
        merge_unified_identifiers(&mut ids, &record.identifiers);

        let lookup_keys = unified_lookup_keys(&ids, &record.title, record.year);
        let mut found_idx = None;
        for k in &lookup_keys {
            if let Some(&idx) = key_to_group_idx.get(k) {
                found_idx = Some(idx);
                break;
            }
        }
        if found_idx.is_none() {
            if let Some(ref ext) = record.external_id {
                let platform_key = format!("{}:{ext}", record.platform);
                if let Some(&idx) = key_to_group_idx.get(&platform_key) {
                    found_idx = Some(idx);
                }
            }
        }

        let idx = match found_idx {
            Some(idx) => idx,
            None => {
                let primary_key = lookup_keys
                    .first()
                    .cloned()
                    .or_else(|| clean_string(record.external_id.as_deref()).map(|ext| format!("{}:{ext}", record.platform)))
                    .unwrap_or_else(|| format!("{}:{}", record.platform, normalize_title(&record.title)));

                let new_item = UnifiedMediaItem {
                    id: primary_key,
                    title: record.title.clone(),
                    original_title: extract_original_title(&record.raw_json),
                    year: record.year,
                    media_type: extract_media_type(&record.raw_json),
                    poster_url: extract_poster_url(&record.raw_json),
                    source_url: record.source_url.clone(),
                    identifiers: ids.clone(),
                    personal_rating: record.rating,
                    rated_at: record.rated_at,
                    public_rating: extract_public_rating(&record.raw_json),
                    public_votes: extract_public_votes(&record.raw_json),
                    source_platforms: Vec::new(),
                    sources: Vec::new(),
                    library_matched: true,
                    library_url: record.source_url.clone(),
                    library_title: Some(record.title.clone()),
                    library_year: record.year,
                    library_media_path: None,
                    library_file_name: None,
                    directors: extract_directors(&record.raw_json),
                    actors: extract_actors(&record.raw_json),
                    genres: extract_genres(&record.raw_json),
                    country: extract_country(&record.raw_json),
                    duration: extract_duration(&record.raw_json),
                };
                groups.push(new_item);
                groups.len() - 1
            }
        };

        let entry = &mut groups[idx];
        merge_unified_identifiers(&mut entry.identifiers, &ids);
        fill_unified_defaults(
            entry,
            &record.title,
            record.year,
            &record.raw_json,
            record.source_url.as_deref(),
        );
        merge_library_preference(entry, &record);
        push_unified_source(
            entry,
            UnifiedSourceEntry {
                platform: record.platform.clone(),
                external_id: record.external_id.clone(),
                source_url: record.source_url.clone(),
                rating: record.rating,
                rated_at: record.rated_at,
            },
        );

        let all_keys = unified_lookup_keys(&entry.identifiers, &entry.title, entry.year);
        for k in all_keys {
            key_to_group_idx.insert(k, idx);
        }
        if let Some(ref ext) = record.external_id {
            key_to_group_idx.insert(format!("{}:{ext}", record.platform), idx);
        }
    }

    groups
}

pub fn normalized_selected_platforms(selected_platforms: &[String]) -> Vec<&str> {
    selected_platforms
        .iter()
        .map(|item| item.trim())
        .filter(|item| LIBRARY_PLATFORMS.contains(item))
        .collect()
}

pub fn has_all_selected_platforms(item: &UnifiedMediaItem, selected_platforms: &[&str]) -> bool {
    selected_platforms.iter().all(|platform| {
        item.source_platforms
            .iter()
            .any(|source| source == platform)
    })
}

pub fn filter_library_view_items(
    items: Vec<UnifiedMediaItem>,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
) -> Vec<UnifiedMediaItem> {
    let selected = normalized_selected_platforms(selected_platforms);
    let show_union = selected.is_empty();
    items
        .into_iter()
        .filter(|item| match platform_filter {
            Some(platform) if LIBRARY_PLATFORMS.contains(&platform) => {
                item.source_platforms
                    .iter()
                    .any(|source| source == platform)
            }
            Some("shared") => {
                if show_union {
                    item.source_platforms.len() > 1
                } else {
                    has_all_selected_platforms(item, &selected)
                }
            }
            Some("single") => {
                item.source_platforms.len() == 1
            }
            _ if show_union => true,
            _ => item
                .source_platforms
                .iter()
                .any(|source| selected.contains(&source.as_str())),
        })
        .collect()
}

pub fn aggregate_wishlist_records(
    records: Vec<WishlistRecord>,
    library: &[UnifiedMediaItem],
    media_server_items: Option<&[MediaServerItem]>,
) -> Vec<UnifiedMediaItem> {
    let library_lookup = build_unified_lookup(library);
    let mut groups = HashMap::<String, UnifiedMediaItem>::new();
    for record in records {
        let key = unified_key(
            &record.identifiers,
            &record.title,
            record.year,
            record.external_id.as_deref(),
            &record.platform,
        );
        let mut library_matched = false;
        let mut library_url = None;
        let mut library_title = None;
        let mut library_year = None;
        let mut library_media_path = None;
        let mut library_file_name = None;

        let in_library_item = unified_lookup_match(
            &library_lookup,
            &record.identifiers,
            &record.title,
            record.year,
        );
        if let Some(item) = in_library_item {
            library_matched = true;
            library_url = item.library_url.clone().or_else(|| item.source_url.clone());
            library_title = item.library_title.clone().or_else(|| Some(item.title.clone()));
            library_year = item.library_year.or(item.year);
            library_media_path = item.library_media_path.clone();
            library_file_name = item.library_file_name.clone();
        }

        if let Some(media_items) = media_server_items {
            for m_item in media_items {
                let mut id_match = false;
                if let Some(imdb) = &m_item.imdb_id {
                    if let Some(w_imdb) = &record.identifiers.imdb {
                        if imdb == w_imdb {
                            id_match = true;
                        }
                    }
                }
                if !id_match {
                    if let Some(tmdb) = &m_item.tmdb_id {
                        if let Some(w_tmdb) = &record.identifiers.tmdb {
                            if tmdb == w_tmdb {
                                id_match = true;
                            }
                        }
                    }
                }
                if !id_match {
                    if m_item.year == record.year {
                        let m_title = m_item.title.to_lowercase().replace(' ', "");
                        let w_title = record.title.to_lowercase().replace(' ', "");
                        if !m_title.is_empty() && m_title == w_title {
                            id_match = true;
                        }
                    }
                }
                if id_match {
                    library_matched = true;
                    if m_item.library_url.is_some() {
                        library_url = m_item.library_url.clone();
                    }
                    library_title = Some(m_item.title.clone());
                    library_year = m_item.year;
                    library_media_path = m_item.media_path.clone();
                    library_file_name = m_item.file_name.clone();
                    break;
                }
            }
        }

        let entry = groups
            .entry(key.clone())
            .or_insert_with(|| UnifiedMediaItem {
                id: key.clone(),
                title: record.title.clone(),
                original_title: extract_original_title(&record.raw_json),
                year: record.year,
                media_type: extract_media_type(&record.raw_json),
                poster_url: extract_poster_url(&record.raw_json),
                source_url: record.source_url.clone(),
                identifiers: record.identifiers.clone(),
                personal_rating: None,
                rated_at: extract_date_like(&record.raw_json).or(record.created_at),
                public_rating: extract_public_rating(&record.raw_json),
                public_votes: extract_public_votes(&record.raw_json),
                source_platforms: Vec::new(),
                sources: Vec::new(),
                library_matched,
                library_url: library_url.clone(),
                library_title: library_title.clone(),
                library_year,
                library_media_path: library_media_path.clone(),
                library_file_name: library_file_name.clone(),
                directors: extract_directors(&record.raw_json),
                actors: extract_actors(&record.raw_json),
                genres: extract_genres(&record.raw_json),
                country: extract_country(&record.raw_json),
                duration: extract_duration(&record.raw_json),
            });
        merge_unified_identifiers(&mut entry.identifiers, &record.identifiers);
        fill_unified_defaults(
            entry,
            &record.title,
            record.year,
            &record.raw_json,
            record.source_url.as_deref(),
        );
        if entry.rated_at.is_none() {
            entry.rated_at = extract_date_like(&record.raw_json).or(record.created_at);
        }
        if entry.library_url.is_none() {
            entry.library_url = library_url.clone();
        }
        if entry.library_title.is_none() {
            entry.library_title = library_title.clone();
        }
        if entry.library_year.is_none() {
            entry.library_year = library_year;
        }
        if entry.library_media_path.is_none() {
            entry.library_media_path = library_media_path.clone();
        }
        if entry.library_file_name.is_none() {
            entry.library_file_name = library_file_name.clone();
        }
        entry.library_matched = entry.library_matched || library_matched;
        push_unified_source(
            entry,
            UnifiedSourceEntry {
                platform: record.platform.clone(),
                external_id: record.external_id.clone(),
                source_url: record.source_url.clone(),
                rating: None,
                rated_at: extract_date_like(&record.raw_json),
            },
        );
    }
    groups.into_values().collect()
}

pub fn merge_library_preference(entry: &mut UnifiedMediaItem, record: &MovieRecord) {
    let newer_rating = match (record.rated_at, entry.rated_at) {
        (Some(new), Some(current)) => new > current,
        (Some(_), None) => true,
        _ => false,
    };
    if entry.rated_at.is_none() || newer_rating {
        entry.personal_rating = record.rating.or(entry.personal_rating);
        entry.rated_at = record.rated_at.or(entry.rated_at);
    }
    if entry.source_url.is_none() {
        entry.source_url = record.source_url.clone();
    }
}

pub fn fill_unified_defaults(
    entry: &mut UnifiedMediaItem,
    title: &str,
    year: Option<i32>,
    raw_json: &serde_json::Value,
    source_url: Option<&str>,
) {
    if entry.title.trim().is_empty() {
        entry.title = title.to_string();
    }
    if entry.year.is_none() {
        entry.year = year.or_else(|| extract_year(raw_json));
    }
    if entry.original_title.is_none() {
        entry.original_title = extract_original_title(raw_json);
    }
    if entry.media_type.is_none() {
        entry.media_type = extract_media_type(raw_json);
    }
    let extracted_poster = extract_poster_url(raw_json);
    if let Some(new_url) = extracted_poster {
        let is_better = entry
            .poster_url
            .as_ref()
            .map(|curr| {
                let curr_invalid = curr.trim().is_empty()
                    || curr.contains("default_poster")
                    || curr.contains("placeholder");
                let new_is_rich = new_url.contains("doubanio.com")
                    || new_url.contains("tmdb.org")
                    || new_url.contains("image.tmdb.org");
                curr_invalid || (new_is_rich && curr.contains("imdb.com"))
            })
            .unwrap_or(true);
        if is_better {
            entry.poster_url = Some(new_url);
        }
    }
    if entry.source_url.is_none() {
        entry.source_url = source_url.map(ToOwned::to_owned);
    }
    if entry.public_rating.is_none() {
        entry.public_rating = extract_public_rating(raw_json);
    }
    if entry.public_votes.is_none() {
        entry.public_votes = extract_public_votes(raw_json);
    }
    if entry.directors.is_none() {
        entry.directors = extract_directors(raw_json);
    }
    if entry.actors.is_none() {
        entry.actors = extract_actors(raw_json);
    }
    if entry.genres.is_none() {
        entry.genres = extract_genres(raw_json);
    }
    if entry.country.is_none() {
        entry.country = extract_country(raw_json);
    }
    if entry.duration.is_none() {
        entry.duration = extract_duration(raw_json);
    }
}

pub fn push_unified_source(entry: &mut UnifiedMediaItem, source: UnifiedSourceEntry) {
    if !entry
        .source_platforms
        .iter()
        .any(|platform| platform == &source.platform)
    {
        entry.source_platforms.push(source.platform.clone());
    }
    let duplicate = entry.sources.iter().any(|item| {
        item.platform == source.platform
            && item.external_id == source.external_id
            && item.source_url == source.source_url
    });
    if !duplicate {
        entry.sources.push(source);
    }
}

pub fn sort_unified_items(items: &mut [UnifiedMediaItem], prefer_date: bool) {
    items.sort_by(|left, right| {
        if prefer_date {
            right
                .rated_at
                .cmp(&left.rated_at)
                .then_with(|| right.year.cmp(&left.year))
                .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
        } else {
            right
                .rated_at
                .cmp(&left.rated_at)
                .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
                .then_with(|| right.year.cmp(&left.year))
        }
    });
}

pub fn apply_paging<T>(items: Vec<T>, limit: Option<i64>, offset: Option<i64>) -> Vec<T> {
    let offset = offset.unwrap_or(0).max(0) as usize;
    let limit = limit.unwrap_or(10_000).max(0) as usize;
    items.into_iter().skip(offset).take(limit).collect()
}

pub fn build_unified_lookup(items: &[UnifiedMediaItem]) -> HashMap<String, UnifiedMediaItem> {
    let mut lookup = HashMap::new();
    for item in items {
        for key in unified_lookup_keys(&item.identifiers, &item.title, item.year) {
            lookup.entry(key).or_insert_with(|| item.clone());
        }
    }
    lookup
}

pub fn unified_lookup_match<'a>(
    lookup: &'a HashMap<String, UnifiedMediaItem>,
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
) -> Option<&'a UnifiedMediaItem> {
    unified_lookup_keys(identifiers, title, year)
        .into_iter()
        .find_map(|key| lookup.get(&key))
}

pub fn unified_lookup_keys(
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
) -> Vec<String> {
    let mut keys = Vec::new();
    let mut imdb = clean_string(identifiers.imdb.as_deref());
    let mut douban = clean_string(identifiers.douban.as_deref());

    if imdb.is_none() {
        if let Some(ref d) = douban {
            imdb = lookup_cached_imdb_for_douban(d);
        }
    }
    if douban.is_none() {
        if let Some(ref im) = imdb {
            douban = lookup_cached_douban_for_imdb(im);
        }
    }

    if let Some(ref im) = imdb {
        keys.push(format!("imdb:{im}"));
    }
    if let Some(tmdb) = clean_string(identifiers.tmdb.as_deref()) {
        keys.push(format!("tmdb:{tmdb}"));
    }
    if let Some(trakt) = clean_string(identifiers.trakt.as_deref()) {
        keys.push(format!("trakt:{trakt}"));
    }
    if let Some(ref d) = douban {
        keys.push(format!("douban:{d}"));
    }
    if let Some(letterboxd) = clean_string(identifiers.letterboxd.as_deref()) {
        keys.push(format!("letterboxd:{letterboxd}"));
    }
    if let Some(title_key) = title_year_key(title, year) {
        keys.push(title_key);
    }
    keys
}

pub fn unified_key(
    identifiers: &MovieIdentifiers,
    title: &str,
    year: Option<i32>,
    external_id: Option<&str>,
    platform: &str,
) -> String {
    unified_lookup_keys(identifiers, title, year)
        .into_iter()
        .next()
        .or_else(|| clean_string(external_id).map(|value| format!("{platform}:{value}")))
        .unwrap_or_else(|| format!("{platform}:{}", normalize_title(title)))
}

pub fn title_year_key(title: &str, year: Option<i32>) -> Option<String> {
    let normalized = normalize_title(title);
    if normalized.is_empty() {
        return None;
    }
    Some(format!("title:{normalized}:{}", year.unwrap_or_default()))
}

pub fn normalize_title(title: &str) -> String {
    title
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ('\u{4e00}'..='\u{9fff}').contains(&ch) {
                ch.to_ascii_lowercase()
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn clean_string(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

pub fn merge_unified_identifiers(target: &mut MovieIdentifiers, source: &MovieIdentifiers) {
    if target.imdb.is_none() {
        target.imdb = source.imdb.clone();
    }
    if target.tmdb.is_none() {
        target.tmdb = source.tmdb.clone();
    }
    if target.trakt.is_none() {
        target.trakt = source.trakt.clone();
    }
    if target.douban.is_none() {
        target.douban = source.douban.clone();
    }
    if target.letterboxd.is_none() {
        target.letterboxd = source.letterboxd.clone();
    }
}

pub fn extract_original_title(raw_json: &serde_json::Value) -> Option<String> {
    json_string(raw_json, &["original_title", "Original Title", "原名"])
}

pub fn extract_media_type(raw_json: &serde_json::Value) -> Option<String> {
    let value = json_string(
        raw_json,
        &["Type", "type", "Title Type", "media_type", "titleType"],
    )?;
    let lower = value.to_lowercase();
    if ["tv", "series", "show", "episode", "miniseries"]
        .iter()
        .any(|part| lower.contains(part))
    {
        return Some("tv".to_string());
    }
    Some("movie".to_string())
}

pub fn extract_poster_url(raw_json: &serde_json::Value) -> Option<String> {
    if let Some(value) = json_string(
        raw_json,
        &["Cover URL", "cover_url", "poster_url", "poster", "Cover"],
    ) {
        return Some(value);
    }
    if let Some(path) = json_string(raw_json, &["poster_path"]) {
        if path.starts_with("http://") || path.starts_with("https://") {
            return Some(path);
        }
        return Some(format!("https://image.tmdb.org/t/p/w500{path}"));
    }
    raw_json
        .get("primaryImage")
        .and_then(|value| value.get("url"))
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned)
}

pub fn parse_douban_intro(
    intro: &str,
) -> (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
) {
    let parts: Vec<&str> = intro.split('/').map(|s| s.trim()).collect();
    if parts.is_empty() {
        return (None, None, None, None);
    }

    let mut release_dates = Vec::new();
    let mut names = Vec::new();
    let mut countries = Vec::new();
    let mut genres = Vec::new();

    let common_countries = [
        "美国",
        "中国大陆",
        "中国香港",
        "中国台湾",
        "日本",
        "韩国",
        "英国",
        "法国",
        "德国",
        "意大利",
        "西班牙",
        "加拿大",
        "澳大利亚",
        "印度",
        "泰国",
        "新西兰",
        "瑞典",
        "丹麦",
        "俄罗斯",
        "爱尔兰",
        "巴西",
        "中国",
        "香港",
        "台湾",
        "日本",
        "韩国",
        "新加坡",
    ];

    let common_genres = [
        "剧情",
        "喜剧",
        "动作",
        "爱情",
        "科幻",
        "悬疑",
        "惊悚",
        "恐怖",
        "犯罪",
        "同性",
        "音乐",
        "歌舞",
        "传记",
        "历史",
        "战争",
        "西部",
        "奇幻",
        "冒险",
        "灾难",
        "武侠",
        "古装",
        "纪录片",
        "动画",
        "短片",
        "戏曲",
        "家庭",
        "儿童",
        "运动",
        "荒诞",
    ];

    for part in parts {
        if part.chars().next().map_or(false, |c| c.is_ascii_digit()) {
            release_dates.push(part);
            continue;
        }
        if part.contains("分钟") {
            continue;
        }
        if common_countries
            .iter()
            .any(|c| part == *c || part.contains(c))
        {
            countries.push(part);
            continue;
        }
        if common_genres.iter().any(|g| part == *g || part.contains(g)) {
            genres.push(part);
            continue;
        }
        names.push(part);
    }

    let (director, actors) = if names.is_empty() {
        (None, None)
    } else if names.len() == 1 {
        (Some(names[0].to_string()), None)
    } else {
        let dir = names.last().map(|s| s.to_string());
        let acts = names[0..names.len() - 1].join(", ");
        (dir, Some(acts))
    };

    let country = if countries.is_empty() {
        None
    } else {
        Some(countries.join(", "))
    };
    let genre = if genres.is_empty() {
        None
    } else {
        Some(genres.join(", "))
    };

    (director, actors, genre, country)
}

pub fn get_subject_or_root(raw_json: &serde_json::Value) -> &serde_json::Value {
    if let Some(sub) = raw_json.get("subject") {
        if sub.is_object() {
            return sub;
        }
    }
    raw_json
}

pub fn extract_directors(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("directors")
        .or_else(|| target.get("Directors"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.get("name")
                    .or_else(|| item.get("text"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.to_string())
            })
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (dir, _, _, _) = parse_douban_intro(intro);
        if dir.is_some() {
            return dir;
        }
    }
    json_string(raw_json, &["Directors", "directors", "director"])
}

pub fn extract_actors(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("actors")
        .or_else(|| target.get("Actors"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.get("name")
                    .or_else(|| item.get("text"))
                    .and_then(|n| n.as_str())
                    .map(|s| s.to_string())
            })
            .collect();
        if !names.is_empty() {
            let limit = names.len().min(5);
            return Some(names[0..limit].join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, actors, _, _) = parse_douban_intro(intro);
        if actors.is_some() {
            return actors;
        }
    }
    json_string(raw_json, &["Actors", "actors", "actor"])
}

pub fn extract_genres(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("genres")
        .or_else(|| target.get("Genres"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| {
                item.as_str().map(|s| s.to_string()).or_else(|| {
                    item.get("name")
                        .and_then(|n| n.as_str())
                        .map(|s| s.to_string())
                })
            })
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, _, genres, _) = parse_douban_intro(intro);
        if genres.is_some() {
            return genres;
        }
    }
    json_string(raw_json, &["Genres", "genres", "genre"])
}

pub fn extract_country(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target
        .get("countries")
        .or_else(|| target.get("regions"))
        .and_then(|v| v.as_array())
    {
        let names: Vec<String> = arr
            .iter()
            .filter_map(|item| item.as_str().map(|s| s.to_string()))
            .collect();
        if !names.is_empty() {
            return Some(names.join(", "));
        }
    }
    if let Some(sub) = target.get("card_subtitle").and_then(|v| v.as_str()) {
        let parts: Vec<&str> = sub.split('/').map(|s| s.trim()).collect();
        let common_countries = [
            "美国",
            "中国大陆",
            "中国香港",
            "中国台湾",
            "日本",
            "韩国",
            "英国",
            "法国",
            "德国",
            "意大利",
            "西班牙",
            "加拿大",
            "澳大利亚",
            "印度",
            "泰国",
            "新西兰",
            "瑞典",
            "丹麦",
            "俄罗斯",
            "爱尔兰",
            "巴西",
            "中国",
            "香港",
            "台湾",
        ];
        let matched_countries: Vec<String> = parts
            .iter()
            .filter(|p| common_countries.iter().any(|c| **p == *c || p.contains(c)))
            .map(|s| s.to_string())
            .collect();
        if !matched_countries.is_empty() {
            return Some(matched_countries.join(", "));
        }
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        let (_, _, _, country) = parse_douban_intro(intro);
        if country.is_some() {
            return country;
        }
    }
    json_string(raw_json, &["Country", "country", "countries", "region"])
}

pub fn extract_duration(raw_json: &serde_json::Value) -> Option<String> {
    let target = get_subject_or_root(raw_json);
    if let Some(arr) = target.get("durations").and_then(|v| v.as_array()) {
        if let Some(first) = arr.get(0).and_then(|v| v.as_str()) {
            return Some(first.to_string());
        }
    }
    if let Some(d) = target.get("duration").and_then(|v| v.as_str()) {
        return Some(d.to_string());
    }
    if let Some(intro) = raw_json.get("intro").and_then(|v| v.as_str()) {
        for part in intro.split('/') {
            let part_trimmed = part.trim();
            if part_trimmed.contains("分钟") || part_trimmed.contains("mins") {
                return Some(part_trimmed.to_string());
            }
        }
    }
    None
}

pub fn extract_public_rating(raw_json: &serde_json::Value) -> Option<f64> {
    json_number(
        raw_json,
        &[
            "Douban Rating",
            "IMDb Rating",
            "IMDB Rating",
            "vote_average",
            "tmdb_rating",
        ],
    )
}

pub fn extract_public_votes(raw_json: &serde_json::Value) -> Option<i64> {
    json_number(raw_json, &["Num Votes", "IMDb Votes", "vote_count"])
        .map(|value| value.round() as i64)
}

pub fn extract_year(raw_json: &serde_json::Value) -> Option<i32> {
    json_string(raw_json, &["Year", "year", "release_date", "上映年份"]).and_then(|value| {
        value
            .chars()
            .take(4)
            .collect::<String>()
            .parse::<i32>()
            .ok()
    })
}

pub fn extract_date_like(raw_json: &serde_json::Value) -> Option<DateTime<Utc>> {
    json_string(
        raw_json,
        &[
            "create_time",
            "createTime",
            "created_at",
            "added_at",
            "date_added",
            "Date Added",
            "Date Rated",
            "date",
            "listed_at",
            "listedAt",
        ],
    )
    .and_then(|value| parse_date_string(&value))
}

pub fn parse_date_string(value: &str) -> Option<DateTime<Utc>> {
    DateTime::parse_from_rfc3339(value)
        .ok()
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|| {
            chrono::NaiveDateTime::parse_from_str(value.trim(), "%Y-%m-%d %H:%M:%S")
                .ok()
                .map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
        })
        .or_else(|| {
            chrono::NaiveDate::parse_from_str(value.trim(), "%Y-%m-%d")
                .ok()
                .and_then(|date| date.and_hms_opt(0, 0, 0))
                .map(|naive| DateTime::<Utc>::from_naive_utc_and_offset(naive, Utc))
        })
}

pub fn json_string(raw_json: &serde_json::Value, keys: &[&str]) -> Option<String> {
    keys.iter().find_map(|key| match raw_json.get(*key) {
        Some(serde_json::Value::String(value)) if !value.trim().is_empty() => {
            Some(value.trim().to_string())
        }
        Some(serde_json::Value::Number(value)) => Some(value.to_string()),
        _ => None,
    })
}

pub fn json_number(raw_json: &serde_json::Value, keys: &[&str]) -> Option<f64> {
    keys.iter().find_map(|key| match raw_json.get(*key) {
        Some(serde_json::Value::Number(value)) => value.as_f64(),
        Some(serde_json::Value::String(value)) => value.trim().replace(',', "").parse::<f64>().ok(),
        _ => None,
    })
}

pub fn compute_platform_diff(
    source_records: Vec<MovieRecord>,
    target_records: Vec<MovieRecord>,
    source_platform: &str,
    target_platform: &str,
) -> PlatformDiffResult {
    let mut target_lookup = HashMap::new();
    for target in &target_records {
        for k in unified_lookup_keys(&target.identifiers, &target.title, target.year) {
            target_lookup.entry(k).or_insert_with(|| target.clone());
        }
        if let Some(ref ext) = target.external_id {
            target_lookup.entry(format!("{target_platform}:{ext}")).or_insert_with(|| target.clone());
        }
    }

    let total_source = source_records.len();
    let total_target = target_records.len();
    let mut missing_count = 0usize;
    let mut mismatch_count = 0usize;
    let mut synced_count = 0usize;
    let mut items = Vec::new();

    for source in source_records {
        let keys = unified_lookup_keys(&source.identifiers, &source.title, source.year);
        let target_item = keys.iter().find_map(|k| target_lookup.get(k));

        let mut target_linking_id = match target_platform {
            "imdb" => source.identifiers.imdb.clone().or_else(|| {
                source.identifiers.douban.as_deref().and_then(lookup_cached_imdb_for_douban)
            }),
            "douban" => source.identifiers.douban.clone().or_else(|| {
                source.identifiers.imdb.as_deref().and_then(lookup_cached_douban_for_imdb)
            }),
            "tmdb" => source.identifiers.tmdb.clone(),
            "trakt" => source.identifiers.trakt.clone(),
            _ => None,
        };
        if target_linking_id.is_none() {
            if let Some(t) = target_item {
                target_linking_id = t.external_id.clone();
            }
        }

        let poster_url = extract_poster_url(&source.raw_json)
            .or_else(|| target_item.and_then(|t| extract_poster_url(&t.raw_json)));

        let (category, target_rating, target_rated_at, target_url) = match target_item {
            None => {
                missing_count += 1;
                ("missing".to_string(), None, None, None)
            }
            Some(t) => {
                let s_rating = source.rating;
                let t_rating = t.rating;
                let ratings_equal = match (s_rating, t_rating) {
                    (Some(s), Some(tr)) => (s - tr).abs() < 0.01,
                    (None, None) => true,
                    _ => false,
                };
                if ratings_equal {
                    synced_count += 1;
                    ("synced".to_string(), t.rating, t.rated_at, t.source_url.clone())
                } else {
                    mismatch_count += 1;
                    ("mismatch".to_string(), t.rating, t.rated_at, t.source_url.clone())
                }
            }
        };

        let syncable = target_linking_id.is_some() || target_platform != "imdb";

        items.push(PlatformDiffItem {
            title: source.title,
            year: source.year,
            category,
            source_platform: source_platform.to_string(),
            source_rating: source.rating,
            source_rated_at: source.rated_at,
            source_url: source.source_url,
            target_platform: target_platform.to_string(),
            target_rating,
            target_rated_at,
            target_url,
            identifiers: source.identifiers,
            target_linking_id,
            poster_url,
            syncable,
        });
    }

    items.sort_by(|a, b| {
        let cat_order = |cat: &str| match cat {
            "missing" => 0,
            "mismatch" => 1,
            "synced" => 2,
            _ => 3,
        };
        cat_order(&a.category)
            .cmp(&cat_order(&b.category))
            .then_with(|| b.source_rated_at.cmp(&a.source_rated_at))
            .then_with(|| a.title.to_lowercase().cmp(&b.title.to_lowercase()))
    });

    PlatformDiffResult {
        source_platform: source_platform.to_string(),
        target_platform: target_platform.to_string(),
        total_source,
        total_target,
        missing_count,
        mismatch_count,
        synced_count,
        items,
    }
}

pub fn compute_wishlist_platform_diff(
    source_records: Vec<WishlistRecord>,
    target_records: Vec<WishlistRecord>,
    source_platform: &str,
    target_platform: &str,
) -> PlatformDiffResult {
    let mut target_lookup = HashMap::new();
    for target in &target_records {
        for k in unified_lookup_keys(&target.identifiers, &target.title, target.year) {
            target_lookup.entry(k).or_insert_with(|| target.clone());
        }
        if let Some(ref ext) = target.external_id {
            target_lookup.entry(format!("{target_platform}:{ext}")).or_insert_with(|| target.clone());
        }
    }

    let total_source = source_records.len();
    let total_target = target_records.len();
    let mut missing_count = 0usize;
    let mut synced_count = 0usize;
    let mut items = Vec::new();

    for source in source_records {
        let keys = unified_lookup_keys(&source.identifiers, &source.title, source.year);
        let target_item = keys.iter().find_map(|k| target_lookup.get(k));

        let mut target_linking_id = match target_platform {
            "imdb" => source.identifiers.imdb.clone().or_else(|| {
                source.identifiers.douban.as_deref().and_then(lookup_cached_imdb_for_douban)
            }),
            "douban" => source.identifiers.douban.clone().or_else(|| {
                source.identifiers.imdb.as_deref().and_then(lookup_cached_douban_for_imdb)
            }),
            "tmdb" => source.identifiers.tmdb.clone(),
            "trakt" => source.identifiers.trakt.clone(),
            _ => None,
        };
        if target_linking_id.is_none() {
            if let Some(t) = target_item {
                target_linking_id = t.external_id.clone();
            }
        }

        let poster_url = extract_poster_url(&source.raw_json)
            .or_else(|| target_item.and_then(|t| extract_poster_url(&t.raw_json)));

        let (category, target_url) = match target_item {
            None => {
                missing_count += 1;
                ("missing".to_string(), None)
            }
            Some(t) => {
                synced_count += 1;
                ("synced".to_string(), t.source_url.clone())
            }
        };

        let syncable = target_linking_id.is_some() || target_platform != "imdb";

        items.push(PlatformDiffItem {
            title: source.title,
            year: source.year,
            category,
            source_platform: source_platform.to_string(),
            source_rating: None,
            source_rated_at: source.created_at,
            source_url: source.source_url,
            target_platform: target_platform.to_string(),
            target_rating: None,
            target_rated_at: target_item.and_then(|t| t.created_at),
            target_url,
            identifiers: source.identifiers,
            target_linking_id,
            poster_url,
            syncable,
        });
    }

    items.sort_by(|a, b| {
        let cat_order = |cat: &str| match cat {
            "missing" => 0,
            "synced" => 1,
            _ => 2,
        };
        cat_order(&a.category)
            .cmp(&cat_order(&b.category))
            .then_with(|| b.source_rated_at.cmp(&a.source_rated_at))
            .then_with(|| a.title.to_lowercase().cmp(&b.title.to_lowercase()))
    });

    PlatformDiffResult {
        source_platform: source_platform.to_string(),
        target_platform: target_platform.to_string(),
        total_source,
        total_target,
        missing_count,
        mismatch_count: 0,
        synced_count,
        items,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn title_normalization_handles_chinese_and_english() {
        assert_eq!(
            normalize_title("肖申克的救赎 / The Shawshank Redemption"),
            "肖申克的救赎 the shawshank redemption"
        );
        assert_eq!(normalize_title("Inception (2010)"), "inception 2010");
        assert_eq!(normalize_title("  千与千寻  "), "千与千寻");
    }

    #[test]
    fn search_filtering_matches_title_and_director() {
        let items = vec![
            UnifiedMediaItem {
                id: "1".to_string(),
                title: "星际穿越".to_string(),
                original_title: Some("Interstellar".to_string()),
                directors: Some("克里斯托弗·诺兰".to_string()),
                ..UnifiedMediaItem::default()
            },
            UnifiedMediaItem {
                id: "2".to_string(),
                title: "盗梦空间".to_string(),
                original_title: Some("Inception".to_string()),
                directors: Some("克里斯托弗·诺兰".to_string()),
                ..UnifiedMediaItem::default()
            },
            UnifiedMediaItem {
                id: "3".to_string(),
                title: "教父".to_string(),
                original_title: Some("The Godfather".to_string()),
                directors: Some("弗朗西斯·福特·科波拉".to_string()),
                ..UnifiedMediaItem::default()
            },
        ];

        let results = filter_by_search(items.clone(), Some("诺兰"));
        assert_eq!(results.len(), 2);

        let results_en = filter_by_search(items.clone(), Some("godfather"));
        assert_eq!(results_en.len(), 1);
        assert_eq!(results_en[0].title, "教父");
    }

    #[test]
    fn aggregate_library_records_merges_platforms() {
        let records = vec![
            MovieRecord {
                id: "douban:1292052".to_string(),
                platform: "douban".to_string(),
                title: "肖申克的救赎".to_string(),
                year: Some(1994),
                rating: Some(9.7),
                rated_at: None,
                external_id: Some("1292052".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    douban: Some("1292052".to_string()),
                    imdb: Some("tt0111161".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
            MovieRecord {
                id: "imdb:tt0111161".to_string(),
                platform: "imdb".to_string(),
                title: "The Shawshank Redemption".to_string(),
                year: Some(1994),
                rating: Some(9.3),
                rated_at: None,
                external_id: Some("tt0111161".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    imdb: Some("tt0111161".to_string()),
                    tmdb: Some("278".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
        ];

        let aggregated = aggregate_library_records(records);
        assert_eq!(aggregated.len(), 1);
        assert_eq!(aggregated[0].source_platforms.len(), 2);
        assert!(aggregated[0].source_platforms.contains(&"douban".to_string()));
        assert!(aggregated[0].source_platforms.contains(&"imdb".to_string()));
        assert_eq!(aggregated[0].identifiers.imdb.as_deref(), Some("tt0111161"));
        assert_eq!(aggregated[0].identifiers.douban.as_deref(), Some("1292052"));
        assert_eq!(aggregated[0].identifiers.tmdb.as_deref(), Some("278"));
    }

    #[test]
    fn compute_platform_diff_categorizes_correctly() {
        let douban_records = vec![
            MovieRecord {
                id: "douban:1".to_string(),
                platform: "douban".to_string(),
                title: "星际穿越".to_string(),
                year: Some(2014),
                rating: Some(9.0),
                rated_at: None,
                external_id: Some("1".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    douban: Some("1".to_string()),
                    imdb: Some("tt0816692".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
            MovieRecord {
                id: "douban:2".to_string(),
                platform: "douban".to_string(),
                title: "盗梦空间".to_string(),
                year: Some(2010),
                rating: Some(9.0),
                rated_at: None,
                external_id: Some("2".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    douban: Some("2".to_string()),
                    imdb: Some("tt1375666".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
            MovieRecord {
                id: "douban:3".to_string(),
                platform: "douban".to_string(),
                title: "仅豆瓣有的电影".to_string(),
                year: Some(2020),
                rating: Some(8.0),
                rated_at: None,
                external_id: Some("3".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    douban: Some("3".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
        ];

        let imdb_records = vec![
            MovieRecord {
                id: "imdb:tt0816692".to_string(),
                platform: "imdb".to_string(),
                title: "Interstellar".to_string(),
                year: Some(2014),
                rating: Some(9.0), // Same rating -> synced
                rated_at: None,
                external_id: Some("tt0816692".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    imdb: Some("tt0816692".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
            MovieRecord {
                id: "imdb:tt1375666".to_string(),
                platform: "imdb".to_string(),
                title: "Inception".to_string(),
                year: Some(2010),
                rating: Some(8.0), // Different rating -> mismatch
                rated_at: None,
                external_id: Some("tt1375666".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers {
                    imdb: Some("tt1375666".to_string()),
                    ..MovieIdentifiers::default()
                },
                raw_json: json!({}),
            },
        ];

        let diff = compute_platform_diff(douban_records, imdb_records, "douban", "imdb");
        assert_eq!(diff.total_source, 3);
        assert_eq!(diff.total_target, 2);
        assert_eq!(diff.missing_count, 1);
        assert_eq!(diff.mismatch_count, 1);
        assert_eq!(diff.synced_count, 1);

        let missing = diff.items.iter().find(|i| i.category == "missing").unwrap();
        assert_eq!(missing.title, "仅豆瓣有的电影");

        let mismatch = diff.items.iter().find(|i| i.category == "mismatch").unwrap();
        assert_eq!(mismatch.title, "盗梦空间");
        assert_eq!(mismatch.source_rating, Some(9.0));
        assert_eq!(mismatch.target_rating, Some(8.0));

        let synced = diff.items.iter().find(|i| i.category == "synced").unwrap();
        assert_eq!(synced.title, "星际穿越");
    }
}
