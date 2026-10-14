"""
================================================================================
OpenAlgo Independent Multi-Strategy Health Watchdog & Telegram Alert Monitor
================================================================================
Monitors health, heartbeat freshness, PID liveness, API reachability, and
Analyze-mode safety for all active live strategies concurrently:
  - MACD F&O (macdfno_heartbeat.json)
  - EMA Cross (emacross_heartbeat.json)
  - Open Interest F&O (oifno_heartbeat.json)
  - Nifty Covered Call (nifty_covered_call_heartbeat.json)

Strictly observational: ZERO trading decisions, ZERO order placement,
ZERO automatic process restarts.
================================================================================
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(), override=False)
except ImportError:
    pass

# ==============================================================================
# CONFIGURATION & PATHS
# ==============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Known live strategy heartbeat files
REGISTERED_HEARTBEATS: Dict[str, str] = {
    "MACD_FNO": "macdfno_heartbeat.json",
    "EMACROSS": "emacross_heartbeat.json",
    "OI_FNO": "oifno_heartbeat.json",
    "NIFTY_COVERED_CALL": "nifty_covered_call_heartbeat.json",
}

WATCHDOG_LOG_PATH = Path(os.getenv("WATCHDOG_LOG", PROJECT_ROOT / "log/strategies/watchdog.log" if (PROJECT_ROOT / "log").exists() else SCRIPT_DIR / "watchdog.log"))
WATCHDOG_STATE_PATH = Path(os.getenv("WATCHDOG_STATE", SCRIPT_DIR / "watchdog_state.json"))

OPENALGO_HOST = os.getenv("OPENALGO_HOST", os.getenv("HOST_SERVER", "https://vikashiname.in"))
OPENALGO_API_KEY = os.getenv("OPENALGO_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Health Thresholds (Seconds)
WARNING_THRESHOLD_SECONDS = int(os.getenv("HEARTBEAT_WARN_SEC", "120"))    # 2 minutes
CRITICAL_THRESHOLD_SECONDS = int(os.getenv("HEARTBEAT_CRIT_SEC", "240"))   # 4 minutes
POLL_INTERVAL_SECONDS = int(os.getenv("WATCHDOG_POLL_SEC", "30"))          # Check every 30s
REMINDER_INTERVAL_SECONDS = int(os.getenv("ALERT_REMINDER_SEC", "1800"))   # Re-alert every 30m if still critical

IST = timezone(timedelta(hours=5, minutes=30))

# Setup Watchdog Logging
logger = logging.getLogger("WATCHDOG")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s [WATCHDOG-%(levelname)s] %(message)s")
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setFormatter(formatter)
    logger.addHandler(c_handler)


def send_telegram_alert(message: str) -> bool:
    """Dispatches formatted HTML alert to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram credentials not configured; alert printed to log only.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram dispatch failed: {e}")
        return False


def is_market_hours(now_dt: Optional[datetime] = None) -> bool:
    """
    Checks if current time is within NSE Derivatives normal market hours:
    Monday to Friday, 09:15 to 15:30 IST.
    """
    now_ist = now_dt.astimezone(IST) if now_dt else datetime.now(timezone.utc).astimezone(IST)
    if now_ist.weekday() >= 5:  # Saturday (5) or Sunday (6)
        return False
    current_time = now_ist.time()
    market_open = dtime(9, 15)
    market_close = dtime(15, 30)
    return market_open <= current_time <= market_close


