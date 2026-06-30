use std::{collections::HashMap, convert::Infallible, process::Command};

use axum::{
    Form, Json, Router,
    extract::{Path, Query, State},
    response::{
        Html, IntoResponse, Redirect, Response, Sse,
        sse::{Event, KeepAlive},
    },
    routing::{get, post},
};
use chrono::{Duration, Utc};
use cinerecord_core::{
    AppConfig, AppEvent, ScheduledTask, SyncExecuteRequest, SyncPreviewRequest, SyncTask, TaskKind,
    TaskStatus,
};
use cinerecord_jobs::{
    run_fetch_platform, run_fetch_wishlist, run_import_legacy, run_platform_test, run_sync_execute,
    run_sync_preview,
};
use cinerecord_platforms::{
    complete_tmdb_auth, fetch_platform as fetch_platform_records,
    fetch_platform_wishlist as fetch_platform_wishlist_records, poll_trakt_device_auth,
    refresh_trakt_access_token, start_tmdb_auth, start_trakt_device_auth, sync_cookiecloud,
    validate_cookie_platform,
};
use cinerecord_storage::{
    FriendBackup, count_library_groups, count_library_items, count_library_view_groups,
    count_wishlist_groups, count_wishlist_items, delete_friend_backup, delete_scheduled_task,
    delete_task, get_friend_backup, get_scheduled_task, get_task, insert_task, library_view_counts,
    list_friend_backups, list_library_items_aggregated_paginated, list_library_items_paginated,
    list_library_items_view_paginated, list_platforms, list_scheduled_task_logs,
    list_scheduled_tasks, list_tasks, list_wishlist_items_aggregated_paginated,
    list_wishlist_items_paginated, platform_item_counts, save_config, save_friend_backup,
    upsert_platform_state, upsert_scheduled_task,
};
use futures::stream::Stream;
use serde::Deserialize;
use serde_json::json;
use tokio_stream::{StreamExt, wrappers::BroadcastStream};
use uuid::Uuid;

use crate::{
    AppState, PendingBrowserAuth,
    scheduler::{calculate_next_run_at, trigger_scheduled_task_now},
};

const BROWSER_AUTH_TTL_SECONDS: i64 = 10 * 60;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/", get(index))
        .route("/favicon.ico", get(favicon))
        .route("/proxy/avatar", get(proxy_avatar))
        .route("/proxy/image", get(proxy_image))
        .route("/auth/bridge", get(auth_bridge))
        .route("/auth/bookmarklet/choose", get(auth_bookmarklet_choose))
        .route("/auth/bookmarklet/submit", post(auth_bookmarklet_submit))
        .route("/api/v2/health", get(health))
        .route("/api/v2/overview", get(get_overview))
        .route("/api/v2/config", get(get_config).put(put_config))
        .route("/api/v2/auth/callback", post(auth_callback))
        .route(
            "/api/v2/auth/bookmarklet/callback",
            post(auth_bookmarklet_callback),
        )
        .route("/api/v2/cookiecloud/sync", post(sync_cookiecloud_handler))
        .route("/api/v2/platforms", get(get_platforms))
        .route(
            "/api/v2/platforms/{platform}/browser-auth/start",
            post(start_browser_auth),
        )
        .route("/api/v2/platforms/{platform}/test", post(test_platform))
        .route("/api/v2/platforms/{platform}/fetch", post(fetch_platform))
        .route(
            "/api/v2/platforms/{platform}/fetch-wishlist",
            post(fetch_wishlist),
        )
        .route(
            "/api/v2/platforms/{platform}/import-legacy",
            post(import_legacy),
        )
        .route(
            "/api/v2/platforms/tmdb/auth/start",
            post(start_tmdb_auth_handler),
        )
        .route(
            "/api/v2/platforms/tmdb/auth/complete",
            post(complete_tmdb_auth_handler),
        )
        .route(
            "/api/v2/platforms/trakt/device-auth/start",
            post(start_trakt_auth),
        )
        .route(
            "/api/v2/platforms/trakt/device-auth/poll",
            post(poll_trakt_auth),
        )
        .route("/api/v2/library", get(get_library))
        .route("/api/v2/library/{platform}", get(get_library_for_platform))
        .route("/api/v2/wishlist", get(get_wishlist))
        .route(
            "/api/v2/wishlist/{platform}",
            get(get_wishlist_for_platform),
        )
        .route("/api/v2/sync/preview", post(sync_preview))
        .route("/api/v2/sync/execute", post(sync_execute))
        .route("/api/v2/tasks", get(get_tasks).post(create_task))
        .route(
            "/api/v2/tasks/{task_id}",
            get(get_task_by_id)
                .patch(update_task)
                .delete(delete_task_by_id),
        )
        .route(
            "/api/v2/backups",
            get(get_backups).post(create_friend_backup),
        )
        .route(
            "/api/v2/backups/{backup_id}",
            get(get_backup_by_id).delete(delete_backup_by_id),
        )
        .route("/api/v2/system", get(get_system_info))
        .route(
            "/api/v2/scheduled-tasks",
            get(get_scheduled_tasks).post(create_scheduled_task),
        )
        .route("/api/v2/scheduled-tasks/logs", get(get_scheduled_task_logs))
        .route(
            "/api/v2/scheduled-tasks/{task_id}/run",
            post(run_scheduled_task_now),
        )
        .route(
            "/api/v2/scheduled-tasks/{task_id}",
            get(get_scheduled_task_by_id)
                .patch(update_scheduled_task)
                .delete(delete_scheduled_task_by_id),
        )
        .route("/api/v2/events", get(sse_events))
}

async fn index() -> impl IntoResponse {
    Html(include_str!("../../../web/templates/rust_v2.html"))
}

async fn auth_bridge() -> impl IntoResponse {
    Html(include_str!("../../../web/templates/auth_bridge.html"))
}

async fn auth_bookmarklet_choose() -> impl IntoResponse {
    Html(render_bookmarklet_choose_page())
}

async fn favicon() -> impl IntoResponse {
    Redirect::temporary("/static/images/logo.svg")
}

async fn proxy_avatar(Query(query): Query<ProxyAvatarQuery>) -> Result<Response, ApiError> {
    proxy_remote_image(&query.url).await
}

