"""Shared pytest fixtures."""

import os

# Ensure Qt tests run headless on Linux CI / dev boxes without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
