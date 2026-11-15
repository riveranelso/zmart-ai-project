Verificación hecha: el ZIP **33935** cruza **Hendry (57.4%) y Glades (42.6%)** — ejemplo real confirmado. Entrego el trabajo.

---

# ADVERSARIAL TESTER — FL PROPERTY INTELLIGENCE (PARALLEL DISCOVERY)

**Repo:** `~/workspace/zmart-ai-project`, branch `zmart360/omar-core-v1`, HEAD `5e36df4`. **No existe aún ningún módulo de la capability** — los esqueletos abajo definen el contrato que el Builder debe implementar, en el idioma del repo (`unittest`, frozen dataclasses, `ValueError("FLPI_*")`, fixtures, jamás servicios live).

**Contrato asumido para los esqueletos** (idioma `scan_water.py`): módulo `zion_core/fl_property.py` con `VERIFIED/NOT_FOUND/UNAVAILABLE/INCONCLUSIVE`, dataclasses frozen `PropertyProvenance` / `PropertyProfile`, `normalize_flpi_input()`, `resolve_county()`, `validate_property_profile()`, `plan_flpi_batch()`, `build_flpi_cache_key()` / `flpi_cache_get/put`. Códigos de error `FLPI_*`.

---

## TOP 5 — ataques de mayor valor (con esqueleto)

### ★ T1. `test_cache_hit_requires_same_isolation_key` — Sustitución cross-tenant vía caché sin tenant
- **Invariante que protege:** SAN PEDRO + CHERUBIM — ningún business recupera contexto/provenance/caché de otro. La `isolation_key` es parte de la clave de caché, nunca ambiental.
- **Ataque exacto:** el implementador ingenuo keyea la caché solo por input normalizado (`parcel_id`). SCAN guarda un `PropertyProfile` VERIFIED para la parcela `01-22-28-0000-00-001` (con `owner` y `raw_reference` — PII real). Después `los-duros` pide la misma parcela y recibe **el perfil de SCAN**: provenance ajena + PII filtrada cross-tenant. Doble falla si además la caché se serializa a CRONICAS.
- **Esqueleto:**
```python
import unittest

from zion_core.fl_property import (
    PropertyProvenance,
    build_flpi_cache_key,
    flpi_cache_get,
    flpi_cache_put,
)


class FlpiCacheTenantIsolationTests(unittest.TestCase):
    def test_cache_hit_requires_same_isolation_key(self):
        # arrange: SCAN guarda un perfil VERIFIED bajo su isolation key
        provenance = PropertyProvenance(
            source="orange-county-pa-fixture",
            source_record_id="01-22-28-0000-00-001",
            retrieved_at="2026-10-04T10:00:00-04:00",
            source_updated_at="2026-09-01T00:00:00-04:00",
            raw_reference="fixture://orange-pa/01-22-28-0000-00-001",
        )
        store = {}
        scan_key = build_flpi_cache_key(
            isolation_key="scan-water-intelligence",
            input_kind="PARCEL_ID",
            input_value="01-22-28-0000-00-001",
        )
        flpi_cache_put(store, scan_key, provenance)
        # act: OTRO business pide la misma parcela con su propia key
        other_key = build_flpi_cache_key(
            isolation_key="los-duros",
            input_kind="PARCEL_ID",
            input_value="01-22-28-0000-00-001",
        )
        # assert: miss — el tenant es parte de la key; y lectura directa con
        # tenant ajeno se rechaza aunque el atacante conozca la key
        self.assertIsNone(flpi_cache_get(store, other_key))
        self.assertNotEqual(scan_key, other_key)
        with self.assertRaisesRegex(ValueError, "FLPI_CACHE_TENANT_MISMATCH"):
            flpi_cache_get(store, scan_key, requesting_isolation_key="los-duros")
```

