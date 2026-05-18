use anyhow::Result;
use chrono::Utc;
use cinerecord_core::{
    AppConfig, AppEvent, FetchResult, MovieRecord, ScheduledTask, ScheduledTaskLog, SyncExecuteRequest,
    SyncExecuteResult, SyncPreviewRequest, SyncPreviewResult, SyncTask, TaskStatus,
};
use cinerecord_platforms::{build_sync_preview, execute_sync, fetch_platform, fetch_platform_wishlist, test_platform};
use cinerecord_storage::{
    add_scheduled_task_log, complete_scheduled_task_run, get_scheduled_task, import_legacy_csv, list_library_items,
    replace_library_items, replace_wishlist_items, update_task_status, upsert_platform_state, StoragePaths,
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
        if result.success { result.profile.as_ref() } else { None },
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
    emit_log(events, Some(task.id.clone()), format!("Fetching {platform} data"));

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
            emit_log(events, Some(task.id.clone()), format!("Fetch {platform} failed: {error}"));
            return Err(error);
        }
    };
    let existing_records = list_library_items(pool, Some(platform)).await.unwrap_or_default();
    let records = merge_existing_library_metadata(records, &existing_records);
    replace_library_items(pool, platform, &records).await?;
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

fn merge_existing_library_metadata(mut fetched: Vec<MovieRecord>, existing: &[MovieRecord]) -> Vec<MovieRecord> {
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
            emit_log(events, Some(task.id.clone()), format!("Fetch {platform} wishlist failed: {error}"));
            return Err(error);
        }
    };
    replace_wishlist_items(pool, platform, &records).await?;
    update_task_status(pool, &task.id, TaskStatus::Succeeded, result.clone()).await?;
    emit_event(events, "fetch.completed", Some(task.id.clone()), result.clone());
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
                "phase": "refreshing",
                "message": "正在刷新同步双方的本地库"
            }),
        )
        .await?;
    }
    let task_id = task.map(|task| task.id.clone());
    let result = build_refreshed_sync_preview(pool, events, config, request, task_id.as_deref()).await?;
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
    refresh_platform_for_sync(pool, events, config, &request.source_platform, "源平台", task_id).await?;
    refresh_platform_for_sync(pool, events, config, &request.target_platform, "目标平台", task_id).await?;

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
        "log",
        task_id.map(ToOwned::to_owned),
        json!({
            "level": "info",
            "message": format!("同步前刷新{role} {} 本地库", platform.to_uppercase())
        }),
    );

    let existing_records = list_library_items(pool, Some(platform)).await.unwrap_or_default();
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
        "fetch.completed",
        task_id.map(ToOwned::to_owned),
        json!({
            "platform": platform,
            "item_count": result.item_count,
            "stored_count": result.stored_count,
            "sync_refresh": true
        }),
    );
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
    emit_log(
        events,
        Some(task.id.clone()),
        format!(
            "Executing sync {} -> {}",
            request.source_platform, request.target_platform
        ),
    );

    update_task_status(
        pool,
        &task.id,
        TaskStatus::Running,
        json!({
            "direction": format!("{}-to-{}", request.source_platform, request.target_platform),
            "phase": "refreshing",
            "message": "执行前正在刷新同步双方的本地库"
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
    };
    let mut preview = build_refreshed_sync_preview(pool, events, config, &preview_request, Some(&task.id)).await?;
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
    let result = execute_sync(config, &preview).await?;
    update_task_status(pool, &task.id, TaskStatus::Succeeded, json!(result.clone())).await?;
    emit_event(events, "sync.completed", Some(task.id.clone()), json!(result.clone()));
    Ok(result)
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
                emit_event(events, "scheduled.task.updated", Some(task.id.clone()), json!(updated));
            }
            emit_scheduled_log(pool, events, task, "success", summary).await?;
            Ok(result)
        }
        Err(error) => {
            let message = format!("执行失败：{error}");
            complete_scheduled_task_run(pool, &task.id, next_run_at, Some(&message)).await?;
            if let Some(updated) = get_scheduled_task(pool, &task.id).await? {
                emit_event(events, "scheduled.task.updated", Some(task.id.clone()), json!(updated));
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

fn emit_event(events: &Sender<AppEvent>, event_type: &str, task_id: Option<String>, payload: serde_json::Value) {
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
    emit_event(events, "scheduled.task.log", Some(task.id.clone()), json!(log));
    Ok(())
}
