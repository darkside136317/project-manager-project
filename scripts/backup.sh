#!/usr/bin/env bash
# =============================================================================
# Full backup of the site: database, public and private files, the site's config (its encryption key), and the
# MinIO bucket (photos, documents). docs/SAO_LUU_KHOI_PHUC.md.
#
#   scripts/backup.sh [--prod] [DEST]
#
# --prod uses the production stack (docker/.env.prod); otherwise the stack of docker/.env. DEST defaults to
# backups/<site>-<date-time> under the repository (ignored by git). The folder gets a MANIFEST.txt with the SHA-256 of
# every file, written last: a folder without it is not a backup (restore.sh refuses it). A failed run removes the folder
# it created. The secrets of docker/.env(.prod) are NOT in the backup: keep that file safe on its own.
# =============================================================================
set -euo pipefail

prod=0
dest=""
for arg in "$@"; do
  case "$arg" in
    --prod) prod=1 ;;
    -h|--help) sed -n '3,11p' "$0"; exit 0 ;;
    -*) echo "Tham số không hợp lệ: $arg" >&2; exit 2 ;;
    *) dest="$arg" ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

site="$(get_value FRAPPE_SITE_NAME)"
stamp="$(date +%Y%m%d-%H%M%S)"
dest="${dest:-$root/backups/$site-$stamp}"
created=0
[ -e "$dest" ] || created=1
mkdir -p "$dest/minio"
dest="$(cd "$dest" && pwd)"
dest_host="$(host_path "$dest")"  # the form docker understands (D:/... on Windows)
inside="/tmp/pm-backup-$stamp"
finished=0
cleanup() {
  [ "$finished" = 1 ] && return
  dc exec -T backend rm -rf "$inside" >/dev/null 2>&1 || true
  if [ "$created" = 1 ]; then
    rm -rf "$dest"
    echo "Sao lưu thất bại: đã xóa thư mục dở dang $dest" >&2
  else
    echo "Sao lưu thất bại: $dest chưa đầy đủ (không có MANIFEST.txt), đừng dùng để khôi phục" >&2
  fi
}
trap cleanup EXIT

echo "==> Cơ sở dữ liệu và tệp của site $site"
dc exec -T backend bench --site "$site" backup --with-files --backup-path "$inside" >/dev/null
for file in $(dc exec -T backend bash -c "ls $inside"); do
  file="${file%$'\r'}"
  dc cp "backend:$inside/$file" "$dest_host/$file" >/dev/null 2>&1 || { echo "Không chép được $file" >&2; exit 1; }
done
dc exec -T backend rm -rf "$inside"

bucket="$(get_value MINIO_BUCKET)"
echo "==> Bucket MinIO ${bucket:-pm-files}"
dc run --rm --no-deps -v "$dest_host/minio:/backup" --entrypoint /bin/sh minio-init -ec \
  'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null; mc mirror --quiet --overwrite "local/$MINIO_BUCKET" /backup' >/dev/null

echo "==> MANIFEST.txt"
{
  echo "site: $site"
  echo "taken: $(date -Iseconds)"
  echo "source: $(git -C "$root" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "objects in MinIO: $(find "$dest/minio" -type f | wc -l | tr -d ' ')"
  echo
  (cd "$dest" && find . -type f ! -name 'MANIFEST.txt*' | sort | while read -r f; do
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$f"; else shasum -a 256 "$f"; fi
  done)
} > "$dest/MANIFEST.txt.part"
mv "$dest/MANIFEST.txt.part" "$dest/MANIFEST.txt"
finished=1
echo "Đã sao lưu vào $dest ($(du -sh "$dest" | cut -f1))"
