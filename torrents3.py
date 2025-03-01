import qbittorrentapi
import time
from collections import defaultdict

# 连接 qbittorrent Web UI
QB_HOST = "http://10.233.233.233:2333"  # 替换为你的 qb-webui 地址
QB_USERNAME = "2333"  # 替换为你的用户名
QB_PASSWORD = "23333"  # 替换为你的密码


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


def check_torrents_every_10_min():
    """ 检查前 11 个种子，10 分钟无速度则移至末尾 """
    torrents = get_active_torrents()
    print("⚠️ 10分钟检测 - 当前前 11 个种子:")
    for idx, t in enumerate(torrents[:11], start=1):
        avg_speed = calculate_average_speed(t.hash)
        print(f"  {idx}. {t.name} - 平均速度: {format_speed(avg_speed)}")

    for t in torrents[:11]:
        avg_speed = calculate_average_speed(t.hash)
        if avg_speed == 0:
            print(f"❌ 种子 {t.name} 10 分钟无速度，移动至队列末尾")
            client.torrents.bottom_priority(t.hash)


def check_torrent_12():
    """ 检测 12 号位种子的速度，调整优先级 """
    torrents = get_active_torrents()
    if len(torrents) < 12:
        return  # 任务数不足 12，跳过

    torrent_12 = torrents[11]
    speed_12 = calculate_average_speed(torrent_12.hash)
    print(f"📈 检查 12 号种子: {torrent_12.name} - 平均速度: {format_speed(speed_12)}")

    if speed_12 == 0:
        print(f"❌ 种子 {torrent_12.name} 无速度，移至队列末尾")
        client.torrents.bottom_priority(torrent_12.hash)
        return

    # 检查前 11 个种子，找到平均速度低于 100kB/s 的进行替换
    for i in range(9):  # 只检查前 9 个
        target_speed = calculate_average_speed(torrents[i].hash)
        if target_speed < 100 * 1024 and speed_12 > target_speed:  # 确保 12 号种子速度更快
            print(
                f"🔄 种子 {torrent_12.name} (速度 {format_speed(speed_12)}) 替换 {torrents[i].name} (速度 {format_speed(target_speed)})")
            client.torrents.increase_priority(torrent_12.hash)
            client.torrents.decrease_priority(torrents[i].hash)
            return

    print(f"⚠️ 种子 {torrent_12.name} 速度一般，稍微延后")
    client.torrents.decrease_priority(torrent_12.hash)


def update_speed_history():
    """ 更新种子速度历史记录 """
    torrents = get_active_torrents()
    for t in torrents:
        speed_history[t.hash].append(t.dlspeed)
        if len(speed_history[t.hash]) > 10:  # 保持最近 10 次记录
            speed_history[t.hash].pop(0)


def main():
    """ 主循环 """
    counter_10min = 10  # 立即执行 10 分钟检测
    while True:
        print("🔍 更新种子速度记录...")
        update_speed_history()

        if counter_10min >= 10:
            print("⏳ 运行 10 分钟检测...")
            check_torrents_every_10_min()
            counter_10min = 0  # 重置计数器

        print("⏳ 运行 1 分钟检测...")
        check_torrent_12()

        counter_10min += 1
        time.sleep(60)  # 每分钟执行一次


if __name__ == "__main__":
    main()





