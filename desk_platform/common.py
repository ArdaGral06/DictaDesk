"""Thin re-export shim. Real implementation lives in desk_platform._impl.

Kept for backward-compatible imports like `from desk_platform.common import X`.
"""
from desk_platform import _impl as _impl

globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
