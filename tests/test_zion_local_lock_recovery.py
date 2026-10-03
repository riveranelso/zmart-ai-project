import json
import os
import stat
import tempfile
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


if __name__=="__main__":
    unittest.main()
