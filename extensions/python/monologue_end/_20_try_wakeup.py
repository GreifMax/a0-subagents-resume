from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import config


class TryWakeupParent(Extension):
    async def execute(self, **kwargs):
        if not self.agent:
            return
        try:
            if not config.get_settings(self.agent).get("wakeup", True):
                return
            from usr.plugins.subagent_resume.helpers import wakeup

            wakeup.try_wake_parent(self.agent)
        except Exception:
            pass
