use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{OnceLock, RwLock},
};

static DOUBAN_IMDB_CACHE: OnceLock<RwLock<IdMappingCache>> = OnceLock::new();

#[derive(Debug, Default)]
pub struct IdMappingCache {
    douban_to_imdb: HashMap<String, String>,
    imdb_to_douban: HashMap<String, String>,
    imdb_to_tmdb: HashMap<String, String>,
    tmdb_to_imdb: HashMap<String, String>,
    douban_to_tmdb: HashMap<String, String>,
    tmdb_to_douban: HashMap<String, String>,
    #[allow(dead_code)]
    loaded_path: Option<PathBuf>,
}

impl IdMappingCache {
    pub fn load_from_dir(dir: &Path) -> Self {
        let candidates = [
            dir.join("db_imdb_tmdb.csv"),
            dir.join("data").join("db_imdb_tmdb.csv"),
            dir.parent().map(|p| p.join("db_imdb_tmdb.csv")).unwrap_or_default(),
            dir.parent().map(|p| p.join("data").join("db_imdb_tmdb.csv")).unwrap_or_default(),
            PathBuf::from("data/db_imdb_tmdb.csv"),
            PathBuf::from("./data/db_imdb_tmdb.csv"),
            dir.join("db_imdb.csv"),
            dir.join("data").join("db_imdb.csv"),
            dir.parent().map(|p| p.join("db_imdb.csv")).unwrap_or_default(),
            dir.parent().map(|p| p.join("data").join("db_imdb.csv")).unwrap_or_default(),
            PathBuf::from("data/db_imdb.csv"),
            PathBuf::from("./data/db_imdb.csv"),
        ];
        for path in &candidates {
            if !path.as_os_str().is_empty() && path.exists() {
                return Self::load_from_file(path);
            }
        }
        Self::load_from_file(&dir.join("db_imdb_tmdb.csv"))
    }

    pub fn load_from_file(path: &Path) -> Self {
        let mut douban_to_imdb = HashMap::new();
        let mut imdb_to_douban = HashMap::new();
        let mut imdb_to_tmdb = HashMap::new();
        let mut tmdb_to_imdb = HashMap::new();
        let mut douban_to_tmdb = HashMap::new();
        let mut tmdb_to_douban = HashMap::new();

        if path.exists() {
            if let Ok(mut reader) = csv::ReaderBuilder::new().has_headers(true).from_path(path) {
                let headers = reader.headers().cloned().unwrap_or_default();
                let douban_idx = headers.iter().position(|h| h == "douban_id" || h == "douban");
                let imdb_idx = headers.iter().position(|h| h == "imdb" || h == "imdb_id");
                let tmdb_idx = headers.iter().position(|h| h == "tmdb" || h == "tmdb_id");

                let mut record = csv::StringRecord::new();
                while reader.read_record(&mut record).unwrap_or(false) {
                    let douban_id = douban_idx.and_then(|i| record.get(i)).map(|s| s.trim()).unwrap_or("");
                    let imdb_id = imdb_idx.and_then(|i| record.get(i)).map(|s| s.trim()).unwrap_or("");
                    let tmdb_id = tmdb_idx.and_then(|i| record.get(i)).map(|s| s.trim()).unwrap_or("");

                    if !douban_id.is_empty() && !imdb_id.is_empty() {
                        imdb_to_douban.entry(imdb_id.to_string()).or_insert_with(|| douban_id.to_string());
                        douban_to_imdb.entry(douban_id.to_string()).or_insert_with(|| imdb_id.to_string());
                    }
                    if !imdb_id.is_empty() && !tmdb_id.is_empty() {
                        imdb_to_tmdb.entry(imdb_id.to_string()).or_insert_with(|| tmdb_id.to_string());
                        tmdb_to_imdb.entry(tmdb_id.to_string()).or_insert_with(|| imdb_id.to_string());
                    }
                    if !douban_id.is_empty() && !tmdb_id.is_empty() {
                        douban_to_tmdb.entry(douban_id.to_string()).or_insert_with(|| tmdb_id.to_string());
                        tmdb_to_douban.entry(tmdb_id.to_string()).or_insert_with(|| douban_id.to_string());
                    }
                }
            }
        }

        Self {
            douban_to_imdb,
            imdb_to_douban,
            imdb_to_tmdb,
            tmdb_to_imdb,
            douban_to_tmdb,
            tmdb_to_douban,
            loaded_path: Some(path.to_path_buf()),
        }
    }

