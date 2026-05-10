#!/usr/bin/env python3
"""Compatibility shim during the HomeOps AI Hermes port.

The helper has been renamed to hermes_config_helper.py, but inherited tests and
runtime scripts still import/call oc_config_helper while the full runtime port is
in progress. Remove this shim once run.sh and tests are Hermes-native.
"""
try:
    from . import hermes_config_helper as _helper  # type: ignore
    from .hermes_config_helper import *  # type: ignore # noqa: F401,F403
    from .hermes_config_helper import main  # type: ignore
except ImportError:  # script execution from add-on root/container
    import hermes_config_helper as _helper  # type: ignore
    from hermes_config_helper import *  # type: ignore # noqa: F401,F403
    from hermes_config_helper import main  # type: ignore

if __name__ == "__main__":
    main()


def __getattr__(name):
    return getattr(_helper, name)

def __setattr__(name, value):
    setattr(_helper, name, value)
    globals()[name] = value


def _sync_paths_to_helper():
    if "CONFIG_PATH" in globals():
        _helper.CONFIG_PATH = globals()["CONFIG_PATH"]
    if "EXEC_APPROVALS_PATH" in globals():
        _helper.EXEC_APPROVALS_PATH = globals()["EXEC_APPROVALS_PATH"]

def apply_gateway_settings(*args, **kwargs):
    _sync_paths_to_helper()
    return _helper.apply_gateway_settings(*args, **kwargs)

def write_config(cfg):
    _sync_paths_to_helper()
    return _helper.write_config(cfg)

def read_config():
    _sync_paths_to_helper()
    return _helper.read_config()
