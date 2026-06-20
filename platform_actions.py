"""Backward-compatible import path for the desktop automation helpers.

Re-exports the full desk_platform namespace (including underscore helpers) so
existing `from platform_actions import ...` call sites keep working.
"""
from desk_platform import _impl as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
