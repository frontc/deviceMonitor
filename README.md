# 家庭网络设备监控系统

一个用于监控家庭局域网中设备接入与断开的Python应用程序，通过Bark API发送实时通知。

## 功能特性

- **ARP扫描检测**：使用`arp-scan`或系统ARP表检测局域网内设备
- **设备识别**：通过MAC地址映射识别设备名称
- **智能通知**：支持不同设备的通知级别（震动、静默、普通）
- **配置灵活**：JSON配置文件，易于自定义
- **Docker支持**：一键部署，支持群晖NAS
- **日志记录**：详细的运行日志，便于排查问题

## 快速开始

### 1. 环境要求

- Python 3.7+
- `arp-scan`工具（推荐）或系统ARP命令
- Bark App（用于接收通知）

### 2. 安装依赖

```bash
# 克隆项目
git clone <repository-url>
cd deviceMonitor

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装Python依赖
pip install -r requirements.txt

# 安装arp-scan（Linux/macOS）
# Ubuntu/Debian:
sudo apt-get install arp-scan
# macOS:
brew install arp-scan
```

### 3. 配置

1. 编辑 `config.json` 文件：

```json
{
  "bark_api_key": "你的Bark API Key",
  "bark_base_url": "https://api.day.app",
  "network_interface": "en0",
  "scan_interval": 60,
  "device_mapping": {
    "AA:BB:CC:DD:EE:FF": "iPhone 12",
    "11:22:33:44:55:66": "MacBook Pro"
  },
  "ignore_devices": [
    "FF:FF:FF:FF:FF:FF"
  ],
  "notification_settings": {
    "AA:BB:CC:DD:EE:FF": "vibrate",
    "11:22:33:44:55:66": "silent"
  }
}
```

2. **获取Bark API Key**：
   - 在iPhone上安装Bark App
   - 打开App获取你的设备Key
   - 将Key填入配置文件的`bark_api_key`字段

3. **确定网络接口**：
   - Linux/macOS: 运行 `ifconfig` 或 `ip addr` 查看接口名称
   - 常见接口：`eth0`（有线）、`wlan0`（无线）、`en0`（macOS）

### 4. 运行

#### 方式一：直接运行（开发环境）

```bash
# 单次扫描模式
python src/device_monitor.py --once

# 持续监控模式（默认）
python src/device_monitor.py
```

#### 方式二：使用Docker

```bash
# 构建镜像
docker build -t device-monitor .

# 运行容器
docker run -d \
  --name device-monitor \
  --network host \
  --privileged \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/logs:/var/log/device_monitor \
  device-monitor
```

#### 方式三：使用Docker Compose（推荐）

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 配置文件详解

### 主要配置项

| 配置项 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `bark_api_key` | 字符串 | Bark API密钥 | `"abcd1234"` |
| `bark_base_url` | 字符串 | Bark服务器地址 | `"https://api.day.app"` |
| `network_interface` | 字符串 | 网络接口名称 | `"en0"`, `"eth0"` |
| `scan_interval` | 整数 | 扫描间隔（秒） | `60` |
| `device_mapping` | 对象 | MAC地址到设备名的映射 | `{"AA:BB:CC:DD:EE:FF": "iPhone"}` |
| `ignore_devices` | 数组 | 忽略的MAC地址列表 | `["FF:FF:FF:FF:FF:FF"]` |
| `notification_settings` | 对象 | 设备通知级别设置 | `{"AA:BB:CC:DD:EE:FF": "vibrate"}` |
| `notification_levels` | 对象 | 通知级别说明（文档用途） | 见示例 |

### 通知级别

Bark API支持以下通知级别：

| 级别 | 说明 | Bark API参数 |
|------|------|-------------|
| `"vibrate"` | 震动通知（有声音和震动） | `level=active` |
| `"silent"` | 静默通知（无声音无震动） | `sound=silent`, `level=passive` |
| `"normal"` | 普通通知（默认声音） | 不设置level参数，使用Bark默认行为 |
| `"timeSensitive"` | 时效性通知（iOS 15+） | `level=timeSensitive` |

