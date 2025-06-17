# pydantic LogCluster, AlertPayload
import os
from typing import List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    """
    It would manages env var using Pydantic BaseSettings
    it would automatically read .env file
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')
    log_bucket: str = Field(..., alias='LOG_BUCKET')
    openai_api_key: str = Field(..., alias='OPENAI_API_KEY')
    openai_model: str = Field("gpt-3.5-turbo", alias='OPENAI_MODEL')

settings = AppSettings()

class LogCluster(BaseModel):
    """
    a cluster of similar log entries
    """
    # it's would be a signature that represent error type
    signature: str
    # it would count the number of same error type or similar pattern of error that occur
    count: int
    # list of aw log messages
    log_sample: List[str]
    # example og use for summaries
    representative_log: str