async fn proxy_image(Query(query): Query<ProxyAvatarQuery>) -> Result<Response, ApiError> {
    proxy_remote_image(&query.url).await
}

async fn proxy_remote_image(url: &str) -> Result<Response, ApiError> {
    let url = url.trim();
    if url.is_empty() {
        return Err(ApiError::BadRequest("No URL provided".to_string()));
    }
    let parsed = reqwest::Url::parse(url)
        .map_err(|_| ApiError::BadRequest("Invalid image URL".to_string()))?;
    let host = parsed.host_str().unwrap_or_default().to_ascii_lowercase();
    let allowed_domains = [
        "doubanio.com",
        "douban.com",
        "trakt.tv",
        "imdb.com",
        "media-amazon.com",
        "tmdb.org",
    ];
    if !allowed_domains
        .iter()
        .any(|domain| host == *domain || host.ends_with(&format!(".{domain}")))
    {
        return Err(ApiError::BadRequest("Domain not allowed".to_string()));
    }

    let response = reqwest::Client::new()
        .get(parsed)
        .header(
            "User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        .header("Referer", "https://www.douban.com/")
        .send()
        .await
        .map_err(|error| ApiError::Internal(error.into()))?;
    let status = response.status();
    if !status.is_success() {
        return Err(ApiError::BadRequest(format!(
            "Failed to fetch image ({status})"
        )));
    }
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("image/jpeg")
        .to_string();
    let bytes = response
        .bytes()
        .await
        .map_err(|error| ApiError::Internal(error.into()))?;
    Ok(([(axum::http::header::CONTENT_TYPE, content_type)], bytes).into_response())
}

async fn health() -> impl IntoResponse {
    Json(json!({
        "ok": true,
        "service": "cinerecord",
        "version": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "timestamp": Utc::now(),
    }))
}

async fn get_config(State(state): State<AppState>) -> impl IntoResponse {
    let config = state.config.read().await.clone();
    Json(config)
}

async fn get_overview(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let platforms = list_platforms(&config, &state.pool).await?;
    let library_counts = platform_item_counts(&state.pool, "library_items").await?;
    let wishlist_counts = platform_item_counts(&state.pool, "wishlist_items").await?;
    let tasks = list_tasks(&state.pool).await?;
    let total_library = count_library_groups(&state.pool, None).await?;
    let total_wishlist = count_wishlist_groups(&state.pool, None).await?;
    Ok(Json(json!({
        "platforms": platforms,
        "counts": {
            "library_total": total_library,
            "wishlist_total": total_wishlist,
            "library": library_counts,
            "library_raw": library_counts,
            "wishlist": wishlist_counts
        },
        "tasks": tasks.into_iter().take(12).collect::<Vec<_>>()
    })))
}

async fn put_config(
    State(state): State<AppState>,
    Json(payload): Json<AppConfig>,
) -> Result<Json<serde_json::Value>, ApiError> {
    save_config(&state.paths, &payload).await?;
    {
        let mut current = state.config.write().await;
        *current = payload.clone();
    }
    publish_event(
        &state,
        "log",
        None,
        json!({
            "message": "配置已保存",
            "level": "success"
        }),
    );
    Ok(Json(json!({ "ok": true, "config": payload })))
}

async fn get_platforms(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let platforms = list_platforms(&config, &state.pool).await?;
    Ok(Json(json!({ "platforms": platforms })))
}

async fn start_browser_auth(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if !matches!(platform.as_str(), "douban" | "imdb") {
        return Err(ApiError::BadRequest(
            "browser auth only supports douban and imdb".to_string(),
        ));
    }

    let token = Uuid::new_v4().to_string();
    state.auth_sessions.write().await.insert(
        token.clone(),
        PendingBrowserAuth {
            platform: platform.clone(),
            created_at: Utc::now(),
        },
    );

    let config = state.config.read().await.clone();
    let base_url = format!("http://{}:{}", config.app.host, config.app.port);
    let auth_url = format!(
        "{base_url}/auth/bridge?platform={platform}&token={token}&callback={base_url}/api/v2"
    );
    let opened = open_external_url(&auth_url);

    publish_event(
        &state,
        "log",
        None,
        json!({
            "message": format!("已准备 {} 浏览器授权页", platform.to_uppercase()),
            "level": "info",
            "platform": platform,
            "opened": opened
        }),
    );

    Ok(Json(json!({
        "platform": platform,
        "auth_url": auth_url,
        "opened": opened
    })))
}

async fn auth_callback(
    State(state): State<AppState>,
    Json(payload): Json<BrowserAuthCallbackRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if payload.platform.trim().is_empty()
        || payload.cookie.trim().is_empty()
        || payload.token.trim().is_empty()
    {
        return Err(ApiError::BadRequest(
            "missing platform, cookie, or token".to_string(),
        ));
    }

    let session = {
        let sessions = state.auth_sessions.read().await;
        sessions.get(&payload.token).cloned()
    }
    .ok_or_else(|| ApiError::BadRequest("invalid or expired auth token".to_string()))?;

    if session.platform != payload.platform {
        return Err(ApiError::BadRequest(
            "auth token platform mismatch".to_string(),
        ));
    }
    if (Utc::now() - session.created_at).num_seconds() > BROWSER_AUTH_TTL_SECONDS {
        state.auth_sessions.write().await.remove(&payload.token);
        return Err(ApiError::BadRequest("auth token expired".to_string()));
    }

    let response = persist_cookie_login(&state, &payload.platform, &payload.cookie, false).await?;
    state.auth_sessions.write().await.remove(&payload.token);
    Ok(Json(response))
}

async fn auth_bookmarklet_callback(
    State(state): State<AppState>,
    Json(payload): Json<BookmarkletAuthRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let platform =
        detect_bookmarklet_platform(payload.platform.as_deref(), payload.page_url.as_deref())
            .ok_or_else(|| ApiError::BadRequest("请在豆瓣或 IMDb 页面点击这个书签".to_string()))?;
    if payload.cookie.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "当前页面没有可用 Cookie，请先确认已登录".to_string(),
        ));
    }
    let response = persist_cookie_login(&state, &platform, &payload.cookie, true).await?;
    Ok(Json(response))
}

