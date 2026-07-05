"""
Tests the atomic utilities.
"""

import os
import pytest
import random
import subprocess
import sys
import tempfile
import threading
import time

from util.atomic import AtomicEdit, Queue

FILE_PATH = f"{os.path.dirname(os.path.abspath(__file__))}/test-lock-file.txt"
FILE2_PATH = f"{os.path.dirname(os.path.abspath(__file__))}/test-lock-file2.txt"
LOCK_PATH = f"{FILE_PATH}.lock"


@pytest.fixture(autouse=True)
def test_setup_teardown() -> None:
    """
    Code run before and after each test. Used to configure the environment
    variables.
    """

    # Before the test.
    if os.path.exists(FILE_PATH):
        os.remove(FILE_PATH)
    if os.path.exists(FILE2_PATH):
        os.remove(FILE2_PATH)
    if os.path.exists(LOCK_PATH):
        os.rmdir(LOCK_PATH)

    # Run the tests.
    yield

    # After the test.
    if os.path.exists(FILE_PATH):
        os.remove(FILE_PATH)
    if os.path.exists(FILE2_PATH):
        os.remove(FILE2_PATH)
    if os.path.exists(LOCK_PATH):
        os.rmdir(LOCK_PATH)


class TestAtomicEdit:
    def test_basic(self: "TestAtomicEdit") -> None:
        """
        Basic functionality, it should act as a file.
        """

        # Write to the file.
        assert not os.path.exists(FILE_PATH)
        with AtomicEdit(FILE_PATH) as f:
            f.write_all("test_basic")

        # Read from the file.
        assert os.path.exists(FILE_PATH)
        with AtomicEdit(FILE_PATH) as f:
            assert f.read_all() == "test_basic"

    def test_read_empty(self: "TestAtomicEdit") -> None:
        """
        Reading from a missing file yields an error.
        """

        with AtomicEdit(FILE_PATH) as f:
            try:
                f.read_all()
                raise RuntimeError()
            except FileNotFoundError:
                pass

    def test_lock_state(self: "TestAtomicEdit") -> None:
        """
        The lock file exists within the "with" block, but not outside (if
        single-process).
        """

        assert not os.path.exists(LOCK_PATH)
        with AtomicEdit(FILE_PATH) as f:
            assert os.path.exists(LOCK_PATH)
        assert not os.path.exists(LOCK_PATH)

    def test_lock_cleared_error(self: "TestAtomicEdit") -> None:
        """
        Even if an error occurs during the "with" block, the lock should be
        cleared.
        """

        assert not os.path.exists(LOCK_PATH)
        try:
            with AtomicEdit(FILE_PATH) as f:
                assert os.path.exists(LOCK_PATH)
                assert False
        except AssertionError:
            pass
        assert not os.path.exists(LOCK_PATH)

    def test_delete_in_with(self: "TestAtomicEdit") -> None:
        """
        We should be able to delete the file while it's acquired.
        """

        assert not os.path.exists(FILE_PATH)
        assert not os.path.exists(LOCK_PATH)
        with open(FILE_PATH, "w") as f:
            f.write("foo")

        with AtomicEdit(FILE_PATH) as f:
            assert os.path.exists(FILE_PATH)
            os.remove(FILE_PATH)
            assert not os.path.exists(FILE_PATH)
            assert os.path.exists(LOCK_PATH)
        assert not os.path.exists(FILE_PATH)
        assert not os.path.exists(LOCK_PATH)

    def test_multiple(self: "TestAtomicEdit") -> None:
        """
        We must be able to use the same AtomicEdit instance multiple times.
        """

        f = AtomicEdit(FILE_PATH)
        with f:
            f.write_all("1")
        with f:
            assert f.read_all() == "1"

    def test_second_attempt_waits_for_first(self: "TestAtomicEdit") -> None:
        """
        Attempts should be properly serialized. Uses threads to force genuine
        overlap.
        """

        with open(FILE_PATH, "w") as f:
            f.write("x")

        release_first = threading.Event()
        second_acquired_after = []

        def hold_first() -> None:
            with AtomicEdit(FILE_PATH):
                release_first.wait(timeout=5)

        def try_second() -> None:
            start = time.monotonic()
            with AtomicEdit(FILE_PATH):
                second_acquired_after.append(time.monotonic() - start)

        t1 = threading.Thread(target=hold_first)
        t1.start()
        time.sleep(0.1)  # let t1 actually acquire before t2 tries

        t2 = threading.Thread(target=try_second)
        t2.start()
        time.sleep(0.3)
        assert second_acquired_after == [], "second attempt should be blocked"

        release_first.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(second_acquired_after) == 1
        assert second_acquired_after[0] >= 0.2, "it should have actually waited"

    def test_partial_write(self: "TestAtomicEdit", monkeypatch) -> None:
        """
        Asserts that partial writes are not an issue. The underlying function is
        implemented with "NamedTemporaryFile", so we can replace this with a new
        function that intentionally breaks after the first line is written. In
        the real-world, it could be an issue for something like half of a JSON
        file to be written, with a parser expecting to read an entire valid JSON
        file.
        """

        with open(FILE_PATH, "w") as f:
            f.write("original 1\noriginal 2")

        # Replace the tempfile write with a version that breaks after half of
        # the content is written.
        real_ntf = tempfile.NamedTemporaryFile

        def flaky_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)

            real_write = f.write

            def flaky_write(data):
                real_write(data[: len(data) // 2])
                raise OSError("simulated crash mid-write")

            f.write = flaky_write
            return f

        monkeypatch.setattr(tempfile, "NamedTemporaryFile", flaky_ntf)

        # Run this with the new "open" method.
        with monkeypatch.context() as m:
            with pytest.raises(OSError):
                with AtomicEdit(FILE_PATH) as edit:
                    edit.write_all("new 1\nnew 2")

        with open(FILE_PATH, "r") as f:
            leftover = f.read()
        assert leftover == "original 1\noriginal 2"

    def test_stuck(self: "TestAtomicEdit") -> None:
        """
        Tests that the lock is cleared if the timeout is exceeded.
        """

        # Simulate a holder that crashed before exit.
        begin_time = time.time()
        with open(FILE_PATH, "w") as f:
            f.write("foo")
        os.mkdir(LOCK_PATH)

        # Someone else tries to acquire it, and they succeed once the timeout is
        # passed.
        with AtomicEdit(FILE_PATH, timeout=1.0, backoff=False) as f:
            f.write_all("bar")
        assert 1.0 <= time.time() - begin_time <= 2.0

        with open(FILE_PATH, "r") as f:
            assert f.read() == "bar"

    class TestMultiprocess:
        def worker():
            # The timeout is *not* for this specific worker; it's checking that
            # the lock has been modified at all. So it's fine if another process
            # acquires the lock, causing us to wait longer than the timeout.
            with AtomicEdit(FILE_PATH, timeout=1.0, backoff=False) as f:
                val = int(f.read_all())
                val += 1
                time.sleep(random.random() * 0.1)
                f.write_all(str(val))

        def test_multiprocess(self: "TestMultiprocess") -> None:
            """
            Tests a large number of processes attempting to write to the file.
            This looks like what a real program would do here.
            """

            # Set up the file.
            with open(FILE_PATH, "w") as f:
                f.write("0")

            # Launch each subprocess.
            start_time = time.time()
            processes = [
                subprocess.Popen(
                    [sys.executable, __file__, "worker"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(100)
            ]

            # Get their status.
            failures = []
            for idx, proc in enumerate(processes):
                _, stderr = proc.communicate(timeout=15)
                if proc.returncode != 0:
                    failures.append((idx, stderr))
            assert len(failures) == 0, failures

            with open(FILE_PATH, "r") as f:
                assert int(f.read()) == 100

            # Each subprocess waits between 0 and 0.1 seconds. If they wait the
            # maximum, then 100 * 0.1 = 10 seconds.
            assert time.time() - start_time < 15


class TestAtomicQueue:
    def test_basic(self: "TestAtomicQueue"):
        q = Queue(["hello", "world"], path=FILE_PATH)
        assert q.pop() == "hello"
        q.push("foo")
        assert q.pop() == "world"
        assert q.pop() == "foo"

    def test_wait_empty(self: "TestAtomicQueue"):
        """
        Waiting on an empty queue.
        """

        assert not os.path.exists(FILE_PATH)
        q = Queue(path=FILE_PATH)

        t = threading.Thread(target=lambda: q.pop())
        t.start()
        t.join(timeout=0.1)  # Should still be blocked.
        assert t.is_alive()

        # Adding something afterwards should wake it up.
        q.push("foo")
        time.sleep(0.1)
        assert not t.is_alive()

        q.push("bar")
        assert q.pop() == "bar"

    def test_push_empty(self: "TestAtomicQueue"):
        """
        It should be fine for us to push something to an empty queue.
        """

        q = Queue(path=FILE_PATH)
        q.push("hello")
        assert q.pop() == "hello"

    class TestMultiprocess:
        def worker():
            in_q = Queue(path=FILE_PATH)
            value = in_q.pop()
            out_q = Queue(path=FILE2_PATH)
            out_q.push(value + 1000000)

        def test_multiprocess(self: "TestMultiprocess") -> None:
            # Set up the queue.
            count = 100
            in_q = Queue(list(range(count)), path=FILE_PATH)
            out_q = Queue([], path=FILE2_PATH)

            # Launch each subprocess.
            start_time = time.time()
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        __file__,
                        "TestAtomicQueue.TestMultiprocess",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(count)
            ]

            # Get their status.
            failures = []
            for idx, proc in enumerate(processes):
                _, stderr = proc.communicate(timeout=5)
                if proc.returncode != 0:
                    failures.append((idx, stderr))
            assert len(failures) == 0, failures

            # Confirm all correct.
            assert len(out_q) == count
            vals = set(out_q.pop() for _ in range(count))
            assert vals == set(1000000 + i for i in range(count))

            # Delete the file.
            assert os.path.exists(FILE_PATH)
            assert os.path.exists(FILE2_PATH)
            in_q.delete()
            out_q.delete()
            assert not os.path.exists(FILE_PATH)
            assert not os.path.exists(FILE2_PATH)
            assert not os.path.exists(LOCK_PATH)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        if sys.argv[1] == "worker":
            TestAtomicEdit.TestMultiprocess.worker()
        elif sys.argv[1] == "TestAtomicQueue.TestMultiprocess":
            TestAtomicQueue.TestMultiprocess.worker()
        else:
            raise ValueError(repr(sys.argv))
