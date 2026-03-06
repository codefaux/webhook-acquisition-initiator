from dataclasses import dataclass
from typing import Optional


@dataclass
class ServarrConfig:
    sonarr_url: str
    sonarr_api: str
    sonarr_in_path: str
    radarr_url: Optional[str] = None
    radarr_api: Optional[str] = None


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
    ripeness_per_day: int = 4


@dataclass
class DownloadQueueConfig(BaseQueueConfig):
    interval: int = 30


@dataclass
class DecisionQueueConfig(BaseQueueConfig):
    matcher_threads: int = 8
    cache_ttl: int = 5
    overwrite_eps: bool = False
    honor_unmon_eps: bool = True
    honor_unmon_series: bool = True


@dataclass
class ManualInterventionThreadConfig:
    file: str
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
class ExampleConfig:
    user: str
    host: str = "localhost"
    port: int = 5432
    proxy: Optional[str] = None


@dataclass
class WAIConfigRoot:
    wai: WAIConfig
    arr: ServarrConfig
    aging_queue: AgingQueueConfig
    download_queue: DownloadQueueConfig
    decision_queue: DecisionQueueConfig
    manual_intervention: ManualInterventionThreadConfig
    telegram: TelegramConfig
    ytdlp: YtdlpConfig
    debug: DebugConfig
    example: Optional[ExampleConfig] = None
