"""Tests for the verified Orange Parcels_BCC KTEMA adapter."""
import ast
import unittest
from pathlib import Path

from zion_core.ktema import NOT_FOUND, UNAVAILABLE, VERIFIED, KtemaError, PropertyQuery, PropertySource
from zion_core.ktema_orange import (
    ORANGE_PARCELS_BCC_FIELDS,
    ORANGE_PARCELS_BCC_SOURCE_ID,
    OrangeParcelsBccSource,
    orange_property_registry,
)

BUSINESS="zmart-consumer-rights"
ISOLATION="zmart-consumer-rights"
PARCEL="123456789012345"

def _query(**kwargs):
    data={"business_id":BUSINESS,"address":"200 S Orange Ave","zip":"32801"}
    data.update(kwargs)
    return PropertyQuery(**data)

def _response(**overrides):
    attrs={
        "PARCEL":PARCEL,"SITUS":"200 S ORANGE AVE","SITUS_ZIP":"32801",
        "SUBTYPE":1,"TYPE_CODE":"SF","DOR_CODE":"0100","LAND_DOR_CODE":"0100",
        "AYB":1985,"LIVING_AREA":1800,"ACREAGE":0.25,"NAME1":"SHOULD NOT ESCAPE",
    }
    attrs.update(overrides)
    return {"features":[{"attributes":attrs}],"_retrieved_at":"2026-10-04T20:00:00+00:00"}

class OrangeKtemaTests(unittest.TestCase):
    def setUp(self):
        self.source=OrangeParcelsBccSource()

    def test_protocol_and_registry(self):
        self.assertIsInstance(self.source, PropertySource)
        self.assertEqual(orange_property_registry().get(ORANGE_PARCELS_BCC_SOURCE_ID).source_id, ORANGE_PARCELS_BCC_SOURCE_ID)

    def test_verified_field_contract(self):
        self.assertIn("PARCEL", ORANGE_PARCELS_BCC_FIELDS)
        self.assertIn("SITUS", ORANGE_PARCELS_BCC_FIELDS)
        self.assertIn("SITUS_ZIP", ORANGE_PARCELS_BCC_FIELDS)
        self.assertIn("AYB", ORANGE_PARCELS_BCC_FIELDS)
        self.assertIn("LIVING_AREA", ORANGE_PARCELS_BCC_FIELDS)
        self.assertIn("ACREAGE", ORANGE_PARCELS_BCC_FIELDS)

    def test_fetch_intent_opaque_and_bounded(self):
        intent=self.source.fetch_intent(_query())
        self.assertTrue(intent.target_descriptor.startswith("orange-parcels-bcc://address/"))
        self.assertNotIn("http", intent.target_descriptor)
        self.assertNotIn("200 S Orange", intent.target_descriptor)
        p=self.source.fetch_intent(PropertyQuery(business_id=BUSINESS, parcel_id=PARCEL))
        self.assertTrue(p.target_descriptor.startswith("orange-parcels-bcc://parcel/"))
        self.assertNotIn(PARCEL, p.target_descriptor)
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_SOURCE_QUERY_UNSUPPORTED"):
            self.source.fetch_intent(PropertyQuery(business_id=BUSINESS, zip="32801"))

    def test_normalizes_official_arcgis_shape(self):
        p=self.source.normalize(_response(), _query(), ISOLATION)
        self.assertEqual(p.verification_status, VERIFIED)
        self.assertEqual(p.source, ORANGE_PARCELS_BCC_SOURCE_ID)
        self.assertEqual(p.source_record_id, PARCEL)
        self.assertEqual(p.county, "Orange")
        self.assertEqual(p.site_address, "200 S ORANGE AVE")
        self.assertEqual(p.zip, "32801")
        self.assertEqual(p.land_use, "0100")
        self.assertEqual(p.year_built, 1985)
        self.assertEqual(p.living_sqft, 1800.0)
        self.assertEqual(p.lot_acres, 0.25)
        self.assertTrue(p.property_exists)
        self.assertIsNone(p.owner)
        self.assertNotIn(PARCEL, p.raw_reference)

    def test_zero_features_not_found(self):
        p=self.source.normalize({"features":[]}, _query(), ISOLATION)
        self.assertEqual(p.verification_status, NOT_FOUND)
        self.assertIsNone(p.property_exists)

    def test_arcgis_error_unavailable(self):
        p=self.source.normalize({"error":{"code":500}}, _query(), ISOLATION)
        self.assertEqual(p.verification_status, UNAVAILABLE)
        self.assertIsNone(p.property_exists)

    def test_multiple_features_ambiguous(self):
        r={"features":[{"attributes":{"PARCEL":"A"}},{"attributes":{"PARCEL":"B"}}]}
        with self.assertRaisesRegex(KtemaError, r"^KTEMA_MATCH_AMBIGUOUS.*A.*B"):
            self.source.normalize(r, _query(), ISOLATION)

    def test_required_fields_fail_closed(self):
        with self.assertRaisesRegex(KtemaError, r"PARCEL-required"):
            self.source.normalize(_response(PARCEL=None), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"SITUS-required"):
            self.source.normalize(_response(SITUS=None), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"SITUS_ZIP-invalid"):
            self.source.normalize(_response(SITUS_ZIP="3280X"), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"AYB-type"):
            self.source.normalize(_response(AYB="1985"), _query(), ISOLATION)

    def test_non_finite_numerics_fail_closed(self):
        # NaN/inf are not measurements: the adapter contract is KtemaError,
        # never a raw ValueError and never a cached non-finite profile.
        nan=float("nan"); inf=float("inf")
        with self.assertRaisesRegex(KtemaError, r"AYB-non-finite"):
            self.source.normalize(_response(AYB=nan), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"LIVING_AREA-non-finite"):
            self.source.normalize(_response(LIVING_AREA=inf), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"ACREAGE-non-finite"):
            self.source.normalize(_response(ACREAGE=float("-inf")), _query(), ISOLATION)
        with self.assertRaisesRegex(KtemaError, r"LIVING_AREA-non-finite"):
            self.source.normalize(_response(LIVING_AREA=nan), _query(), ISOLATION)

    def test_no_network_imports(self):
        import zion_core.ktema_orange as module
        tree=ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported=set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse({"urllib","requests","http"} & imported)

if __name__=="__main__":
    unittest.main()