async fn auth_bookmarklet_submit(
    State(state): State<AppState>,
    Form(payload): Form<BookmarkletAuthRequest>,
) -> Result<Html<String>, ApiError> {
    let platform =
        detect_bookmarklet_platform(payload.platform.as_deref(), payload.page_url.as_deref())
            .ok_or_else(|| ApiError::BadRequest("请在豆瓣或 IMDb 页面点击这个书签".to_string()))?;
    if payload.cookie.trim().is_empty() {
        return Err(ApiError::BadRequest(
            "当前页面没有可用 Cookie，请先确认已登录".to_string(),
        ));
    }
    let response = persist_cookie_login(&state, &platform, &payload.cookie, true).await?;
    let success = response
        .get("success")
        .and_then(|value| value.as_bool())
        .unwrap_or(false);
    let message = response
        .get("validation")
        .and_then(|value| value.get("message"))
        .and_then(|value| value.as_str())
        .or_else(|| response.get("error").and_then(|value| value.as_str()))
        .unwrap_or("CineRecord 处理完成");
    Ok(Html(render_bookmarklet_result_page(success, message)))
}

async fn sync_cookiecloud_handler(
    State(state): State<AppState>,
    Json(payload): Json<CookieCloudSyncRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let mut next_config = state.config.read().await.clone();
    let result = sync_cookiecloud(
        &mut next_config,
        payload.host.clone(),
        payload.uuid.clone(),
        payload.password.clone(),
    )
    .await
    .map_err(|error| ApiError::BadRequest(error.to_string()))?;

    save_config(&state.paths, &next_config).await?;
    *state.config.write().await = next_config.clone();

    for imported in &result.imported {
        upsert_platform_state(
            &state.pool,
            &imported.platform,
            true,
            Some(&imported.validation.message),
            imported.validation.profile.as_ref(),
        )
        .await?;
        publish_event(
            &state,
            "platform.validated",
            None,
            json!(imported.validation.clone()),
        );
    }

    if !result.imported.is_empty() {
        let summary = result
            .imported
            .iter()
            .map(|item| {
                if item.imported_without_validation {
                    format!(
                        "{} ({} 项，待验证)",
                        item.platform.to_uppercase(),
                        item.matched_count
                    )
                } else {
                    format!(
                        "{} ({} 项)",
                        item.platform.to_uppercase(),
                        item.matched_count
                    )
                }
            })
            .collect::<Vec<_>>()
            .join("、");
        publish_event(
            &state,
            "log",
            None,
            json!({
                "message": format!("CookieCloud 同步完成：{summary}"),
                "level": "success"
            }),
        );
    }

    if !result.skipped.is_empty() {
        for skipped in &result.skipped {
            publish_event(
                &state,
                "log",
                None,
                json!({
                    "message": format!("已跳过 {} CookieCloud 导入：{}", skipped.platform.to_uppercase(), skipped.reason),
                    "level": "warning"
                }),
            );
        }
    }

    Ok(Json(json!({
        "success": true,
        "result": result,
        "config": next_config
    })))
}

async fn ensure_fresh_trakt_auth(state: &AppState) -> Result<(), ApiError> {
    let current_config = state.config.read().await.clone();
    let trakt = &current_config.platforms.trakt;
    let should_refresh = trakt
        .access_token
        .as_deref()
        .filter(|value| !value.trim().is_empty())
        .is_some()
        && trakt
            .refresh_token
            .as_deref()
            .filter(|value| !value.trim().is_empty())
            .is_some()
        && trakt
            .token_expires_at
            .map(|expires_at| expires_at <= Utc::now() + Duration::minutes(2))
            .unwrap_or(false);

    if !should_refresh {
        return Ok(());
    }

    let refresh = refresh_trakt_access_token(&current_config)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;

    let mut next_config = current_config.clone();
    match refresh.status.as_str() {
        "success" => {
            next_config.platforms.trakt.access_token = refresh.access_token.clone();
            if refresh.refresh_token.is_some() {
                next_config.platforms.trakt.refresh_token = refresh.refresh_token.clone();
            }
            next_config.platforms.trakt.token_expires_at = refresh.token_expires;
            save_config(&state.paths, &next_config).await?;
            *state.config.write().await = next_config;
            publish_event(
                state,
                "log",
                None,
                json!({
                    "message": "Trakt access token 已自动刷新",
                    "level": "success",
                    "platform": "trakt"
                }),
            );
        }
        "expired" => {
            next_config.platforms.trakt.access_token = None;
            next_config.platforms.trakt.refresh_token = None;
            next_config.platforms.trakt.token_expires_at = None;
            save_config(&state.paths, &next_config).await?;
            *state.config.write().await = next_config;
            publish_event(
                state,
                "log",
                None,
                json!({
                    "message": refresh.message.clone().unwrap_or_else(|| "Trakt refresh token 已失效，请重新授权".to_string()),
                    "level": "warning",
                    "platform": "trakt"
                }),
            );
        }
        _ => {
            publish_event(
                state,
                "log",
                None,
                json!({
                    "message": refresh.message.clone().unwrap_or_else(|| "Trakt token refresh 失败".to_string()),
                    "level": "warning",
                    "platform": "trakt"
                }),
            );
        }
    }

    Ok(())
}

async fn test_platform(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if platform == "trakt" {
        ensure_fresh_trakt_auth(&state).await?;
    }
    let config = state.config.read().await.clone();
    let result = run_platform_test(&state.pool, &state.events, &config, &platform, None).await?;
    Ok(Json(json!(result)))
}

