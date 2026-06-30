#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

mod api;
mod scheduler;

use std::{collections::HashMap, env, io::Write, path::PathBuf, sync::Arc};

use anyhow::Result;
use axum::{
    Router,
    extract::Path,
    http::{StatusCode, header},
    response::{IntoResponse, Response},
    routing::get,
};
use chrono::{DateTime, Utc};
use cinerecord_core::{AppConfig, AppEvent};
use cinerecord_storage::{StoragePaths, connect, load_or_init_config};
use tokio::sync::{RwLock, broadcast};
use tower_http::{
    cors::{Any, CorsLayer},
    trace::TraceLayer,
};
use tracing::info;

mod embedded_assets {
    include!(concat!(env!("OUT_DIR"), "/embedded_assets.rs"));
}

#[derive(Clone)]
pub struct AppState {
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
    let app_home = resolve_app_home()?;
    let paths = StoragePaths::from_repo_root(&app_home);
    init_tracing(&paths)?;
    let config = load_or_init_config(&paths).await?;
    let host = env::var("CINERECORD_HOST").unwrap_or_else(|_| config.app.host.clone());
    let port = env::var("CINERECORD_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(config.app.port);
    let bind_addr = format!("{host}:{port}");

    #[cfg(target_os = "windows")]
    let browser_url = format!("http://127.0.0.1:{port}");
    #[cfg(target_os = "windows")]
    if !env_flag("CINERECORD_NO_BROWSER") && server_is_ready(&browser_url).await {
        open_browser(&browser_url)?;
        return Ok(());
    }

    let pool = connect(&paths).await?;
    let (event_tx, _) = broadcast::channel(512);
    append_bootstrap_log(
        &paths,
        &format!(
            "Starting CineRecord server on http://{bind_addr} (home: {})",
            app_home.display()
        ),
    )?;

    let app_state = AppState {
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

    #[cfg(target_os = "windows")]
    if !env_flag("CINERECORD_NO_BROWSER") {
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(350)).await;
            if server_is_ready(&browser_url).await {
                let _ = open_browser(&browser_url);
            }
        });
    }

    axum::serve(listener, app).await?;
    Ok(())
}

#[cfg(target_os = "windows")]
async fn server_is_ready(url: &str) -> bool {
    let Ok(client) = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(1))
        .build()
    else {
        return false;
    };
    client
        .get(format!("{url}/api/v2/health"))
        .send()
        .await
        .is_ok_and(|response| response.status().is_success())
}

#[cfg(target_os = "windows")]
fn open_browser(url: &str) -> Result<()> {
    use std::os::windows::process::CommandExt;
    use std::process::{Command, Stdio};

    const CREATE_NO_WINDOW: u32 = 0x08000000;
    Command::new("cmd")
        .args(["/C", "start", "", url])
        .creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    Ok(())
}

fn build_router(state: AppState) -> Router {
    Router::new()
        .merge(api::router())
        .route("/static/{*path}", get(static_asset))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_headers(Any)
                .allow_methods(Any),
        )
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

async fn static_asset(Path(path): Path<String>) -> Response {
    match embedded_assets::get(path.trim_start_matches('/')) {
        Some((bytes, content_type)) => (
            StatusCode::OK,
            [
                (header::CONTENT_TYPE, content_type),
                (header::CACHE_CONTROL, "no-cache, must-revalidate"),
            ],
            bytes,
        )
            .into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

fn resolve_app_home() -> Result<PathBuf> {
    if let Some(path) = non_empty_env("CINERECORD_HOME") {
        return Ok(PathBuf::from(path));
    }

    let current_dir = env::current_dir()?;
    if env_flag("CINERECORD_PORTABLE")
        || current_dir
            .join("config")
            .join("v2")
            .join("config.toml")
            .exists()
        || (current_dir.join("Cargo.toml").exists() && current_dir.join("web").exists())
    {
        return Ok(current_dir);
    }

    #[cfg(target_os = "macos")]
    if let Some(home) = non_empty_env("HOME") {
        return Ok(PathBuf::from(home)
            .join("Library")
            .join("Application Support")
            .join("CineRecord"));
    }

    #[cfg(target_os = "windows")]
    if let Some(app_data) = non_empty_env("APPDATA").or_else(|| non_empty_env("LOCALAPPDATA")) {
        return Ok(PathBuf::from(app_data).join("CineRecord"));
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        if let Some(data_home) = non_empty_env("XDG_DATA_HOME") {
            return Ok(PathBuf::from(data_home).join("cinerecord"));
        }
        if let Some(home) = non_empty_env("HOME") {
            return Ok(PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("cinerecord"));
        }
    }

    Ok(current_dir.join("CineRecordData"))
}

fn non_empty_env(key: &str) -> Option<String> {
    env::var(key).ok().filter(|value| !value.trim().is_empty())
}

fn env_flag(key: &str) -> bool {
    non_empty_env(key).is_some_and(|value| {
        matches!(
            value.to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    })
}

fn init_tracing(paths: &StoragePaths) -> Result<()> {
    std::fs::create_dir_all(paths.log_path.parent().expect("log dir must exist"))?;
    let file_appender = tracing_appender::rolling::never(
        paths.log_path.parent().expect("log dir must exist"),
        paths
            .log_path
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
