#!/usr/bin/env python3
"""Compatibility shim during the HomeOps AI Hermes port.

The helper has been renamed to hermes_config_helper.py, but inherited tests and
runtime scripts still import/call oc_config_helper while the full runtime port is
in progress. Remove this shim once run.sh and tests are Hermes-native.
"""
try:
    from .hermes_config_helper import *  # type: ignore # noqa: F401,F403
    from .hermes_config_helper import main  # type: ignore
except ImportError:  # script execution from add-on root/container
    from hermes_config_helper import *  # type: ignore # noqa: F401,F403
    from hermes_config_helper import main  # type: ignore

if __name__ == "__main__":
    main()
