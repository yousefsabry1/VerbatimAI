from app.core.cuda_init import register_nvidia_dll_directories

# Automatically register CUDA DLL directories when app package is loaded
register_nvidia_dll_directories()
