//! Optional login gate for deployments reachable from other machines (Docker / NAS).
//!
//! Enabled by setting `CINERECORD_PASSWORD` (and optionally `CINERECORD_USERNAME`,
//! default `cinerecord`). Sessions live in memory, so a restart requires logging in again.

use std::{collections::HashSet, sync::Arc};

use axum::{
    Form,
    extract::{Request, State},
    http::{HeaderMap, StatusCode, header},
    middleware::Next,
    response::{Html, IntoResponse, Redirect, Response},
};
use serde::Deserialize;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::AppState;

const SESSION_COOKIE: &str = "cr_session";

pub struct ServerAuth {
    username: String,
    password: String,
    sessions: RwLock<HashSet<String>>,
}

impl ServerAuth {
    pub fn from_env() -> Option<Arc<Self>> {
        let password = std::env::var("CINERECORD_PASSWORD")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())?;
        let username = std::env::var("CINERECORD_USERNAME")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "cinerecord".to_string());
        Some(Arc::new(Self {
            username,
            password,
            sessions: RwLock::new(HashSet::new()),
        }))
    }

    async fn is_authenticated(&self, headers: &HeaderMap) -> bool {
        match session_cookie(headers) {
            Some(token) => self.sessions.read().await.contains(token),
            None => false,
        }
    }
}

fn session_cookie(headers: &HeaderMap) -> Option<&str> {
    headers
        .get_all(header::COOKIE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(';'))
        .filter_map(|pair| pair.trim().split_once('='))
        .find(|(name, _)| *name == SESSION_COOKIE)
        .map(|(_, value)| value)
}

/// Paths that must work without a session: the login page itself, static assets,
/// health checks, and the cross-site cookie callbacks posted from Douban / IMDb pages.
fn is_public_path(path: &str) -> bool {
    path == "/login"
        || path == "/favicon.ico"
        || path == "/api/v2/health"
        || path == "/api/v2/auth/callback"
        || path == "/api/v2/auth/bookmarklet/callback"
        || path == "/auth/bookmarklet/submit"
        || path.starts_with("/static/")
}

pub async fn require_login(State(state): State<AppState>, request: Request, next: Next) -> Response {
    let Some(auth) = state.server_auth.as_ref() else {
        return next.run(request).await;
    };
    if is_public_path(request.uri().path()) || auth.is_authenticated(request.headers()).await {
        return next.run(request).await;
    }
    if request.uri().path().starts_with("/api/") {
        return (StatusCode::UNAUTHORIZED, "login required").into_response();
    }
    Redirect::to("/login").into_response()
}

#[derive(Deserialize)]
pub struct LoginForm {
    username: String,
    password: String,
}

pub async fn login_page(State(state): State<AppState>) -> Response {
    if state.server_auth.is_none() {
        return Redirect::to("/").into_response();
    }
    Html(render_login_page(None, "")).into_response()
}

pub async fn login_submit(State(state): State<AppState>, Form(form): Form<LoginForm>) -> Response {
    let Some(auth) = state.server_auth.as_ref() else {
        return Redirect::to("/").into_response();
    };
    if !constant_time_eq(form.username.trim(), &auth.username)
        || !constant_time_eq(&form.password, &auth.password)
    {
        return (
            StatusCode::UNAUTHORIZED,
            Html(render_login_page(
                Some("用户名或密码错误 / Invalid username or password"),
                form.username.trim(),
            )),
        )
            .into_response();
    }
    let token = Uuid::new_v4().simple().to_string();
    auth.sessions.write().await.insert(token.clone());
    (
        [(
            header::SET_COOKIE,
            format!("{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"),
        )],
        Redirect::to("/"),
    )
        .into_response()
}

pub async fn logout(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if let (Some(auth), Some(token)) = (state.server_auth.as_ref(), session_cookie(&headers)) {
        auth.sessions.write().await.remove(token);
    }
    (
        [(
            header::SET_COOKIE,
            format!("{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"),
        )],
        Redirect::to("/login"),
    )
        .into_response()
}

fn html_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn constant_time_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn render_login_page(error: Option<&str>, username: &str) -> String {
    let username = html_escape(username);
    // Focus the field the user most likely needs to fill next.
    let (user_focus, pass_focus) = if username.is_empty() { (" autofocus", "") } else { ("", " autofocus") };
    let error_html = error
        .map(|message| format!(r#"<div class="error">{message}</div>"#))
        .unwrap_or_default();
    format!(
        r#"<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CineRecord 登录</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#0f1115; color:#e5e7eb; margin:0; }}
    .card {{ max-width:360px; margin:12vh auto; padding:28px; background:#171a21; border:1px solid #262b36; border-radius:14px; }}
    h1 {{ font-size:18px; margin:0 0 16px; }}
    label {{ display:block; font-size:12px; margin:12px 0 6px; color:#9ca3af; }}
    input {{ box-sizing:border-box; width:100%; padding:10px 12px; border-radius:8px; border:1px solid #333a48; background:#0f1115; color:#e5e7eb; font-size:14px; }}
    button {{ width:100%; margin-top:18px; padding:10px 12px; border:0; border-radius:8px; background:#4f7cff; color:#fff; font-weight:600; font-size:14px; cursor:pointer; }}
    .error {{ margin-top:14px; color:#fca5a5; font-size:12px; }}
  </style>
</head>
<body>
  <form class="card" method="post" action="/login">
    <h1>🔒 CineRecord</h1>
    <label for="username">用户名 / Username</label>
    <input id="username" name="username" autocomplete="username" value="{username}"{user_focus}>
    <label for="password">密码 / Password</label>
    <input id="password" type="password" name="password" autocomplete="current-password"{pass_focus}>
    <button type="submit">登录 / Sign in</button>
    {error_html}
  </form>
</body>
</html>"#
    )
}
