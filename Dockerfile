# 使用Python 3.9 slim镜像作为基础
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（arp-scan需要）
RUN apt-get update && apt-get install -y \
    arp-scan \
    net-tools \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序代码
COPY src/ ./src/
COPY config.json .

# 创建日志目录
RUN mkdir -p /var/log/device_monitor

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 设置容器启动命令
CMD ["python", "src/device_monitor.py"]