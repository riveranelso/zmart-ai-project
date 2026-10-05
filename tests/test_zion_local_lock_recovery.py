import json
import multiprocessing
import os
import signal
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from zion_core.persistence import LocalOperationLock, _operation_digest


class LocalOperationLockRecoveryTests(unittest.TestCase):
    def lock_path(self,root,business,operation,identity):
        digest=_operation_digest(business,operation,identity)
        return root/(digest+".lock")

    def test_proven_dead_owner_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="crashed-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":99999999,"business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            with patch.object(LocalOperationLock,"_owner_alive",return_value=False):
                with lock.hold(business,operation,identity):
                    self.assertTrue(path.exists())
                    owner=json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(owner["pid"],os.getpid())
            self.assertFalse(path.exists())

    def test_dead_owner_recovery_syncs_lock_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="crashed-fsync"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":99999999,"business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            real_fsync=os.fsync
            fsync_calls=[]
            def recording_fsync(fd):
                fsync_calls.append(fd)
                return real_fsync(fd)
            with patch.object(LocalOperationLock,"_owner_alive",return_value=False), \
                 patch("zion_core.persistence.os.fsync",side_effect=recording_fsync):
                with lock.hold(business,operation,identity):
                    pass
            self.assertGreaterEqual(len(fsync_calls),3)
            self.assertFalse(path.exists())

    def test_live_or_unknown_owner_is_not_stolen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="live-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":12345,"business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,poll_seconds=0.001,timeout_seconds=0.01)
            with patch.object(LocalOperationLock,"_owner_alive",return_value=True):
                with self.assertRaisesRegex(TimeoutError,"IDEMPOTENCY_LOCK_TIMEOUT"):
                    with lock.hold(business,operation,identity):
                        pass
            self.assertTrue(path.exists())

    def test_reused_pid_with_different_start_identity_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="reused-pid-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":12345,"process_start":"old-start","business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            with patch.object(LocalOperationLock,"_owner_alive",return_value=True), \
                 patch.object(LocalOperationLock,"_process_start_identity",return_value="new-start"):
                with lock.hold(business,operation,identity):
                    owner=json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(owner["pid"],os.getpid())
            self.assertFalse(path.exists())

    def test_live_pid_without_comparable_start_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="unverifiable-pid-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":12345,"process_start":None,"business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,poll_seconds=0.001,timeout_seconds=0.01)
            with patch.object(LocalOperationLock,"_owner_alive",return_value=True), \
                 patch.object(LocalOperationLock,"_process_start_identity",return_value=None):
                with self.assertRaisesRegex(TimeoutError,"IDEMPOTENCY_LOCK_TIMEOUT"):
                    with lock.hold(business,operation,identity):
                        pass
            self.assertTrue(path.exists())

    def test_malformed_owner_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="unknown-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text("not-json",encoding="utf-8")
            lock=LocalOperationLock(root,poll_seconds=0.001,timeout_seconds=0.01)
            with self.assertRaisesRegex(TimeoutError,"IDEMPOTENCY_LOCK_TIMEOUT"):
                with lock.hold(business,operation,identity):
                    pass
            self.assertTrue(path.exists())

    def test_stale_malformed_metadata_is_recovered(self):
        # Under the atomic-link protocol a live holder can never present an
        # unreadable lock file, so stale garbage is a legacy artifact or
        # corruption — recoverable, never a permanent brick.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="stale-garbage-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_text("not-json",encoding="utf-8")
            old=time.time()-7200
            os.utime(path,(old,old))
            lock=LocalOperationLock(root,poll_seconds=0.001,timeout_seconds=0.5)
            with lock.hold(business,operation,identity):
                owner=json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(owner["pid"],os.getpid())
            self.assertFalse(path.exists())

    def test_stale_empty_lock_file_is_recovered(self):
        # The old create-then-write protocol could leave an empty lock file on
        # crash; the new protocol never creates one. Stale empties recover.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="stale-empty-1"
            path=self.lock_path(root,business,operation,identity)
            path.write_bytes(b"")
            old=time.time()-7200
            os.utime(path,(old,old))
            lock=LocalOperationLock(root,poll_seconds=0.001,timeout_seconds=0.5)
            with lock.hold(business,operation,identity):
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())



    def test_owner_metadata_write_failure_does_not_leave_unrecoverable_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="metadata-write-failure"
            path=self.lock_path(root,business,operation,identity)

            with patch("zion_core.persistence.os.write",side_effect=OSError("SIMULATED_WRITE_FAILURE")):
                with self.assertRaisesRegex(OSError,"SIMULATED_WRITE_FAILURE"):
                    with lock.hold(business,operation,identity):
                        self.fail("protected section must not be entered")

            self.assertFalse(path.exists())
            with lock.hold(business,operation,identity):
                self.assertTrue(path.exists())
            self.assertFalse(path.exists())

    def test_partial_owner_metadata_write_is_completed_before_entering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="partial-metadata-write"
            path=self.lock_path(root,business,operation,identity)
            real_write=os.write
            first=True

            def partial_first_write(fd,data):
                nonlocal first
                if first and len(data)>1:
                    first=False
                    split=max(1,len(data)//2)
                    return real_write(fd,data[:split])
                return real_write(fd,data)

            with patch("zion_core.persistence.os.write",side_effect=partial_first_write):
                with lock.hold(business,operation,identity):
                    owner=json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(owner["pid"],os.getpid())
                    self.assertEqual(owner["identity"],identity)
            self.assertFalse(path.exists())

    def test_zero_owner_metadata_write_fails_closed_and_cleans_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="zero-metadata-write"
            path=self.lock_path(root,business,operation,identity)

            with patch("zion_core.persistence.os.write",return_value=0):
                with self.assertRaisesRegex(OSError,"LOCK_OWNER_METADATA_SHORT_WRITE"):
                    with lock.hold(business,operation,identity):
                        self.fail("protected section must not be entered")

            self.assertFalse(path.exists())
            with lock.hold(business,operation,identity):
                pass
            self.assertFalse(path.exists())

    def test_owner_metadata_fsync_failure_does_not_leave_unrecoverable_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            lock=LocalOperationLock(root,timeout_seconds=0.1)
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="metadata-fsync-failure"
            path=self.lock_path(root,business,operation,identity)
            real_fsync=os.fsync
            failed=False

            def fail_first_file_fsync(fd):
                nonlocal failed
                if not stat.S_ISDIR(os.fstat(fd).st_mode) and not failed:
                    failed=True
                    raise OSError("SIMULATED_OWNER_FSYNC_FAILURE")
                return real_fsync(fd)

            with patch("zion_core.persistence.os.fsync",side_effect=fail_first_file_fsync):
                with self.assertRaisesRegex(OSError,"SIMULATED_OWNER_FSYNC_FAILURE"):
                    with lock.hold(business,operation,identity):
                        self.fail("protected section must not be entered")

            self.assertTrue(failed)
            self.assertFalse(path.exists())
            with lock.hold(business,operation,identity):
                pass

    def test_release_directory_sync_failure_does_not_fail_completed_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            lock=LocalOperationLock(root,timeout_seconds=0.2)
            real_fsync=os.fsync
            failed_directory_sync=False

            def fail_directory_fsync(fd):
                nonlocal failed_directory_sync
                if stat.S_ISDIR(os.fstat(fd).st_mode) and not failed_directory_sync:
                    failed_directory_sync=True
                    raise OSError("SIMULATED_RELEASE_DIRECTORY_FSYNC_FAILURE")
                return real_fsync(fd)

            completed=[]
            with patch("zion_core.persistence.os.fsync",side_effect=fail_directory_fsync):
                with lock.hold("zmart-consumer-rights","MISSION_DISPATCH","release-fsync"):
                    completed.append(True)

            self.assertEqual(completed,[True])
            self.assertTrue(failed_directory_sync)
            with lock.hold("zmart-consumer-rights","MISSION_DISPATCH","release-fsync"):
                pass

    def test_dead_owner_directory_sync_failure_still_recovers_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="dead-owner-post-unlink-fsync"
            path=self.lock_path(root,business,operation,identity)
            path.write_text(json.dumps({
                "pid":99999999,"business_id":business,
                "operation":operation,"identity":identity,
            }),encoding="utf-8")
            lock=LocalOperationLock(root,timeout_seconds=0.2)
            real_fsync=os.fsync
            failed_directory_sync=False

            def fail_first_directory_fsync(fd):
                nonlocal failed_directory_sync
                if stat.S_ISDIR(os.fstat(fd).st_mode) and not failed_directory_sync:
                    failed_directory_sync=True
                    raise OSError("SIMULATED_RECOVERY_DIRECTORY_FSYNC_FAILURE")
                return real_fsync(fd)

            completed=[]
            with patch.object(LocalOperationLock,"_owner_alive",return_value=False), \
                 patch("zion_core.persistence.os.fsync",side_effect=fail_first_directory_fsync):
                with lock.hold(business,operation,identity):
                    completed.append(True)

            self.assertEqual(completed,[True])
            self.assertTrue(failed_directory_sync)
            self.assertFalse(path.exists())


def _hold_and_sleep(root_text,business,operation,identity,flag_text):
    # Child: acquire the lock, signal the parent, then sleep until killed.
    # SIGKILL runs no cleanup: this simulates a crash mid-hold.
    from zion_core.persistence import LocalOperationLock
    from pathlib import Path
    lock=LocalOperationLock(Path(root_text))
    with lock.hold(business,operation,identity):
        Path(flag_text).write_text("holding",encoding="utf-8")
        time.sleep(60)


class LocalOperationLockCrashTests(unittest.TestCase):
    def test_sigkill_mid_hold_is_recoverable(self):
        # Ownership metadata is published atomically with acquisition, so a
        # crash mid-hold always leaves a recoverable lock — never a brick.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"locks"
            root.mkdir()
            business="zmart-consumer-rights"
            operation="MISSION_DISPATCH"
            identity="sigkill-1"
            flag=Path(tmp)/"holding.flag"
            ctx=multiprocessing.get_context("spawn")
            child=ctx.Process(
                target=_hold_and_sleep,
                args=(str(root),business,operation,identity,str(flag)),
            )
            child.start()
            try:
                deadline=time.monotonic()+10
                digest=_operation_digest(business,operation,identity)
                path=root/(digest+".lock")
                while time.monotonic() < deadline:
                    if flag.exists():
                        break
                    time.sleep(0.01)
                self.assertTrue(flag.exists(),"child never acquired the lock")
                # The lock file must carry complete, recoverable metadata.
                owner=json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(owner["pid"],child.pid)
                os.kill(child.pid,signal.SIGKILL)
                child.join(10)
                self.assertFalse(child.is_alive(),"killed child did not exit")
                lock=LocalOperationLock(root,poll_seconds=0.01,timeout_seconds=5.0)
                with lock.hold(business,operation,identity):
                    owner=json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(owner["pid"],os.getpid())
                self.assertFalse(path.exists())
            finally:
                if child.is_alive():
                    child.terminate()
                    child.join(5)

if __name__=="__main__":
    unittest.main()
