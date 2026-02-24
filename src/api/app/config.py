from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str = "db-doc"
    cosmos_container: str = "jobs"
    blob_connection_string: str
    blob_container: str

settings = Settings()