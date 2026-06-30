use anyhow::Result;
use chrono::Utc;
use cinerecord_core::{
    AppConfig, AppEvent, FetchResult, MovieRecord, ScheduledTask, ScheduledTaskLog,
    SyncExecuteRequest, SyncExecuteResult, SyncPreviewRequest, SyncPreviewResult, SyncTask,
    TaskStatus,
};
use cinerecord_platforms::{
    build_sync_preview, execute_sync_with_progress, fetch_platform, fetch_platform_wishlist,
    test_platform,
};
use cinerecord_storage::{
    StoragePaths, add_scheduled_task_log, complete_scheduled_task_run, get_scheduled_task,
    import_legacy_csv, list_library_items, replace_library_items, replace_wishlist_items,
    update_platform_local_counts, update_task_status, upsert_platform_state,
};
use serde_json::json;
use sqlx::SqlitePool;
use tokio::sync::broadcast::Sender;
use tracing::info;
use uuid::Uuid;

pub async fn run_platform_test(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    platform: &str,
    task: Option<&SyncTask>,
) -> Result<cinerecord_core::PlatformValidationResult> {
    let result = test_platform(platform, config).await?;
    upsert_platform_state(
        pool,
        platform,
        result.success,
        Some(&result.message),
        if result.success {
            result.profile.as_ref()
        } else {
            None
        },
    )
    .await?;
    emit_event(
        events,
        "platform.validated",
        task.map(|task| task.id.clone()),
        json!(result),
    );
    Ok(result)
}

pub async fn run_fetch_platform(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    platform: &str,
    task: &SyncTask,
) -> Result<FetchResult> {
    update_task_status(pool, &task.id, TaskStatus::Running, task.payload.clone()).await?;
    emit_log(
        events,
        Some(task.id.clone()),
        format!("Fetching {platform} data"),
    );

    let (result, records) = match fetch_platform(platform, config).await {
        Ok(value) => value,
        Err(error) => {
            update_task_status(
                pool,
                &task.id,
                TaskStatus::Failed,
                json!({
                    "platform": platform,
                    "error": error.to_string()
                }),
            )
            .await?;
            emit_log(
                events,
                Some(task.id.clone()),
                format!("Fetch {platform} failed: {error}"),
            );
            return Err(error);
        }
    };
    let existing_records = list_library_items(pool, Some(platform))
        .await
        .unwrap_or_default();
    let records = merge_existing_library_metadata(records, &existing_records);
    replace_library_items(pool, platform, &records).await?;
    update_platform_local_counts(pool, platform, Some(records.len()), None).await?;
    update_task_status(
        pool,
        &task.id,
        TaskStatus::Succeeded,
        json!({
            "platform": platform,
            "stored_count": result.stored_count,
            "item_count": result.item_count
        }),
    )
    .await?;

    emit_event(
        events,
        "fetch.completed",
        Some(task.id.clone()),
        json!({
            "platform": platform,
            "item_count": result.item_count,
            "stored_count": result.stored_count
        }),
    );
    Ok(result)
}

fn merge_existing_library_metadata(
    mut fetched: Vec<MovieRecord>,
    existing: &[MovieRecord],
) -> Vec<MovieRecord> {
    let mut by_external_id = std::collections::HashMap::new();
    for item in existing {
        if let Some(external_id) = item.external_id.as_deref() {
            by_external_id.insert(external_id.to_string(), item);
        }
    }
    for item in &mut fetched {
        let Some(existing_item) = item
            .external_id
            .as_deref()
            .and_then(|external_id| by_external_id.get(external_id))
        else {
            continue;
        };
        if item.year.is_none() {
            item.year = existing_item.year;
        }
        if item.source_url.is_none() {
            item.source_url = existing_item.source_url.clone();
        }
        merge_raw_json_fields(&mut item.raw_json, &existing_item.raw_json);
    }
    fetched
}

fn merge_raw_json_fields(target: &mut serde_json::Value, existing: &serde_json::Value) {
    let Some(target_map) = target.as_object_mut() else {
        return;
    };
    let Some(existing_map) = existing.as_object() else {
        return;
    };
    for key in [
        "Cover URL",
        "Cover",
        "poster",
        "poster_url",
        "Year",
        "Genres",
        "Directors",
        "IMDb Rating",
        "Num Votes",
        "Runtime",
        "TMDB ID",
        "douban_id",
        "Type",
    ] {
        if !target_map.contains_key(key) {
            if let Some(value) = existing_map.get(key) {
                target_map.insert(key.to_string(), value.clone());
            }
        }
    }
}

