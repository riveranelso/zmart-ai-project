"""PARADOSIS — canonical mission context loader.

Invariant map:
  P1  module registry derived from real code (16 modules, complete records)
  P2  build fails closed on unknown/disabled tenant
  P3  packet is frozen (no agent can mutate tenant identity)
  P4  bind_tenant: prompt claims never rebind; mismatch fails closed
  P5  deterministic relevant-module selection
  P6  freshness: sealed HEAD vs current HEAD; STALE reports changed files
  P7  refresh keeps parameters, updates HEAD
  P8  canonical docs mirror the loader (registry doc + agent files)
"""
import subprocess
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from zion_core.paradosis import (
    CORE_MODULES,
    MODULE_REGISTRY,
    MissionPacket,
    ParadosisError,
    TenantBindingError,
    bind_tenant,
    build_mission_packet,
    check_packet_freshness,
    packet_summary,
    refresh_packet,
    repo_head,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = REPO_ROOT


def _oldest_available_sha() -> str | None:
    """Oldest commit reachable locally, or None when there is no history
    to diff against (e.g. CI's depth-1 shallow checkout)."""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    return lines[0] if lines else None


def make_packet(**kw):
    args = dict(
        mission_id="test-mission-1",
        objective="add whatsapp draft support",
        business_id="los-duros",
        repo_root=REPO_ROOT,
    )
    args.update(kw)
    return build_mission_packet(**args)


class TestRegistryIntegrity(unittest.TestCase):
    def test_registry_has_16_modules(self):  # P1
        self.assertEqual(len(MODULE_REGISTRY), 16)

    def test_every_record_complete(self):  # P1
        for name, rec in MODULE_REGISTRY.items():
            self.assertTrue(rec.responsibility.strip(), name)
            self.assertTrue(rec.inputs, name)
            self.assertTrue(rec.outputs, name)
            self.assertTrue(rec.boundaries, name)
            self.assertTrue(rec.must_not, name)
            self.assertTrue(rec.keywords, name)
            self.assertTrue(rec.context_refs, name)
            self.assertIsInstance(rec.dependencies, tuple)

    def test_registry_matches_real_modules(self):  # P1
        for name in MODULE_REGISTRY:
            self.assertTrue(
                (REPO_ROOT / "zion_core" / f"{name}.py").exists(),
                f"registry entry {name} has no real module",
            )

    def test_canonical_names_cover_expected(self):  # P1
        canonicals = {r.canonical for r in MODULE_REGISTRY.values()}
        for want in ("OMAR", "SAN PEDRO", "ANTIPHON", "GLOSSOLALIA",
                     "BIBLIA", "CRONICAS"):
            self.assertIn(want, canonicals)


class TestBuildPacket(unittest.TestCase):
    def test_build_binds_tenant_and_head(self):
        p = make_packet()
        self.assertEqual(p.business_id, "los-duros")
        self.assertEqual(p.brand_id, "los-duros")
        self.assertEqual(p.current_head, repo_head(REPO_ROOT))
        self.assertEqual(p.repo, "riveranelso/zmart-ai-project")

    def test_build_explicit_brand(self):
        p = make_packet(brand_id="los-duros-tv")
        self.assertEqual(p.brand_id, "los-duros-tv")

    def test_build_unknown_business_fails_closed(self):  # P2
        with self.assertRaises(ParadosisError):
            make_packet(business_id="not-a-business")

    def test_build_requires_fields(self):  # P2
        with self.assertRaises(ParadosisError):
            make_packet(mission_id="  ")
        with self.assertRaises(ParadosisError):
            make_packet(objective="")
        with self.assertRaises(ParadosisError):
            make_packet(business_id="")

    def test_core_modules_always_selected(self):  # P5
        p = make_packet(objective="something unrelated entirely")
        for core in CORE_MODULES:
            self.assertIn(core, p.relevant_modules)

    def test_selection_picks_glossolalia(self):  # P5
        p = make_packet(objective="normalize whatsapp and instagram events")
        self.assertIn("glossolalia", p.relevant_modules)

    def test_selection_picks_antiphon(self):  # P5
        p = make_packet(objective="classify youtube comments for los duros")
        self.assertIn("antiphon", p.relevant_modules)

    def test_selection_deterministic(self):  # P5
        a = make_packet(objective="meta channel adapter work")
        b = make_packet(objective="meta channel adapter work")
        self.assertEqual(a.relevant_modules, b.relevant_modules)

    def test_base_context_refs_always_present(self):
        p = make_packet()
        for ref in ("AGENTS.md",
                    ".agents/skills/zion-development/SKILL.md",
                    "zmart360/BIBLIA/GLOBAL.md"):
            self.assertIn(ref, p.canonical_context_refs)


class TestPacketImmutability(unittest.TestCase):
    def test_packet_frozen(self):  # P3
        p = make_packet()
        with self.assertRaises(FrozenInstanceError):
            p.business_id = "zmart-consumer"  # type: ignore[misc]


class TestBindTenant(unittest.TestCase):
    def test_matching_claims_return_packet(self):  # P4
        p = make_packet()
        self.assertIs(bind_tenant(p, "los-duros", "los-duros"), p)

    def test_none_claims_ok(self):  # P4
        p = make_packet()
        self.assertIs(bind_tenant(p, None), p)

    def test_business_mismatch_fails_closed(self):  # P4
        p = make_packet()
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "zmart-consumer")

    def test_brand_mismatch_fails_closed(self):  # P4
        p = make_packet()
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "los-duros", "zmart-consumer")

    def test_cross_tenant_prompt_injection(self):  # P4
        # A prompt mentioning another business must not rebind the packet.
        p = make_packet()
        with self.assertRaises(TenantBindingError):
            bind_tenant(p, "scan")
        self.assertEqual(p.business_id, "los-duros")


