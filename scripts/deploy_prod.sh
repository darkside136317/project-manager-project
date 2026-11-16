#!/usr/bin/env bash
# =============================================================================
# First deploy and upgrades of the production stack, on a Linux server (docs/DEPLOYMENT.md).
#
#   scripts/deploy_prod.sh            build (or pull) the image, create the site if needed, migrate, start
#   scripts/deploy_prod.sh --backup   take a full backup first (scripts/backup.sh --prod), then the same
#
# Needs docker/.env.prod (copy docker/.env.prod.example and fill the site, the company and the port). Empty secrets
# are generated once; the file is checked by scripts/validate_prod_env.py before anything runs. Safe to run again.
# =============================================================================
set -euo pipefail

backup=0
for arg in "$@"; do
  case "$arg" in
    --backup) backup=1 ;;
    -h|--help) sed -n '3,9p' "$0"; exit 0 ;;
    *) echo "Tham số không hợp lệ: $arg (xem --help)" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
env_file="docker/.env.prod"
ONE_SHOTS='^(configurator|create-site|setup-site|minio-init)$'
PYTHON=""
for candidate in python3 python; do  # on Windows "python3" may be the Store's placeholder: it must really run
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done

step() { printf '\n==> %s\n' "$*"; }
die() { printf 'LỖI: %s\n' "$*" >&2; exit 1; }
get_value() { { grep -E "^$1=" "$env_file" || true; } | tail -n 1 | cut -d= -f2-; }
set_value() {
  local tmp
  tmp="$(mktemp)"
  awk -v key="$1" -v value="$2" '
    index($0, key "=") == 1 { print key "=" value; done = 1; next }
    { print }
    END { if (!done) print key "=" value }' "$env_file" > "$tmp"
  cat "$tmp" > "$env_file" && rm -f "$tmp"
}
random_secret() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
pc() { "$PYTHON" scripts/prod_compose.py "$@"; }

step "Kiểm tra Docker và docker/.env.prod"
command -v docker >/dev/null 2>&1 || die "Chưa cài Docker Engine 24+."
docker compose version >/dev/null 2>&1 || die "Cần Docker Compose v2."
[ -n "$PYTHON" ] || die "Cần python3 (để kiểm docker/.env.prod)."
[ -f "$env_file" ] || die "Chưa có $env_file: cp docker/.env.prod.example $env_file rồi điền site, công ty, cổng."
chmod 600 "$env_file"
for key in ADMIN_PASSWORD MARIADB_ROOT_PASSWORD MEILISEARCH_MASTER_KEY MINIO_ROOT_PASSWORD MINIO_APP_SECRET_KEY; do
  if [ -z "$(get_value "$key")" ]; then
    set_value "$key" "$(random_secret)"
    echo "Đã sinh $key"
  fi
done
"$PYTHON" scripts/validate_prod_env.py "$env_file"

data_root="$(get_value DATA_ROOT)"
if [ -n "$data_root" ]; then
  step "Thư mục dữ liệu $data_root"
  for part in db redis-queue sites logs meilisearch minio; do mkdir -p "$data_root/$part"; done
  # the Frappe containers run as uid 1000
  chown 1000:1000 "$data_root/sites" "$data_root/logs" 2>/dev/null || echo "Cảnh báo: không chown được sites, logs (cần quyền root)."
fi

site="$(get_value FRAPPE_SITE_NAME)"
if [ "$backup" = 1 ] && pc ps --status running --services 2>/dev/null | grep -qx backend; then
  step "Sao lưu trước khi nâng cấp"
  scripts/backup.sh --prod
fi

step "Image"
if [ -n "$(get_value PM_IMAGE)" ]; then
  pc pull backend frontend websocket queue-pm queue-short queue-long scheduler
else
  pc build backend
fi
pc build minio minio-init

step "Cơ sở dữ liệu, Redis, Meilisearch, MinIO"
pc up -d db redis-cache redis-queue meilisearch minio
pc run --rm minio-init

step "Cấu hình, tạo site $site (nếu chưa có), setup wizard, migrate"
pc run --rm --no-deps configurator
pc run --rm --no-deps create-site
pc run --rm --no-deps setup-site

step "Khởi động toàn bộ dịch vụ"
# shellcheck disable=SC2046  # one service name per word
pc up -d --no-deps --remove-orphans $(pc config --services | grep -vE "$ONE_SHOTS")

port="$(get_value HTTP_PUBLISH_PORT)"
url="http://${port}"
step "Chờ $url phản hồi"
for _ in $(seq 1 60); do
  if curl -fsS -H "Host: $site" "$url/api/method/ping" >/dev/null 2>&1; then ready=1; break; fi
  sleep 5
done
[ "${ready:-0}" = 1 ] || die "Site chưa phản hồi sau 5 phút: python3 scripts/prod_compose.py logs --tail=100"

cat <<EOF

Xong. Stack đang chạy, nginx nghe ở $url (chỉ trong máy chủ).
  Việc tiếp theo: reverse proxy có TLS cho $(get_value PUBLIC_URL) trỏ về $url (docs/DEPLOYMENT.md),
  lịch sao lưu hằng ngày (scripts/backup.sh --prod, docs/SAO_LUU_KHOI_PHUC.md).
  Tài khoản Administrator, mật khẩu là ADMIN_PASSWORD trong $env_file.
EOF
