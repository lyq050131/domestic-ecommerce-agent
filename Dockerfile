# 国内电商店铺自动化运营智能体 - 生产镜像
# 基于 Python 3.10-slim，安装核心依赖后运行 FastAPI 后台
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
# 国内构建可传 build arg：PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -r requirements.txt -i "$PIP_INDEX_URL"

# 拷贝项目代码（.env 已被 .dockerignore 排除，运行时通过 env_file 注入）
COPY . .

# 运行期数据目录：data(报告库/模板) logs(日志) storage(导出文件)
RUN mkdir -p /app/data /app/logs /app/storage

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
