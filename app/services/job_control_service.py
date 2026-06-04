import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONTROL_FILENAME = "job_control.json"


class JobCancelled(RuntimeError):
    pass


def read_job_control(job_dir: Path) -> dict[str, Any]:
    path = job_dir / CONTROL_FILENAME
    if not path.exists() or not path.is_file():
        return _default_control()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_control()
    if not isinstance(data, dict):
        return _default_control()
    return {**_default_control(), **data}


def write_job_control(job_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = read_job_control(job_dir)
    sequence = int(current.get("action_seq") or 0)
    if updates.get("requested_action") or updates.get("last_action"):
        sequence += 1
    data = {**current, **updates, "action_seq": sequence, "updated_at": _utc_now()}
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / CONTROL_FILENAME
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)
    return data


def request_job_action(job_dir: Path, action: str) -> dict[str, Any]:
    normalized_action = str(action or "").strip()
    updates: dict[str, Any] = {
        "requested_action": normalized_action,
        "last_action": normalized_action,
    }
    if normalized_action == "cancel":
        updates.update(
            {
                "cancel_requested": True,
                "pause_requested": False,
                "rerun_requested": "",
                "control_status": "cancelling",
                "control_message": "正在取消任务。",
            }
        )
    elif normalized_action == "pause":
        updates.update(
            {
                "pause_requested": True,
                "control_status": "pausing",
                "control_message": "正在暂停任务，当前步骤完成后会停在安全节点。",
            }
        )
    elif normalized_action == "resume":
        updates.update(
            {
                "pause_requested": False,
                "control_status": "running",
                "control_message": "任务已继续执行。",
                "resumed_at": _utc_now(),
            }
        )
    elif normalized_action.startswith("rerun") or normalized_action.startswith("retry"):
        updates.update(
            {
                "cancel_requested": False,
                "pause_requested": False,
                "rerun_requested": normalized_action,
                "control_status": "rerun_requested",
                "control_message": "已提交重跑请求。",
            }
        )
    return write_job_control(job_dir, updates)


def reset_runtime_control(job_dir: Path, *, status: str = "running", message: str = "") -> dict[str, Any]:
    return write_job_control(
        job_dir,
        {
            "cancel_requested": False,
            "pause_requested": False,
            "requested_action": "",
            "rerun_requested": "",
            "control_status": status,
            "control_message": message,
        },
    )


def checkpoint_job_control(job_dir: Path) -> None:
    marked_paused = False
    while True:
        data = read_job_control(job_dir)
        if data.get("cancel_requested"):
            write_job_control(
                job_dir,
                {
                    "pause_requested": False,
                    "control_status": "cancelled",
                    "control_message": "任务已取消。",
                },
            )
            raise JobCancelled("任务已取消。")
        if not data.get("pause_requested"):
            if marked_paused:
                write_job_control(
                    job_dir,
                    {
                        "control_status": "running",
                        "control_message": "任务已继续执行。",
                    },
                )
            return
        if not marked_paused or data.get("control_status") != "paused":
            write_job_control(
                job_dir,
                {
                    "control_status": "paused",
                    "control_message": "任务已暂停，点击继续后会从当前安全节点恢复。",
                    "paused_at": _utc_now(),
                },
            )
            marked_paused = True
        time.sleep(0.5)


def _default_control() -> dict[str, Any]:
    return {
        "cancel_requested": False,
        "pause_requested": False,
        "requested_action": "",
        "last_action": "",
        "rerun_requested": "",
        "control_status": "idle",
        "control_message": "",
        "action_seq": 0,
        "paused_at": None,
        "resumed_at": None,
        "updated_at": None,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
