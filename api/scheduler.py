"""每日定时任务：自动运行选品 + 投放分析并落库（零额外依赖，守护线程实现）

- 由 FastAPI 启动时自动拉起（api/app.py lifespan）
- 每天在 AUTO_REPORT_TIME（HH:MM）执行一次，结果写入 SQLite 报告库
- 选品/投放相互隔离：一个失败不影响另一个
"""
import threading
from datetime import datetime

from config.settings import settings
from agents.product_selection_agent import product_selection_agent
from agents.ad_optimization_agent import ad_optimization_agent
from storage.report_store import report_store
from utils.logger import logger


class DailyReportScheduler:
    """每日报告调度器（线程实现，无第三方依赖）"""

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_date: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if not settings.AUTO_REPORT_ENABLED:
            logger.info("每日定时任务未开启（AUTO_REPORT_ENABLED=false），跳过")
            return
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-report-scheduler", daemon=True)
        self._thread.start()
        logger.info(f"每日定时任务已启动：每天 {settings.AUTO_REPORT_TIME} 自动运行选品+投放分析")

    def stop(self) -> None:
        self._stop_event.set()

    # ---------- 内部实现 ----------
    def _loop(self) -> None:
        try:
            datetime.strptime(settings.AUTO_REPORT_TIME, "%H:%M")
        except ValueError:
            logger.error(f"AUTO_REPORT_TIME 格式错误: {settings.AUTO_REPORT_TIME}（应为 HH:MM），定时任务已停止")
            return
        while not self._stop_event.wait(20):
            try:
                now = datetime.now()
                if now.strftime("%H:%M") == settings.AUTO_REPORT_TIME and self._last_run_date != now.strftime("%Y-%m-%d"):
                    self._last_run_date = now.strftime("%Y-%m-%d")
                    self._run_daily()
            except Exception as e:
                logger.error(f"定时任务调度异常: {e}")

    def _run_daily(self) -> None:
        logger.info("========== 每日自动运营任务开始 ==========")
        try:
            result = product_selection_agent.analyze_category(
                settings.AUTO_REPORT_CATEGORY, count=settings.AUTO_REPORT_COUNT
            )
            rid, _ = report_store.save_selection_report(result)
            logger.info(f"✅ 自动选品报告已生成并落库（id={rid}，品类={result.get('category')}）")
        except Exception as e:
            logger.error(f"自动选品失败: {e}")
        try:
            result = ad_optimization_agent.optimize_campaigns(top_n=settings.AUTO_REPORT_AD_TOP_N)
            rid, _ = report_store.save_ad_report(result)
            logger.info(f"✅ 自动投放报告已生成并落库（id={rid}）")
        except Exception as e:
            logger.error(f"自动投放失败: {e}")
        logger.info("========== 每日自动运营任务结束 ==========")


daily_scheduler = DailyReportScheduler()
