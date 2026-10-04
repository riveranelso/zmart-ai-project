import unittest

from zion_core.scan_water import (
    NEEDS_MORE_LOCATION,
    RESOLVED,
    SCAN_BUSINESS_ID,
    plan_scan_zip_batch,
    validate_scan_zip_result,
)


class ScanWaterContractTests(unittest.TestCase):
    def test_scan_batch_is_fixed_to_scan_business(self):
        plan=plan_scan_zip_batch(("32744","32807"),batch_id="scan-fl-2026q4")
        self.assertEqual(plan.business_id,SCAN_BUSINESS_ID)
        self.assertEqual(tuple(item.item_key for item in plan.items),("32744","32807"))
        self.assertTrue(all(item.mission["business_id"]==SCAN_BUSINESS_ID for item in plan.items))

    def test_invalid_zip_fails_before_batch_dispatch(self):
        with self.assertRaisesRegex(ValueError,"SCAN_ZIP_INVALID"):
            plan_scan_zip_batch(("32744","not-a-zip"),batch_id="scan-fl-2026q4")

    def test_resolved_requires_pwsid_and_evidence(self):
        result=validate_scan_zip_result(
            zip_code="32744",status=RESOLVED,pwsid="FL1234567",confidence=.97,
            evidence_refs=("epa:system:FL1234567","utility:lake-helen"),reason="single supported active CWS",
        )
        self.assertEqual(result.pwsid,"FL1234567")
        with self.assertRaisesRegex(ValueError,"SCAN_RESOLVED_EVIDENCE_REQUIRED"):
            validate_scan_zip_result(
                zip_code="32744",status=RESOLVED,pwsid="FL1234567",confidence=.97,
                evidence_refs=(),reason="unsupported",
            )

    def test_ambiguous_zip_cannot_smuggle_pwsid(self):
        with self.assertRaisesRegex(ValueError,"SCAN_UNRESOLVED_PWSID_FORBIDDEN"):
            validate_scan_zip_result(
                zip_code="32807",status=NEEDS_MORE_LOCATION,pwsid="FL1234567",confidence=.5,
                evidence_refs=("epa:candidate-set",),reason="multiple plausible systems",
            )

    def test_ambiguous_zip_is_valid_without_guessing(self):
        result=validate_scan_zip_result(
            zip_code="32807",status=NEEDS_MORE_LOCATION,pwsid=None,confidence=.5,
            evidence_refs=("epa:candidate-set",),reason="city or address required",
        )
        self.assertEqual(result.status,NEEDS_MORE_LOCATION)
        self.assertIsNone(result.pwsid)


if __name__=="__main__":
    unittest.main()
