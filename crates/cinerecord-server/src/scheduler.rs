use std::{str::FromStr, time::Duration};

use anyhow::{Context, Result};
use chrono::Utc;
use cinerecord_core::{AppEvent, ScheduledTask};
use cinerecord_jobs::run_scheduled_sync_task;
use cinerecord_storage::{claim_due_scheduled_tasks, get_scheduled_task, mark_scheduled_task_idle, start_scheduled_task_run};
use cron::Schedule;
use serde_json::json;
use tokio::time::sleep;

use crate::AppState;

pub fn spawn_scheduler_loop(state: AppState) {
    tokio::spawn(async move {
        loop {
            if let Err(error) = process_due_tasks(state.clone()).await {
                let _ = state.events.send(AppEvent {
                    event_type: "scheduled.task.log".to_string(),
                    task_id: None,
                    timestamp: Utc::now(),
                    payload: json!({
                        "task_name": "scheduler",
                        "log_type": "error",
                        "message": format!("调度器轮询失败: {error}")
                    }),
                });
            }
            sleep(Duration::from_secs(15)).await;
        }
    });
}

pub fn calculate_next_run_at(expr: &str, from: chrono::DateTime<Utc>) -> Result<Option<chrono::DateTime<Utc>>> {
    let normalized = normalize_cron_expression(expr);
    let schedule = Schedule::from_str(&normalized).with_context(|| format!("invalid cron expression: {expr}"))?;
    Ok(schedule.upcoming(Utc).find(|next| *next > from))
}

fn normalize_cron_expression(expr: &str) -> String {
    let parts = expr.split_whitespace().collect::<Vec<_>>();
    if parts.len() == 5 {
        format!("0 {}", parts.join(" "))
    } else {
        expr.trim().to_string()
    }
}

async fn process_due_tasks(state: AppState) -> Result<()> {
    let due_tasks = claim_due_scheduled_tasks(&state.pool, Utc::now()).await?;
    for task in due_tasks {
        let state = state.clone();
        tokio::spawn(async move {
            if let Err(error) = run_one_scheduled_task(state, task).await {
                tracing::error!("scheduled task failed: {error}");
            }
        });
    }
    Ok(())
}

pub async fn trigger_scheduled_task_now(state: AppState, task_id: &str) -> Result<ScheduledTask> {
    let task = get_scheduled_task(&state.pool, task_id)
        .await?
        .with_context(|| format!("scheduled task {task_id} not found"))?;
    if task.paused {
        anyhow::bail!("paused task cannot be run until re-enabled");
    }
    if !start_scheduled_task_run(&state.pool, &task.id).await? {
        anyhow::bail!("scheduled task is already running");
    }

    let running_task = ScheduledTask {
        running: true,
        ..task
    };
    let state_for_run = state.clone();
    let task_for_run = running_task.clone();
    tokio::spawn(async move {
        if let Err(error) = run_one_scheduled_task(state_for_run, task_for_run).await {
            tracing::error!("manual scheduled task run failed: {error}");
        }
    });

    Ok(running_task)
}

async fn run_one_scheduled_task(state: AppState, task: ScheduledTask) -> Result<()> {
    let config = state.config.read().await.clone();
    let now = Utc::now();
    let next_run = match calculate_next_run_at(&task.schedule, now) {
        Ok(next) => next,
        Err(error) => {
            let message = format!("Cron 无法解析，任务已暂停: {error}");
            mark_scheduled_task_idle(&state.pool, &task.id, true, None, Some(&message)).await?;
            let _ = state.events.send(AppEvent {
                event_type: "scheduled.task.updated".to_string(),
                task_id: Some(task.id.clone()),
                timestamp: Utc::now(),
                payload: json!({
                    "id": task.id,
                    "paused": true,
                    "running": false,
                    "last_status_message": message
                }),
            });
            return Ok(());
        }
    };

    let _ = run_scheduled_sync_task(&state.pool, &state.events, &config, &task, next_run).await;
    Ok(())
}
