from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import config


class WakeupSweeper(Extension):
    async def execute(self, **kwargs):
        try:
            if not config.get_settings(None).get("wakeup", True):
                return
            from usr.plugins.subagent_resume.helpers import wakeup

            wakeup.sweep()
        except Exception:
            pass
