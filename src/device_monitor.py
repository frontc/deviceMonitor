#!/usr/bin/env python3
"""
设备监控主程序
通过ARP扫描局域网设备，检测设备接入/断开，并通过Bark发送通知
"""

import subprocess
import re
import json
import time
import logging
from datetime import datetime
from typing import Dict, Set, Optional
import requests
import sys
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/device_monitor/device_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DeviceMonitor:
    def __init__(self, config_path: str = 'config.json'):
        """
        初始化监控器
        :param config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self.load_config()
        self.known_devices: Dict[str, str] = self.config.get('device_mapping', {})
        self.ignore_devices: Set[str] = set(self.config.get('ignore_devices', []))
        self.notification_settings: Dict[str, str] = self.config.get('notification_settings', {})
        self.bark_api_key = self.config.get('bark_api_key', '')
        self.bark_base_url = self.config.get('bark_base_url', 'https://api.day.app')
        self.scan_interval = self.config.get('scan_interval', 60)  # 秒
        self.network_interface = self.config.get('network_interface', 'en0')
        self.scan_subnets = self.config.get('scan_subnets', ['192.168.1.0/24'])
        self.previous_devices: Set[str] = set()
        
        # 验证配置
        if not self.bark_api_key:
            logger.warning("Bark API Key未配置，通知功能将禁用")
        
        logger.info(f"设备监控初始化完成，已知设备 {len(self.known_devices)} 个，忽略设备 {len(self.ignore_devices)} 个，扫描子网 {len(self.scan_subnets)} 个")

    def load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"配置文件加载成功: {self.config_path}")
                return config
        except FileNotFoundError:
            logger.error(f"配置文件不存在: {self.config_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            sys.exit(1)

    def arp_scan(self) -> Set[str]:
        """
        执行ARP扫描，返回当前在线的MAC地址集合
        支持多子网扫描，检测跨路由器的设备
        """
        mac_addresses = set()
        
        # 对每个子网进行扫描
        for subnet in self.scan_subnets:
            try:
                logger.debug(f"扫描子网: {subnet}")
                # 方法1: 使用arp-scan（推荐，更准确）
                cmd = ['arp-scan', subnet, '--interface', self.network_interface]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    # 解析arp-scan输出，提取MAC地址
                    lines = result.stdout.split('\n')
                    for line in lines:
                        # 匹配MAC地址格式（如 00:11:22:33:44:55）
                        mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                        if mac_match:
                            mac = mac_match.group(0).upper().replace('-', ':')
                            mac_addresses.add(mac)
                    logger.debug(f"子网 {subnet} 发现 {len(mac_addresses)} 个设备")
                else:
                    logger.warning(f"子网 {subnet} arp-scan 失败")
            except FileNotFoundError:
                logger.warning("arp-scan 未安装，尝试使用备选方法")
                break  # 如果arp-scan未安装，跳出循环使用备选方法
            except subprocess.TimeoutExpired:
                logger.error(f"子网 {subnet} ARP扫描超时")
            except Exception as e:
                logger.error(f"子网 {subnet} 扫描异常: {e}")
        
        # 如果arp-scan未安装或所有子网扫描失败，使用备选方法
        if not mac_addresses:
            logger.info("使用备选ARP扫描方法")
            self._fallback_arp_scan(mac_addresses)
        
        # 过滤掉忽略的设备
        filtered_macs = {mac for mac in mac_addresses if mac not in self.ignore_devices}
        logger.info(f"扫描完成，发现 {len(filtered_macs)} 个设备（过滤后）")
        return filtered_macs

    def _fallback_arp_scan(self, mac_addresses: Set[str]):
        """备选ARP扫描方法（使用系统arp表）"""
        try:
            # macOS/Linux
            cmd = ['arp', '-a']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    # 匹配MAC地址
                    mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', line)
                    if mac_match:
                        mac = mac_match.group(0).upper().replace('-', ':')
                        mac_addresses.add(mac)
                logger.debug(f"系统ARP表发现 {len(mac_addresses)} 个设备")
                
                # 备选方法只能扫描本地子网，记录警告
                if len(self.scan_subnets) > 1:
                    logger.warning("备选ARP扫描只能检测本地子网，无法扫描配置的多个子网。请安装arp-scan以获得完整功能。")
        except Exception as e:
            logger.error(f"备选ARP扫描失败: {e}")

    def get_device_name(self, mac: str) -> str:
        """根据MAC地址获取设备名称"""
        # 如果配置了设备名称，则使用配置的名称，否则使用"未知设备"
        return self.known_devices.get(mac, f"未知设备 ({mac})")

    def send_bark_notification(self, title: str, body: str, mac: str = '', special_notification: bool = False):
        """
        通过Bark发送通知
        :param title: 通知标题
        :param body: 通知内容
        :param mac: 设备MAC地址，用于确定通知级别
        :param special_notification: 是否为特殊通知（如初始报告），使用active级别
        """
        if not self.bark_api_key:
            logger.debug("Bark API Key未配置，跳过通知")
            return
        
        # 如果是特殊通知（如初始报告），使用active级别
        if special_notification:
            notification_level = 'active'
        else:
            # 根据设备MAC获取通知设置
            notification_level = self.notification_settings.get(mac, 'normal')
        
        # 构建URL（Bark API v2格式）
        # 格式: https://api.day.app/{key}/{title}/{body}?{params}
        url = f"{self.bark_base_url}/{self.bark_api_key}"
        
        # URL编码标题和内容
        import urllib.parse
        encoded_title = urllib.parse.quote(title)
        encoded_body = urllib.parse.quote(body)
        url = f"{url}/{encoded_title}/{encoded_body}"
        
        # 根据Bark API最新规范设置参数
        # 参考：https://github.com/Finb/Bark/blob/master/Documents/API_V2.md
        params = {}
        
        # 通知级别设置（level参数）
        # Bark API level参数说明：
        # - active: 主动通知（有声音、有震动）
        # - timeSensitive: 时效性通知（iOS 15+）
        # - passive: 被动通知（无声音、无震动，仅通知中心）
        # sound参数可以单独控制声音
        
        if notification_level == 'silent':
            # 静默通知：无声音，无震动
            params['sound'] = 'silent'
            params['level'] = 'passive'
        elif notification_level == 'vibrate' or notification_level == 'active':
            # 震动通知：有声音，有震动
            params['level'] = 'active'
            # 可以指定声音类型，如'alarm', 'bell', 'electronic'等
            # params['sound'] = 'alarm'
        elif notification_level == 'timeSensitive':
            # 时效性通知（iOS 15+）
            params['level'] = 'timeSensitive'
        else:
            # 普通通知：默认声音，被动级别
            # 不设置level参数，使用Bark默认行为（有声音）
            pass
        
        # 其他可选参数
        # params['badge'] = 1  # 角标数量
        # params['icon'] = 'https://example.com/icon.png'  # 图标
        # params['group'] = 'device_monitor'  # 通知分组
        # params['url'] = 'https://example.com'  # 点击跳转链接
        
        try:
            # Bark API v2 支持GET和POST，使用GET更简单
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                logger.info(f"Bark通知发送成功: {title}")
            else:
                logger.warning(f"Bark通知发送失败: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Bark通知发送异常: {e}")

    def detect_changes(self, current_devices: Set[str]):
        """
        检测设备变化并发送通知
        :param current_devices: 当前在线设备集合
        """
        # 新接入的设备
        new_devices = current_devices - self.previous_devices
        # 断开的设备
        gone_devices = self.previous_devices - current_devices
        
        # 处理新设备
        for mac in new_devices:
            device_name = self.get_device_name(mac)
            title = "设备接入"
            body = f"{device_name} ({mac}) 已接入网络"
            logger.info(f"新设备接入: {device_name} ({mac})")
            self.send_bark_notification(title, body, mac)
        
        # 处理断开设备
        for mac in gone_devices:
            device_name = self.get_device_name(mac)
            title = "设备断开"
            body = f"{device_name} ({mac}) 已断开网络"
            logger.info(f"设备断开: {device_name} ({mac})")
            self.send_bark_notification(title, body, mac)
        
        # 更新前一次设备集合
        self.previous_devices = current_devices.copy()
        
        # 记录状态
        if new_devices or gone_devices:
            logger.info(f"设备变化: +{len(new_devices)} -{len(gone_devices)}")
        else:
            logger.debug("无设备变化")

    def run_once(self, send_initial_report: bool = False):
        """
        执行一次完整的扫描和检测
        :param send_initial_report: 是否发送初始设备报告（容器启动时使用）
        """
        logger.info("开始设备扫描...")
        current_devices = self.arp_scan()
        
        # 如果是第一次运行
        if not self.previous_devices:
            logger.info(f"首次扫描发现 {len(current_devices)} 个在线设备")
            self.previous_devices = current_devices.copy()
            
            # 输出设备列表到日志
            for mac in sorted(current_devices):
                device_name = self.get_device_name(mac)
                logger.info(f"  - {device_name} ({mac})")
            
            # 如果要求发送初始报告，则通过Bark发送全量设备清单
            if send_initial_report and current_devices:
                self.send_initial_device_report(current_devices)
        else:
            self.detect_changes(current_devices)
        
        # 输出当前状态
        logger.info(f"当前在线设备: {len(current_devices)} 个")
        return current_devices
    
    def send_initial_device_report(self, devices: Set[str]):
        """
        发送初始设备报告（容器启动时调用）
        :param devices: 当前在线设备集合
        """
        if not devices:
            logger.info("无在线设备，不发送初始报告")
            return
        
        if not self.bark_api_key:
            logger.warning("Bark API Key未配置，无法发送初始报告")
            return
        
        logger.info("发送初始设备报告...")
        
        # 构建设备清单
        device_list = []
        for mac in sorted(devices):
            device_name = self.get_device_name(mac)
            device_list.append(f"{device_name} ({mac})")
        
        device_count = len(devices)
        device_summary = "\n".join(device_list)
        
        # 发送报告
        title = "设备监控启动报告"
        body = f"设备监控服务已启动\n\n当前在线设备 ({device_count} 个):\n{device_summary}\n\n扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # 使用特殊通知级别"active"确保用户能看到
        self.send_bark_notification(title, body, special_notification=True)
        
        logger.info(f"初始设备报告已发送，包含 {device_count} 个设备")

    def run_forever(self):
        """持续运行监控"""
        logger.info(f"设备监控启动，扫描间隔 {self.scan_interval} 秒")
        
        try:
            while True:
                start_time = time.time()
                self.run_once()
                
                # 计算下一次扫描的时间
                elapsed = time.time() - start_time
                sleep_time = max(1, self.scan_interval - elapsed)
                
                logger.debug(f"本次扫描耗时 {elapsed:.2f} 秒，等待 {sleep_time:.2f} 秒后继续")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("监控程序被用户中断")
        except Exception as e:
            logger.error(f"监控程序异常: {e}")
            raise


def main():
    """主函数"""
    # 检查配置文件是否存在，如果不存在则创建示例配置
    if not os.path.exists('config.json'):
        print("配置文件 config.json 不存在，正在创建示例配置...")
        create_example_config()
        print("请编辑 config.json 文件并重新运行程序")
        return
    
    # 创建监控器
    monitor = DeviceMonitor()
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == '--once':
            # 单次扫描模式
            monitor.run_once()
        elif sys.argv[1] == '--init-report':
            # 初始报告模式（容器启动时使用）
            logger.info("运行初始报告模式...")
            monitor.run_once(send_initial_report=True)
        elif sys.argv[1] == '--help':
            print("用法:")
            print("  python src/device_monitor.py           # 持续监控模式")
            print("  python src/device_monitor.py --once    # 单次扫描模式")
            print("  python src/device_monitor.py --init-report  # 发送初始设备报告")
            print("  python src/device_monitor.py --help    # 显示此帮助")
        else:
            print(f"未知参数: {sys.argv[1]}")
            print("使用 --help 查看可用参数")
    else:
        # 默认：持续监控模式，但先发送一次初始报告
        logger.info("启动持续监控模式，发送初始设备报告...")
        monitor.run_once(send_initial_report=True)
        monitor.run_forever()


def create_example_config():
    """创建示例配置文件"""
    example_config = {
        "bark_api_key": "your_bark_api_key_here",
        "bark_base_url": "https://api.day.app",
        "network_interface": "eth0",
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
    
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(example_config, f, indent=2, ensure_ascii=False)
    
    print("示例配置文件 config.json 已创建")


if __name__ == '__main__':
    main()