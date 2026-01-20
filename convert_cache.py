#!/usr/bin/env python3
import json
import re

# 读取 Node 缓存
with open('scrapers/letterboxd-csv-imdb-tmdb-mapper/cache/cache.json', 'r') as f:
    node_cache = json.load(f)

# 构建 Title+Year -> IDs 映射 (从 Node 缓存)
title_year_to_ids = {}
for node_key, node_value in node_cache.items():
    parts = node_key.split('|:|')
    if len(parts) >= 2:
        title = parts[0].strip()
        year = parts[1].strip()
        key = f"{title}|:|{year}"
        
        value_parts = node_value.split('|')
        if len(value_parts) >= 3:
            title_year_to_ids[key] = {
                'tmdb_id': value_parts[1],
                'imdb_id': value_parts[2]
            }

print(f"从 Node 缓存读取 {len(title_year_to_ids)} 条 ID 映射")

# 读取 diary.csv，用 Title+Year 匹配，建立 URI -> IDs 映射
mapper_cache = {}
matched = 0
with open('diary.csv', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for line in lines[1:]:  # 跳过表头
        parts = line.strip().split(',')
        if len(parts) >= 4:
            name = parts[1].strip().strip('"')
            year = parts[2].strip()
            uri = parts[3].strip()
            
            if name and uri:
                key = f"{name}|:|{year}"
                ids = title_year_to_ids.get(key)
                if ids and ids.get('imdb_id'):
                    mapper_cache[uri] = {
                        'imdb_id': ids['imdb_id'],
                        'tmdb_id': ids['tmdb_id'],
                        'last_updated': '2026-01-07'
                    }
                    matched += 1

# 保存
with open('adapters/utils/letterboxd_platform_mapping.json', 'w') as f:
    json.dump(mapper_cache, f, indent=2, ensure_ascii=False)

print(f"成功转换 {matched} 条缓存")
