#!/usr/bin/env python3
"""Enriquecimiento de telefonos de leads (Puerto Rico) via NumVerify.

Lee una lista de telefonos, consulta NumVerify (plan gratis: 100/mes) y genera:
  - CSV enriquecido (valido, carrier, tipo de linea, ubicacion)
  - SQL para cargar los resultados en Supabase (tabla public.phone_enrichment)

Uso:
  NUMVERIFY_API_KEY=xxx python3 enrich_phones.py --input contactos.csv --out enriched.csv --sql enrich.sql
  python3 enrich_phones.py --mock --input contactos.csv --out enriched.csv --sql enrich.sql

El API key SIEMPRE va por variable de entorno. Nunca hardcodear ni commitear keys.
Con --mock no se hacen llamadas reales (datos falsos, para probar el pipeline).

El CSV de entrada debe tener columna `phone` (se aceptan formatos +1787..., 787-...,
etc.). Los numeros se normalizan a digitos antes de consultar.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API_URL = "https://apilayer.net/api/validate"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".enrich_cache.json")
RATE_LIMIT_S = 1.2  # pausa entre llamadas para no saturar el plan gratis


def norm_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10:  # NANP sin codigo de pais -> asumir +1 (PR: 787/939)
        digits = "1" + digits
    return digits


def mock_result(phone):
    return {
        "phone": phone,
        "valid": True,
        "international_format": "+" + phone,
        "country_code": "US",
        "country_name": "United States of America",
        "location": "Puerto Rico (MOCK)",
        "carrier": "Claro PR (MOCK)",
        "line_type": "mobile",
    }


def query_numverify(phone, api_key):
    params = urllib.parse.urlencode({"access_key": api_key, "number": phone, "country_code": "US"})
    req = urllib.request.Request(API_URL + "?" + params, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"phone": phone, "error": f"request failed: {e}"}
    if not data.get("valid") and data.get("error"):
        return {"phone": phone, "error": str(data["error"].get("info", data["error"]))}
    return {
        "phone": phone,
        "valid": bool(data.get("valid")),
        "international_format": data.get("international_format") or "",
        "country_code": data.get("country_code") or "",
        "country_name": data.get("country_name") or "",
        "location": data.get("location") or "",
        "carrier": data.get("carrier") or "",
        "line_type": data.get("line_type") or "",
    }


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache):
    json.dump(cache, open(CACHE_FILE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def sql_lit(v):
    if v is None or v == "":
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser(description="Enriquecer telefonos via NumVerify")
    ap.add_argument("--input", required=True, help="CSV con columna `phone`")
    ap.add_argument("--out", required=True, help="CSV enriquecido de salida")
    ap.add_argument("--sql", required=True, help="Archivo SQL de salida (para Supabase)")
    ap.add_argument("--mock", action="store_true", help="No llamar la API; usar datos falsos")
    args = ap.parse_args()

    api_key = os.environ.get("NUMVERIFY_API_KEY", "")
    if not args.mock and not api_key:
        print("ERROR: define NUMVERIFY_API_KEY o usa --mock", file=sys.stderr)
        sys.exit(2)

    rows = list(csv.DictReader(open(args.input, encoding="utf-8")))
    if "phone" not in (rows[0].keys() if rows else []):
        print("ERROR: el CSV debe tener columna `phone`", file=sys.stderr)
        sys.exit(2)

    phones = []
    seen = set()
    for r in rows:
        p = norm_phone(r["phone"])
        if p and p not in seen:
            seen.add(p)
            phones.append(p)
    print(f"{len(phones)} telefonos unicos a procesar")

    cache = load_cache()
    results = []
    calls = 0
    for p in phones:
        if p in cache:
            results.append(cache[p])
            continue
        res = mock_result(p) if args.mock else query_numverify(p, api_key)
        calls += 1
        if "error" not in res:
            cache[p] = res
        results.append(res)
        print(f"  [{calls}] {p}: " + (res.get("error") or f"valid={res['valid']} carrier={res['carrier']} type={res['line_type']}"))
        if not args.mock:
            time.sleep(RATE_LIMIT_S)
    save_cache(cache)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phone", "valid", "international_format", "country_code", "country_name",
                    "location", "carrier", "line_type", "whatsapp_ok", "error"])
        for r in results:
            w.writerow([r.get("phone"), r.get("valid"), r.get("international_format"),
                        r.get("country_code"), r.get("country_name"), r.get("location"),
                        r.get("carrier"), r.get("line_type"),
                        (r.get("valid") is True and r.get("line_type") == "mobile"),
                        r.get("error", "")])

    with open(args.sql, "w", encoding="utf-8") as f:
        f.write("-- Enriquecimiento de telefonos (NumVerify). Generado por enrich_phones.py\n")
        f.write("-- NO commitear este archivo si contiene telefonos reales (PII).\n\n")
        for r in results:
            if "error" in r:
                f.write(f"-- SKIP {r['phone']}: {r['error']}\n")
                continue
            f.write(
                "insert into public.phone_enrichment "
                "(phone, valid, number_e164, country_code, country_name, location, carrier, line_type) values ("
                + ", ".join([sql_lit(r["phone"]), sql_lit(r["valid"]), sql_lit(r["international_format"]),
                             sql_lit(r["country_code"]), sql_lit(r["country_name"]), sql_lit(r["location"]),
                             sql_lit(r["carrier"]), sql_lit(r["line_type"])])
                + ") on conflict (phone) do update set "
                "valid=excluded.valid, number_e164=excluded.number_e164, country_code=excluded.country_code, "
                "country_name=excluded.country_name, location=excluded.location, carrier=excluded.carrier, "
                "line_type=excluded.line_type, checked_at=now(), source='numverify';\n"
            )
    print(f"OK: {args.out} ({len(results)} filas), {args.sql}, llamadas API: {calls}")


if __name__ == "__main__":
    main()
