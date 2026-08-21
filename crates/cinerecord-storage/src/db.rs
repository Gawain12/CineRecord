use std::{
    collections::HashMap,
    sync::RwLock,
    time::Duration,
};

use anyhow::Result;
use chrono::{DateTime, Utc};
use cinerecord_core::{
    AppConfig, MediaServerItem, MovieRecord, PlatformDescriptor, PlatformDiffResult, PlatformStatus,
    ScheduledTask, ScheduledTaskLog, SyncTask, TaskKind, TaskStatus, UnifiedMediaItem,
    WishlistRecord,
};
use sqlx::{
    ConnectOptions, Row, SqlitePool,
    sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous},
};

use crate::{
    StoragePaths,
    aggregation::{
        LIBRARY_PLATFORMS, aggregate_library_records, aggregate_wishlist_records, apply_paging,
        compute_platform_diff, compute_wishlist_platform_diff, filter_by_search,
        filter_library_view_items, infer_identifiers,
        parse_date_string, sort_unified_items,
    },
    cache::init_id_mapping_cache,
};

// Global cache for aggregated library and wishlist to avoid re-aggregating on every pagination request
static AGGREGATION_CACHE: std::sync::OnceLock<RwLock<AggregationState>> =
    std::sync::OnceLock::new();

#[derive(Default)]
struct AggregationState {
    library_epoch: u64,
    wishlist_epoch: u64,
    cached_library: Option<Vec<UnifiedMediaItem>>,
    cached_wishlist: Option<Vec<UnifiedMediaItem>>,
}

fn aggregation_state() -> &'static RwLock<AggregationState> {
    AGGREGATION_CACHE.get_or_init(|| RwLock::new(AggregationState::default()))
}

fn invalidate_library_cache() {
    if let Ok(mut state) = aggregation_state().write() {
        state.library_epoch = state.library_epoch.wrapping_add(1);
        state.cached_library = None;
    }
}

fn invalidate_wishlist_cache() {
    if let Ok(mut state) = aggregation_state().write() {
        state.wishlist_epoch = state.wishlist_epoch.wrapping_add(1);
        state.cached_wishlist = None;
    }
}

pub async fn connect(paths: &StoragePaths) -> Result<SqlitePool> {
    paths.ensure_dirs().await?;
    init_id_mapping_cache(&paths.data_dir);

    let options = SqliteConnectOptions::new()
        .filename(&paths.db_path)
        .create_if_missing(true)
        .journal_mode(SqliteJournalMode::Wal)
        .synchronous(SqliteSynchronous::Normal)
        .busy_timeout(Duration::from_secs(10));

    let pool = SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(options.disable_statement_logging())
        .await?;

    init_schema(&pool).await?;
    recover_incomplete_tasks(&pool).await?;
    Ok(pool)
}