    pub fn get_imdb_by_douban(&self, douban_id: &str) -> Option<String> {
        self.douban_to_imdb.get(douban_id).cloned()
    }

    pub fn get_douban_by_imdb(&self, imdb_id: &str) -> Option<String> {
        self.imdb_to_douban.get(imdb_id).cloned()
    }

    pub fn get_tmdb_by_imdb(&self, imdb_id: &str) -> Option<String> {
        self.imdb_to_tmdb.get(imdb_id).cloned()
    }

    pub fn get_imdb_by_tmdb(&self, tmdb_id: &str) -> Option<String> {
        self.tmdb_to_imdb.get(tmdb_id).cloned()
    }

    pub fn get_tmdb_by_douban(&self, douban_id: &str) -> Option<String> {
        self.douban_to_tmdb.get(douban_id).cloned()
    }

    pub fn get_douban_by_tmdb(&self, tmdb_id: &str) -> Option<String> {
        self.tmdb_to_douban.get(tmdb_id).cloned()
    }
}

fn global_cache() -> &'static RwLock<IdMappingCache> {
    DOUBAN_IMDB_CACHE.get_or_init(|| {
        let default_path = std::env::current_dir()
            .ok()
            .map(|cwd| cwd.join("data").join("db_imdb_tmdb.csv"))
            .filter(|p| p.exists())
            .unwrap_or_else(|| {
                std::env::current_dir()
                    .ok()
                    .map(|cwd| cwd.join("data").join("db_imdb.csv"))
                    .unwrap_or_else(|| PathBuf::from("data/db_imdb.csv"))
            });
        RwLock::new(IdMappingCache::load_from_file(&default_path))
    })
}

/// Explicitly initialize or reload cache with a known storage data directory.
pub fn init_id_mapping_cache(data_dir: &Path) {
    let new_cache = IdMappingCache::load_from_dir(data_dir);
    if let Ok(mut lock) = global_cache().write() {
        *lock = new_cache;
    }
}

pub fn lookup_cached_imdb_for_douban(douban_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_imdb_by_douban(douban_id))
}

pub fn lookup_cached_douban_for_imdb(imdb_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_douban_by_imdb(imdb_id))
}

pub fn lookup_cached_tmdb_for_imdb(imdb_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_tmdb_by_imdb(imdb_id))
}

pub fn lookup_cached_imdb_for_tmdb(tmdb_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_imdb_by_tmdb(tmdb_id))
}

pub fn lookup_cached_tmdb_for_douban(douban_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_tmdb_by_douban(douban_id))
}

pub fn lookup_cached_douban_for_tmdb(tmdb_id: &str) -> Option<String> {
    global_cache()
        .read()
        .ok()
        .and_then(|cache| cache.get_douban_by_tmdb(tmdb_id))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn id_mapping_cache_bidirectional() {
        let temp_dir = std::env::temp_dir().join(format!("test_cache_{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&temp_dir).unwrap();
        let csv_path = temp_dir.join("db_imdb.csv");

        let content = "douban_id,imdb\n1292052,tt0111161\n1291546,tt0133093\n";
        std::fs::write(&csv_path, content).unwrap();

        let cache = IdMappingCache::load_from_file(&csv_path);
        assert_eq!(
            cache.get_imdb_by_douban("1292052"),
            Some("tt0111161".to_string())
        );
        assert_eq!(
            cache.get_douban_by_imdb("tt0111161"),
            Some("1292052".to_string())
        );
        assert_eq!(
            cache.get_imdb_by_douban("1291546"),
            Some("tt0133093".to_string())
        );
        assert_eq!(
            cache.get_douban_by_imdb("tt0133093"),
            Some("1291546".to_string())
        );
        assert_eq!(cache.get_imdb_by_douban("unknown"), None);
        assert_eq!(cache.get_douban_by_imdb("unknown"), None);

        let _ = std::fs::remove_dir_all(temp_dir);
    }
}
