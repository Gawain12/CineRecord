use std::{
    env, fs,
    path::{Path, PathBuf},
};

fn main() {
    let manifest_dir =
        PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR missing"));
    let static_dir = manifest_dir.join("../../web/static");
    println!("cargo:rerun-if-changed={}", static_dir.display());
    configure_windows_resources(&manifest_dir);

    let mut files = Vec::new();
    collect_files(&static_dir, &static_dir, &mut files);
    files.sort_by(|left, right| left.0.cmp(&right.0));

    let mut generated = String::from(
        "pub fn get(path: &str) -> Option<(&'static [u8], &'static str)> {\n    match path {\n",
    );
    for (relative, absolute) in files {
        generated.push_str(&format!(
            "        {relative:?} => Some((include_bytes!({absolute:?}), {mime:?})),\n",
            relative = relative,
            absolute = absolute.to_string_lossy(),
            mime = mime_type(&absolute),
        ));
    }
    generated.push_str("        _ => None,\n    }\n}\n");

    let output =
        PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR missing")).join("embedded_assets.rs");
    fs::write(output, generated).expect("failed writing embedded assets");
}

fn configure_windows_resources(manifest_dir: &Path) {
    if env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }

    let icon = manifest_dir.join("../../packaging/CineRecordIcon.ico");
    println!("cargo:rerun-if-changed={}", icon.display());

    winresource::WindowsResource::new()
        .set_icon(icon.to_str().expect("Windows icon path is not valid UTF-8"))
        .set("ProductName", "CineRecord")
        .set(
            "FileDescription",
            "CineRecord movie library and sync client",
        )
        .set("OriginalFilename", "CineRecord.exe")
        .set("LegalCopyright", "CineRecord Contributors")
        .compile()
        .expect("failed compiling Windows executable resources");
}

fn collect_files(root: &Path, directory: &Path, files: &mut Vec<(String, PathBuf)>) {
    let entries = fs::read_dir(directory).expect("failed reading static directory");
    for entry in entries {
        let path = entry.expect("failed reading static entry").path();
        if path.is_dir() {
            collect_files(root, &path, files);
            continue;
        }
        if path.extension().and_then(|value| value.to_str()) == Some("bak") {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .expect("static path outside root")
            .to_string_lossy()
            .replace('\\', "/");
        files.push((relative, path));
    }
}

fn mime_type(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
    {
        "css" => "text/css; charset=utf-8",
        "js" => "text/javascript; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "png" => "image/png",
        "svg" => "image/svg+xml",
        "ico" => "image/x-icon",
        "webp" => "image/webp",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        _ => "application/octet-stream",
    }
}