pub async fn run_fetch_wishlist(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    platform: &str,
    task: &SyncTask,
) -> Result<serde_json::Value> {
    update_task_status(pool, &task.id, TaskStatus::Running, task.payload.clone()).await?;
    let (result, records) = match fetch_platform_wishlist(platform, config).await {
        Ok(value) => value,
        Err(error) => {
            update_task_status(
                pool,
                &task.id,
                TaskStatus::Failed,
                json!({
                    "platform": platform,
                    "wishlist": true,
                    "error": error.to_string()
                }),
            )
            .await?;
            emit_log(
                events,
                Some(task.id.clone()),
                format!("Fetch {platform} wishlist failed: {error}"),
            );
            return Err(error);
        }
    };
    replace_wishlist_items(pool, platform, &records).await?;
    update_platform_local_counts(pool, platform, None, Some(records.len())).await?;
    update_task_status(pool, &task.id, TaskStatus::Succeeded, result.clone()).await?;
    emit_event(
        events,
        "fetch.completed",
        Some(task.id.clone()),
        result.clone(),
    );
    Ok(result)
}

pub async fn mark_stubbed_task(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    task: &SyncTask,
    event_type: &str,
    payload: serde_json::Value,
) -> Result<()> {
    update_task_status(pool, &task.id, TaskStatus::Succeeded, payload.clone()).await?;
    emit_event(events, event_type, Some(task.id.clone()), payload);
    Ok(())
}

pub async fn run_sync_preview(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    request: &SyncPreviewRequest,
    task: Option<&SyncTask>,
) -> Result<SyncPreviewResult> {
    if let Some(task) = task {
        update_task_status(
            pool,
            &task.id,
            TaskStatus::Running,
            json!({
                "direction": format!("{}-to-{}", request.source_platform, request.target_platform),
                "phase": if request.refresh_before_sync { "refreshing" } else { "previewing" },
                "message": if request.refresh_before_sync { "正在刷新同步双方的本地库" } else { "正在使用本地库生成同步预览" }
            }),
        )
        .await?;
    }
    let task_id = task.map(|task| task.id.clone());
    let result = if request.refresh_before_sync {
        build_refreshed_sync_preview(pool, events, config, request, task_id.as_deref()).await?
    } else {
        build_local_sync_preview(pool, events, request, task_id.as_deref()).await?
    };
    if let Some(task) = task {
        update_task_status(pool, &task.id, TaskStatus::Succeeded, json!(result.clone())).await?;
    }
    emit_event(
        events,
        "sync.preview.ready",
        task.map(|task| task.id.clone()),
        json!(result),
    );
    Ok(result)
}

async fn build_refreshed_sync_preview(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    request: &SyncPreviewRequest,
    task_id: Option<&str>,
) -> Result<SyncPreviewResult> {
    refresh_platform_for_sync(
        pool,
        events,
        config,
        &request.source_platform,
        "源平台",
        task_id,
    )
    .await?;
    refresh_platform_for_sync(
        pool,
        events,
        config,
        &request.target_platform,
        "目标平台",
        task_id,
    )
    .await?;

    let source_items = list_library_items(pool, Some(&request.source_platform)).await?;
    let target_items = list_library_items(pool, Some(&request.target_platform)).await?;
    let result = build_sync_preview(
        &request.source_platform,
        &request.target_platform,
        &source_items,
        &target_items,
        request,
    )?;
    emit_event(
        events,
        "log",
        task_id.map(ToOwned::to_owned),
        json!({
            "level": "success",
            "message": format!(
                "同步预览已生成：{} -> {}，源 {} 条，目标 {} 条，候选 {} 条",
                request.source_platform.to_uppercase(),
                request.target_platform.to_uppercase(),
                result.source_count,
                result.target_count,
                result.preview_count
            )
        }),
    );
    Ok(result)
}

