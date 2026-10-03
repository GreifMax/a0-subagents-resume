"""Lifecycle hooks for the subagent_resume plugin.

The plugin is pure in-process behavior with no external dependencies, files
or registrations: nothing to install, update or uninstall.
"""


def install():
    return True


def pre_update():
    return True


def uninstall():
    return True