### ★ T2. `test_not_found_is_never_an_existence_claim` — NOT_FOUND lavado a "la propiedad no existe"
- **Invariante que protege:** REGLA CRÍTICA — `NOT_FOUND` = "esa fuente no produjo match", NUNCA una afirmación de existencia. El perfil usa existencia tri-estado (`True/False/None`); `None` = desconocido.
- **Ataque exacto:** el implementador mapea `status == NOT_FOUND → property_exists=False` y el copy operativo dice "la propiedad no existe". Peor variante (ataque compuesto): el county resolver elige el county equivocado para un ZIP multi-county → la fuente correcta-nunca-consultada → `NOT_FOUND` → el sistema concluye inexistencia. El test fuerza la distinción estructural: sellar `property_exists=False` sobre `NOT_FOUND` debe fallar cerrado, y el perfil NOT_FOUND válido debe llevar `attempted_sources` (qué se consultó), no una conclusión.
- **Esqueleto:**
```python
import unittest

from zion_core.fl_property import NOT_FOUND, validate_property_profile


class FlpiNotFoundSemanticsTests(unittest.TestCase):
    def test_not_found_cannot_carry_an_existence_claim(self):
        # act/assert: sellar exists=False sobre NOT_FOUND falla cerrado
        with self.assertRaisesRegex(ValueError, "FLPI_NOTFOUND_EXISTENCE_CLAIM_FORBIDDEN"):
            validate_property_profile(
                input_kind="PARCEL_ID",
                input_value="01-22-28-0000-00-001",
                county="orange",
                status=NOT_FOUND,
                property_exists=False,  # <-- la línea del implementador ingenuo
                provenance=None,
                isolation_key="scan-water-intelligence",
                reason="source returned zero matches",
            )

    def test_not_found_profile_records_attempt_not_existence(self):
        profile = validate_property_profile(
            input_kind="PARCEL_ID",
            input_value="01-22-28-0000-00-001",
            county="orange",
            status=NOT_FOUND,
            property_exists=None,  # desconocido, jamás False por defecto
            provenance=None,
            isolation_key="scan-water-intelligence",
            reason="orange-county-pa-fixture returned zero matches",
            attempted_sources=("orange-county-pa-fixture",),
        )
        self.assertEqual(profile.status, NOT_FOUND)
        self.assertIsNone(profile.property_exists)
        self.assertIn("orange-county-pa-fixture", profile.attempted_sources)
```

### ★ T3. `test_spoofed_business_ids_fail_closed` — Canonicalización que acepta lookalikes
- **Invariante que protege:** SAN PEDRO — resolución por match exacto; "suffix lookalikes are not authorization"; `deny_unknown_business: true` (verificado en `san_pedro_registry.json`).
- **Ataque exacto:** el resolver hace `.strip().lower()` antes de matchear "para ser amable". Entonces `" Scan-Water-Intelligence "`, `"SCAN-WATER-INTELLIGENCE"`, `"scan-water-intelligence2"` (sufijo — el caso que SAN PEDRO nombra explícitamente), `"scan-water-inteligence"` (typo registrado por error), `"scan-water"` (prefijo) o el display name `"SCAN Water Intelligence"` resuelven al contexto de SCAN → el atacante obtiene `context_refs` y `isolation_key` ajenos. El `""` vacío tampoco puede defaultear a SCAN.
- **Esqueleto:**
```python
import unittest

from zion_core.fl_property import plan_flpi_batch


class FlpiBusinessSpoofTests(unittest.TestCase):
    SPOOFS = (
        " Scan-Water-Intelligence ",  # whitespace
        "SCAN-WATER-INTELLIGENCE",     # case
        "scan-water-intelligence2",    # sufijo lookalike
        "scan-water-inteligence",      # typo
        "scan-water",                  # prefijo
        "SCAN Water Intelligence",     # display name, no es el id
        "",                           # vacío: jamás defaultea a SCAN
    )

    def test_spoofed_business_ids_fail_closed(self):
        for spoof in self.SPOOFS:
            with self.subTest(business_id=spoof):
                with self.assertRaisesRegex(ValueError, "FLPI_BUSINESS_UNKNOWN"):
                    plan_flpi_batch(
                        (("PARCEL_ID", "01-22-28-0000-00-001"),),
                        batch_id="flpi-spoof",
                        business_id=spoof,
                    )

    def test_exact_registered_id_still_resolves(self):
        plan = plan_flpi_batch(
            (("PARCEL_ID", "01-22-28-0000-00-001"),),
            batch_id="flpi-ok",
            business_id="scan-water-intelligence",
        )
        self.assertEqual(plan.business_id, "scan-water-intelligence")
```
(Nota: `plan_flpi_batch` resuelve contra el registry SAN PEDRO vía fixture; el `business_id` es parámetro **requerido**, nunca defaulteado.)

