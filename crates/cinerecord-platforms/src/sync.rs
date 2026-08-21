use anyhow::{Result, bail};
use cinerecord_core::{
    AppConfig, SyncExecuteResult, SyncExecutionItem, SyncPreviewItem, SyncPreviewResult,
};
use serde_json::json;

use crate::{
    douban::sync_item_to_douban,
    imdb::sync_item_to_imdb,
    preview::format_rating,
    tmdb::{sync_item_to_tmdb, tmdb_client},
    trakt::{sync_item_to_trakt, trakt_client},
};

pub async fn execute_sync_with_progress<F>(
    config: &AppConfig,
    preview: &SyncPreviewResult,
    mut on_progress: F,
) -> Result<SyncExecuteResult>
where
    F: FnMut(serde_json::Value),
{
    let target = preview
        .direction
        .split("-to-")
        .nth(1)
        .unwrap_or_default()
        .to_string();

    let mut items = Vec::new();
    let mut success_count = 0usize;
    let mut failed_count = 0usize;
    let mut skipped_count = 0usize;

    let candidates: Vec<&SyncPreviewItem> = preview
        .items
        .iter()
        .filter(|item| item.action != "skip" && item.reason.is_none())
        .collect();
    let total_candidates = candidates.len();

    let tmdb = if target == "tmdb" {
        Some(tmdb_client(&config.platforms.tmdb)?)
    } else {
        None
    };

    let trakt = if target == "trakt" {
        Some(trakt_client(&config.platforms.trakt)?)
    } else {
        None
    };

    let mut current_idx = 0usize;

    for item in &preview.items {
        if item.action == "skip" || item.reason.is_some() {
            skipped_count += 1;
            items.push(skipped_item(item, item.reason.clone()));
            continue;
        }

        current_idx += 1;
        let year_str = item.year.map(|y: i32| y.to_string()).unwrap_or_else(|| "-".to_string());
        on_progress(json!({
            "phase": "executing",
            "current": current_idx,
            "total": total_candidates,
            "title": item.title,
            "year": item.year,
            "rating": item.source_rating,
            "message": format!(
                "[{current_idx}/{total_candidates}] 正在同步《{}》 ({year_str}) 评分: {}",
                item.title,
                format_rating(item.source_rating)
            )
        }));

        let result = match target.as_str() {
            "tmdb" => sync_item_to_tmdb(tmdb.as_ref().unwrap(), item).await,
            "trakt" => sync_item_to_trakt(trakt.as_ref().unwrap(), item).await,
            "imdb" => sync_item_to_imdb(&config.platforms.imdb, item).await,
            "douban" => sync_item_to_douban(&config.platforms.douban, item).await,
            other => bail!("unsupported sync target: {other}"),
        };

        match result {
            Ok(exec_item) => {
                success_count += 1;
                items.push(exec_item);
            }
            Err(e) => {
                let msg = e.to_string();
                failed_count += 1;
                items.push(failed_item(item, msg));
            }
        }

        // Rate limiting sleeps
        if target == "douban" {
            tokio::time::sleep(std::time::Duration::from_millis(6000)).await;
        } else if target == "imdb" {
            tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
        }
    }

    Ok(SyncExecuteResult {
        direction: preview.direction.clone(),
        success_count,
        failed_count,
        skipped_count,
        items,
    })
}

pub fn skipped_item(item: &SyncPreviewItem, reason: Option<String>) -> SyncExecutionItem {
    SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.target_linking_id.clone(),
        target_url: None,
        status: "skipped".to_string(),
        reason,
    }
}

pub fn failed_item(item: &SyncPreviewItem, reason: String) -> SyncExecutionItem {
    SyncExecutionItem {
        title: item.title.clone(),
        year: item.year,
        source_rating: item.source_rating,
        source_url: item.source_url.clone(),
        target_linking_id: item.target_linking_id.clone(),
        target_url: None,
        status: "failed".to_string(),
        reason: Some(reason),
    }
}
