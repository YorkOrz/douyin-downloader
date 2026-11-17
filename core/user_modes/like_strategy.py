from typing import Any, Dict, List
from core.user_modes.base_strategy import BaseUserModeStrategy, PageRequestFailedError
from utils.logger import setup_logger

logger = setup_logger("LikeStrategy")


class LikeUserModeStrategy(BaseUserModeStrategy):
    mode_name = "like"
    api_method_name = "get_user_like"

    async def collect_items(self, sec_uid: str, user_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        paged_error = None
        # 首先尝试常规 API 分页请求
        try:
            items = await self._collect_paged_aweme(sec_uid, user_info)
            if items:
                return items
        except PageRequestFailedError as exc:
            paged_error = exc
            logger.warning("喜欢列表常规接口请求受限 (%s)，启动浏览器回退采集...", exc)
        except Exception as exc:
            paged_error = exc
            logger.warning("喜欢列表常规接口请求异常 (%s)，启动浏览器回退采集...", exc)

        # 浏览器兜底
        browser_cfg = self.downloader.config.get("browser_fallback", {}) or {}
        collector = getattr(self.downloader.api_client, "collect_user_like_ids_via_browser", None)
        if not browser_cfg.get("enabled", True) or not callable(collector):
            if paged_error is not None:
                raise paged_error
            logger.warning("browser_fallback 未启用或不可用，无法兜底喜欢列表")
            return []

        number_limit = self.downloader.config.get("number", {}).get("like", 0)
        expected_count = int(number_limit or 0)
        headless = bool(browser_cfg.get("headless", True))
        max_scrolls = int(browser_cfg.get("max_scrolls", 240) or 240)
        idle_rounds = int(browser_cfg.get("idle_rounds", 8) or 8)
        wait_timeout = int(browser_cfg.get("wait_timeout_seconds", 600) or 600)

        if hasattr(self.downloader, "_progress_update_step"):
            self.downloader._progress_update_step("浏览器回退", "正在采集喜欢列表...")

        browser_aweme_ids = await collector(
            sec_uid=sec_uid,
            expected_count=expected_count,
            headless=headless,
            max_scrolls=max_scrolls,
            idle_rounds=idle_rounds,
            wait_timeout_seconds=wait_timeout,
        )

        browser_items = self.downloader.api_client.pop_browser_like_aweme_items() or {}

        collected_items: List[Dict[str, Any]] = []
        seen = set()
        for aweme_id in browser_aweme_ids:
            if aweme_id in seen:
                continue
            seen.add(aweme_id)
            item = browser_items.get(str(aweme_id))
            if item:
                collected_items.append(item)
            else:
                collected_items.append({"aweme_id": aweme_id})

        if not collected_items and paged_error is not None:
            raise paged_error

        logger.info("喜欢列表浏览器回退采集完成，共获取 %d 个作品数据", len(collected_items))
        return collected_items
