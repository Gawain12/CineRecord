use aes::Aes256;
use anyhow::{Context, Result, anyhow};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use cbc::cipher::{BlockDecryptMut, KeyIvInit, block_padding::Pkcs7};
use cinerecord_core::{AppConfig, CookiePlatformConfig, PlatformValidationResult};
use reqwest::Client;
use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;

type Aes256CbcDec = cbc::Decryptor<Aes256>;

pub const COOKIECLOUD_REQUIRED_DOUBAN: &[&str] = &["dbcl2"];
pub const COOKIECLOUD_ALLOWED_IMDB: &[&str] = &[
    "ubid-main",
    "at-main",
    "sess-at-main",
    "session-id",
    "session-id-time",
    "session-token",
    "x-main",
    "csm-hit",
    "uu",
    "lc-main",
];
pub const COOKIECLOUD_REQUIRED_IMDB: &[&str] = &["ubid-main", "at-main", "session-token"];

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudImportedPlatform {
    pub platform: String,
    pub matched_count: usize,
    pub cookie_names: Vec<String>,
    pub user_id: Option<String>,
    pub imported_without_validation: bool,
    pub validation: PlatformValidationResult,
}

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudSkippedPlatform {
    pub platform: String,
    pub matched_count: usize,
    pub cookie_names: Vec<String>,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CookieCloudSyncResult {
    pub imported: Vec<CookieCloudImportedPlatform>,
    pub skipped: Vec<CookieCloudSkippedPlatform>,
    pub missing: Vec<String>,
}

pub fn cookie_names_from_header(cookie_header: &str) -> Vec<String> {
    cookie_header
        .split(';')
        .filter_map(|part| part.split_once('=').map(|(name, _)| name.trim().to_string()))
        .filter(|name| !name.is_empty())
        .collect()
}

pub fn required_cookie_names(platform: &str) -> &'static [&'static str] {
    match platform {
        "douban" => COOKIECLOUD_REQUIRED_DOUBAN,
        "imdb" => COOKIECLOUD_REQUIRED_IMDB,
        _ => &[],
    }
}

pub fn allowed_cookie_names(platform: &str) -> Option<&'static [&'static str]> {
    match platform {
        "imdb" => Some(COOKIECLOUD_ALLOWED_IMDB),
        _ => None,
    }
}

pub fn platform_domain_keywords(platform: &str) -> Vec<&'static str> {
    match platform {
        "douban" => vec!["douban.com"],
        "imdb" => vec!["imdb.com"],
        _ => Vec::new(),
    }
}

pub fn normalize_cookiecloud_host(host: &str) -> Result<String> {
    let trimmed = host.trim().trim_end_matches('/');
    if trimmed.is_empty() {
        return Err(anyhow!("CookieCloud host cannot be empty"));
    }
    if trimmed.starts_with("http://") || trimmed.starts_with("https://") {
        Ok(trimmed.to_string())
    } else {
        Ok(format!("http://{trimmed}"))
    }
}

pub async fn request_cookiecloud_payload(
    host: &str,
    uuid: &str,
    password: &str,
) -> Result<Value> {
    let url = format!("{host}/get/{uuid}");
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;
    let response = client
        .get(&url)
        .header("User-Agent", "CineRecord/2.0")
        .send()
        .await
        .with_context(|| format!("failed to request CookieCloud at {url}"))?;

    let status = response.status();
    let body: Value = response
        .json()
        .await
        .with_context(|| format!("failed to parse CookieCloud response (HTTP {status})"))?;

    if let Some(encrypted_data) = body.get("encrypted").and_then(|v| v.as_str()) {
        let decrypted = decrypt_cookiecloud_data(encrypted_data, uuid, password)?;
        return serde_json::from_str(&decrypted).context("failed to parse decrypted CookieCloud JSON");
    }

    if body.get("cookie_data").is_some() {
        return Ok(body);
    }

    Err(anyhow!(
        "unexpected CookieCloud payload format (no 'encrypted' or 'cookie_data' field)"
    ))
}