async fn build_local_sync_preview(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    request: &SyncPreviewRequest,
    task_id: Option<&str>,
) -> Result<SyncPreviewResult> {
    let source_items = list_library_items(pool, Some(&request.source_platform)).await?;
    let target_items = list_library_items(pool, Some(&request.target_platform)).await?;
    let result = build_sync_preview(
        &request.source_platform,
        &request.target_platform,
        &source_items,
        &target_items,
        request,
    )?;
    emit_event(
        events,
        "log",
        task_id.map(ToOwned::to_owned),
        json!({
            "level": "success",
            "message": format!(
                "同步预览已生成：{} -> {}，源 {} 条，目标 {} 条，候选 {} 条（本地库）",
                request.source_platform.to_uppercase(),
                request.target_platform.to_uppercase(),
                result.source_count,
                result.target_count,
                result.preview_count
            )
        }),
    );
    Ok(result)
}

async fn refresh_platform_for_sync(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    platform: &str,
    role: &str,
    task_id: Option<&str>,
) -> Result<FetchResult> {
    emit_event(
        events,
        "sync.progress",
        task_id.map(ToOwned::to_owned),
        json!({
            "phase": "library.refresh.started",
            "platform": platform,
            "role": role,
            "message": format!("正在刷新{role} {} 本地库", platform.to_uppercase())
        }),
    );

    let existing_records = list_library_items(pool, Some(platform))
        .await
        .unwrap_or_default();
    let (result, records) = match fetch_platform(platform, config).await {
        Ok(value) => value,
        Err(error) => {
            emit_event(
                events,
                "log",
                task_id.map(ToOwned::to_owned),
                json!({
                    "level": "error",
                    "message": format!("同步前刷新 {} 失败：{error}", platform.to_uppercase())
                }),
            );
            return Err(error);
        }
    };
    let records = merge_existing_library_metadata(records, &existing_records);
    replace_library_items(pool, platform, &records).await?;

    emit_event(
        events,
        "log",
        task_id.map(ToOwned::to_owned),
        json!({
            "level": "success",
            "message": format!(
                "{} {} 已刷新：{} 条",
                role,
                platform.to_uppercase(),
                result.stored_count
            )
        }),
    );
    emit_event(
        events,
        "sync.progress",
        task_id.map(ToOwned::to_owned),
        json!({
            "phase": "library.refresh.completed",
            "platform": platform,
            "role": role,
            "stored_count": result.stored_count,
            "message": format!("{role} {} 已刷新 · {} 条", platform.to_uppercase(), result.stored_count)
        }),
    );
    Ok(result)
}

pub async fn run_sync_execute(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    request: &SyncExecuteRequest,
    task: &SyncTask,
) -> Result<SyncExecuteResult> {
    update_task_status(pool, &task.id, TaskStatus::Running, task.payload.clone()).await?;

    update_task_status(
        pool,
        &task.id,
        TaskStatus::Running,
        json!({
            "direction": format!("{}-to-{}", request.source_platform, request.target_platform),
            "phase": if request.refresh_before_sync { "refreshing" } else { "previewing" },
            "message": if request.refresh_before_sync { "执行前正在刷新同步双方的本地库" } else { "正在使用本地库确认待执行条目" }
        }),
    )
    .await?;

    let preview_request = SyncPreviewRequest {
        source_platform: request.source_platform.clone(),
        target_platform: request.target_platform.clone(),
        recent_limit: request.recent_limit,
        only_new: request.only_new,
        overwrite: request.overwrite,
        default_rating: request.default_rating,
        refresh_before_sync: request.refresh_before_sync,
    };
    let mut preview = if request.refresh_before_sync {
        build_refreshed_sync_preview(pool, events, config, &preview_request, Some(&task.id)).await?
    } else {
        build_local_sync_preview(pool, events, &preview_request, Some(&task.id)).await?
    };
    if !request.selected_target_ids.is_empty() {
        let allowed = request
            .selected_target_ids
            .iter()
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
            .collect::<std::collections::HashSet<_>>();
        preview.items.retain(|item| {
            item.target_linking_id
                .as_deref()
                .is_some_and(|value| allowed.contains(value))
        });
        preview.preview_count = preview.items.len();
    }
    emit_event(
        events,
        "sync.progress",
        Some(task.id.clone()),
        json!({
            "phase": "execution.prepared",
            "direction": &preview.direction,
            "current": 0,
            "total": preview.items.len(),
            "message": format!("执行清单已确认 · 共 {} 项", preview.items.len())
        }),
    );
    let result = execute_sync_with_progress(config, &preview, |payload| {
        emit_event(events, "sync.progress", Some(task.id.clone()), payload);
    })
    .await?;
    persist_successful_sync_items(pool, &request.target_platform, &preview, &result).await?;
    update_task_status(pool, &task.id, TaskStatus::Succeeded, json!(result.clone())).await?;
    emit_event(
        events,
        "sync.completed",
        Some(task.id.clone()),
        json!(result.clone()),
    );
    Ok(result)
}

