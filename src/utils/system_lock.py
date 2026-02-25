"""
v6.0 Windows 系统锁（防止休眠和网卡节能）
"""
import ctypes
import logging
import platform

logger = logging.getLogger(__name__)


class WindowsSystemLock:
    """
    Windows 系统锁 - 强制保持唤醒状态

    功能：
    1. 阻止系统休眠
    2. 阻止显示器关闭
    3. 保持网络连接活跃
    """

    def __init__(self):
        if platform.system() != 'Windows':
            logger.warning("SystemLock 仅支持 Windows 系统")
            self.available = False
            return

        self.available = True

        # Windows API 常量
        self.ES_CONTINUOUS = 0x80000000
        self.ES_SYSTEM_REQUIRED = 0x00000001
        self.ES_DISPLAY_REQUIRED = 0x00000002
        self.ES_AWAYMODE_REQUIRED = 0x00000040

        # 加载 Windows API
        self.kernel32 = ctypes.windll.kernel32

    def prevent_sleep(self):
        """
        阻止系统休眠和显示器关闭

        调用 Windows API SetThreadExecutionState
        """
        if not self.available:
            logger.warning("SystemLock 不可用，跳过防休眠设置")
            return False

        try:
            # 设置执行状态：保持系统唤醒 + 保持显示器开启
            result = self.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS |
                self.ES_SYSTEM_REQUIRED |
                self.ES_DISPLAY_REQUIRED |
                self.ES_AWAYMODE_REQUIRED
            )

            if result == 0:
                logger.error("❌ SetThreadExecutionState 调用失败")
                return False

            logger.info("✅ 系统锁定：已阻止休眠和显示器关闭")
            return True

        except Exception as e:
            logger.error(f"❌ 系统锁定失败: {e}")
            return False

    def allow_sleep(self):
        """
        恢复系统正常休眠行为

        程序退出时调用
        """
        if not self.available:
            return False

        try:
            # 恢复正常状态
            result = self.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS
            )

            if result == 0:
                logger.error("❌ 恢复休眠设置失败")
                return False

            logger.info("✅ 系统解锁：已恢复正常休眠行为")
            return True

        except Exception as e:
            logger.error(f"❌ 恢复休眠设置失败: {e}")
            return False


def disable_network_power_saving():
    """
    禁用网卡节能模式（需要管理员权限）

    通过 PowerShell 修改网卡电源管理设置
    """
    if platform.system() != 'Windows':
        logger.warning("此功能仅支持 Windows 系统")
        return False

    try:
        import subprocess

        # PowerShell 脚本：禁用所有网卡的节能模式
        ps_script = """
        Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object {
            $adapter = $_
            try {
                Set-NetAdapterPowerManagement -Name $adapter.Name -WakeOnMagicPacket Enabled -WakeOnPattern Enabled -ErrorAction SilentlyContinue
                Write-Host "已禁用网卡节能: $($adapter.Name)"
            } catch {
                Write-Host "无法修改网卡: $($adapter.Name)"
            }
        }
        """

        # 执行 PowerShell 脚本
        result = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            logger.info("✅ 网卡节能已禁用")
            logger.info(result.stdout)
            return True
        else:
            logger.warning(f"⚠️ 网卡节能禁用失败（需要管理员权限）: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"❌ 网卡节能禁用异常: {e}")
        return False


# 全局系统锁实例
_system_lock = None


def get_system_lock() -> WindowsSystemLock:
    """获取全局系统锁实例"""
    global _system_lock
    if _system_lock is None:
        _system_lock = WindowsSystemLock()
    return _system_lock


if __name__ == '__main__':
    # 测试系统锁
    logging.basicConfig(level=logging.INFO)

    lock = get_system_lock()

    print("测试系统锁...")
    lock.prevent_sleep()

    print("\n测试网卡节能禁用...")
    disable_network_power_saving()

    print("\n按 Ctrl+C 退出...")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出中...")
        lock.allow_sleep()