### ★ T4. `test_cross_county_zip_is_ambiguous_never_first_match` — ZIP multi-county resuelto a un solo county
- **Invariante que protege:** el county resolver jamás elige un county por orden alfabético/primero-de-lista; un ZIP 1:N produce `FLPI_COUNTY_AMBIGUOUS` con el candidate set.
- **Ataque exacto:** fixture real — ZIP **33935** = Hendry 57.4% / Glades 42.6% (Port LaBelle cruza la línea; verificado hoy). El implementador ingenuo usa un dict `zip→county` donde 33935 apunta a un solo county (o `candidates[0]`). Resultado: la parcela se busca en el property appraiser equivocado → `NOT_FOUND` espurio → (compuesto con T2) se concluye "no existe". El test exige que el error porte ambos candidatos para que el caller pida desambiguación (address/coordenadas).
- **Esqueleto:**
```python
import unittest

from zion_core.fl_property import resolve_county


class FlpiCountyResolverTests(unittest.TestCase):
    # fixture: ZIP 33935 cruza la línea Hendry/Glades (Port LaBelle)
    COUNTY_ZIP_FIXTURE = {
        "32801": ("orange",),
        "33935": ("hendry", "glades"),
    }

    def test_cross_county_zip_is_ambiguous_never_first_match(self):
        with self.assertRaisesRegex(ValueError, "FLPI_COUNTY_AMBIGUOUS") as ctx:
            resolve_county(
                input_kind="ZIP",
                input_value="33935",
                county_zip_map=self.COUNTY_ZIP_FIXTURE,
            )
        self.assertIn("hendry", str(ctx.exception))
        self.assertIn("glades", str(ctx.exception))

    def test_single_county_zip_resolves(self):
        resolution = resolve_county(
            input_kind="ZIP",
            input_value="32801",
            county_zip_map=self.COUNTY_ZIP_FIXTURE,
        )
        self.assertEqual(resolution.county, "orange")
```

### ★ T5. `test_owner_without_authorization_fails_closed` — `owner` expuesto sin gate
- **Invariante que protege:** CHERUBIM + regla del repo (nunca PII en repos/APIs) — `owner` existe solo "cuando sea apropiado"; por defecto ausente; exponerlo exige autorización explícita del consumidor.
- **Ataque exacto:** el normalizador copia `owner="Jane Doe"` del adapter al perfil para cualquier consumidor (incluido un lookup público de SCAN o un log). O el perfil con owner se serializa a CRONICAS / caché compartida sin redactar. El test: pasar `owner` sin `owner_authorized=True` → `FLPI_OWNER_UNAUTHORIZED` (fail closed, no silencioso `None` que oculte el intento); y `to_cronicas_event()` sobre un perfil autorizado jamás contiene el nombre.
- **Esqueleto:**
```python
import unittest

from zion_core.fl_property import (
    VERIFIED,
    to_cronicas_event,
    validate_property_profile,
)


def fixture_provenance():
    from zion_core.fl_property import PropertyProvenance
    return PropertyProvenance(
        source="orange-county-pa-fixture",
        source_record_id="01-22-28-0000-00-001",
        retrieved_at="2026-10-04T10:00:00-04:00",
        source_updated_at="2026-09-01T00:00:00-04:00",
        raw_reference="fixture://orange-pa/01-22-28-0000-00-001",
    )


class FlpiOwnerExposureTests(unittest.TestCase):
    def _kwargs(self, **overrides):
        base = dict(
            input_kind="PARCEL_ID", input_value="01-22-28-0000-00-001",
            county="orange", status=VERIFIED, provenance=fixture_provenance(),
            isolation_key="scan-water-intelligence", reason="fixture match",
        )
        base.update(overrides)
        return base

    def test_owner_without_authorization_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "FLPI_OWNER_UNAUTHORIZED"):
            validate_property_profile(
                **self._kwargs(owner="Jane Doe", owner_authorized=False))

    def test_authorized_consumer_receives_owner(self):
        profile = validate_property_profile(
            **self._kwargs(owner="Jane Doe", owner_authorized=True))
        self.assertEqual(profile.owner, "Jane Doe")

    def test_owner_never_leaks_into_cronicas_event(self):
        profile = validate_property_profile(
            **self._kwargs(owner="Jane Doe", owner_authorized=True))
        event = to_cronicas_event(profile)
        self.assertNotIn("Jane Doe", event)
        self.assertIn(profile.provenance.source, event)  # provenance sí, PII no
```