pub fn decrypt_cookiecloud_data(
    encrypted_data: &str,
    uuid: &str,
    password: &str,
) -> Result<String> {
    let key_raw = format!("{uuid}-{password}");
    let key_md5 = format!("{:x}", md5::compute(key_raw.as_bytes()));
    let key_bytes = key_md5.as_bytes(); // 32 bytes ASCII hex

    let iv_raw = format!("{password}-{uuid}");
    let iv_md5 = format!("{:x}", md5::compute(iv_raw.as_bytes()));
    let iv_bytes = &iv_md5.as_bytes()[0..16]; // 16 bytes

    let ciphertext = BASE64
        .decode(encrypted_data)
        .context("invalid base64 encrypted data in CookieCloud")?;

    let mut buf = ciphertext;
    let cipher = Aes256CbcDec::new_from_slices(key_bytes, iv_bytes)
        .map_err(|e| anyhow!("invalid key/iv length for AES-256-CBC: {e}"))?;

    let decrypted = cipher
        .decrypt_padded_mut::<Pkcs7>(&mut buf)
        .map_err(|e| anyhow!("failed to decrypt CookieCloud data (wrong password?): {e}"))?;

    String::from_utf8(decrypted.to_vec()).context("decrypted CookieCloud data is not valid UTF-8")
}

pub fn extract_cookie_data(payload: &Value) -> Result<HashMap<String, Vec<Value>>> {
    if let Some(cookie_data) = payload.get("cookie_data").and_then(|v| v.as_object()) {
        let mut map = HashMap::new();
        for (domain, items) in cookie_data {
            if let Some(arr) = items.as_array() {
                map.insert(domain.clone(), arr.clone());
            }
        }
        return Ok(map);
    }
    Err(anyhow!("cookie_data is missing or not an object"))
}

pub fn build_cookie_header(
    cookie_data: &HashMap<String, Vec<Value>>,
    domain_keywords: &[&str],
    allowed_names: Option<&[&str]>,
) -> (String, usize) {
    let mut cookies = HashMap::new();
    for (domain, items) in cookie_data {
        let matches_domain = domain_keywords
            .iter()
            .any(|kw| domain.contains(kw));
        if !matches_domain {
            continue;
        }
        for item in items {
            let name = item.get("name").and_then(|v| v.as_str());
            let value = item.get("value").and_then(|v| v.as_str());
            if let (Some(name), Some(value)) = (name, value) {
                if let Some(allowed) = allowed_names {
                    if !allowed.contains(&name) {
                        continue;
                    }
                }
                cookies.insert(name.to_string(), value.to_string());
            }
        }
    }

    let count = cookies.len();
    let header_str = cookies
        .iter()
        .map(|(k, v)| format!("{k}={v}"))
        .collect::<Vec<_>>()
        .join("; ");

    (header_str, count)
}

pub async fn validate_cookie_platform(
    platform: &str,
    cookie: &str,
    existing_user_id: Option<&str>,
) -> Result<PlatformValidationResult> {
    let cfg = CookiePlatformConfig {
        user_id: existing_user_id.map(ToOwned::to_owned),
        cookie: Some(cookie.to_string()),
    };
    match platform {
        "douban" => crate::douban::validate_douban_cookie(&cfg).await,
        "imdb" => crate::imdb::validate_imdb_cookie(&cfg).await,
        other => Err(anyhow!("unsupported cookie platform: {other}")),
    }
}

pub fn current_platform_cookie_config<'a>(
    config: &'a AppConfig,
    platform: &str,
) -> &'a CookiePlatformConfig {
    match platform {
        "douban" => &config.platforms.douban,
        "imdb" => &config.platforms.imdb,
        _ => panic!("unsupported cookie platform {platform}"),
    }
}

pub fn current_platform_cookie_config_mut<'a>(
    config: &'a mut AppConfig,
    platform: &str,
) -> Result<&'a mut CookiePlatformConfig> {
    match platform {
        "douban" => Ok(&mut config.platforms.douban),
        "imdb" => Ok(&mut config.platforms.imdb),
        _ => Err(anyhow!("unsupported cookie platform {platform}")),
    }
}
