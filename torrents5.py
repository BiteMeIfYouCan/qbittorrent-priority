import qbittorrentapi
import time
import os
import json
from collections import defaultdict

# 读取配置文件
config_path = os.getenv("QB_CONFIG", "config.json")
try:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"✅ 读取配置文件: {config_path}")
except Exception as e:
    print(f"❌ 配置文件读取失败: {e}")
    exit(1)

# 获取 qBittorrent 服务器信息
QB_HOST = config.get("qb_host", "http://127.0.0.1:8080")
QB_USERNAME = config.get("qb_username", "admin")
QB_PASSWORD = config.get("qb_password", "adminadmin")
DOWNLOAD_SEQUENCE = config.get("download_sequence", list(range(1, 11)))  # 1-11
CHECK_SEQUENCE = config.get("check_sequence", 12)  # 默认 12 号检测
FULL_QUEUE_CHECK_INTERVAL = config.get("check_interval_10min", 600)  # 默认 10 分钟（600秒）
INDIVIDUAL_TEST_INTERVAL = config.get("check_interval_1min", 60)  # 默认 1 分钟（60秒）

# 连接客户端
client = qbittorrentapi.Client(host=QB_HOST, username=QB_USERNAME, password=QB_PASSWORD)
try:
    client.auth_log_in()
    print("✅ 成功连接到 qBittorrent Web UI")
except Exception as e:
    print("❌ 连接失败:", e)
    exit(1)

# 速度记录
speed_history = defaultdict(list)


def get_active_torrents():
    """ 获取所有正在下载或排队的种子 """
    torrents = client.torrents_info(status_filter="downloading")
    active_torrents = [t for t in torrents if t.state in ("downloading", "stalledDL", "queuedDL")]
    return sorted(active_torrents, key=lambda x: x.priority)


def format_speed(speed):
    """ 将速度转换为更友好的格式 """
    if speed >= 1024 * 1024:
        return f"{speed / (1024 * 1024):.2f} MB/s"
    elif speed >= 1024:
        return f"{speed / 1024:.2f} KB/s"
    else:
        return f"{speed:.2f} B/s"


def calculate_average_speed(torrent_hash):
    """ 计算过去 10 分钟内的平均速度 """
    speeds = speed_history[torrent_hash]
    if not speeds:
        return 0
    return sum(speeds) / len(speeds)


def check_torrents_every():
    """ 检查前 x 个种子，x 秒无速度则移至末尾 """
    torrents = get_active_torrents()
    print(f"⚠️ {FULL_QUEUE_CHECK_INTERVAL} 秒检测 - 当前下载序列种子:")
    move_list = []
    for idx in DOWNLOAD_SEQUENCE:
        if idx - 1 < len(torrents):
            t = torrents[idx - 1]
            avg_speed = calculate_average_speed(t.hash)
            print(f"  {idx}. {t.name} - 平均速度: {format_speed(avg_speed)}")
            if avg_speed == 0:
                move_list.append(t)

    for t in move_list:
        print(f"❌ 种子 {t.name} {FULL_QUEUE_CHECK_INTERVAL} 秒无速度，移动至队列末尾")
        client.torrents.bottom_priority(t.hash)


def check_torrent_12():
    """ 检测指定检测队列的种子速度，调整优先级 """
    torrents = get_active_torrents()
    seq = CHECK_SEQUENCE  # 仅允许一个检测种子

    if seq - 1 >= len(torrents):
        return

    torrent = torrents[seq - 1]
    avg_speed = calculate_average_speed(torrent.hash)
    instant_speed = torrent.dlspeed  # 瞬时速度
    effective_speed = avg_speed  # 默认用平均速度

    if instant_speed > avg_speed:
        effective_speed = instant_speed  # 只有瞬时速度高时才使用瞬时速度

    print(
        f"📈 检查 {seq} 号种子: {torrent.name} - 瞬时速度: {format_speed(instant_speed)}, 平均速度: {format_speed(avg_speed)}")

    if effective_speed == 0:
        print(f"❌ 种子 {torrent.name} 无速度，移至队列末尾")
        client.torrents.bottom_priority(torrent.hash)
        return

    # **找出 `DOWNLOAD_SEQUENCE` 中平均速度最慢的种子**
    slowest_torrent = None
    slowest_speed = float('inf')

    for i in DOWNLOAD_SEQUENCE:
        if i - 1 >= len(torrents):
            continue

        target_torrent = torrents[i - 1]
        target_avg_speed = calculate_average_speed(target_torrent.hash)

        if target_avg_speed < slowest_speed:
            slowest_speed = target_avg_speed
            slowest_torrent = target_torrent

    # **只有当 `torrent` 的瞬时速度高于平均速度时，才使用瞬时速度进行比较**
    if slowest_torrent and effective_speed > slowest_speed:
        print(
            f"🔄 种子 {torrent.name} (速度 {format_speed(effective_speed)}) "
            f"替换 {slowest_torrent.name} (速度 {format_speed(slowest_speed)}) "
            f"🔢 替换序列 ID: {seq} -> {DOWNLOAD_SEQUENCE[torrents.index(slowest_torrent)]}"
        )
        client.torrents.increase_priority(torrent.hash)
        client.torrents.decrease_priority(slowest_torrent.hash)
    else:
        print(f"⚠️ 种子 {torrent.name} 速度一般，稍微延后")
        client.torrents.decrease_priority(torrent.hash)


def update_speed_history():
    """ 更新种子速度历史记录 """
    torrents = get_active_torrents()
    for t in torrents:
        speed_history[t.hash].append(t.dlspeed)
        if len(speed_history[t.hash]) > 10:  # 保持最近 10 次记录
            speed_history[t.hash].pop(0)


def main():
    """ 主循环 """
    counter_full = FULL_QUEUE_CHECK_INTERVAL // INDIVIDUAL_TEST_INTERVAL  # 计算检测次数
    while True:
        print("🔍 更新种子速度记录...")
        update_speed_history()

        if counter_full >= FULL_QUEUE_CHECK_INTERVAL // INDIVIDUAL_TEST_INTERVAL:
            print(f"⏳ 运行 {FULL_QUEUE_CHECK_INTERVAL} 秒检测...")
            check_torrents_every()
            counter_full = 0  # 重置计数器

        print(f"⏳ 运行 {INDIVIDUAL_TEST_INTERVAL} 秒检测...")
        check_torrent_12()

        counter_full += 1
        time.sleep(INDIVIDUAL_TEST_INTERVAL)  # 使用可配置的检测间隔


if __name__ == "__main__":
    main()