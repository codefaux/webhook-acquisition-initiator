from dataclasses import dataclass
from typing import Optional


@dataclass
class ServarrConfig:
    in_path: str
    api: str
    url: str = "http://localhost:8989"


@dataclass
class WAIConfig:
    output_path: str
    temp_path: str
    data_dir: str = "./data"
    conf_dir: str = "./conf"


@dataclass
class BaseQueueConfig:
    file: str
    interval: int = 10
    flip_flop: Optional[bool] = False
    run: bool = True


@dataclass
class AgingQueueConfig(BaseQueueConfig):
    file: str = "aging_queue.json"
    ripeness_per_day: int = 4


@dataclass
class DownloadQueueConfig(BaseQueueConfig):
    file: str = "download_queue.json"
    interval: int = 30


@dataclass
class DecisionQueueConfig(BaseQueueConfig):
    file: str = "decision_queue.json"
    matcher_threads: int = 8
    cache_ttl: int = 5
    overwrite_eps: bool = False
    honor_unmon_eps: bool = True
    honor_unmon_series: bool = True


@dataclass
class ManualInterventionThreadConfig:
    file: str = "manual_intervention.json"
    run: bool = True


@dataclass
class DebugConfig:
    debug_print: bool = False
    decision_lower: int = 0
    decision_upper: int = 0
    debug_break: bool = False
    debug_safe: bool = False
    export_dir: Optional[str] = None


@dataclass
class TelegramConfig:
    token: str
    chat_id: int
    run: bool = True
    known_chats_file: str = "known_chats.json"
    notify_chats_file: str = "notify_chats.json"


@dataclass
class YtdlpConfig:
    netrc_file: Optional[str] = None
    conf_file: Optional[str] = None
    cookies_file: Optional[str] = None


@dataclass
class WAIConfigRoot:
    wai: WAIConfig
    sonarr: ServarrConfig
    aging_queue: AgingQueueConfig
    download_queue: DownloadQueueConfig
    decision_queue: DecisionQueueConfig
    manual_intervention: ManualInterventionThreadConfig
    telegram: TelegramConfig
    ytdlp: YtdlpConfig
    debug: Optional[DebugConfig] = None
    radarr: Optional[ServarrConfig] = None