---

## LISTA COMPLETA POR CATEGORÍA

### 1. Cross-tenant substitution
- **T1** ★ (arriba).
- **`test_duplicate_isolation_key_fails_closed`** — Invariante: `isolation_key` único por business. Ataque: registry con `scan-water-intelligence` y `los-duros` compartiendo `isolation_key="shared-key"` (error de config o inyección) → `OmarRuntime`/dispatch colapsa dos tenants en uno. Assert: construir el runtime o despachar con ese registry levanta `ValueError("FLPI_ISOLATION_KEY_COLLISION")` / equivalente SAN PEDRO.
- **`test_deserialized_profile_is_rebound_to_requesting_tenant`** — Invariante: el tenant binding se re-valida en cada consumo, no se hereda del objeto. Ataque: un `PropertyProfile` de SCAN serializado (JSON/pickle) se deserializa dentro de un execution context de `los-duros`; el consumidor ingenuo confía en `profile.isolation_key` del payload. Assert: `validate_property_profile(..., requesting_isolation_key="los-duros")` sobre perfil sellado para SCAN → `FLPI_PROFILE_TENANT_MISMATCH`.
- **`test_registry_typo_business_does_not_shadow_canonical`** — Invariante: un business casi-idéntico no hereda contexto del canónico. Ataque: registry con `"scan-water-inteligence"` (typo) cuyas `context_refs` apuntan a los .md de SCAN. Assert: dispatch con el id typo recibe solo sus propios refs (vacíos/inexistentes → fail closed), nunca `# Scan`.

### 2. Wrong business context / spoofed identifiers
- **T3** ★ (arriba).
- **`test_none_business_id_does_not_default`** — Invariante: `business_id` requerido, sin default. Ataque: `plan_flpi_batch(..., business_id=None)` → el builder "ayuda" defaulteando a `SCAN_BUSINESS_ID`. Assert: `FLPI_BUSINESS_REQUIRED`.
- **`test_brand_id_is_not_business_id`** — Invariante: la resolución usa `business_id` del registry, no `brand_id`/alias comerciales. Ataque: pasar `"SCAN"` o `"scan"` (brand) esperando que resuelva. Assert: `FLPI_BUSINESS_UNKNOWN`.

### 3. County resolver
- **T4** ★ (arriba).
- **`test_invalid_zip_never_defaults_to_a_county`** — Invariante: ZIP malformado/desconocido falla antes de rutear. Ataque: `"00000"`, `"99999"` (no en fixture), `"1234"`, `"ABCDE"` → el resolver ingenuo cae a un county default o al primero del mapa. Assert: `FLPI_ZIP_INVALID` / `FLPI_ZIP_UNKNOWN`, sin campo `county` en el error.
- **`test_parcel_id_validated_per_county_format`** — Invariante: cada county tiene su formato de parcel ID (fixture); formato genérico permisivo = IDs malformados llegan a la fuente. Ataque: `"12-34-56"` contra fixture Orange `^\d{2}-\d{2}-\d{2}-\d{4}-\d{2}-\d{3}$`; o un ID con formato válido de Miami-Dade enviado al router de Orange. Assert: `FLPI_PARCEL_ID_MALFORMED` / `FLPI_PARCEL_COUNTY_MISMATCH`.
- **`test_coordinates_outside_fl_fail_before_county_lookup`** — Invariante: scope geográfico FL se valida antes de resolver county. Ataque: coordenadas en Georgia (32.0,-84.0), en el Golfo (agua, 27.5,-84.5), o (0,0) → el resolver "nearest county" las asigna a un county FL y produce un lookup absurdo. Assert: `FLPI_OUT_OF_SCOPE`, sin intento de fuente.
- **`test_address_matching_two_parcels_is_ambiguous`** — Invariante: address→parcela 1:N no elige. Ataque: `"123 Main St"` existe en Orlando (Orange) y Kissimmee (Osceola); o una dirección sin unidad matchea 4 sub-parcelas de un multifamiliar → el normalizador toma `matches[0]`. Assert: `FLPI_MATCH_AMBIGUOUS` con `candidates` preservados (los IDs de parcela de ambas), jamás un `PropertyProfile` VERIFIED.

