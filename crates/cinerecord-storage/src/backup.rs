use anyhow::{Result, bail};
use chrono::{DateTime, Utc};
use cinerecord_core::{MovieRecord, WishlistRecord};
use serde::{Deserialize, Serialize};
use tokio::fs;

use crate::StoragePaths;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriendBackup {
    pub id: String,
    pub platform: String,
    pub user_id: String,
    pub watched: Vec<MovieRecord>,
    pub wishlist: Vec<WishlistRecord>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FriendBackupSummary {
    pub id: String,
    pub platform: String,
    pub user_id: String,
    pub watched_count: usize,
    pub wishlist_count: usize,
    pub created_at: DateTime<Utc>,
}

impl From<&FriendBackup> for FriendBackupSummary {
    fn from(value: &FriendBackup) -> Self {
        Self {
            id: value.id.clone(),
            platform: value.platform.clone(),
            user_id: value.user_id.clone(),
            watched_count: value.watched.len(),
            wishlist_count: value.wishlist.len(),
            created_at: value.created_at,
        }
    }
}

pub async fn save_friend_backup(paths: &StoragePaths, backup: &FriendBackup) -> Result<()> {
    paths.ensure_dirs().await?;
    validate_backup_id(&backup.id)?;
    let content = serde_json::to_vec_pretty(backup)?;
    fs::write(
        paths.backups_dir.join(format!("{}.json", backup.id)),
        content,
    )
    .await?;
    Ok(())
}

pub async fn list_friend_backups(paths: &StoragePaths) -> Result<Vec<FriendBackupSummary>> {
    paths.ensure_dirs().await?;
    let mut entries = fs::read_dir(&paths.backups_dir).await?;
    let mut backups = Vec::new();
    while let Some(entry) = entries.next_entry().await? {
        if entry.path().extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let content = fs::read(entry.path()).await?;
        if let Ok(backup) = serde_json::from_slice::<FriendBackup>(&content) {
            backups.push(FriendBackupSummary::from(&backup));
        }
    }
    backups.sort_by(|left, right| right.created_at.cmp(&left.created_at));
    Ok(backups)
}

pub async fn get_friend_backup(
    paths: &StoragePaths,
    backup_id: &str,
) -> Result<Option<FriendBackup>> {
    validate_backup_id(backup_id)?;
    let path = paths.backups_dir.join(format!("{backup_id}.json"));
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read(path).await?;
    Ok(Some(serde_json::from_slice(&content)?))
}

pub async fn delete_friend_backup(paths: &StoragePaths, backup_id: &str) -> Result<bool> {
    validate_backup_id(backup_id)?;
    let path = paths.backups_dir.join(format!("{backup_id}.json"));
    if !path.exists() {
        return Ok(false);
    }
    fs::remove_file(path).await?;
    Ok(true)
}

fn validate_backup_id(backup_id: &str) -> Result<()> {
    if backup_id.is_empty()
        || !backup_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-')
    {
        bail!("invalid backup id");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use cinerecord_core::MovieIdentifiers;
    use uuid::Uuid;

    #[tokio::test]
    async fn friend_backup_round_trip_and_delete() {
        let root = std::env::temp_dir().join(format!("cinerecord-backup-test-{}", Uuid::new_v4()));
        let paths = StoragePaths::from_repo_root(&root);
        let backup = FriendBackup {
            id: Uuid::new_v4().to_string(),
            platform: "douban".to_string(),
            user_id: "friend-test".to_string(),
            watched: vec![MovieRecord {
                id: "douban:1".to_string(),
                platform: "douban".to_string(),
                title: "Test Movie".to_string(),
                year: Some(2026),
                rating: Some(8.0),
                rated_at: None,
                external_id: Some("1".to_string()),
                source_url: None,
                identifiers: MovieIdentifiers::default(),
                raw_json: serde_json::json!({}),
            }],
            wishlist: Vec::new(),
            created_at: Utc::now(),
        };

        save_friend_backup(&paths, &backup).await.unwrap();
        let summaries = list_friend_backups(&paths).await.unwrap();
        assert_eq!(summaries.len(), 1);
        assert_eq!(summaries[0].watched_count, 1);
        assert_eq!(
            get_friend_backup(&paths, &backup.id)
                .await
                .unwrap()
                .unwrap()
                .user_id,
            "friend-test"
        );
        assert!(delete_friend_backup(&paths, &backup.id).await.unwrap());
        assert!(
            get_friend_backup(&paths, &backup.id)
                .await
                .unwrap()
                .is_none()
        );
        let _ = fs::remove_dir_all(root).await;
    }
}