def is_process_alive(pid: int) -> bool:
    """Checks whether a process with given PID is alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class HealthWatchdog:
    """
    Multi-strategy watchdog engine. Observes all registered strategy heartbeats
    or a single specified heartbeat, maintaining per-strategy alert suppression.
    """
    def __init__(
        self,
        heartbeat_file: Optional[Path] = None,
        host: str = OPENALGO_HOST,
        api_key: str = OPENALGO_API_KEY,
    ):
        self.explicit_heartbeat = heartbeat_file or (Path(os.getenv("HEARTBEAT_FILE")) if os.getenv("HEARTBEAT_FILE") else None)
        self.host = host
        self.api_key = api_key
        self.state_file = WATCHDOG_STATE_PATH
        # Strategy name -> {"last_state": "INITIAL", "last_alert_time": 0.0}
        self.strategy_states: Dict[str, Dict[str, Any]] = {}
        self.load_state()

    def get_monitored_targets(self) -> Dict[str, Path]:
        """Resolves target heartbeats to monitor."""
        if self.explicit_heartbeat:
            key = self.explicit_heartbeat.stem.replace("_heartbeat", "").upper()
            return {key: self.explicit_heartbeat}

        targets: Dict[str, Path] = {}
        for key, fname in REGISTERED_HEARTBEATS.items():
            targets[key] = SCRIPT_DIR / fname

        # Backward compatibility fallback
        legacy = SCRIPT_DIR / "heartbeat.json"
        if legacy.exists() and "MACD_FNO" not in targets:
            targets["LEGACY_MACD"] = legacy

        return targets

    def load_state(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        # Migrate legacy single-state format if found
                        if "last_state" in data:
                            self.strategy_states["DEFAULT"] = {
                                "last_state": data.get("last_state", "INITIAL"),
                                "last_alert_time": float(data.get("last_alert_time", 0.0)),
                            }
                        else:
                            self.strategy_states = data
            except Exception:
                pass

    def save_state(self):
        try:
            pid = os.getpid()
            tmp_path = self.state_file.with_suffix(f".tmp.{pid}")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.strategy_states, f, indent=2)
            tmp_path.replace(self.state_file)
        except Exception:
            pass

    def check_openalgo_health(self) -> Tuple[bool, str, str]:
        """Checks OpenAlgo reachability and verifies Analyze Mode."""
        try:
            resp = requests.post(f"{self.host}/api/v1/positionbook", json={"apikey": self.api_key}, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                mode = str(data.get("mode", "")).lower()
                if mode == "analyze":
                    return True, "analyze", "OK"
                else:
                    return False, mode, f"CRITICAL: Mode is {mode} (NOT analyze)"
            else:
                return False, "unknown", f"HTTP {resp.status_code}"
        except Exception as e:
            return False, "unknown", str(e)

    def evaluate_target_health(
        self,
        key: str,
        hb_path: Path,
        now: float,
        api_ok: bool,
        api_mode: str,
        api_msg: str,
    ) -> Dict[str, Any]:
        """Evaluates health for a single strategy target."""
        now_dt = datetime.fromtimestamp(now, tz=IST)
        in_market = is_market_hours(now_dt)

        hb_exists = hb_path.exists()
        hb_data = {}
        hb_age = 999999.0
        pid = 0
        proc_alive = False
        strategy_name = key

        if hb_exists:
            try:
                with open(hb_path, "r", encoding="utf-8") as f:
                    hb_data = json.load(f)
                hb_epoch = float(hb_data.get("timestamp_epoch", 0.0))
                hb_age = now - hb_epoch
                pid = int(hb_data.get("pid", 0))
                strategy_name = str(hb_data.get("strategy", key))
                proc_alive = is_process_alive(pid) if pid > 0 else False
            except Exception as e:
                logger.warning(f"Error reading heartbeat file {hb_path.name}: {e}")

        reasons = []
        if not in_market:
            health_state = "OFF_HOURS"
            reasons.append("Outside NSE Market Hours (09:15–15:30 IST)")
        elif not hb_exists:
            health_state = "CRITICAL"
            reasons.append(f"Heartbeat file {hb_path.name} not found")
        elif not proc_alive:
            health_state = "CRITICAL"
            reasons.append(f"Bot PID {pid} is NOT running / dead")
        elif hb_age > CRITICAL_THRESHOLD_SECONDS:
            health_state = "CRITICAL"
            reasons.append(f"Heartbeat is frozen/stale ({hb_age:.1f}s > {CRITICAL_THRESHOLD_SECONDS}s)")
        elif not api_ok:
            health_state = "CRITICAL" if "NOT analyze" in api_msg else "WARNING"
            reasons.append(f"OpenAlgo API issue: {api_msg}")
        elif hb_age > WARNING_THRESHOLD_SECONDS:
            health_state = "WARNING"
            reasons.append(f"Heartbeat delayed ({hb_age:.1f}s > {WARNING_THRESHOLD_SECONDS}s)")
        else:
            health_state = "HEALTHY"
            reasons.append("All health gates OK")

        return {
            "key": key,
            "strategy": strategy_name,
            "heartbeat_file": hb_path.name,
            "timestamp_ist": now_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            "health_state": health_state,
            "in_market_hours": in_market,
            "heartbeat_age_seconds": round(hb_age, 1),
            "pid": pid,
            "process_alive": proc_alive,
            "api_reachable": api_ok,
            "openalgo_mode": api_mode,
            "active_positions": hb_data.get("active_positions_count", 0),
            "last_candle": hb_data.get("last_completed_candle", "N/A"),
            "reasons": reasons,
        }

    def evaluate_health(self, now_epoch: Optional[float] = None) -> Dict[str, Any]:
        """Runs health evaluation across all monitored targets."""
        now = now_epoch if now_epoch is not None else time.time()
        api_ok, api_mode, api_msg = self.check_openalgo_health()

        targets = self.get_monitored_targets()
        reports = {}
        for key, path in targets.items():
            reports[key] = self.evaluate_target_health(key, path, now, api_ok, api_mode, api_msg)

        # Aggregate summary state: worst-case health
        all_states = [r["health_state"] for r in reports.values()]
        if "CRITICAL" in all_states:
            aggregate_state = "CRITICAL"
        elif "WARNING" in all_states:
            aggregate_state = "WARNING"
        elif "OFF_HOURS" in all_states and all(s in ["OFF_HOURS", "HEALTHY"] for s in all_states):
            aggregate_state = "OFF_HOURS"
        else:
            aggregate_state = "HEALTHY"

        primary = next(iter(reports.values())) if reports else {}
        return {
            "timestamp_ist": datetime.fromtimestamp(now, tz=IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "health_state": aggregate_state,
            "api_reachable": api_ok,
            "openalgo_mode": api_mode,
            "strategies": reports,
            # Backward compatibility fields for test harnesses
            "strategy": primary.get("strategy", "MACD_FNO"),
            "heartbeat_age_seconds": primary.get("heartbeat_age_seconds", 0.0),
            "pid": primary.get("pid", 0),
            "process_alive": primary.get("process_alive", False),
            "active_positions": primary.get("active_positions", 0),
            "last_candle": primary.get("last_candle", "N/A"),
            "reasons": primary.get("reasons", []),
        }

    def process_health_check(self, now_epoch: Optional[float] = None) -> Dict[str, Any]:
        """Runs evaluation, handles per-strategy transitions, and sends deduplicated alerts."""
        now = now_epoch if now_epoch is not None else time.time()
        summary = self.evaluate_health(now)

        for key, report in summary["strategies"].items():
            current_state = report["health_state"]
            reasons_text = ", ".join(report["reasons"])
            strategy_name = report["strategy"]

            logger.info(
                f"[{report['timestamp_ist']}] [{key:<10}] State: {current_state:<10} | "
                f"HB Age: {report['heartbeat_age_seconds']}s | PID Alive: {report['process_alive']} | "
                f"API: {report['openalgo_mode']} | Reason: {reasons_text}"
            )

            st_state = self.strategy_states.get(key, {"last_state": "INITIAL", "last_alert_time": 0.0})
            last_state = st_state.get("last_state", "INITIAL")
            last_alert_time = float(st_state.get("last_alert_time", 0.0))

            should_alert = False
            alert_title = ""

            # Transition: Recovery to HEALTHY
            if current_state == "HEALTHY" and last_state in ["WARNING", "CRITICAL"]:
                should_alert = True
                alert_title = "🟢 <b>WATCHDOG: STRATEGY HEALTH RESTORED</b>"

            # Transition: Entering WARNING or CRITICAL
            elif current_state in ["WARNING", "CRITICAL"] and last_state != current_state:
                should_alert = True
                alert_title = f"🚨 <b>WATCHDOG ALERT: {current_state}</b>"

            # Periodic reminder if remaining in CRITICAL during market hours
            elif current_state == "CRITICAL" and (now - last_alert_time) >= REMINDER_INTERVAL_SECONDS:
                should_alert = True
                alert_title = "🚨 <b>WATCHDOG REMINDER: STILL CRITICAL</b>"

            if should_alert:
                msg = (
                    f"{alert_title}\n\n"
                    f"• <b>Timestamp:</b> {report['timestamp_ist']}\n"
                    f"• <b>Strategy:</b> <code>{strategy_name}</code>\n"
                    f"• <b>Health State:</b> <b>{current_state}</b>\n"
                    f"• <b>Process PID:</b> {report['pid']} (Alive: {report['process_alive']})\n"
                    f"• <b>Heartbeat Age:</b> {report['heartbeat_age_seconds']}s\n"
                    f"• <b>Last Candle:</b> {report['last_candle']}\n"
                    f"• <b>OpenAlgo API Mode:</b> {report['openalgo_mode'].upper()}\n"
                    f"• <b>Reason:</b> {reasons_text}\n\n"
                    f"<i>ℹ️ Note: Observational Watchdog only. ZERO trading actions taken.</i>"
                )
                send_telegram_alert(msg)
                last_alert_time = now

            self.strategy_states[key] = {
                "last_state": current_state,
                "last_alert_time": last_alert_time,
            }

        self.save_state()
        return summary

    def run_loop(self):
        """Continuous watchdog polling loop."""
        targets = self.get_monitored_targets()
        logger.info(
            f"🐕 Starting Multi-Strategy Watchdog Loop (Interval: {POLL_INTERVAL_SECONDS}s, "
            f"Monitoring {len(targets)} strategies: {', '.join(targets.keys())})... Press Ctrl+C to stop.\n"
        )
        while True:
            try:
                self.process_health_check()
            except KeyboardInterrupt:
                logger.info("🛑 Watchdog stopped by user.")
                break
            except Exception as e:
                logger.error(f"❌ Unhandled exception in watchdog: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Independent Multi-Strategy Health Watchdog")
    parser.add_argument("--check-once", action="store_true", help="Run single health check and exit")
    parser.add_argument("--heartbeat-file", type=str, default="", help="Optional single heartbeat file to monitor")
    args = parser.parse_args()

    hb_override = Path(args.heartbeat_file) if args.heartbeat_file else None
    wd = HealthWatchdog(heartbeat_file=hb_override)
    if args.check_once:
        rep = wd.process_health_check()
        print(json.dumps(rep, indent=2))
    else:
        wd.run_loop()