### 4. Source router
- **`test_county_without_registered_source_fails_closed`** — Invariante: county sin fuente registrada → HUMAN REVIEW, nunca fallback silencioso. Ataque: no hay adapter para Glades → el router usa el de Hendry "porque es vecino". Assert: `FLPI_COUNTY_SOURCE_UNREGISTERED`.
- **`test_source_outage_is_unavailable_not_not_found`** — Invariante: caída de fuente ≠ `NOT_FOUND`. Ataque: adapter caído (fixture `raise TimeoutError`) → el router ingenuo lo traduce a `NOT_FOUND` → (compuesto T2) "no existe". Assert: status `UNAVAILABLE`, `reason` cita la fuente y el timeout.
- **`test_malformed_adapter_response_rejected_at_boundary`** — Invariante: el normalizador valida, no coerciona. Ataque: el adapter (fixture) devuelve `{"parcel": {...}}` sin `source_record_id`, o `source_updated_at` como string libre `"ayer"`. Assert: `FLPI_ADAPTER_RESPONSE_MALFORMED`; ningún perfil a medio construir escapa.
- **`test_timeout_fallback_never_serves_stale_as_verified`** — Invariante: el único fallback permitido ante timeout es degradar el status. Ataque: ante timeout, servir la entrada de caché vieja con status `VERIFIED` y `retrieved_at` fresco. Assert: el perfil degradado es `UNAVAILABLE`/`INCONCLUSIVE`, o si se sirve caché lleva `stale=True` explícito y status ≠ `VERIFIED`.
- **`test_ambiguous_source_match_preserves_candidates`** — (hermano de T4- address) Invariante: 2 parcelas del source → ambiguo con candidatos. Ataque: el normalizador elige por "score" interno del adapter. Assert: `FLPI_MATCH_AMBIGUOUS`; análogo directo al test `test_ambiguous_zip_cannot_smuggle_pwsid` de `scan_water`.

### 5. VerificationStatus
- **T2** ★ (arriba).
- **`test_missing_status_is_never_defaulted`** — Invariante: status ausente en payload del adapter = error, no default. Ataque: `status = payload.get("status") or "NOT_FOUND"` o `payload.get("status", "INCONCLUSIVE")` — el ingenuo "rellena" y fabrica semántica. Assert: `FLPI_STATUS_REQUIRED`.
- **`test_unknown_status_string_rejected`** — Invariante: enum cerrado de 4. Ataque: adapter devuelve `"FOUND"`, `"verified"` (case), `"PARTIAL"` → coercionado a `VERIFIED`. Assert: `FLPI_STATUS_INVALID`; el set válido es exactamente `{VERIFIED, NOT_FOUND, UNAVAILABLE, INCONCLUSIVE}`.

### 6. Provenance
- **`test_verified_without_provenance_rejected`** — Invariante: `VERIFIED` exige provenance completa. Ataque: perfil `VERIFIED` con `provenance=None` o `source=""` (el builder "lo llena después"). Assert: `FLPI_PROVENANCE_SOURCE_REQUIRED` (patrón `SCAN_RESOLVED_PWSID_REQUIRED` / `SCAN_RESOLVED_EVIDENCE_REQUIRED`).
- **`test_source_record_id_matches_source_pattern`** — Invariante: `source_record_id` no falsificable dentro del contrato. Ataque: el normalizador inventa/interpola el record id (`f"{county}-{parcel}"`) o acepta cualquier string. Assert: el id debe matchear el patrón declarado por la fuente en fixture; `raw_reference` es un puntero opaco de recuperación, jamás construido interpolando PII.
- **`test_freshness_uses_source_updated_at_not_retrieved_at`** — Invariante: "fresco" se juzga por `source_updated_at`. Ataque: consumidor ordena por `retrieved_at` (ayer) y declara "datos frescos" cuando `source_updated_at` tiene 3 años. Assert: predicado `is_fresh` usa `source_updated_at`; además `retrieved_at >= source_updated_at` o `FLPI_PROVENANCE_TIME_INVERSION`.
- **`test_raw_reference_pii_never_reaches_cronicas`** — Invariante: CRONICAS = historial operacional con PII acotada (AGENTS.md). Ataque: `raw_reference` contiene nombre del owner o dirección completa y se loguea tal cual. Assert: `to_cronicas_event()` redacta/trunca `raw_reference` y excluye `owner` (ver T5, tercer assert).