async fn persist_successful_sync_items(
    pool: &SqlitePool,
    target_platform: &str,
    preview: &SyncPreviewResult,
    result: &SyncExecuteResult,
) -> Result<()> {
    let mut records = list_library_items(pool, Some(target_platform)).await?;
    let mut changed = false;

    for (preview_item, executed) in preview.items.iter().zip(result.items.iter()) {
        if executed.status != "success" {
            continue;
        }

        if let Some(existing) = records
            .iter_mut()
            .find(|record| record_matches_sync_target(record, target_platform, preview_item))
        {
            if executed.source_rating.is_some() && existing.rating != executed.source_rating {
                existing.rating = executed.source_rating;
                existing.rated_at = Some(Utc::now());
                changed = true;
            }
            continue;
        }

        let mut identifiers = preview_item.identifiers.clone();
        let target_id = executed.target_linking_id.clone();
        match target_platform {
            "imdb" => identifiers.imdb = target_id.clone(),
            "tmdb" => identifiers.tmdb = target_id.clone(),
            "douban" => identifiers.douban = target_id.clone(),
            "trakt" => {
                if target_id
                    .as_deref()
                    .is_some_and(|value| value.chars().all(|ch| ch.is_ascii_digit()))
                {
                    identifiers.trakt = target_id.clone();
                }
            }
            _ => {}
        }
        let external_id = match target_platform {
            "imdb" => identifiers.imdb.clone(),
            "tmdb" => identifiers.tmdb.clone(),
            "douban" => identifiers.douban.clone(),
            "trakt" => identifiers.trakt.clone(),
            _ => target_id.clone(),
        };
        let raw_json = json!({
            "IMDb ID": identifiers.imdb,
            "TMDB ID": identifiers.tmdb,
            "Trakt ID": identifiers.trakt,
            "douban_id": identifiers.douban,
            "sync_source": preview_item.source_platform,
            "sync_target": target_platform,
        });
        records.push(MovieRecord {
            id: Uuid::new_v4().to_string(),
            platform: target_platform.to_string(),
            title: executed.title.clone(),
            year: executed.year,
            rating: executed.source_rating,
            rated_at: Some(Utc::now()),
            external_id,
            source_url: executed.target_url.clone(),
            identifiers,
            raw_json,
        });
        changed = true;
    }

    if changed {
        replace_library_items(pool, target_platform, &records).await?;
        update_platform_local_counts(pool, target_platform, Some(records.len()), None).await?;
    }
    Ok(())
}

fn record_matches_sync_target(
    record: &MovieRecord,
    target_platform: &str,
    item: &cinerecord_core::SyncPreviewItem,
) -> bool {
    match target_platform {
        "imdb" => {
            record.identifiers.imdb.is_some() && record.identifiers.imdb == item.identifiers.imdb
        }
        "tmdb" => {
            record.identifiers.tmdb.is_some() && record.identifiers.tmdb == item.identifiers.tmdb
        }
        "douban" => {
            record.identifiers.douban.is_some()
                && record.identifiers.douban == item.identifiers.douban
        }
        "trakt" => {
            (record.identifiers.trakt.is_some()
                && record.identifiers.trakt == item.identifiers.trakt)
                || (record.identifiers.imdb.is_some()
                    && record.identifiers.imdb == item.identifiers.imdb)
                || (record.identifiers.tmdb.is_some()
                    && record.identifiers.tmdb == item.identifiers.tmdb)
        }
        _ => record.external_id.is_some() && record.external_id == item.target_linking_id,
    }
}

pub async fn run_import_legacy(
    paths: &StoragePaths,
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    platform: &str,
    task: &SyncTask,
) -> Result<cinerecord_storage::LibrarySnapshot> {
    update_task_status(pool, &task.id, TaskStatus::Running, task.payload.clone()).await?;
    emit_log(
        events,
        Some(task.id.clone()),
        format!("Importing legacy CSV for {platform}"),
    );

    let snapshot = import_legacy_csv(paths, platform, config, pool).await?;
    let payload = json!({
        "platform": snapshot.platform,
        "item_count": snapshot.item_count,
        "source": "legacy_csv"
    });
    update_task_status(pool, &task.id, TaskStatus::Succeeded, payload.clone()).await?;
    emit_event(events, "fetch.completed", Some(task.id.clone()), payload);
    Ok(snapshot)
}