async fn fetch_platform(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = new_task(
        format!("Fetch {}", platform.to_uppercase()),
        TaskKind::FetchPlatform,
        json!({ "platform": platform }),
    );
    insert_task(&state.pool, &task).await?;
    let platform = task.payload["platform"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    if platform == "trakt" {
        ensure_fresh_trakt_auth(&state).await?;
    }
    let config = state.config.read().await.clone();
    let result = run_fetch_platform(&state.pool, &state.events, &config, &platform, &task).await?;
    let task = get_task(&state.pool, &task.id).await?.unwrap_or(task);
    Ok(Json(json!({ "task": task, "result": result })))
}

async fn fetch_wishlist(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = new_task(
        format!("Fetch {} wishlist", platform.to_uppercase()),
        TaskKind::FetchWishlist,
        json!({ "platform": platform }),
    );
    insert_task(&state.pool, &task).await?;
    if platform == "trakt" {
        ensure_fresh_trakt_auth(&state).await?;
    }
    let config = state.config.read().await.clone();
    let result = run_fetch_wishlist(&state.pool, &state.events, &config, &platform, &task).await?;
    let task = get_task(&state.pool, &task.id).await?.unwrap_or(task);
    Ok(Json(json!({ "task": task, "result": result })))
}

async fn import_legacy(
    State(state): State<AppState>,
    Path(platform): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = new_task(
        format!("Import legacy {}", platform.to_uppercase()),
        TaskKind::ImportLegacy,
        json!({ "platform": platform }),
    );
    insert_task(&state.pool, &task).await?;
    let platform = task.payload["platform"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let config = state.config.read().await.clone();
    let result = run_import_legacy(
        &state.paths,
        &state.pool,
        &state.events,
        &config,
        &platform,
        &task,
    )
    .await?;
    let task = get_task(&state.pool, &task.id).await?.unwrap_or(task);
    Ok(Json(json!({ "task": task, "result": result })))
}

async fn get_library(
    State(state): State<AppState>,
    Query(query): Query<LibraryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let raw = query.mode.as_deref() == Some("raw");
    let full_view = query.view.as_deref() == Some("full");
    let selected_platforms = selected_library_platforms(&query);
    let total = if raw {
        count_library_items(&state.pool, None).await?
    } else if full_view {
        count_library_groups(&state.pool, None).await?
    } else {
        count_library_view_groups(&state.pool, None, &selected_platforms).await?
    };
    let items = if raw {
        json!(list_library_items_paginated(&state.pool, None, query.limit, query.offset).await?)
    } else if full_view {
        json!(
            list_library_items_aggregated_paginated(&state.pool, None, query.limit, query.offset)
                .await?
        )
    } else {
        json!(
            list_library_items_view_paginated(
                &state.pool,
                None,
                &selected_platforms,
                query.limit,
                query.offset
            )
            .await?
        )
    };
    let raw_counts = platform_item_counts(&state.pool, "library_items").await?;
    let platform_counts = library_view_counts(&state.pool, &selected_platforms).await?;
    let platforms_with_data = platforms_with_data(&raw_counts);
    Ok(Json(json!({
        "items": items,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
        "mode": if raw { "raw" } else { "aggregate" },
        "filter": "all",
        "platform_counts": platform_counts,
        "platforms_with_data": platforms_with_data
    })))
}

async fn get_library_for_platform(
    State(state): State<AppState>,
    Path(platform): Path<String>,
    Query(query): Query<LibraryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let raw = query.mode.as_deref() == Some("raw");
    let full_view = query.view.as_deref() == Some("full");
    let selected_platforms = selected_library_platforms(&query);
    let total = if raw {
        count_library_items(&state.pool, Some(&platform)).await?
    } else if full_view {
        count_library_groups(&state.pool, Some(&platform)).await?
    } else {
        count_library_view_groups(&state.pool, Some(&platform), &selected_platforms).await?
    };
    let items = if raw {
        json!(
            list_library_items_paginated(&state.pool, Some(&platform), query.limit, query.offset)
                .await?
        )
    } else if full_view {
        json!(
            list_library_items_aggregated_paginated(
                &state.pool,
                Some(&platform),
                query.limit,
                query.offset
            )
            .await?
        )
    } else {
        json!(
            list_library_items_view_paginated(
                &state.pool,
                Some(&platform),
                &selected_platforms,
                query.limit,
                query.offset
            )
            .await?
        )
    };
    let raw_counts = platform_item_counts(&state.pool, "library_items").await?;
    let platform_counts = library_view_counts(&state.pool, &selected_platforms).await?;
    let platforms_with_data = platforms_with_data(&raw_counts);
    Ok(Json(json!({
        "platform": platform,
        "items": items,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
        "mode": if raw { "raw" } else { "aggregate" },
        "filter": platform,
        "platform_counts": platform_counts,
        "platforms_with_data": platforms_with_data
    })))
}

async fn get_wishlist(
    State(state): State<AppState>,
    Query(query): Query<LibraryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let raw = query.mode.as_deref() == Some("raw");
    let total = if raw {
        count_wishlist_items(&state.pool, None).await?
    } else {
        count_wishlist_groups(&state.pool, None).await?
    };
    let items = if raw {
        json!(list_wishlist_items_paginated(&state.pool, None, query.limit, query.offset).await?)
    } else {
        json!(
            list_wishlist_items_aggregated_paginated(&state.pool, None, query.limit, query.offset)
                .await?
        )
    };
    Ok(Json(json!({
        "items": items,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
        "mode": if raw { "raw" } else { "aggregate" }
    })))
}

async fn get_wishlist_for_platform(
    State(state): State<AppState>,
    Path(platform): Path<String>,
    Query(query): Query<LibraryQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let raw = query.mode.as_deref() == Some("raw");
    let total = if raw {
        count_wishlist_items(&state.pool, Some(&platform)).await?
    } else {
        count_wishlist_groups(&state.pool, Some(&platform)).await?
    };
    let items = if raw {
        json!(
            list_wishlist_items_paginated(&state.pool, Some(&platform), query.limit, query.offset)
                .await?
        )
    } else {
        json!(
            list_wishlist_items_aggregated_paginated(
                &state.pool,
                Some(&platform),
                query.limit,
                query.offset
            )
            .await?
        )
    };
    Ok(Json(json!({
        "platform": platform,
        "items": items,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
        "mode": if raw { "raw" } else { "aggregate" }
    })))
}

async fn sync_preview(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let request: SyncPreviewRequest = serde_json::from_value(payload.clone())?;
    let task = new_task("Sync preview".to_string(), TaskKind::SyncPreview, payload);
    insert_task(&state.pool, &task).await?;
    if request.source_platform == "trakt" || request.target_platform == "trakt" {
        ensure_fresh_trakt_auth(&state).await?;
    }
    let config = state.config.read().await.clone();
    let result =
        run_sync_preview(&state.pool, &state.events, &config, &request, Some(&task)).await?;
    let task = get_task(&state.pool, &task.id).await?.unwrap_or(task);
    Ok(Json(json!({ "task": task, "result": result })))
}

async fn sync_execute(
    State(state): State<AppState>,
    Json(payload): Json<serde_json::Value>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let request: SyncExecuteRequest = serde_json::from_value(payload.clone())?;
    let task = new_task("Sync execute".to_string(), TaskKind::SyncExecute, payload);
    insert_task(&state.pool, &task).await?;
    if request.source_platform == "trakt" || request.target_platform == "trakt" {
        ensure_fresh_trakt_auth(&state).await?;
    }
    let config = state.config.read().await.clone();
    let result = run_sync_execute(&state.pool, &state.events, &config, &request, &task).await?;
    let task = get_task(&state.pool, &task.id).await?.unwrap_or(task);
    Ok(Json(json!({ "task": task, "result": result })))
}

async fn get_tasks(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let tasks = list_tasks(&state.pool).await?;
    Ok(Json(json!({ "tasks": tasks })))
}

async fn get_backups(State(state): State<AppState>) -> Result<Json<serde_json::Value>, ApiError> {
    let backups = list_friend_backups(&state.paths).await?;
    Ok(Json(json!({ "backups": backups })))
}

async fn create_friend_backup(
    State(state): State<AppState>,
    Json(payload): Json<FriendBackupRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let user_id = validate_douban_user_id(&payload.user_id)?;
    if !payload.include_watched && !payload.include_wishlist {
        return Err(ApiError::BadRequest("至少选择看过或想看".to_string()));
    }

    let mut config = state.config.read().await.clone();
    config.platforms.douban.user_id = Some(user_id.clone());
    // Friend backups only read public profile data and never reuse the owner's authenticated session.
    config.platforms.douban.cookie = None;

    let watched = if payload.include_watched {
        fetch_platform_records("douban", &config).await?.1
    } else {
        Vec::new()
    };
    let wishlist = if payload.include_wishlist {
        fetch_platform_wishlist_records("douban", &config).await?.1
    } else {
        Vec::new()
    };
    let backup = FriendBackup {
        id: Uuid::new_v4().to_string(),
        platform: "douban".to_string(),
        user_id,
        watched,
        wishlist,
        created_at: Utc::now(),
    };
    save_friend_backup(&state.paths, &backup).await?;
    publish_event(
        &state,
        "backup.completed",
        Some(backup.id.clone()),
        json!({
            "backup_id": backup.id,
            "user_id": backup.user_id,
            "watched_count": backup.watched.len(),
            "wishlist_count": backup.wishlist.len()
        }),
    );
    Ok(Json(json!({
        "backup": {
            "id": backup.id,
            "platform": backup.platform,
            "user_id": backup.user_id,
            "watched_count": backup.watched.len(),
            "wishlist_count": backup.wishlist.len(),
            "created_at": backup.created_at
        }
    })))
}

async fn get_backup_by_id(
    State(state): State<AppState>,
    Path(backup_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let backup = get_friend_backup(&state.paths, &backup_id)
        .await?
        .ok_or_else(|| ApiError::NotFound(format!("backup {backup_id} not found")))?;
    let watched = backup
        .watched
        .iter()
        .take(200)
        .map(|item| {
            json!({
                "title": item.title,
                "year": item.year,
                "rating": item.rating,
                "source_url": item.source_url
            })
        })
        .collect::<Vec<_>>();
    let wishlist = backup
        .wishlist
        .iter()
        .take(200)
        .map(|item| {
            json!({
                "title": item.title,
                "year": item.year,
                "source_url": item.source_url
            })
        })
        .collect::<Vec<_>>();
    Ok(Json(json!({
        "backup": {
            "id": backup.id,
            "platform": backup.platform,
            "user_id": backup.user_id,
            "watched_count": backup.watched.len(),
            "wishlist_count": backup.wishlist.len(),
            "created_at": backup.created_at,
            "watched": watched,
            "wishlist": wishlist
        }
    })))
}

async fn delete_backup_by_id(
    State(state): State<AppState>,
    Path(backup_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    if !delete_friend_backup(&state.paths, &backup_id).await? {
        return Err(ApiError::NotFound(format!("backup {backup_id} not found")));
    }
    Ok(Json(json!({ "ok": true })))
}

async fn get_system_info(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let tasks = list_tasks(&state.pool).await?;
    let scheduled_tasks = list_scheduled_tasks(&state.pool).await?;
    let backups = list_friend_backups(&state.paths).await?;
    Ok(Json(json!({
        "service": "cinerecord",
        "version": env!("CARGO_PKG_VERSION"),
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "storage": {
            "config": state.paths.config_path.display().to_string(),
            "database": state.paths.db_path.display().to_string(),
            "backups": state.paths.backups_dir.display().to_string(),
            "logs": state.paths.log_path.display().to_string()
        },
        "counts": {
            "tasks": tasks.len(),
            "scheduled_tasks": scheduled_tasks.len(),
            "backups": backups.len()
        }
    })))
}

async fn get_scheduled_tasks(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let tasks = list_scheduled_tasks(&state.pool).await?;
    Ok(Json(json!({ "tasks": tasks })))
}

async fn get_scheduled_task_logs(
    State(state): State<AppState>,
    Query(query): Query<ScheduledTaskLogsQuery>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let logs = list_scheduled_task_logs(&state.pool, query.limit.unwrap_or(200)).await?;
    Ok(Json(json!({ "logs": logs })))
}

async fn create_scheduled_task(
    State(state): State<AppState>,
    Json(payload): Json<ScheduledTaskUpsertRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = build_scheduled_task(None, payload)?;
    upsert_scheduled_task(&state.pool, &task).await?;
    publish_event(
        &state,
        "scheduled.task.updated",
        Some(task.id.clone()),
        json!(task.clone()),
    );
    Ok(Json(json!({ "task": task })))
}

async fn get_scheduled_task_by_id(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = get_scheduled_task(&state.pool, &task_id).await?;
    Ok(Json(json!({ "task": task })))
}

async fn update_scheduled_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
    Json(payload): Json<ScheduledTaskUpsertRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let existing = get_scheduled_task(&state.pool, &task_id).await?;
    let Some(existing) = existing else {
        return Err(ApiError::NotFound(format!(
            "scheduled task {task_id} not found"
        )));
    };
    let task = build_scheduled_task(Some(existing), payload)?;
    upsert_scheduled_task(&state.pool, &task).await?;
    publish_event(
        &state,
        "scheduled.task.updated",
        Some(task.id.clone()),
        json!(task.clone()),
    );
    Ok(Json(json!({ "task": task })))
}

async fn delete_scheduled_task_by_id(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    delete_scheduled_task(&state.pool, &task_id).await?;
    publish_event(
        &state,
        "scheduled.task.updated",
        Some(task_id.clone()),
        json!({ "deleted": true, "task_id": task_id }),
    );
    Ok(Json(json!({ "ok": true })))
}

async fn run_scheduled_task_now(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = trigger_scheduled_task_now(state.clone(), &task_id)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;
    publish_event(
        &state,
        "scheduled.task.updated",
        Some(task.id.clone()),
        json!(task.clone()),
    );
    Ok(Json(json!({ "ok": true, "task": task })))
}

async fn create_task(
    State(state): State<AppState>,
    Json(payload): Json<CreateTaskRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = new_task(
        payload.name,
        payload.kind,
        payload.payload.unwrap_or_else(|| json!({})),
    );
    insert_task(&state.pool, &task).await?;
    publish_event(
        &state,
        "task.updated",
        Some(task.id.clone()),
        json!(task.clone()),
    );
    Ok(Json(json!({ "task": task })))
}

async fn get_task_by_id(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let task = get_task(&state.pool, &task_id).await?;
    Ok(Json(json!({ "task": task })))
}

async fn update_task(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
    Json(payload): Json<UpdateTaskRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let existing = get_task(&state.pool, &task_id).await?;
    let Some(mut task) = existing else {
        return Err(ApiError::NotFound(format!("task {task_id} not found")));
    };
    if let Some(name) = payload.name {
        task.name = name;
    }
    if let Some(status) = payload.status {
        task.status = status;
    }
    if let Some(new_payload) = payload.payload {
        task.payload = new_payload;
    }
    task.updated_at = Utc::now();

    cinerecord_storage::update_task_status(
        &state.pool,
        &task.id,
        task.status.clone(),
        task.payload.clone(),
    )
    .await?;
    publish_event(
        &state,
        "task.updated",
        Some(task.id.clone()),
        json!(task.clone()),
    );
    Ok(Json(json!({ "task": task })))
}

async fn delete_task_by_id(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<Json<serde_json::Value>, ApiError> {
    delete_task(&state.pool, &task_id).await?;
    publish_event(
        &state,
        "task.updated",
        Some(task_id.clone()),
        json!({ "deleted": true, "task_id": task_id }),
    );
    Ok(Json(json!({ "ok": true })))
}

async fn start_trakt_auth(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let result = start_trakt_device_auth(&config)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;
    publish_event(
        &state,
        "log",
        None,
        json!({
            "message": "Started Trakt device auth flow",
            "level": "info"
        }),
    );
    Ok(Json(json!({ "auth": result })))
}

async fn start_tmdb_auth_handler(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let result = start_tmdb_auth(&config)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;

    let mut next_config = config.clone();
    next_config.platforms.tmdb.request_token = result
        .get("request_token")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    save_config(&state.paths, &next_config).await?;
    *state.config.write().await = next_config;

    publish_event(
        &state,
        "log",
        None,
        json!({
            "message": "Started TMDB browser authorization flow",
            "level": "info"
        }),
    );
    Ok(Json(json!({ "auth": result })))
}

async fn complete_tmdb_auth_handler(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let result = complete_tmdb_auth(&config)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;

    let mut next_config = config.clone();
    next_config.platforms.tmdb.session_id = result
        .get("session_id")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    next_config.platforms.tmdb.account_id = result
        .get("account_id")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    next_config.platforms.tmdb.username = result
        .get("username")
        .and_then(|v| v.as_str())
        .map(ToOwned::to_owned);
    next_config.platforms.tmdb.request_token = None;
    save_config(&state.paths, &next_config).await?;
    *state.config.write().await = next_config;

    publish_event(
        &state,
        "platform.validated",
        None,
        json!({
            "platform": "tmdb",
            "success": true,
            "message": "TMDB authorization completed",
            "profile": result.get("profile").cloned()
        }),
    );

    Ok(Json(json!({ "result": result })))
}

async fn poll_trakt_auth(
    State(state): State<AppState>,
    Json(payload): Json<TraktDevicePollRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    let config = state.config.read().await.clone();
    let result = poll_trakt_device_auth(&config, &payload.device_code)
        .await
        .map_err(|error| ApiError::BadRequest(error.to_string()))?;
    if result.status == "success" {
        let mut next_config = config.clone();
        next_config.platforms.trakt.access_token = result.access_token.clone();
        next_config.platforms.trakt.refresh_token = result.refresh_token.clone();
        next_config.platforms.trakt.token_expires_at = result.token_expires;
        save_config(&state.paths, &next_config).await?;
        *state.config.write().await = next_config;
        publish_event(
            &state,
            "platform.validated",
            None,
            json!({
                "platform": "trakt",
                "success": true,
                "message": "Trakt OAuth authorization completed",
                "profile": result.profile
            }),
        );
    }
    Ok(Json(json!({ "result": result })))
}

async fn sse_events(
    State(state): State<AppState>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let stream = BroadcastStream::new(state.events.subscribe())
        .map(|message| match message {
            Ok(event) => {
                let data = serde_json::to_string(&event).unwrap_or_else(|_| "{}".to_string());
                Some(Ok(Event::default().event(event.event_type).data(data)))
            }
            Err(_) => None,
        })
        .filter_map(|item| item);

    Sse::new(stream).keep_alive(KeepAlive::default())
}

#[derive(Debug, Deserialize)]
struct CreateTaskRequest {
    pub name: String,
    pub kind: TaskKind,
    pub payload: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct UpdateTaskRequest {
    pub name: Option<String>,
    pub status: Option<TaskStatus>,
    pub payload: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct TraktDevicePollRequest {
    pub device_code: String,
}

#[derive(Debug, Deserialize)]
struct BrowserAuthCallbackRequest {
    pub platform: String,
    pub cookie: String,
    pub token: String,
}

#[derive(Debug, Deserialize)]
struct ProxyAvatarQuery {
    url: String,
}

#[derive(Debug, Deserialize)]
struct BookmarkletAuthRequest {
    pub platform: Option<String>,
    pub page_url: Option<String>,
    pub cookie: String,
}

#[derive(Debug, Default, Deserialize)]
struct CookieCloudSyncRequest {
    pub host: Option<String>,
    pub uuid: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct LibraryQuery {
    pub limit: Option<i64>,
    pub offset: Option<i64>,
    pub mode: Option<String>,
    pub view: Option<String>,
    pub platforms: Option<String>,
}

fn selected_library_platforms(query: &LibraryQuery) -> Vec<String> {
    query
        .platforms
        .as_deref()
        .unwrap_or("")
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn platforms_with_data(counts: &HashMap<String, i64>) -> Vec<String> {
    ["douban", "imdb", "trakt", "letterboxd", "tmdb"]
        .into_iter()
        .filter(|platform| counts.get(*platform).copied().unwrap_or_default() > 0)
        .map(ToOwned::to_owned)
        .collect()
}

#[derive(Debug, Default, Deserialize)]
struct ScheduledTaskLogsQuery {
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct FriendBackupRequest {
    pub user_id: String,
    #[serde(default = "default_true")]
    pub include_watched: bool,
    #[serde(default = "default_true")]
    pub include_wishlist: bool,
}

#[derive(Debug, Deserialize)]
struct ScheduledTaskUpsertRequest {
    pub name: String,
    pub source_platform: String,
    pub target_platform: String,
    pub schedule: String,
    pub recent_limit: Option<usize>,
    pub only_new: Option<bool>,
    pub overwrite: Option<bool>,
    pub default_rating: Option<f64>,
    pub paused: Option<bool>,
}

fn default_true() -> bool {
    true
}

fn validate_douban_user_id(value: &str) -> Result<String, ApiError> {
    let value = value.trim();
    if value.is_empty() {
        return Err(ApiError::BadRequest("请输入好友豆瓣 ID".to_string()));
    }
    if value.len() > 80
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
    {
        return Err(ApiError::BadRequest("豆瓣 ID 格式不正确".to_string()));
    }
    Ok(value.to_string())
}

#[derive(Debug)]
enum ApiError {
    Internal(anyhow::Error),
    BadRequest(String),
    NotFound(String),
}

impl From<anyhow::Error> for ApiError {
    fn from(value: anyhow::Error) -> Self {
        Self::Internal(value)
    }
}

impl From<serde_json::Error> for ApiError {
    fn from(value: serde_json::Error) -> Self {
        Self::BadRequest(value.to_string())
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        match self {
            ApiError::Internal(err) => (
                axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({ "error": err.to_string() })),
            )
                .into_response(),
            ApiError::BadRequest(message) => (
                axum::http::StatusCode::BAD_REQUEST,
                Json(json!({ "error": message })),
            )
                .into_response(),
            ApiError::NotFound(message) => (
                axum::http::StatusCode::NOT_FOUND,
                Json(json!({ "error": message })),
            )
                .into_response(),
        }
    }
}

fn new_task(name: String, kind: TaskKind, payload: serde_json::Value) -> SyncTask {
    SyncTask {
        id: Uuid::new_v4().to_string(),
        name,
        kind,
        status: TaskStatus::Pending,
        payload,
        created_at: Utc::now(),
        updated_at: Utc::now(),
    }
}

fn publish_event(
    state: &AppState,
    event_type: &str,
    task_id: Option<String>,
    payload: serde_json::Value,
) {
    let _ = state.events.send(AppEvent {
        event_type: event_type.to_string(),
        task_id,
        timestamp: Utc::now(),
        payload,
    });
}

async fn persist_cookie_login(
    state: &AppState,
    platform: &str,
    cookie: &str,
    from_bookmarklet: bool,
) -> Result<serde_json::Value, ApiError> {
    let existing_config = state.config.read().await.clone();
    let existing_user_id = match platform {
        "douban" => existing_config.platforms.douban.user_id.as_deref(),
        "imdb" => existing_config.platforms.imdb.user_id.as_deref(),
        _ => None,
    };
    let validation = validate_cookie_platform(platform, cookie, existing_user_id)
        .await
        .map_err(ApiError::Internal)?;

    if !validation.success {
        let error_message = if from_bookmarklet {
            bookmarklet_error_message(platform, &validation.message)
        } else {
            validation.message.clone()
        };
        return Ok(json!({
            "success": false,
            "error": error_message,
            "validation": validation
        }));
    }

    let user_id = validation
        .profile
        .as_ref()
        .and_then(|profile| profile.get("user_id"))
        .and_then(|value| value.as_str())
        .map(ToOwned::to_owned);

    let mut next_config = existing_config.clone();
    match platform {
        "douban" => {
            next_config.platforms.douban.cookie = Some(cookie.to_string());
            if user_id.is_some() {
                next_config.platforms.douban.user_id = user_id.clone();
            }
        }
        "imdb" => {
            next_config.platforms.imdb.cookie = Some(cookie.to_string());
            if user_id.is_some() {
                next_config.platforms.imdb.user_id = user_id.clone();
            }
        }
        _ => return Err(ApiError::BadRequest("unsupported platform".to_string())),
    }

    save_config(&state.paths, &next_config).await?;
    *state.config.write().await = next_config;
    upsert_platform_state(
        &state.pool,
        platform,
        true,
        Some(&validation.message),
        validation.profile.as_ref(),
    )
    .await?;

    publish_event(state, "platform.validated", None, json!(validation.clone()));
    publish_event(
        state,
        "log",
        None,
        json!({
            "message": format!("{} 登录已写回 CineRecord", platform.to_uppercase()),
            "level": "success",
            "platform": platform,
            "user_id": user_id
        }),
    );

    Ok(json!({
        "success": true,
        "platform": platform,
        "user_id": user_id,
        "validation": validation
    }))
}

fn detect_bookmarklet_platform(platform: Option<&str>, page_url: Option<&str>) -> Option<String> {
    if let Some(platform) = platform.map(str::trim).filter(|value| !value.is_empty()) {
        if matches!(platform, "douban" | "imdb") {
            return Some(platform.to_string());
        }
    }
    let url = page_url.unwrap_or_default().to_lowercase();
    if url.contains("douban.com") {
        return Some("douban".to_string());
    }
    if url.contains("imdb.com") {
        return Some("imdb".to_string());
    }
    None
}

fn bookmarklet_error_message(platform: &str, raw_message: &str) -> String {
    if raw_message.contains("缺少关键 Cookie") {
        return match platform {
            "imdb" => "这个书签拿不到 IMDb 的关键登录 Cookie（常见是 at-main / session-token）。这是浏览器限制，请改用 CookieCloud 或手动粘贴完整 Cookie。".to_string(),
            "douban" => "这个书签拿不到豆瓣的关键登录 Cookie（常见是 dbcl2）。这是浏览器限制，请改用 CookieCloud 或手动粘贴完整 Cookie。".to_string(),
            _ => raw_message.to_string(),
        };
    }
    raw_message.to_string()
}

fn render_bookmarklet_result_page(success: bool, message: &str) -> String {
    let (title, color) = if success {
        ("已连接到 CineRecord", "#10b981")
    } else {
        ("连接失败", "#ef4444")
    };
    format!(
        r#"<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin:0; min-height:100vh; display:grid; place-items:center; background:#111827; color:#f3f4f6; }}
    .card {{ width:min(92vw, 420px); padding:24px; border-radius:18px; background:#1f2937; border:1px solid rgba(255,255,255,0.08); }}
    .title {{ font-size:1.2rem; font-weight:700; margin-bottom:10px; color:{color}; }}
    .msg {{ line-height:1.6; color:#d1d5db; }}
    .tip {{ margin-top:14px; font-size:0.85rem; color:#9ca3af; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">{title}</div>
    <div class="msg">{message}</div>
    <div class="tip">这个窗口可以直接关闭。</div>
  </div>
  <script>setTimeout(function(){{ window.close(); }}, 1800);</script>
</body>
</html>"#,
        title = title,
        color = color,
        message = html_escape(message),
    )
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn render_bookmarklet_choose_page() -> String {
    r#"<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>选择目标网站</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin:0; min-height:100vh; display:grid; place-items:center; background:#111827; color:#f3f4f6; }
    .card { width:min(92vw, 440px); padding:28px; border-radius:20px; background:#1f2937; border:1px solid rgba(255,255,255,0.08); }
    h1 { margin:0 0 10px 0; font-size:1.25rem; }
    p { margin:0 0 18px 0; color:#d1d5db; line-height:1.6; }
    .actions { display:grid; gap:10px; }
    a { display:flex; align-items:center; justify-content:center; min-height:48px; border-radius:12px; text-decoration:none; font-weight:700; }
    .primary { background:#10b981; color:white; }
    .secondary { background:#f5c518; color:#111827; }
    .tip { margin-top:14px; font-size:0.84rem; color:#9ca3af; }
  </style>
</head>
<body>
  <div class="card">
    <h1>请先打开目标网站</h1>
    <p>这个书签需要在豆瓣或 IMDb 页面里点击，才能自动把登录 Cookie 发回 CineRecord。</p>
    <div class="actions">
      <a class="primary" href="https://www.douban.com/" target="_self">打开豆瓣</a>
      <a class="secondary" href="https://www.imdb.com/" target="_self">打开 IMDb</a>
    </div>
    <div class="tip">打开后保持登录，再次点击同一个书签即可。</div>
  </div>
</body>
</html>"#
        .to_string()
}

fn open_external_url(url: &str) -> bool {
    #[cfg(target_os = "macos")]
    {
        return Command::new("open").arg(url).status().is_ok();
    }
    #[cfg(target_os = "linux")]
    {
        return Command::new("xdg-open").arg(url).status().is_ok();
    }
    #[cfg(target_os = "windows")]
    {
        return Command::new("cmd")
            .args(["/C", "start", "", url])
            .status()
            .is_ok();
    }
    #[allow(unreachable_code)]
    false
}

fn build_scheduled_task(
    existing: Option<ScheduledTask>,
    payload: ScheduledTaskUpsertRequest,
) -> Result<ScheduledTask, ApiError> {
    if payload.source_platform == payload.target_platform {
        return Err(ApiError::BadRequest(
            "source and target platform cannot be the same".to_string(),
        ));
    }
    let now = Utc::now();
    let paused = payload
        .paused
        .unwrap_or_else(|| existing.as_ref().map(|task| task.paused).unwrap_or(false));
    let next_run_at = if paused {
        None
    } else {
        calculate_next_run_at(&payload.schedule, now)
            .map_err(|error| ApiError::BadRequest(error.to_string()))?
    };
    Ok(ScheduledTask {
        id: existing
            .as_ref()
            .map(|task| task.id.clone())
            .unwrap_or_else(|| Uuid::new_v4().to_string()),
        name: payload.name,
        source_platform: payload.source_platform,
        target_platform: payload.target_platform,
        schedule: payload.schedule,
        recent_limit: payload.recent_limit.unwrap_or_else(|| {
            existing
                .as_ref()
                .map(|task| task.recent_limit)
                .unwrap_or(100)
        }),
        only_new: payload
            .only_new
            .unwrap_or_else(|| existing.as_ref().map(|task| task.only_new).unwrap_or(true)),
        overwrite: payload.overwrite.unwrap_or_else(|| {
            existing
                .as_ref()
                .map(|task| task.overwrite)
                .unwrap_or(false)
        }),
        default_rating: payload
            .default_rating
            .or_else(|| existing.as_ref().and_then(|task| task.default_rating)),
        paused,
        running: false,
        last_run_at: existing.as_ref().and_then(|task| task.last_run_at),
        next_run_at,
        last_status_message: existing
            .as_ref()
            .and_then(|task| task.last_status_message.clone())
            .or_else(|| {
                next_run_at.map(|time| {
                    format!(
                        "下次执行：{}",
                        time.with_timezone(&chrono::Local)
                            .format("%Y-%m-%d %H:%M:%S")
                    )
                })
            }),
        created_at: existing.as_ref().map(|task| task.created_at).unwrap_or(now),
        updated_at: now,
    })
}
