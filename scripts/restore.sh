#!/usr/bin/env bash
# =============================================================================
# Restore a backup made by scripts/backup.sh onto a running stack (the same machine, or another one after
# scripts/bootstrap.sh or scripts/deploy_prod.sh with the SAME site name). docs/SAO_LUU_KHOI_PHUC.md.
#
#   scripts/restore.sh [--prod] BACKUP_DIR
#
# Replaces the site's database, public and private files, puts back its encryption key (so stored passwords and
# keys still decrypt), copies the MinIO bucket back, migrates, rebuilds the search index and restarts the app.
# The accounts and the Administrator password are those of the backup.
# =============================================================================
set -euo pipefail

prod=0
src=""
for arg in "$@"; do
  case "$arg" in
    --prod) prod=1 ;;
    -h|--help) sed -n '3,11p' "$0"; exit 0 ;;
    -*) echo "Tham số không hợp lệ: $arg" >&2; exit 2 ;;
    *) src="$arg" ;;
  esac
done
[ -n "$src" ] && [ -d "$src" ] || { echo "Cách dùng: scripts/restore.sh [--prod] BACKUP_DIR" >&2; exit 2; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$(cd "$src" && pwd)"
export MSYS_NO_PATHCONV=1
PYTHON=""
for candidate in python3 python; do  # on Windows "python3" may be the Store's placeholder: it must really run
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
if [ "$prod" = 1 ]; then env_file="$root/docker/.env.prod"; else env_file="$root/docker/.env"; fi
[ -f "$env_file" ] || { echo "Không có $env_file" >&2; exit 1; }
get_value() { { grep -E "^$1=" "$env_file" || true; } | tail -n 1 | cut -d= -f2-; }
dc() {
  # a relative script path: Windows Python cannot read a Git Bash path (/d/...) when MSYS_NO_PATHCONV is set
  if [ "$prod" = 1 ]; then (cd "$root" && "$PYTHON" scripts/prod_compose.py "$@"); else (cd "$root/docker" && docker compose "$@"); fi
}
host_path() { if (cd "$1" && pwd -W) >/dev/null 2>&1; then (cd "$1" && pwd -W); else (cd "$1" && pwd); fi; }
one() { find "$src" -maxdepth 1 -name "$1" | head -n 1; }
src_host="$(host_path "$src")"  # the form docker understands (D:/... on Windows)

site="$(get_value FRAPPE_SITE_NAME)"
database="$(one '*-database.sql.gz')"
public="$(one '*-files.tar*')"
private="$(one '*-private-files.tar*')"
config="$(one '*-site_config_backup.json')"
[ -n "$database" ] || { echo "Thiếu *-database.sql.gz trong $src" >&2; exit 1; }
# backup.sh writes MANIFEST.txt last: without it the backup did not finish
[ -f "$src/MANIFEST.txt" ] || { echo "Thiếu MANIFEST.txt trong $src: bản sao lưu chưa xong, không khôi phục" >&2; exit 1; }
# the MinIO keys of photos and documents carry a hash of the site name: another name would orphan them all
from_site="$(sed -n 's/^site: //p' "$src/MANIFEST.txt" | head -n 1 | tr -d '\r')"
[ "$from_site" = "$site" ] || { echo "Bản sao lưu của site '$from_site', stack này là '$site': cài lại với FRAPPE_SITE_NAME=$from_site (ảnh, tài liệu gắn với tên site)" >&2; exit 1; }
echo "==> Kiểm SHA-256 theo MANIFEST.txt"
(cd "$src" && grep -E '^[0-9a-f]{64} ' MANIFEST.txt | if command -v sha256sum >/dev/null 2>&1; then sha256sum -c --quiet -; else shasum -a 256 -c --quiet -; fi)

inside="/tmp/pm-restore"
echo "==> Chép bản sao lưu vào container"
dc exec -T backend rm -rf "$inside"
dc exec -T backend mkdir -p "$inside"
for file in "$database" "$public" "$private" "$config"; do
  [ -n "$file" ] || continue
  dc cp "$src_host/$(basename "$file")" "backend:$inside/$(basename "$file")" >/dev/null 2>&1 || { echo "Không chép được $file" >&2; exit 1; }
done

echo "==> Khôi phục cơ sở dữ liệu và tệp của site $site"
args=(--db-root-username root --force)
[ -n "$public" ] && args+=(--with-public-files "$inside/$(basename "$public")")
[ -n "$private" ] && args+=(--with-private-files "$inside/$(basename "$private")")
PM_ROOT_PW="$(get_value MARIADB_ROOT_PASSWORD)"
export PM_ROOT_PW
dc exec -T -e PM_ROOT_PW backend bash -c \
  "bench --site '$site' restore '$inside/$(basename "$database")' ${args[*]} --db-root-password \"\$PM_ROOT_PW\"" | tail -n 3
unset PM_ROOT_PW

if [ -n "$config" ]; then
  echo "==> Khóa mã hóa của site"
  dc exec -T backend /home/frappe/frappe-bench/env/bin/python - "$site" "$inside/$(basename "$config")" <<'PY'
import json, sys
site, backup = sys.argv[1], sys.argv[2]
key = json.load(open(backup)).get("encryption_key")
path = f"/home/frappe/frappe-bench/sites/{site}/site_config.json"
config = json.load(open(path))
if key and config.get("encryption_key") != key:
    config["encryption_key"] = key
    json.dump(config, open(path, "w"), indent=1)
    print("encryption_key restored")
PY
fi

if [ -d "$src/minio" ]; then
  bucket="$(get_value MINIO_BUCKET)"
  echo "==> Bucket MinIO ${bucket:-pm-files}"
  dc run --rm --no-deps -v "$src_host/minio:/backup:ro" --entrypoint /bin/sh minio-init -ec \
    'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mirror --quiet --overwrite /backup "local/$MINIO_BUCKET"' >/dev/null
fi

echo "==> Migrate, chỉ mục tìm kiếm, khởi động lại"
dc exec -T backend bench --site "$site" migrate >/dev/null
dc exec -T backend bench --site "$site" execute project_manager.project_manager.services.search_index.rebuild >/dev/null || \
  echo "Cảnh báo: chưa dựng lại được chỉ mục tìm kiếm (Meilisearch); chạy lại lệnh rebuild sau."
dc exec -T backend rm -rf "$inside"
dc restart backend websocket queue-pm queue-short queue-long scheduler frontend >/dev/null
echo "Đã khôi phục $site từ $src"
