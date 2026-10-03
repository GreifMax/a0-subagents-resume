from helpers.extension import Extension

from usr.plugins.subagent_resume.helpers import config


class WakeupArgPrompt(Extension):
    def execute(self, system_prompt: list = [], **kwargs):
        try:
            if not self.agent:
                return
            if not config.get_settings(self.agent).get("wakeup", True):
                return
            fragment = self.agent.read_prompt("subagent_resume.wakeup.md")
            if fragment:
                system_prompt.append(fragment)
        except Exception:
            pass
