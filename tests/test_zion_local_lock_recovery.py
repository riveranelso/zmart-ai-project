import json
import os
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


if __name__=="__main__":
    unittest.main()