pub async fn run_scheduled_sync_task(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    config: &AppConfig,
    task: &ScheduledTask,
    next_run_at: Option<chrono::DateTime<Utc>>,
) -> Result<SyncExecuteResult> {
    emit_scheduled_log(
        pool,
        events,
        task,
        "start",
        format!(
            "开始执行定时同步 {} -> {}",
            task.source_platform, task.target_platform
        ),
    )
    .await?;

    let request = SyncExecuteRequest {
        source_platform: task.source_platform.clone(),
        target_platform: task.target_platform.clone(),
        recent_limit: task.recent_limit,
        only_new: task.only_new,
        overwrite: task.overwrite,
        default_rating: task.default_rating,
        refresh_before_sync: true,
        selected_target_ids: Vec::new(),
    };

    let result = run_sync_execute(
        pool,
        events,
        config,
        &request,
        &SyncTask {
            id: format!("scheduled-{}", task.id),
            name: task.name.clone(),
            kind: cinerecord_core::TaskKind::SyncExecute,
            status: TaskStatus::Running,
            payload: json!({
                "scheduled_task_id": task.id,
                "direction": format!("{}-to-{}", task.source_platform, task.target_platform)
            }),
            created_at: Utc::now(),
            updated_at: Utc::now(),
        },
    )
    .await;

    match result {
        Ok(result) => {
            let summary = format!(
                "完成：成功 {}，跳过 {}，失败 {}",
                result.success_count, result.skipped_count, result.failed_count
            );
            complete_scheduled_task_run(pool, &task.id, next_run_at, Some(&summary)).await?;
            if let Some(updated) = get_scheduled_task(pool, &task.id).await? {
                emit_event(
                    events,
                    "scheduled.task.updated",
                    Some(task.id.clone()),
                    json!(updated),
                );
            }
            emit_scheduled_log(pool, events, task, "success", summary).await?;
            Ok(result)
        }
        Err(error) => {
            let message = format!("执行失败：{error}");
            complete_scheduled_task_run(pool, &task.id, next_run_at, Some(&message)).await?;
            if let Some(updated) = get_scheduled_task(pool, &task.id).await? {
                emit_event(
                    events,
                    "scheduled.task.updated",
                    Some(task.id.clone()),
                    json!(updated),
                );
            }
            emit_scheduled_log(pool, events, task, "error", message.clone()).await?;
            Err(error)
        }
    }
}

fn emit_log(events: &Sender<AppEvent>, task_id: Option<String>, message: String) {
    emit_event(
        events,
        "log",
        task_id,
        json!({
            "message": message,
            "level": "info"
        }),
    );
}

fn emit_event(
    events: &Sender<AppEvent>,
    event_type: &str,
    task_id: Option<String>,
    payload: serde_json::Value,
) {
    let event = AppEvent {
        event_type: event_type.to_string(),
        task_id,
        timestamp: Utc::now(),
        payload,
    };
    let _ = events.send(event);
    info!(target: "cinerecord.events", event_type);
}

