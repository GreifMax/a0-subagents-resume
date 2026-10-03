from helpers.plugins import get_plugin_config

PLUGIN_NAME = "subagent_resume"

DEFAULTS = {
    "enabled": True,
    "restore_links": True,
    "repair_dangling": True,
    "rehydrate_parallel": True,
    "inject_hints": True,
    "wakeup": True,
}


def get_settings(agent=None) -> dict:
    """Resolve plugin settings with defaults; never raises."""
    settings = dict(DEFAULTS)
    try:
        config = get_plugin_config(PLUGIN_NAME, agent=agent)
        if isinstance(config, dict):
            settings.update(
                {key: value for key, value in config.items() if key in DEFAULTS}
            )
    except Exception:
        pass
    return settings


def is_enabled(agent=None) -> bool:
    return bool(get_settings(agent).get("enabled", True))
