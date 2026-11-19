import os
import sys
import site
import logging
from typing import List

logger = logging.getLogger(__name__)

_NVIDIA_DIRS_REGISTERED = False


def register_nvidia_dll_directories() -> List[str]:
    """
    Discovers and registers NVIDIA CUDA 12 runtime DLL directories
    (cublas, cudnn, cuda_nvrtc) in Python site-packages on Windows.
    This resolves dynamic library loading issues like:
    'RuntimeError: Library cublas64_12.dll is not found or cannot be loaded'
    """
    global _NVIDIA_DIRS_REGISTERED
    if _NVIDIA_DIRS_REGISTERED:
        return []

    added_paths: List[str] = []

    if sys.platform != "win32":
        _NVIDIA_DIRS_REGISTERED = True
        return added_paths

    search_roots = []
    try:
        search_roots.extend(site.getsitepackages())
    except Exception:
        pass
    if site.getusersitepackages():
        search_roots.append(site.getusersitepackages())

    # Add python installation directory, virtualenv, and base interpreter if not in search roots
    py_dir = os.path.dirname(sys.executable)
    search_roots.append(os.path.join(py_dir, "Lib", "site-packages"))
    search_roots.append(os.path.join(sys.prefix, "Lib", "site-packages"))
    if hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix:
        search_roots.append(os.path.join(sys.base_prefix, "Lib", "site-packages"))

    target_packages = ["cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"]

    for root in set(search_roots):
        nvidia_root = os.path.join(root, "nvidia")
        if not os.path.isdir(nvidia_root):
            continue

        for pkg in target_packages:
            bin_dir = os.path.join(nvidia_root, pkg, "bin")
            if os.path.isdir(bin_dir) and bin_dir not in added_paths:
                try:
                    os.add_dll_directory(bin_dir)
                    added_paths.append(bin_dir)
                    logger.info("Registered NVIDIA DLL directory: %s", bin_dir)
                except Exception as e:
                    logger.warning("Failed to add DLL directory %s: %s", bin_dir, e)

    if added_paths:
        # Also prepend to PATH environment variable for legacy dlopen callers
        current_path = os.environ.get("PATH", "")
        new_path_entries = [p for p in added_paths if p not in current_path]
        if new_path_entries:
            os.environ["PATH"] = os.pathsep.join(new_path_entries) + os.pathsep + current_path
            logger.info("Prepended %d NVIDIA directories to PATH", len(new_path_entries))

    _NVIDIA_DIRS_REGISTERED = True
    return added_paths
