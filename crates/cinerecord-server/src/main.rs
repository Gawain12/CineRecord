mod api;
mod scheduler;

use std::{collections::HashMap, io::Write, path::PathBuf, sync::Arc};

use anyhow::Result;
use axum::Router;
use chrono::{DateTime, Utc};
use cinerecord_core::{AppConfig, AppEvent};
use cinerecord_storage::{StoragePaths, connect, load_or_init_config};
use tokio::sync::{RwLock, broadcast};
use tower_http::{
    cors::{Any, CorsLayer},
    services::ServeDir,
    trace::TraceLayer,
};
use tracing::info;

#[derive(Clone)]
pub struct AppState {
    pub repo_root: PathBuf,
    pub paths: StoragePaths,
    pub config: Arc<RwLock<AppConfig>>,
    pub pool: sqlx::SqlitePool,
    pub events: broadcast::Sender<AppEvent>,
    pub auth_sessions: Arc<RwLock<HashMap<String, PendingBrowserAuth>>>,
}

#[derive(Clone, Debug)]
pub struct PendingBrowserAuth {
    pub platform: String,
    pub created_at: DateTime<Utc>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let repo_root = std::env::current_dir()?;
    let paths = StoragePaths::from_repo_root(&repo_root);
    init_tracing(&paths)?;
    let config = load_or_init_config(&paths).await?;
    let pool = connect(&paths).await?;
    let (event_tx, _) = broadcast::channel(512);
    let bind_addr = format!("{}:{}", config.app.host, config.app.port);
    append_bootstrap_log(
        &paths,
        &format!("Starting CineRecord server on http://{bind_addr}"),
    )?;

    let app_state = AppState {
        repo_root: repo_root.clone(),
        paths,
        config: Arc::new(RwLock::new(config.clone())),
        pool,
        events: event_tx,
        auth_sessions: Arc::new(RwLock::new(HashMap::new())),
    };

    scheduler::spawn_scheduler_loop(app_state.clone());

    let app = build_router(app_state);
    info!("Starting CineRecord server on http://{bind_addr}");

    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

fn build_router(state: AppState) -> Router {
    let static_dir = state.repo_root.join("web").join("static");
    Router::new()
        .merge(api::router())
        .nest_service("/static", ServeDir::new(static_dir))
        .layer(CorsLayer::new().allow_origin(Any).allow_headers(Any).allow_methods(Any))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

fn init_tracing(paths: &StoragePaths) -> Result<()> {
    std::fs::create_dir_all(paths.log_path.parent().expect("log dir must exist"))?;
    let file_appender = tracing_appender::rolling::never(
        paths.log_path.parent().expect("log dir must exist"),
        paths.log_path
            .file_name()
            .expect("log file name must exist"),
    );
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| "info,tower_http=info".into());
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_writer(file_appender)
        .with_ansi(false)
        .init();
    Ok(())
}

fn append_bootstrap_log(paths: &StoragePaths, message: &str) -> Result<()> {
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&paths.log_path)?;
    writeln!(
        file,
        "{} [bootstrap] {message}",
        chrono::Utc::now().to_rfc3339()
    )?;
    Ok(())
}
