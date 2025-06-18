# pydantic LogCluster, AlertPayload
import os
from typing import List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    """
    Loads env vars when *explicitly* instantiated.
    Defaults keep unit-tests happy when env vars aren’t set.
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    log_bucket: str = Field("dummy-bucket", alias='LOG_BUCKET')
    openai_api_key: str = Field("dummy-api-key", alias='OPENAI_API_KEY')
    openai_model: str = Field("gpt-3.5-turbo", alias='OPENAI_MODEL')

# Helper: call inside Lambdas, *not* at import time
def get_settings() -> AppSettings:
    return AppSettings()

class LogCluster(BaseModel):
    """
    a cluster of similar log entries
    """
    # # it's would be a signature that represent error type
    signature: str
    # # it would count the number of same error type or similar pattern of error that occur
    count: int
    # # list of aw log messages
    log_samples: List[str]
    # # example og use for summaries
    representative_log: str