async fn emit_scheduled_log(
    pool: &SqlitePool,
    events: &Sender<AppEvent>,
    task: &ScheduledTask,
    log_type: &str,
    message: String,
) -> Result<()> {
    let log = ScheduledTaskLog {
        id: Uuid::new_v4().to_string(),
        task_id: Some(task.id.clone()),
        task_name: task.name.clone(),
        source_platform: Some(task.source_platform.clone()),
        target_platform: Some(task.target_platform.clone()),
        log_type: log_type.to_string(),
        message: message.clone(),
        created_at: Utc::now(),
    };
    add_scheduled_task_log(pool, &log).await?;
    emit_event(
        events,
        "scheduled.task.log",
        Some(task.id.clone()),
        json!(log),
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use cinerecord_core::{MovieIdentifiers, SyncExecutionItem, SyncPreviewItem};
    use cinerecord_storage::{connect, list_platforms};

    #[tokio::test]
    async fn successful_sync_is_added_to_target_library_and_counts() {
        let root = std::env::temp_dir().join(format!("cinerecord-jobs-test-{}", Uuid::new_v4()));
        let paths = StoragePaths::from_repo_root(&root);
        let pool = connect(&paths)
            .await
            .expect("test storage should initialize");
        upsert_platform_state(
            &pool,
            "trakt",
            true,
            Some("Trakt test account"),
            Some(&json!({"display_name": "tester", "watched": 0})),
        )
        .await
        .expect("platform state should initialize");

        let preview = SyncPreviewResult {
            direction: "imdb-to-trakt".to_string(),
            source_count: 1,
            target_count: 0,
            preview_count: 1,
            items: vec![SyncPreviewItem {
                title: "Chef".to_string(),
                year: Some(2014),
                source_platform: "imdb".to_string(),
                target_platform: "trakt".to_string(),
                source_rating: Some(7.0),
                target_existing_rating: None,
                source_url: Some("https://www.imdb.com/title/tt2883512/".to_string()),
                target_linking_id: Some("tt2883512".to_string()),
                identifiers: MovieIdentifiers {
                    imdb: Some("tt2883512".to_string()),
                    ..MovieIdentifiers::default()
                },
                action: "new".to_string(),
                reason: None,
            }],
        };
        let result = SyncExecuteResult {
            direction: preview.direction.clone(),
            success_count: 1,
            failed_count: 0,
            skipped_count: 0,
            items: vec![SyncExecutionItem {
                title: "Chef".to_string(),
                year: Some(2014),
                source_rating: Some(7.0),
                source_url: Some("https://www.imdb.com/title/tt2883512/".to_string()),
                target_linking_id: Some("tt2883512".to_string()),
                target_url: Some("https://trakt.tv/search/imdb/tt2883512".to_string()),
                status: "success".to_string(),
                reason: None,
            }],
        };

        persist_successful_sync_items(&pool, "trakt", &preview, &result)
            .await
            .expect("successful sync should persist");

        let records = list_library_items(&pool, Some("trakt"))
            .await
            .expect("target library should load");
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].identifiers.imdb.as_deref(), Some("tt2883512"));
        assert_eq!(records[0].rating, Some(7.0));

        let mut config = AppConfig::default();
        config.platforms.trakt.client_id = Some("test-client".to_string());
        let platforms = list_platforms(&config, &pool)
            .await
            .expect("platform state should load");
        let trakt = platforms
            .iter()
            .find(|platform| platform.id == "trakt")
            .expect("trakt descriptor should exist");
        assert_eq!(
            trakt
                .status
                .profile
                .as_ref()
                .and_then(|profile| profile.get("watched")),
            Some(&json!(1))
        );

        pool.close().await;
        tokio::fs::remove_dir_all(root).await.ok();
    }

    #[tokio::test]
    async fn douban_sync_persists_resolved_subject_id() {
        let root = std::env::temp_dir().join(format!("cinerecord-douban-test-{}", Uuid::new_v4()));
        let paths = StoragePaths::from_repo_root(&root);
        let pool = connect(&paths)
            .await
            .expect("test storage should initialize");

        let preview = SyncPreviewResult {
            direction: "trakt-to-douban".to_string(),
            source_count: 1,
            target_count: 0,
            preview_count: 1,
            items: vec![SyncPreviewItem {
                title: "Fear and Desire".to_string(),
                year: Some(1953),
                source_platform: "trakt".to_string(),
                target_platform: "douban".to_string(),
                source_rating: None,
                target_existing_rating: None,
                source_url: None,
                target_linking_id: Some("tt0045758".to_string()),
                identifiers: MovieIdentifiers {
                    imdb: Some("tt0045758".to_string()),
                    ..MovieIdentifiers::default()
                },
                action: "new".to_string(),
                reason: None,
            }],
        };
        let result = SyncExecuteResult {
            direction: preview.direction.clone(),
            success_count: 1,
            failed_count: 0,
            skipped_count: 0,
            items: vec![SyncExecutionItem {
                title: "Fear and Desire".to_string(),
                year: Some(1953),
                source_rating: None,
                source_url: None,
                target_linking_id: Some("1293398".to_string()),
                target_url: Some("https://movie.douban.com/subject/1293398/".to_string()),
                status: "success".to_string(),
                reason: None,
            }],
        };

        persist_successful_sync_items(&pool, "douban", &preview, &result)
            .await
            .expect("resolved Douban item should persist");

        let records = list_library_items(&pool, Some("douban"))
            .await
            .expect("Douban library should load");
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].identifiers.douban.as_deref(), Some("1293398"));
        assert_eq!(records[0].identifiers.imdb.as_deref(), Some("tt0045758"));

        pool.close().await;
        tokio::fs::remove_dir_all(root).await.ok();
    }
}
