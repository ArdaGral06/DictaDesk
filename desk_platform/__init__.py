"""Windows desktop automation package.

The implementation lives in desk_platform._impl as a single namespace to avoid
the circular dependencies that the historical line-range split introduced. The
submodules (common/automation/gui/files) remain as thin re-export shims for
backward-compatible import paths.
"""
from desk_platform import _impl as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})

__all__ = [name for name in globals() if not name.startswith("_")]
