"""Run from project root: python -m unittest discover -s tests -v"""
import math
import os
import time
import unittest

os.environ.setdefault("OMP_NUM_THREADS", "4")
from server.native import Native, Simulation
from server.app import app


def cell_hash(index, step):
    """Independent Python reference for the specified unsigned 32-bit hash."""
    mask = 0xFFFFFFFF
    x = index ^ ((step * 747796405 + 2891336453) & mask)
    x = ((x ^ (x >> 16)) * 2246822519) & mask
    x = ((x ^ (x >> 13)) * 3266489917) & mask
    return x ^ (x >> 16)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = Native()

    def test_equation_and_edges_against_independent_reference(self):
        # Distinct corner values reveal incorrect neighbor averaging/wraparound.
        for backend in ["cpu", "openmp"] + (["cuda"] if self.native.info()["cuda_available"] else []):
            with self.subTest(backend=backend), Simulation(self.native, 2, backend) as sim:
                temperatures = [20, 40, 60, 90]
                for i, t in enumerate(temperatures):
                    sim.modify([i], {"temperature": t, "workload": 70, "cooling": 20})
                sim.configure(ambient=30, threshold=55)
                sim.step()
                result = sim.frame()
                expected = []
                for i, neighbors in enumerate(((1, 2), (0, 3), (0, 3), (1, 2))):
                    work = 70 + cell_hash(i, 0) % 5 - 2
                    temperature = temperatures[i] + .2 * (sum(temperatures[j] for j in neighbors) / 2 - temperatures[i]) + .01 * work - .01 * 15
                    expected.append(temperature)
                    self.assertAlmostEqual(result["temperature"][i], temperature, delta=0.00002)
                    self.assertEqual(result["workload"][i], work)
                self.assertEqual(result["stats"]["hotspots"], sum(t > 55 for t in expected))

    def test_backends_match_full_grids_and_statistics(self):
        for size in (1, 2, 17, 64):
            backends = [("cpu", False), ("openmp", False)]
            if self.native.info()["cuda_available"]:
                backends += [("cuda", False), ("cuda", True)]
            reference = None
            for backend, tiled in backends:
                with self.subTest(size=size, backend=backend, tiled=tiled), Simulation(self.native, size, backend) as sim:
                    sim.configure(ambient=35, threshold=80, tiled=tiled)
                    sim.modify(list(range(0, size * size, 3)), {"temperature": 92, "workload": 97, "cooling": 10})
                    sim.step(75)
                    result = sim.frame()
                    if reference is None:
                        reference = result
                        continue
                    for field in ("temperature", "workload", "cooling"):
                        self.assertLessEqual(max(abs(a - b) for a, b in zip(reference[field], result[field])), .001)
                    for field in ("maximum", "average", "throughput", "hotspots", "step"):
                        self.assertAlmostEqual(reference["stats"][field], result["stats"][field], delta=.001)

    def test_duplicate_edits_and_invalid_indices_are_atomic(self):
        with Simulation(self.native, 2, "cpu") as sim:
            sim.modify([1, 1, 1], {"delta": 10})
            self.assertEqual(sim.frame()["temperature"], [25, 35, 25, 25])
            with self.assertRaises(RuntimeError):
                sim.modify([0, 4], {"temperature": 99})
            self.assertEqual(sim.frame()["temperature"], [25, 35, 25, 25])

    def test_throttle_threshold_is_separate_from_hotspot_threshold(self):
        with Simulation(self.native, 2, "cpu") as sim:
            sim.modify([0, 1, 2, 3], {"temperature": 86, "workload": 100})
            sim.configure(threshold=100)
            self.assertEqual(sim.stats()["hotspots"], 0)
            self.assertEqual(sim.stats()["throughput"], 280)
            sim.modify([0], {"temperature": 85})
            self.assertEqual(sim.stats()["throughput"], 310)

    def test_ambient_shifts_cooling_by_expected_amount(self):
        with Simulation(self.native, 1, "cpu") as cold, Simulation(self.native, 1, "cpu") as warm:
            cold.configure(ambient=25)
            warm.configure(ambient=35)
            cold.step(); warm.step()
            self.assertAlmostEqual(warm.stats()["maximum"] - cold.stats()["maximum"], .1, delta=0.00001)

    def test_cuda_is_explicitly_unavailable_or_real(self):
        if not self.native.info()["cuda_available"]:
            with self.assertRaisesRegex(RuntimeError, "GPU not available"):
                Simulation(self.native, 64, "cuda")
        else:
            with Simulation(self.native, 64, "cuda") as sim:
                sim.step()
                self.assertGreater(sim.stats()["milliseconds"], 0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.assertEqual(self.client.post("/init", json={"size": 64, "backend": "cpu", "ambient": 25, "threshold": 85, "tiled": False}).status_code, 200)

    def test_rectangular_batch_and_settings(self):
        response = self.client.post("/modify", json={"rectangle": {"r0": 1, "c0": 2, "r1": 3, "c1": 4}, "values": {"temperature": 100, "workload": 100}})
        self.assertEqual(response.json["updated"], 9)
        self.assertEqual(response.json["stats"]["hotspots"], 9)
        response = self.client.post("/step", json={"n": 0, "threshold": 105})
        self.assertEqual(response.json["stats"]["hotspots"], 0)
        frame = self.client.get("/frame").json
        self.assertEqual(frame["temperature"][66], 100)
        self.assertEqual(frame["temperature"][65], 25)
        self.assertEqual(frame["stats"]["step"], 0)

    def test_invalid_payloads_are_rejected(self):
        cases = [("/modify", {"indices": [-1], "values": {"temperature": 40}}),
                 ("/modify", {"indices": [], "values": {"cooling": 20}}),
                 ("/modify", {"indices": [1], "values": {"workload": 101}}),
                 ("/modify", {"indices": [True], "values": {"cooling": 20}}),
                 ("/modify", {"rectangle": {"r0": 4, "r1": 2, "c0": 0, "c1": 2}, "values": {"cooling": 20}}),
                 ("/step", {"n": -1}), ("/step", {"n": 1.5}),
                 ("/step", {"n": 0, "ambient": float("nan")}),
                 ("/init", {"size": 65}), ("/init", {"backend": []}),
                 ("/preset", {"name": "unknown"}), ("/benchmark", {"sizes": []})]
        for endpoint, data in cases:
            with self.subTest(endpoint=endpoint, data=data):
                self.assertEqual(self.client.post(endpoint, json=data).status_code, 400)

    def test_every_preset(self):
        for name in ("normal", "hot-aisle", "cooling-failure", "cooling-boost", "random-spikes"):
            response = self.client.post("/preset", json={"name": name})
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.json["indices"]), 0)

    def test_pages_and_local_chart_asset(self):
        for path in ("/", "/benchmark-page", "/static/app.js", "/static/style.css", "/static/vendor/chart.umd.min.js"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)

    def test_benchmark_completes_and_keeps_live_state(self):
        self.client.post("/modify", json={"indices": [10], "values": {"temperature": 77}})
        response = self.client.post("/benchmark", json={"sizes": [128], "steps": 3})
        self.assertEqual(response.status_code, 202)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job = self.client.get("/benchmark").json
            if job["status"] != "running":
                break
            time.sleep(.05)
        self.assertEqual(job["status"], "done", job)
        self.assertTrue(job["rows"][0]["verified"])
        self.assertTrue(math.isfinite(job["rows"][0]["runs"]["cpu"]["ms"]))
        frame = self.client.get("/frame").json
        self.assertEqual(frame["temperature"][10], 77)
        self.assertEqual(frame["stats"]["step"], 0)


if __name__ == "__main__":
    unittest.main()
