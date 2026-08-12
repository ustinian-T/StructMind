# StructMind — Docker 部署配置
FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用
COPY . .

# 创建运行时目录
RUN mkdir -p runtime

# 暴露端口
EXPOSE 8765

# 容器内必须监听全部接口，宿主机端口映射才能访问。
ENV SM_HOST=0.0.0.0

# 安全：以非root用户运行
RUN useradd -m -s /bin/bash structmind && chown -R structmind:structmind /app
USER structmind

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/stats')" || exit 1

CMD ["python", "server.py"]
