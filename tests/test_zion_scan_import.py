import unittest

from zion_core.scan_import import plan_scan_import_batch, select_scan_needs_more_location


class ScanImportTests(unittest.TestCase):
    def test_selects_only_needs_more_location_and_preserves_resolved(self):
        rows=(
            {"zip_code":"32744","status":"RESOLVED"},
            {"zip_code":"32807","status":"needs_more_location"},
            {"zip_code":"32822","status":"NEEDS_MORE_LOCATION"},
            {"zip_code":"32825","status":"NO_ACTIVE_CWS"},
        )
        summary=select_scan_needs_more_location(rows)
        self.assertEqual(summary.total_rows,4)
        self.assertEqual(summary.unique_zips,4)
        self.assertEqual(summary.selected,("32807","32822"))
        self.assertEqual(summary.skipped_resolved,1)
        self.assertEqual(summary.skipped_other,1)

    def test_duplicate_same_status_is_idempotent(self):
        rows=(
            {"zip_code":"32807","status":"needs_more_location"},
            {"zip_code":"32807","status":"needs_more_location"},
        )
        summary=select_scan_needs_more_location(rows)
        self.assertEqual(summary.total_rows,2)
        self.assertEqual(summary.unique_zips,1)
        self.assertEqual(summary.selected,("32807",))

    def test_duplicate_conflicting_status_fails_closed(self):
        rows=(
            {"zip_code":"32807","status":"needs_more_location"},
            {"zip_code":"32807","status":"RESOLVED"},
        )
        with self.assertRaisesRegex(ValueError,"SCAN_IMPORT_ZIP_STATUS_CONFLICT"):
            select_scan_needs_more_location(rows)

    def test_import_plan_is_scan_scoped_and_only_unresolved(self):
        summary,plan=plan_scan_import_batch((
            {"zip_code":"32744","status":"RESOLVED"},
            {"zip_code":"32807","status":"needs_more_location"},
        ),batch_id="scan-existing-q4")
        self.assertEqual(summary.selected,("32807",))
        self.assertEqual(plan.business_id,"scan-water-intelligence")
        self.assertEqual(tuple(x.item_key for x in plan.items),("32807",))


if __name__=="__main__":
    unittest.main()