async fn init_schema(pool: &SqlitePool) -> Result<()> {
    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS library_items (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            rating REAL,
            rated_at TEXT,
            external_id TEXT,
            source_url TEXT,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS platform_state (
            platform TEXT PRIMARY KEY,
            configured INTEGER NOT NULL DEFAULT 0,
            last_validated_at TEXT,
            message TEXT,
            profile_json TEXT
        );
        "#,
    )
    .execute(pool)
    .await?;

    ensure_platform_state_profile_column(pool).await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS wishlist_items (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            external_id TEXT,
            source_url TEXT,
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_platform TEXT NOT NULL,
            target_platform TEXT NOT NULL,
            schedule TEXT NOT NULL,
            recent_limit INTEGER NOT NULL DEFAULT 100,
            only_new INTEGER NOT NULL DEFAULT 1,
            overwrite INTEGER NOT NULL DEFAULT 0,
            default_rating REAL,
            paused INTEGER NOT NULL DEFAULT 0,
            running INTEGER NOT NULL DEFAULT 0,
            last_run_at TEXT,
            next_run_at TEXT,
            last_status_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    sqlx::query(
        r#"
        CREATE TABLE IF NOT EXISTS scheduled_task_logs (
            id TEXT PRIMARY KEY,
            task_id TEXT,
            task_name TEXT NOT NULL,
            source_platform TEXT,
            target_platform TEXT,
            log_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        "#,
    )
    .execute(pool)
    .await?;

    // Create high-performance secondary indexes
    let indexes = [
        "CREATE INDEX IF NOT EXISTS idx_library_items_platform ON library_items(platform);",
        "CREATE INDEX IF NOT EXISTS idx_library_items_title ON library_items(title);",
        "CREATE INDEX IF NOT EXISTS idx_wishlist_items_platform ON wishlist_items(platform);",
        "CREATE INDEX IF NOT EXISTS idx_wishlist_items_created_at ON wishlist_items(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
        "CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);",
        "CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due ON scheduled_tasks(paused, running, next_run_at);",
        "CREATE INDEX IF NOT EXISTS idx_scheduled_task_logs_created ON scheduled_task_logs(created_at);",
    ];

    for idx_sql in indexes {
        sqlx::query(idx_sql).execute(pool).await?;
    }

    Ok(())
}

pub async fn recover_incomplete_tasks(pool: &SqlitePool) -> Result<()> {
    sqlx::query(
        "UPDATE tasks SET status = 'failed', payload_json = json_object('error', 'Recovered after previous process stopped'), updated_at = ?1 WHERE status = 'running'",
    )
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    sqlx::query(
        "UPDATE scheduled_tasks SET running = 0, last_status_message = COALESCE(last_status_message, '上次运行被中断，已在启动时恢复'), updated_at = ?1 WHERE running = 1",
    )
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_platforms(
    config: &AppConfig,
    pool: &SqlitePool,
) -> Result<Vec<PlatformDescriptor>> {
    let states = sqlx::query(
        "SELECT platform, configured, last_validated_at, message, profile_json FROM platform_state",
    )
    .fetch_all(pool)
    .await?;

    let latest_rows = sqlx::query(
        "SELECT platform, MAX(rated_at) as max_rated FROM library_items GROUP BY platform",
    )
    .fetch_all(pool)
    .await
    .unwrap_or_default();

    let mut latest_map: HashMap<String, Option<DateTime<Utc>>> = HashMap::new();
    for row in latest_rows {
        let p: String = row.get("platform");
        let max_rated: Option<String> = row.get("max_rated");
        let dt = max_rated
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc));
        latest_map.insert(p, dt);
    }

    let mut state_map = HashMap::new();
    for row in states {
        let platform: String = row.get("platform");
        let configured_num: i64 = row.get("configured");
        let last_validated_at: Option<String> = row.get("last_validated_at");
        let message: Option<String> = row.get("message");
        let profile_json: Option<String> = row.get("profile_json");
        let last_fetch_at = latest_map.get(&platform).copied().flatten();
        let token_expires_at = if platform == "trakt" {
            config.platforms.trakt.token_expires_at
        } else {
            None
        };
        state_map.insert(
            platform,
            PlatformStatus {
                config_present: false,
                configured: configured_num == 1,
                last_validated_at: last_validated_at
                    .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
                    .map(|dt| dt.with_timezone(&Utc)),
                last_fetch_at,
                token_expires_at,
                message,
                profile: profile_json.and_then(|value| serde_json::from_str(&value).ok()),
            },
        );
    }

    let descriptors = vec![
        (
            "tmdb",
            "TMDB",
            "api_key",
            config.platforms.tmdb.api_key.is_some(),
            true,
            true,
        ),
        (
            "trakt",
            "Trakt",
            "oauth",
            config.platforms.trakt.client_id.is_some() && config.platforms.trakt.access_token.is_some(),
            true,
            true,
        ),
        (
            "imdb",
            "IMDb",
            "cookie",
            config.platforms.imdb.cookie.is_some(),
            true,
            true,
        ),
        (
            "douban",
            "Douban",
            "cookie",
            config.platforms.douban.cookie.is_some() || config.platforms.douban.user_id.is_some(),
            true,
            true,
        ),
        ("letterboxd", "Letterboxd", "csv", true, true, false),
        (
            "cinepersona",
            "CinePersona",
            "api_key",
            config.cinepersona.api_key.is_some(),
            true,
            true,
        ),
    ];

    Ok(descriptors
        .into_iter()
        .map(
            |(id, name, auth_type, config_present, supports_fetch, supports_sync)| {
                let persisted = state_map.remove(id);
                let last_fetch_at = latest_map.get(id).copied().flatten();
                let token_expires_at = if id == "trakt" {
                    config.platforms.trakt.token_expires_at
                } else {
                    None
                };

                let is_expired = if id == "trakt" {
                    config
                        .platforms
                        .trakt
                        .token_expires_at
                        .map(|expires_at| expires_at <= Utc::now())
                        .unwrap_or(false)
                } else {
                    false
                };

                let status = match persisted {
                    Some(state) => {
                        let configured = config_present && state.configured && !is_expired;
                        let message = if is_expired {
                            let expire_str = config
                                .platforms
                                .trakt
                                .token_expires_at
                                .map(|t| t.format("%Y-%m-%d %H:%M").to_string())
                                .unwrap_or_default();
                            Some(format!(
                                "Trakt 授权已于 {expire_str} 过期，请在下方点击“设备码登录”重新授权"
                            ))
                        } else if state
                            .message
                            .as_deref()
                            .is_some_and(|message| !message.trim().is_empty())
                        {
                            state.message
                        } else {
                            None
                        };

                        PlatformStatus {
                            config_present,
                            configured,
                            last_validated_at: state.last_validated_at,
                            last_fetch_at,
                            token_expires_at,
                            message,
                            profile: if config_present && !is_expired { state.profile } else { None },
                        }
                    }
                    None => {
                        let configured = (id == "letterboxd" && config_present) && !is_expired;
                        let message = if is_expired {
                            Some("Trakt 授权已过期，请在下方点击“设备码登录”重新授权".to_string())
                        } else {
                            None
                        };
                        PlatformStatus {
                            config_present,
                            configured,
                            last_validated_at: None,
                            last_fetch_at,
                            token_expires_at,
                            message,
                            profile: None,
                        }
                    }
                };
                PlatformDescriptor {
                    id: id.to_string(),
                    name: name.to_string(),
                    auth_type: auth_type.to_string(),
                    supports_fetch,
                    supports_sync,
                    status,
                }
            },
        )
        .collect())
}

pub async fn upsert_platform_state(
    pool: &SqlitePool,
    platform: &str,
    configured: bool,
    message: Option<&str>,
    profile: Option<&serde_json::Value>,
) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO platform_state (platform, configured, last_validated_at, message, profile_json)
        VALUES (?1, ?2, ?3, ?4, ?5)
        ON CONFLICT(platform) DO UPDATE SET
            configured = excluded.configured,
            last_validated_at = excluded.last_validated_at,
            message = excluded.message,
            profile_json = excluded.profile_json
        "#,
    )
    .bind(platform)
    .bind(if configured { 1_i64 } else { 0_i64 })
    .bind(Utc::now().to_rfc3339())
    .bind(message)
    .bind(profile.map(|value| value.to_string()))
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn update_platform_local_counts(
    pool: &SqlitePool,
    platform: &str,
    library_count: Option<usize>,
    wishlist_count: Option<usize>,
) -> Result<()> {
    let profile_json = sqlx::query_scalar::<_, Option<String>>(
        "SELECT profile_json FROM platform_state WHERE platform = ?1",
    )
    .bind(platform)
    .fetch_optional(pool)
    .await?
    .flatten();

    let mut profile = profile_json
        .and_then(|value| serde_json::from_str::<serde_json::Value>(&value).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    let Some(profile) = profile.as_object_mut() else {
        return Ok(());
    };

    if let Some(count) = library_count {
        let keys: &[&str] = match platform {
            "douban" => &["watched", "watched_total"],
            "imdb" => &["ratings", "ratings_total"],
            "trakt" => &["watched"],
            "tmdb" => &["ratings", "rated_total"],
            "letterboxd" => &["watched"],
            _ => &[],
        };
        for key in keys {
            profile.insert((*key).to_string(), serde_json::json!(count));
        }
    }

    if let Some(count) = wishlist_count {
        let keys: &[&str] = if platform == "douban" {
            &["wish", "wish_total"]
        } else {
            &["watchlist", "watchlist_total"]
        };
        for key in keys {
            profile.insert((*key).to_string(), serde_json::json!(count));
        }
    }

    sqlx::query("UPDATE platform_state SET profile_json = ?1 WHERE platform = ?2")
        .bind(serde_json::Value::Object(profile.clone()).to_string())
        .bind(platform)
        .execute(pool)
        .await?;
    Ok(())
}

async fn ensure_platform_state_profile_column(pool: &SqlitePool) -> Result<()> {
    let rows = sqlx::query("PRAGMA table_info(platform_state)")
        .fetch_all(pool)
        .await?;
    let has_profile_json = rows
        .iter()
        .filter_map(|row| row.try_get::<String, _>("name").ok())
        .any(|name| name == "profile_json");
    if !has_profile_json {
        sqlx::query("ALTER TABLE platform_state ADD COLUMN profile_json TEXT")
            .execute(pool)
            .await?;
    }
    Ok(())
}

pub async fn insert_task(pool: &SqlitePool, task: &SyncTask) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO tasks (id, name, kind, status, payload_json, created_at, updated_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
        "#,
    )
    .bind(&task.id)
    .bind(&task.name)
    .bind(task_kind_to_str(&task.kind))
    .bind(task_status_to_str(&task.status))
    .bind(task.payload.to_string())
    .bind(task.created_at.to_rfc3339())
    .bind(task.updated_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_tasks(pool: &SqlitePool) -> Result<Vec<SyncTask>> {
    let rows = sqlx::query("SELECT id, name, kind, status, payload_json, created_at, updated_at FROM tasks ORDER BY updated_at DESC")
        .fetch_all(pool)
        .await?;
    rows.into_iter().map(task_from_row).collect()
}

pub async fn get_task(pool: &SqlitePool, task_id: &str) -> Result<Option<SyncTask>> {
    let row = sqlx::query("SELECT id, name, kind, status, payload_json, created_at, updated_at FROM tasks WHERE id = ?1")
        .bind(task_id)
        .fetch_optional(pool)
        .await?;
    row.map(task_from_row).transpose()
}

pub async fn update_task_status(
    pool: &SqlitePool,
    task_id: &str,
    status: TaskStatus,
    payload: serde_json::Value,
) -> Result<()> {
    sqlx::query("UPDATE tasks SET status = ?2, payload_json = ?3, updated_at = ?4 WHERE id = ?1")
        .bind(task_id)
        .bind(task_status_to_str(&status))
        .bind(payload.to_string())
        .bind(Utc::now().to_rfc3339())
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn delete_task(pool: &SqlitePool, task_id: &str) -> Result<()> {
    sqlx::query("DELETE FROM tasks WHERE id = ?1")
        .bind(task_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn replace_library_items(
    pool: &SqlitePool,
    platform: &str,
    items: &[MovieRecord],
) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query("DELETE FROM library_items WHERE platform = ?1")
        .bind(platform)
        .execute(&mut *tx)
        .await?;

    for item in items {
        sqlx::query(
            r#"
            INSERT INTO library_items (id, platform, title, year, rating, rated_at, external_id, source_url, raw_json)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)
            "#,
        )
        .bind(&item.id)
        .bind(&item.platform)
        .bind(&item.title)
        .bind(item.year)
        .bind(item.rating)
        .bind(item.rated_at.map(|dt| dt.to_rfc3339()))
        .bind(&item.external_id)
        .bind(&item.source_url)
        .bind(item.raw_json.to_string())
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;
    invalidate_library_cache();
    Ok(())
}

pub async fn replace_wishlist_items(
    pool: &SqlitePool,
    platform: &str,
    items: &[WishlistRecord],
) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query("DELETE FROM wishlist_items WHERE platform = ?1")
        .bind(platform)
        .execute(&mut *tx)
        .await?;

    for item in items {
        sqlx::query(
            r#"
            INSERT INTO wishlist_items (id, platform, title, year, external_id, source_url, raw_json, created_at)
            VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, COALESCE(?8, CURRENT_TIMESTAMP))
            "#,
        )
        .bind(&item.id)
        .bind(&item.platform)
        .bind(&item.title)
        .bind(item.year)
        .bind(&item.external_id)
        .bind(&item.source_url)
        .bind(item.raw_json.to_string())
        .bind(item.created_at.map(|dt| dt.to_rfc3339()))
        .execute(&mut *tx)
        .await?;
    }

    tx.commit().await?;
    invalidate_wishlist_cache();
    Ok(())
}

pub async fn list_library_items(
    pool: &SqlitePool,
    platform: Option<&str>,
) -> Result<Vec<MovieRecord>> {
    list_library_items_paginated(pool, platform, None, None).await
}

pub async fn list_library_items_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<MovieRecord>> {
    let limit = limit.unwrap_or(10_000);
    let offset = offset.unwrap_or(0);
    let rows = if let Some(platform) = platform {
        sqlx::query(
            "SELECT id, platform, title, year, rating, rated_at, external_id, source_url, raw_json FROM library_items WHERE platform = ?1 ORDER BY rated_at DESC, created_at DESC, id DESC LIMIT ?2 OFFSET ?3",
        )
        .bind(platform)
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT id, platform, title, year, rating, rated_at, external_id, source_url, raw_json FROM library_items ORDER BY rated_at DESC, created_at DESC, id DESC LIMIT ?1 OFFSET ?2",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    };

    rows.into_iter().map(movie_from_row).collect()
}

pub async fn count_library_items(pool: &SqlitePool, platform: Option<&str>) -> Result<i64> {
    let row = if let Some(platform) = platform {
        sqlx::query("SELECT COUNT(*) AS count FROM library_items WHERE platform = ?1")
            .bind(platform)
            .fetch_one(pool)
            .await?
    } else {
        sqlx::query("SELECT COUNT(*) AS count FROM library_items")
            .fetch_one(pool)
            .await?
    };
    Ok(row.get("count"))
}

pub async fn list_wishlist_items(
    pool: &SqlitePool,
    platform: Option<&str>,
) -> Result<Vec<WishlistRecord>> {
    list_wishlist_items_paginated(pool, platform, None, None).await
}

pub async fn list_wishlist_items_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<WishlistRecord>> {
    let limit = limit.unwrap_or(10_000);
    let offset = offset.unwrap_or(0);
    let rows = if let Some(platform) = platform {
        sqlx::query(
            "SELECT id, platform, title, year, external_id, source_url, raw_json, created_at FROM wishlist_items WHERE platform = ?1 ORDER BY created_at DESC LIMIT ?2 OFFSET ?3",
        )
        .bind(platform)
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT id, platform, title, year, external_id, source_url, raw_json, created_at FROM wishlist_items ORDER BY created_at DESC LIMIT ?1 OFFSET ?2",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(pool)
        .await?
    };

    rows.into_iter().map(wishlist_from_row).collect()
}

pub async fn count_wishlist_items(pool: &SqlitePool, platform: Option<&str>) -> Result<i64> {
    let row = if let Some(platform) = platform {
        sqlx::query("SELECT COUNT(*) AS count FROM wishlist_items WHERE platform = ?1")
            .bind(platform)
            .fetch_one(pool)
            .await?
    } else {
        sqlx::query("SELECT COUNT(*) AS count FROM wishlist_items")
            .fetch_one(pool)
            .await?
    };
    Ok(row.get("count"))
}

async fn get_or_compute_library_aggregated(
    pool: &SqlitePool,
) -> Result<Vec<UnifiedMediaItem>> {
    {
        let state = aggregation_state().read().unwrap();
        if let Some(ref cached) = state.cached_library {
            return Ok(cached.clone());
        }
    }

    let records = list_library_items(pool, None).await?;
    let aggregated = aggregate_library_records(records);

    {
        let mut state = aggregation_state().write().unwrap();
        state.cached_library = Some(aggregated.clone());
    }

    Ok(aggregated)
}

pub async fn list_library_items_aggregated_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let items = if platform.is_none() {
        get_or_compute_library_aggregated(pool).await?
    } else {
        aggregate_library_records(list_library_items(pool, platform).await?)
    };

    let mut filtered = filter_by_search(items, search);
    sort_unified_items(&mut filtered, true);
    Ok(apply_paging(filtered, limit, offset))
}

pub async fn count_library_groups(
    pool: &SqlitePool,
    platform: Option<&str>,
    search: Option<&str>,
) -> Result<i64> {
    let items = if platform.is_none() {
        get_or_compute_library_aggregated(pool).await?
    } else {
        aggregate_library_records(list_library_items(pool, platform).await?)
    };
    let filtered = filter_by_search(items, search);
    Ok(filtered.len() as i64)
}

pub async fn list_library_items_view_paginated(
    pool: &SqlitePool,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let base = get_or_compute_library_aggregated(pool).await?;
    let mut items = filter_library_view_items(base, platform_filter, selected_platforms);
    items = filter_by_search(items, search);
    sort_unified_items(&mut items, true);
    Ok(apply_paging(items, limit, offset))
}

pub async fn count_library_view_groups(
    pool: &SqlitePool,
    platform_filter: Option<&str>,
    selected_platforms: &[String],
    search: Option<&str>,
) -> Result<i64> {
    let base = get_or_compute_library_aggregated(pool).await?;
    let items = filter_library_view_items(base, platform_filter, selected_platforms);
    let items = filter_by_search(items, search);
    Ok(items.len() as i64)
}

pub async fn library_view_counts(
    pool: &SqlitePool,
    _selected_platforms: &[String],
) -> Result<HashMap<String, i64>> {
    let items = get_or_compute_library_aggregated(pool).await?;
    let mut counts = HashMap::new();
    let total_all = items.len();
    let shared_count = items
        .iter()
        .filter(|item| item.source_platforms.len() >= 2)
        .count();
    let single_count = items
        .iter()
        .filter(|item| item.source_platforms.len() == 1)
        .count();

    counts.insert("all".to_string(), total_all as i64);
    counts.insert("shared".to_string(), shared_count as i64);
    counts.insert("single".to_string(), single_count as i64);

    for platform in LIBRARY_PLATFORMS {
        let count = count_library_items(pool, Some(platform)).await?;
        counts.insert(platform.to_string(), count);
    }
    Ok(counts)
}

pub async fn get_library_diff(
    pool: &SqlitePool,
    source_platform: &str,
    target_platform: &str,
    category_filter: Option<&str>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<PlatformDiffResult> {
    let source_records = list_library_items(pool, Some(source_platform)).await?;
    let target_records = list_library_items(pool, Some(target_platform)).await?;

    let mut full_diff = compute_platform_diff(source_records, target_records, source_platform, target_platform);

    if let Some(category) = category_filter.filter(|c| !c.is_empty() && *c != "all") {
        full_diff.items.retain(|item| item.category == category);
    }
    if let Some(q) = search.filter(|s| !s.trim().is_empty()) {
        let q_lower = q.to_lowercase();
        full_diff.items.retain(|item| item.title.to_lowercase().contains(&q_lower));
    }

    full_diff.items = apply_paging(full_diff.items, limit, offset);
    Ok(full_diff)
}

pub async fn get_wishlist_diff(
    pool: &SqlitePool,
    source_platform: &str,
    target_platform: &str,
    category_filter: Option<&str>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<PlatformDiffResult> {
    let source_records = list_wishlist_items(pool, Some(source_platform)).await?;
    let target_records = list_wishlist_items(pool, Some(target_platform)).await?;

    let mut full_diff = compute_wishlist_platform_diff(source_records, target_records, source_platform, target_platform);

    if let Some(category) = category_filter.filter(|c| !c.is_empty() && *c != "all") {
        full_diff.items.retain(|item| item.category == category);
    }
    if let Some(q) = search.filter(|s| !s.trim().is_empty()) {
        let q_lower = q.to_lowercase();
        full_diff.items.retain(|item| item.title.to_lowercase().contains(&q_lower));
    }

    full_diff.items = apply_paging(full_diff.items, limit, offset);
    Ok(full_diff)
}

pub async fn list_wishlist_items_aggregated_paginated(
    pool: &SqlitePool,
    platform: Option<&str>,
    media_server_items: Option<&[MediaServerItem]>,
    search: Option<&str>,
    limit: Option<i64>,
    offset: Option<i64>,
) -> Result<Vec<UnifiedMediaItem>> {
    let library = get_or_compute_library_aggregated(pool).await?;
    let mut items = aggregate_wishlist_records(
        list_wishlist_items(pool, platform).await?,
        &library,
        media_server_items,
    );
    items = filter_by_search(items, search);
    sort_unified_items(&mut items, false);
    Ok(apply_paging(items, limit, offset))
}

pub async fn count_wishlist_groups(
    pool: &SqlitePool,
    platform: Option<&str>,
    media_server_items: Option<&[MediaServerItem]>,
    search: Option<&str>,
) -> Result<i64> {
    let library = get_or_compute_library_aggregated(pool).await?;
    let items = aggregate_wishlist_records(
        list_wishlist_items(pool, platform).await?,
        &library,
        media_server_items,
    );
    let items = filter_by_search(items, search);
    Ok(items.len() as i64)
}

pub async fn wishlist_view_counts(
    pool: &SqlitePool,
    media_server_items: Option<&[MediaServerItem]>,
) -> Result<HashMap<String, i64>> {
    let library = get_or_compute_library_aggregated(pool).await?;
    let raw_wishlist = list_wishlist_items(pool, None).await?;
    let items = aggregate_wishlist_records(raw_wishlist, &library, media_server_items);
    let mut counts = HashMap::new();
    let total_all = items.len();
    let shared_count = items
        .iter()
        .filter(|item| item.source_platforms.len() >= 2)
        .count();
    let single_count = items
        .iter()
        .filter(|item| item.source_platforms.len() == 1)
        .count();

    counts.insert("all".to_string(), total_all as i64);
    counts.insert("shared".to_string(), shared_count as i64);
    counts.insert("single".to_string(), single_count as i64);

    for platform in LIBRARY_PLATFORMS {
        let count = count_wishlist_items(pool, Some(platform)).await?;
        counts.insert(platform.to_string(), count);
    }
    Ok(counts)
}

pub async fn list_scheduled_tasks(pool: &SqlitePool) -> Result<Vec<ScheduledTask>> {
    let rows = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks ORDER BY paused ASC, next_run_at ASC, updated_at DESC",
    )
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(scheduled_task_from_row).collect()
}

pub async fn get_scheduled_task(pool: &SqlitePool, task_id: &str) -> Result<Option<ScheduledTask>> {
    let row = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks WHERE id = ?1",
    )
    .bind(task_id)
    .fetch_optional(pool)
    .await?;
    row.map(scheduled_task_from_row).transpose()
}

pub async fn upsert_scheduled_task(pool: &SqlitePool, task: &ScheduledTask) -> Result<()> {
    sqlx::query(
        r#"
        INSERT INTO scheduled_tasks (
            id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating,
            paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at
        )
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            source_platform = excluded.source_platform,
            target_platform = excluded.target_platform,
            schedule = excluded.schedule,
            recent_limit = excluded.recent_limit,
            only_new = excluded.only_new,
            overwrite = excluded.overwrite,
            default_rating = excluded.default_rating,
            paused = excluded.paused,
            running = excluded.running,
            last_run_at = excluded.last_run_at,
            next_run_at = excluded.next_run_at,
            last_status_message = excluded.last_status_message,
            updated_at = excluded.updated_at
        "#,
    )
    .bind(&task.id)
    .bind(&task.name)
    .bind(&task.source_platform)
    .bind(&task.target_platform)
    .bind(&task.schedule)
    .bind(task.recent_limit as i64)
    .bind(if task.only_new { 1_i64 } else { 0_i64 })
    .bind(if task.overwrite { 1_i64 } else { 0_i64 })
    .bind(task.default_rating)
    .bind(if task.paused { 1_i64 } else { 0_i64 })
    .bind(if task.running { 1_i64 } else { 0_i64 })
    .bind(task.last_run_at.map(|value| value.to_rfc3339()))
    .bind(task.next_run_at.map(|value| value.to_rfc3339()))
    .bind(&task.last_status_message)
    .bind(task.created_at.to_rfc3339())
    .bind(task.updated_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn delete_scheduled_task(pool: &SqlitePool, task_id: &str) -> Result<()> {
    sqlx::query("DELETE FROM scheduled_tasks WHERE id = ?1")
        .bind(task_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn claim_due_scheduled_tasks(
    pool: &SqlitePool,
    now: DateTime<Utc>,
) -> Result<Vec<ScheduledTask>> {
    let due = sqlx::query(
        "SELECT id, name, source_platform, target_platform, schedule, recent_limit, only_new, overwrite, default_rating, paused, running, last_run_at, next_run_at, last_status_message, created_at, updated_at FROM scheduled_tasks WHERE paused = 0 AND running = 0 AND next_run_at IS NOT NULL AND next_run_at <= ?1 ORDER BY next_run_at ASC",
    )
    .bind(now.to_rfc3339())
    .fetch_all(pool)
    .await?;

    let mut tasks = Vec::new();
    for row in due {
        let task = scheduled_task_from_row(row)?;
        let affected = sqlx::query(
            "UPDATE scheduled_tasks SET running = 1, updated_at = ?2 WHERE id = ?1 AND running = 0",
        )
        .bind(&task.id)
        .bind(Utc::now().to_rfc3339())
        .execute(pool)
        .await?
        .rows_affected();
        if affected == 1 {
            tasks.push(ScheduledTask {
                running: true,
                ..task
            });
        }
    }
    Ok(tasks)
}

pub async fn start_scheduled_task_run(pool: &SqlitePool, task_id: &str) -> Result<bool> {
    let affected = sqlx::query(
        "UPDATE scheduled_tasks SET running = 1, updated_at = ?2 WHERE id = ?1 AND running = 0 AND paused = 0",
    )
    .bind(task_id)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?
    .rows_affected();
    Ok(affected == 1)
}

pub async fn complete_scheduled_task_run(
    pool: &SqlitePool,
    task_id: &str,
    next_run_at: Option<DateTime<Utc>>,
    last_status_message: Option<&str>,
) -> Result<()> {
    sqlx::query(
        "UPDATE scheduled_tasks SET running = 0, last_run_at = ?2, next_run_at = ?3, last_status_message = ?4, updated_at = ?5 WHERE id = ?1",
    )
    .bind(task_id)
    .bind(Utc::now().to_rfc3339())
    .bind(next_run_at.map(|value| value.to_rfc3339()))
    .bind(last_status_message)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn mark_scheduled_task_idle(
    pool: &SqlitePool,
    task_id: &str,
    paused: bool,
    next_run_at: Option<DateTime<Utc>>,
    message: Option<&str>,
) -> Result<()> {
    sqlx::query(
        "UPDATE scheduled_tasks SET paused = ?2, running = 0, next_run_at = ?3, last_status_message = ?4, updated_at = ?5 WHERE id = ?1",
    )
    .bind(task_id)
    .bind(if paused { 1_i64 } else { 0_i64 })
    .bind(next_run_at.map(|value| value.to_rfc3339()))
    .bind(message)
    .bind(Utc::now().to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn add_scheduled_task_log(pool: &SqlitePool, log: &ScheduledTaskLog) -> Result<()> {
    sqlx::query(
        "INSERT INTO scheduled_task_logs (id, task_id, task_name, source_platform, target_platform, log_type, message, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
    )
    .bind(&log.id)
    .bind(&log.task_id)
    .bind(&log.task_name)
    .bind(&log.source_platform)
    .bind(&log.target_platform)
    .bind(&log.log_type)
    .bind(&log.message)
    .bind(log.created_at.to_rfc3339())
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_scheduled_task_logs(
    pool: &SqlitePool,
    limit: i64,
) -> Result<Vec<ScheduledTaskLog>> {
    let rows = sqlx::query(
        "SELECT id, task_id, task_name, source_platform, target_platform, log_type, message, created_at FROM scheduled_task_logs ORDER BY created_at DESC LIMIT ?1",
    )
    .bind(limit)
    .fetch_all(pool)
    .await?;
    rows.into_iter().map(scheduled_task_log_from_row).collect()
}

pub async fn platform_item_counts(pool: &SqlitePool, table: &str) -> Result<HashMap<String, i64>> {
    let query = match table {
        "library_items" => {
            "SELECT platform, COUNT(*) AS count FROM library_items GROUP BY platform"
        }
        "wishlist_items" => {
            "SELECT platform, COUNT(*) AS count FROM wishlist_items GROUP BY platform"
        }
        other => anyhow::bail!("unsupported table for counts: {other}"),
    };
    let rows = sqlx::query(query).fetch_all(pool).await?;
    let mut counts = HashMap::new();
    for row in rows {
        counts.insert(row.get::<String, _>("platform"), row.get::<i64, _>("count"));
    }
    Ok(counts)
}

fn task_from_row(row: sqlx::sqlite::SqliteRow) -> Result<SyncTask> {
    Ok(SyncTask {
        id: row.get("id"),
        name: row.get("name"),
        kind: task_kind_from_str(row.get::<String, _>("kind").as_str()),
        status: task_status_from_str(row.get::<String, _>("status").as_str()),
        payload: serde_json::from_str(row.get::<String, _>("payload_json").as_str())?,
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
        updated_at: DateTime::parse_from_rfc3339(row.get::<String, _>("updated_at").as_str())?
            .with_timezone(&Utc),
    })
}

fn movie_from_row(row: sqlx::sqlite::SqliteRow) -> Result<MovieRecord> {
    let platform: String = row.get("platform");
    let external_id: Option<String> = row.get("external_id");
    let raw_json: serde_json::Value =
        serde_json::from_str(row.get::<String, _>("raw_json").as_str())?;
    Ok(MovieRecord {
        id: row.get("id"),
        platform: platform.clone(),
        title: row.get("title"),
        year: row.get("year"),
        rating: row.get("rating"),
        rated_at: row
            .get::<Option<String>, _>("rated_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        external_id: external_id.clone(),
        source_url: row.get("source_url"),
        identifiers: infer_identifiers(&platform, external_id.as_deref(), &raw_json),
        raw_json,
    })
}

fn wishlist_from_row(row: sqlx::sqlite::SqliteRow) -> Result<WishlistRecord> {
    let platform: String = row.get("platform");
    let external_id: Option<String> = row.get("external_id");
    let raw_json: serde_json::Value =
        serde_json::from_str(row.get::<String, _>("raw_json").as_str())?;
    let created_at_str: Option<String> = row.try_get("created_at").ok();
    let created_at = created_at_str.and_then(|s| parse_date_string(&s));
    Ok(WishlistRecord {
        id: row.get("id"),
        platform: platform.clone(),
        title: row.get("title"),
        year: row.get("year"),
        external_id: external_id.clone(),
        source_url: row.get("source_url"),
        identifiers: infer_identifiers(&platform, external_id.as_deref(), &raw_json),
        raw_json,
        created_at,
    })
}

fn scheduled_task_from_row(row: sqlx::sqlite::SqliteRow) -> Result<ScheduledTask> {
    Ok(ScheduledTask {
        id: row.get("id"),
        name: row.get("name"),
        source_platform: row.get("source_platform"),
        target_platform: row.get("target_platform"),
        schedule: row.get("schedule"),
        recent_limit: row.get::<i64, _>("recent_limit") as usize,
        only_new: row.get::<i64, _>("only_new") == 1,
        overwrite: row.get::<i64, _>("overwrite") == 1,
        default_rating: row.get("default_rating"),
        paused: row.get::<i64, _>("paused") == 1,
        running: row.get::<i64, _>("running") == 1,
        last_run_at: row
            .get::<Option<String>, _>("last_run_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        next_run_at: row
            .get::<Option<String>, _>("next_run_at")
            .and_then(|s| DateTime::parse_from_rfc3339(&s).ok())
            .map(|dt| dt.with_timezone(&Utc)),
        last_status_message: row.get("last_status_message"),
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
        updated_at: DateTime::parse_from_rfc3339(row.get::<String, _>("updated_at").as_str())?
            .with_timezone(&Utc),
    })
}

fn scheduled_task_log_from_row(row: sqlx::sqlite::SqliteRow) -> Result<ScheduledTaskLog> {
    Ok(ScheduledTaskLog {
        id: row.get("id"),
        task_id: row.get("task_id"),
        task_name: row.get("task_name"),
        source_platform: row.get("source_platform"),
        target_platform: row.get("target_platform"),
        log_type: row.get("log_type"),
        message: row.get("message"),
        created_at: DateTime::parse_from_rfc3339(row.get::<String, _>("created_at").as_str())?
            .with_timezone(&Utc),
    })
}

fn task_kind_to_str(kind: &TaskKind) -> &'static str {
    match kind {
        TaskKind::FetchPlatform => "fetch_platform",
        TaskKind::FetchWishlist => "fetch_wishlist",
        TaskKind::ImportLegacy => "import_legacy",
        TaskKind::SyncPreview => "sync_preview",
        TaskKind::SyncExecute => "sync_execute",
        TaskKind::Maintenance => "maintenance",
    }
}

fn task_kind_from_str(value: &str) -> TaskKind {
    match value {
        "fetch_platform" => TaskKind::FetchPlatform,
        "fetch_wishlist" => TaskKind::FetchWishlist,
        "import_legacy" => TaskKind::ImportLegacy,
        "sync_preview" => TaskKind::SyncPreview,
        "sync_execute" => TaskKind::SyncExecute,
        _ => TaskKind::Maintenance,
    }
}

fn task_status_to_str(status: &TaskStatus) -> &'static str {
    match status {
        TaskStatus::Pending => "pending",
        TaskStatus::Running => "running",
        TaskStatus::Succeeded => "succeeded",
        TaskStatus::Failed => "failed",
        TaskStatus::Cancelled => "cancelled",
    }
}

fn task_status_from_str(value: &str) -> TaskStatus {
    match value {
        "running" => TaskStatus::Running,
        "succeeded" => TaskStatus::Succeeded,
        "failed" => TaskStatus::Failed,
        "cancelled" => TaskStatus::Cancelled,
        _ => TaskStatus::Pending,
    }
}