### 7. Cache
- **T1** ★ cubre contaminación cross-tenant (variante: escritura desde B leyendo entrada de A).
- **`test_cache_key_separates_input_kinds`** — Invariante: la key incluye `(tenant, input_kind, valor normalizado, versión de fuente)`. Ataque: `kind=ADDRESS, value="12345"` y `kind=PARCEL_ID, value="12345"` normalizan al mismo string → colisión: un lookup por dirección devuelve el perfil de una parcela. Assert: keys distintas; lookup cruzado = miss.
- **`test_stale_cache_served_as_stale_or_rejected`** — Invariante: `source_updated_at` viejo no se sirve como fresco. Ataque: entrada con `source_updated_at` de 2022 servida con status `VERIFIED` sin marca. Assert: `stale=True` explícito o `FLPI_CACHE_STALE` cuando el caller exige frescura.
- **`test_negative_cache_is_ttl_bounded`** — Invariante: `NOT_FOUND` cacheado expira; un negativo permanente = `NOT_FOUND` eterno aunque la fuente ya tenga datos. Ataque: entrada negativa sin `expires_at`. Assert: `flpi_cache_put` exige TTL en negativos; servir un negativo expirado → refresh o `FLPI_CACHE_STALE`.

### 8. Owner/PII
- **T5** ★ (arriba).
- **`test_owner_defaults_to_absent_not_null_leak`** — Invariante: ante la duda, se omite. Ataque: `owner=""` vs `owner=None` vs campo ausente tratados distinto por serializadores (el `""` se renderiza en un reporte). Assert: `validate_property_profile` normaliza a `None` y el serializador omite la llave.

### 9. SCAN-coupling
- **`test_capability_dispatches_for_non_scan_consumer`** — Invariante: la capability no es de SCAN; cualquier business autorizado la consume. Ataque: `fl_property.py` importa `SCAN_BUSINESS_ID` o `plan_flpi_batch` lo defaultea. Assert: dispatch con `business_id="los-duros"` funciona; `assert not hasattr(fl_property_module, "SCAN_BUSINESS_ID")` y sin imports de `scan_water`.
- **`test_scan_context_cannot_bleed_into_profile`** — Invariante: el perfil porta solo su `isolation_key`; nada de SCAN. Ataque: `mission_defaults={"risk_level":...}` del batch de SCAN, o knowledge de SCAN, terminan en campos del perfil o en `reason`. Assert: el perfil construido bajo SCAN no contiene strings de defaults de SCAN; `profile.isolation_key == "scan-water-intelligence"` y ningún otro business aparece en el objeto.
- **`test_batch_requires_explicit_consumer_business`** — Invariante: sin `business_id` explícito no hay batch (hermano de T2-`test_none_business_id_does_not_default`). Ataque: el builder reutiliza `plan_scan_zip_batch` como base y hereda el hardcode a SCAN. Assert: `FLPI_BUSINESS_REQUIRED`; `plan_flpi_batch` no delega en `plan_scan_zip_batch`.

---

## Notas para el parent / Builder
1. **Orden sugerido de construcción:** T1 (aislamiento) → T3 (spoofing) → T2 (semántica NOT_FOUND) → T4 (resolver) → T5 (owner). Son independientes entre sí salvo T2↔T4 (ataque compuesto documentado).
2. **Fixtures, no live:** todos los tests usan mapas/adapter fixtures en memoria (patrón `test_zion_scan_water.py`); la regla "adapters no hacen HTTP" se testea con `test_no_http_in_adapter` si el Builder añade dependencias de red (assert sobre imports).
3. **No implementé nada** — solo esqueletos y escenarios; el módulo `zion_core/fl_property.py` no existe en HEAD `5e36df4`.
4. Riesgo adyacente no pedido pero visible: cuando exista caché persistente, las reglas de idempotencia de `zion-development/SKILL.md` aplican — un retry no debe duplicar entradas ni extender TTLs silenciosamente.