**技术细节**：
- `level=active`: 主动通知，有声音和震动
- `level=passive`: 被动通知，无声音无震动，仅出现在通知中心
- `level=timeSensitive`: 时效性通知，绕过静音和勿扰模式（iOS 15+）
- `sound=silent`: 无声音通知，可与任意level组合

未配置的设备使用普通通知（默认声音）。

## 部署到群晖NAS

### 通过Docker套件部署

1. 在群晖NAS中安装Docker套件
2. 将项目文件上传到NAS（如 `/volume1/docker/deviceMonitor`）
3. 打开Docker套件，选择"映像" → "新增" → "从文件添加"
4. 选择项目中的Dockerfile构建镜像
5. 创建容器时设置：
   - 网络模式：主机模式
   - 卷映射：配置文件路径
   - 特权模式：开启
6. 启动容器

### 通过SSH部署

```bash
# 连接到群晖NAS
ssh admin@nas-ip

# 进入项目目录
cd /volume1/docker/deviceMonitor

# 使用docker-compose启动
docker-compose up -d
```

## 获取设备MAC地址

### 方法1：使用arp-scan扫描

```bash
# 安装arp-scan后运行
sudo arp-scan --localnet

# 输出示例：
# 192.168.1.1   00:11:22:33:44:55   Router
# 192.168.1.101 AA:BB:CC:DD:EE:FF   (Unknown)
```

### 方法2：查看路由器设备列表

登录路由器管理界面，查看已连接设备的MAC地址。

### 方法3：在设备上查看

- **iPhone/iPad**：设置 → 通用 → 关于本机 → Wi-Fi地址
- **Android**：设置 → 关于手机 → 状态信息 → Wi-Fi MAC地址
- **Windows**：命令提示符输入 `ipconfig /all`
- **macOS**：系统偏好设置 → 网络 → 高级 → 硬件

## 故障排除

### 常见问题

1. **无法检测到设备**
   - 检查网络接口配置是否正确
   - 确认有权限执行ARP扫描（可能需要sudo）
   - 尝试使用 `arp -a` 命令查看ARP表

2. **Bark通知未发送**
   - 检查API Key是否正确
   - 确认设备可以访问互联网
   - 查看日志文件 `device_monitor.log`

3. **Docker容器权限不足**
   - 确保容器以特权模式运行（`--privileged`）
   - 使用主机网络模式（`--network host`）

4. **扫描速度太慢**
   - 调整 `scan_interval` 配置项
   - 考虑网络规模，适当增加间隔时间

### 查看日志

```bash
# 直接运行时的日志
tail -f device_monitor.log

# Docker容器日志
docker logs device-monitor

# Docker Compose日志
docker-compose logs -f
```

## 项目结构

```
deviceMonitor/
├── src/
│   └── device_monitor.py    # 主程序
├── config.json              # 配置文件
├── requirements.txt         # Python依赖
├── Dockerfile              # Docker构建文件
├── docker-compose.yml      # Docker Compose配置
├── README.md               # 本文档
└── projectRequirements.md  # 项目需求文档
```

## 开发指南

### 添加新功能

1. 创建功能分支
2. 修改代码并测试
3. 更新配置文件格式（如有需要）
4. 更新文档
5. 提交Pull Request

### 测试

```bash
# 运行单元测试（待实现）
python -m pytest tests/

# 代码风格检查
python -m flake8 src/
```

### 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

## 支持

如有问题，请：
1. 查看本文档的故障排除部分
2. 检查日志文件
3. 提交GitHub Issue
4. 联系维护者

---

**提示**：首次运行建议使用 `--once` 参数测试配置是否正确，确认设备识别和通知功能正常后再启用持续监控。