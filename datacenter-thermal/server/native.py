"""Small ctypes bridge. Python owns handles; C++ owns simulation memory."""
import ctypes as ct
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = {"cpu": 0, "openmp": 1, "cuda": 2}


class Stats(ct.Structure):
    _fields_ = [(key, ct.c_double) for key in
                ("maximum", "average", "hotspots", "throughput", "step", "milliseconds")]

    def as_dict(self):
        result = {key: getattr(self, key) for key, _ in self._fields_}
        for key in ("hotspots", "step"):
            result[key] = int(result[key])
        return result


class Native:
    def __init__(self):
        # Python 3.8+ needs explicit Windows search directories for DLL dependencies.
        self.dll_dirs = []
        if os.name == "nt":
            for path in os.environ.get("PATH", "").split(os.pathsep):
                if path and Path(path).is_dir():
                    try:
                        self.dll_dirs.append(os.add_dll_directory(str(Path(path).resolve())))
                    except OSError:
                        pass
        names = ("thermal.dll", "libthermal.dll", "libthermal.so", "libthermal.dylib")
        candidates = [ROOT / "build" / folder / name
                      for folder in ("", "Release") for name in names]
        if os.environ.get("THERMAL_LIBRARY"):
            candidates = [Path(os.environ["THERMAL_LIBRARY"])]
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            raise RuntimeError("Native library missing. Build the C++ core first; see README.md.")
        try:
            self.lib = ct.CDLL(str(path.resolve()))
        except OSError as exc:
            raise RuntimeError(f"Cannot load {path}. Use 64-bit Python and compiler, and put "
                               "the compiler/OpenMP DLL directory on PATH. " + str(exc)) from exc
        pfloat, pint = ct.POINTER(ct.c_float), ct.POINTER(ct.c_int)
        signatures = {
            "dc_create": ([ct.c_int, ct.c_int], ct.c_void_p),
            "dc_destroy": ([ct.c_void_p], None),
            "dc_step": ([ct.c_void_p, ct.c_int], ct.c_int),
            "dc_configure": ([ct.c_void_p, ct.c_float, ct.c_float, ct.c_int], ct.c_int),
            "dc_modify": ([ct.c_void_p, pint, ct.c_int, ct.c_int] + [ct.c_float] * 4, ct.c_int),
            "dc_frame": ([ct.c_void_p, pfloat, pfloat, pfloat, ct.POINTER(Stats)], ct.c_int),
            "dc_stats": ([ct.c_void_p, ct.POINTER(Stats)], ct.c_int),
            "dc_error": ([], ct.c_char_p), "dc_omp_threads": ([], ct.c_int),
            "dc_cuda_available": ([], ct.c_int), "dc_gpu_name": ([], ct.c_char_p),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, result

    def check(self, code):
        if code != 0:
            raise RuntimeError(self.lib.dc_error().decode("utf-8", errors="replace"))

    def info(self):
        return {"cuda_available": bool(self.lib.dc_cuda_available()),
                "gpu": self.lib.dc_gpu_name().decode(),
                "openmp_threads": self.lib.dc_omp_threads(), "block_size": [16, 16]}


class Simulation:
    def __init__(self, native, size, backend):
        self.native, self.size, self.backend = native, size, backend
        self.handle = native.lib.dc_create(size, BACKENDS[backend])
        if not self.handle:
            native.check(-1)
        self.ambient, self.threshold, self.tiled = 25, 85, False

    def close(self):
        if self.handle:
            self.native.lib.dc_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def configure(self, ambient=25, threshold=85, tiled=False):
        self.native.check(self.native.lib.dc_configure(self.handle, ambient, threshold, int(tiled)))
        self.ambient, self.threshold, self.tiled = ambient, threshold, tiled

    def step(self, count=1):
        self.native.check(self.native.lib.dc_step(self.handle, count))

    def stats(self):
        result = Stats()
        self.native.check(self.native.lib.dc_stats(self.handle, ct.byref(result)))
        return result.as_dict()

    def modify(self, indices, values):
        # The C API also deduplicates, so direct callers are safe too.
        indices = sorted(set(indices))
        selection = (ct.c_int * len(indices))(*indices)
        fields = ("temperature", "workload", "cooling", "delta")
        mask = sum(1 << bit for bit, name in enumerate(fields) if name in values)
        args = [values.get(name, 0) for name in fields]
        self.native.check(self.native.lib.dc_modify(self.handle, selection, len(indices), mask, *args))

    def frame(self):
        array = ct.c_float * (self.size * self.size)
        temperature, workload, cooling, stats = array(), array(), array(), Stats()
        self.native.check(self.native.lib.dc_frame(self.handle, temperature, workload, cooling, ct.byref(stats)))
        return {"size": self.size, "backend": self.backend,
                "temperature": list(temperature), "workload": list(workload), "cooling": list(cooling),
                "stats": stats.as_dict(), "ambient": self.ambient,
                "threshold": self.threshold, "tiled": self.tiled}