class TestFreshness(unittest.TestCase):
    def test_fresh_packet(self):  # P6
        p = make_packet()
        f = check_packet_freshness(p, REPO_ROOT)
        self.assertEqual(f.status, "FRESH")
        self.assertEqual(f.changed_files, ())
        self.assertEqual(f.current_head, p.current_head)

    def test_stale_packet_reports_changed_files(self):  # P6
        root_sha = _oldest_available_sha()
        if root_sha is None or root_sha == repo_head(REPO_ROOT):
            self.skipTest("no git history available for stale diff")
        old = MissionPacket(
            mission_id="m", repo="r", branch="b", current_head=root_sha,
            business_id="los-duros", brand_id="los-duros", objective="o",
            allowed_scope=(), forbidden_scope=(), relevant_modules=(),
            canonical_context_refs=(), security_boundaries=(),
            production_boundary="", test_requirements=(),
            write_permissions=(), current_known_state="",
        )
        f = check_packet_freshness(old, REPO_ROOT)
        self.assertEqual(f.status, "STALE")
        self.assertEqual(f.packet_head, root_sha)
        self.assertEqual(f.current_head, repo_head(REPO_ROOT))
        self.assertTrue(len(f.changed_files) > 0)

    def test_refresh_keeps_params_updates_head(self):  # P7
        p = make_packet(mission_id="keep-me", objective="keep objective")
        r = refresh_packet(p, REPO_ROOT)
        self.assertEqual(r.mission_id, "keep-me")
        self.assertEqual(r.objective, "keep objective")
        self.assertEqual(r.business_id, p.business_id)
        self.assertEqual(r.relevant_modules, p.relevant_modules)
        self.assertEqual(r.current_head, repo_head(REPO_ROOT))


class TestSummary(unittest.TestCase):
    def test_summary_has_essentials(self):
        p = make_packet()
        s = packet_summary(p)
        self.assertIn("test-mission-1", s)
        self.assertIn("los-duros", s)
        self.assertIn(p.current_head[:12], s)


class TestDocsMirror(unittest.TestCase):
    def test_module_registry_doc_exists_and_covers(self):  # P8
        doc = DOCS_ROOT / "zmart360" / "MODULE_REGISTRY.md"
        self.assertTrue(doc.exists())
        text = doc.read_text(encoding="utf-8")
        for want in ("ANTIPHON", "GLOSSOLALIA", "SAN PEDRO", "PARADOSIS"):
            self.assertIn(want, text)

    def test_agent_files_reference_packet(self):  # P8
        for agent in ("zion-architect", "zion-builder",
                      "zion-adversarial", "zion-reviewer"):
            path = DOCS_ROOT / ".github" / "agents" / f"{agent}.md"
            self.assertTrue(path.exists(), agent)
            text = path.read_text(encoding="utf-8")
            self.assertIn("MissionPacket", text, agent)
            self.assertIn("bind_tenant", text, agent)
            self.assertIn("check_packet_freshness", text, agent)


if __name__ == "__main__":
    unittest.main()
