#!/usr/bin/env bash
# =====================================================================
# 国内电商店铺自动化运营智能体 - 阿里云一键部署脚本
# 适用系统：Alibaba Cloud Linux 3 / Ubuntu 22.04+ / Debian 12
# 用法：
#   bash deploy.sh                    # 全新部署（拉代码 + 建 .env + 启动）
#   bash deploy.sh update             # 更新到最新代码并重建
# =====================================================================
set -euo pipefail

APP_DIR="/opt/domestic-ecommerce-agent"
REPO_URL="https://github.com/lyq050131/domestic-ecommerce-agent.git"
BRANCH="main"
PORT="${PORT:-8000}"

log()  { echo -e "\033[1;32m[deploy]\033[0m $*"; }
warn() { echo -e "\033[1;33m[deploy]\033[0m $*"; }
err()  { echo -e "\033[1;31m[deploy]\033[0m $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || err "未检测到 Docker，请先安装：https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || docker-compose --version >/dev/null 2>&1 || err "未检测到 docker compose 插件，请安装 compose v2"

# ---------- 拉取/更新代码 ----------
if [ ! -d "$APP_DIR/.git" ]; then
    log "首次部署：克隆代码到 $APP_DIR"
    sudo mkdir -p "$APP_DIR"
    sudo chown "$(id -u):$(id -g)" "$APP_DIR"
    git clone -b "$BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
else
    log "更新代码：$APP_DIR"
    cd "$APP_DIR"
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
fi
cd "$APP_DIR"

# ---------- 初始化 .env ----------
if [ ! -f .env ]; then
    cp .env.example .env
    warn "已生成 .env 模板，请编辑配置真实密钥："
    warn "  vi $APP_DIR/.env"
    warn "  必填：LLM_API_KEY / TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID"
    warn "  可选：WEB_ACCESS_TOKEN（Web 后台登录令牌）、DINGTALK_WEBHOOK_URL"
    read -r -p "编辑完成后按回车继续启动..." _
fi

# 启动前校验必填项（缺失则中止，避免白启动）
if ! grep -q '^LLM_API_KEY=.\+' .env; then
    err ".env 缺少 LLM_API_KEY（DeepSeek API Key），请先填写再启动"
fi
for k in TAOBAO_APP_KEY TAOBAO_APP_SECRET TAOBAO_ADZONE_ID; do
    if ! grep -q "^${k}=.\+" .env; then
        err ".env 缺少 ${k}（淘宝客三要素），请先填写再启动"
    fi
done

# ---------- 构建并启动 ----------
log "构建并启动容器（端口 $PORT）..."
docker compose up -d --build

# ---------- 健康检查 ----------
log "等待服务就绪..."
for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        log "服务已就绪！"
        echo "  Web 后台: http://<服务器公网IP>:${PORT}/"
        echo "  API 文档: http://<服务器公网IP>:${PORT}/docs"
        echo "  健康检查: http://<服务器公网IP>:${PORT}/health"
        echo ""
        echo "常用命令："
        echo "  查看日志 : cd $APP_DIR && docker compose logs -f app"
        echo "  重启服务 : cd $APP_DIR && docker compose restart"
        echo "  更新版本 : bash deploy.sh update"
        exit 0
    fi
    sleep 2
done
err "服务未在 ${PORT} 端口就绪，请执行: cd $APP_DIR && docker compose logs app"
