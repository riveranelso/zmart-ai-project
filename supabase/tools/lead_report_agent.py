#!/usr/bin/env python3
"""Agente automatico de reporte de leads (Zmart CR).

Pipeline:
  1. Busca en Gmail notificaciones "NUEVO LEAD" posteriores al watermark.
  2. Extrae nombre, telefono, email, direccion, ciudad, ZIP.
  3. Enriquece el telefono via NumVerify (con cache local; respeta cuota gratis).
  4. Corrobora: veredicto consistente/dudoso/descartable + razones
     (incluye comparacion pueblo del lead vs ubicacion del numero).
  5. Envia el reporte por email a riveranelso@gmail.com (o --dry-run).
  6. Actualiza el watermark.

Uso:
  python3 lead_report_agent.py [--dry-run] [--since-days N] [--to email]

El key de NumVerify sale del conector custom.numverify si existe,
si no de la variable NUMVERIFY_API_KEY. Nunca hardcodear keys.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from corroborate_leads import corroborate  # reglas de veredicto (sin PII en repo)

WATERMARK = os.path.join(HERE, ".lead_report_watermark.json")
CACHE = os.path.join(HERE, ".enrich_cache.json")
NUMVERIFY_URL = "https://apilayer.net/api/validate"
GMAIL = ["hatch_gws_cli", "gmail"]
DEFAULT_TO = "riveranelso@gmail.com"
LEAD_QUERY = 'subject:"NUEVO LEAD"'


def gws(*args):
    r = subprocess.run(GMAIL + list(args), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gmail fallo: {r.stderr[:300]}")
    return r.stdout


def get_numverify_caller():
    """Devuelve funcion numero->dict usando conector o env (sin llamada de prueba: ahorra cuota)."""
    try:
        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        import dynamic_credentials as dc
        entry = dc.dynamic_credential_entry("custom.numverify")  # valida que existe
        def via_connector(phone):
            params = urllib.parse.urlencode({"number": phone, "country_code": "US"})
            url = dc.url_with_surrogate_query_param(
                f"{NUMVERIFY_URL}?{params}", "custom.numverify",
                allowed_hosts=["apilayer.net"])
            with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=25) as resp:
                return dc.read_json_response(resp)
        return via_connector
    except Exception:
        pass
    key = os.environ.get("NUMVERIFY_API_KEY", "")
    if not key:
        raise RuntimeError("Sin acceso a NumVerify: ni conector ni NUMVERIFY_API_KEY")
    def via_env(phone):
        params = urllib.parse.urlencode(
            {"access_key": key, "number": phone, "country_code": "US"})
        with urllib.request.urlopen(
                urllib.request.Request(f"{NUMVERIFY_URL}?{params}", method="GET"),
                timeout=25) as resp:
            return json.loads(resp.read().decode())
    return via_env


def load_cache():
    return json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def save_cache(c):
    json.dump(c, open(CACHE, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def load_watermark():
    if os.path.exists(WATERMARK):
        return json.load(open(WATERMARK, encoding="utf-8"))
    return {"last_internal_ms": 0, "last_id": ""}


def save_watermark(w):
    json.dump(w, open(WATERMARK, "w", encoding="utf-8"), indent=1)


def clean_field(line, label):
    m = re.search(re.escape(label) + r"\s+(.+)", line)
    if not m:
        return ""
    val = m.group(1).strip()
    val = re.sub(r"\s*\[.*$", "", val).strip()  # quita [tel:...] / [mailto:...]
    return val


def parse_lead(text):
    """Extrae campos del cuerpo plano del email de lead."""
    get = lambda label: next((clean_field(l, label) for l in text.splitlines()
                              if l.strip().startswith(label)), "")
    phone = re.sub(r"\D", "", get("Teléfono"))
    if len(phone) == 10:
        phone = "1" + phone
    return {
        "name": get("Nombre"),
        "phone": phone,
        "email": get("Email"),
        "address": get("Dirección"),
        "city": get("Ciudad"),
        "zip": get("Código postal"),
    }


def fetch_new_leads(since_days):
    wm = load_watermark()
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    q = f'{LEAD_QUERY} after:{since.strftime("%Y/%m/%d")}'
    msgs = json.loads(gws("+triage", "--query", q, "--max", "50", "--format", "json")
                      ).get("messages", [])
    leads = []
    newest_ms = wm["last_internal_ms"]
    for m in msgs:
        mid = m["id"]
        det = json.loads(gws("users", "messages", "get", "--params",
                             json.dumps({"userId": "me", "id": mid, "format": "full"})))
        internal_ms = int(det.get("internalDate", "0"))
        if internal_ms <= wm["last_internal_ms"]:
            continue
        body = ""
        for part in det.get("payload", {}).get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                import base64
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
                break
        lead = parse_lead(body)
        if not lead["phone"]:
            # fallback: telefono del subject "NUEVO LEAD — Zmart CR | Nombre | +1 787-..."
            subj = m.get("subject", "")
            pm = re.search(r"\+\d[\d\s\-\(\)]+", subj)
            if pm:
                lead["phone"] = re.sub(r"\D", "", pm.group(0))
            nm = re.search(r"NUEVO LEAD\s*[—–-]\s*Zmart CR\s*\|\s*(.+?)\s*\|", subj)
            if nm and not lead["name"]:
                lead["name"] = nm.group(1).strip()
        if lead["phone"]:
            lead["gmail_id"] = mid
            lead["date_ms"] = internal_ms
            leads.append(lead)
        newest_ms = max(newest_ms, internal_ms)
    # dedup por telefono dentro del lote
    seen, uniq = set(), []
    for l in leads:
        if l["phone"] not in seen:
            seen.add(l["phone"])
            uniq.append(l)
    return uniq, newest_ms


def enrich_phones(phones, caller, cache):
    import urllib.error
    out = {}
    for p in phones:
        if p in cache:
            out[p] = cache[p]
            continue
        r = None
        for attempt in range(3):
            try:
                d = caller(p)
                r = {"phone": p, "valid": bool(d.get("valid")),
                     "international_format": d.get("international_format") or "",
                     "country_code": d.get("country_code") or "",
                     "country_name": d.get("country_name") or "",
                     "location": d.get("location") or "",
                     "carrier": d.get("carrier") or "",
                     "line_type": d.get("line_type") or ""}
                if not d.get("valid") and d.get("error"):
                    r = {"phone": p, "error": str(d["error"])}
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(15 * (attempt + 1))  # backoff en rate limit
                    continue
                r = {"phone": p, "error": f"HTTP {e.code}"}
                break
            except Exception as e:
                r = {"phone": p, "error": str(e)[:120]}
                break
        if "error" not in r:
            cache[p] = r
        out[p] = r
        time.sleep(2.0)
    save_cache(cache)
    return out


def build_report(leads, enriched):
    rows = []
    for l in leads:
        enr = enriched.get(l["phone"], {})
        if "error" in enr:
            verdict, reasons = "dudoso", [f"no se pudo validar: {enr['error']}"]
        else:
            verdict, reasons, notes = corroborate(
                l["phone"],
                {"valid": str(enr.get("valid", False)),
                 "line_type": enr.get("line_type", ""),
                 "carrier": enr.get("carrier", ""),
                 "location": enr.get("location", "")},
                l.get("city", ""))
            reasons = reasons + [f"nota: {n}" for n in notes]
        rows.append({**l, "verdict": verdict, "reasons": " | ".join(reasons),
                     "carrier": enr.get("carrier", ""), "line_type": enr.get("line_type", ""),
                     "api_location": enr.get("location", "")})
    return rows


COLOR = {"consistente": "#1a7f37", "dudoso": "#b26a00", "descartable": "#b42318"}


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def report_html(rows, since_days):
    from collections import Counter
    c = Counter(r["verdict"] for r in rows)
    trs = []
    for r in rows:
        trs.append(
            f"<tr><td>{esc(r['name'])}</td><td>{esc(r['phone'])}</td>"
            f"<td>{esc(r['email'])}</td><td>{esc(r['city'])} {esc(r['zip'])}</td>"
            f"<td style='color:{COLOR.get(r['verdict'],'#000')};font-weight:bold'>{r['verdict']}</td>"
            f"<td>{esc(r['reasons'])}</td>"
            f"<td>{esc(r['carrier'])} / {esc(r['line_type'])} / {esc(r['api_location'])}</td></tr>")
    return f"""<h2>Reporte de leads — Zmart CR</h2>
<p>Nuevos leads (últimos {since_days} días): <b>{len(rows)}</b> —
<span style="color:{COLOR['consistente']}">consistentes: {c.get('consistente',0)}</span> ·
<span style="color:{COLOR['dudoso']}">dudosos: {c.get('dudoso',0)}</span> ·
<span style="color:{COLOR['descartable']}">descartables: {c.get('descartable',0)}</span></p>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>Nombre</th><th>Teléfono</th><th>Email</th><th>Ciudad/ZIP</th><th>Veredicto</th><th>Razones</th><th>Carrier / Línea / Ubicación API</th></tr>
{''.join(trs) if trs else '<tr><td colspan="7">Sin leads nuevos en el período.</td></tr>'}
</table>
<p style="color:#666;font-size:12px">Generado automáticamente por el agente de corroboración (NumVerify + reglas determinísticas).</p>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since-days", type=int, default=7)
    ap.add_argument("--to", default=DEFAULT_TO)
    args = ap.parse_args()

    leads, newest_ms = fetch_new_leads(args.since_days)
    print(f"leads nuevos: {len(leads)}")
    caller = get_numverify_caller()
    cache = load_cache()
    enriched = enrich_phones([l["phone"] for l in leads], caller, cache)
    rows = build_report(leads, enriched)
    html = report_html(rows, args.since_days)

    if args.dry_run:
        print(html[:1500])
        print("... [dry-run: no se envía email ni se actualiza watermark]")
        return

    subj = f"Reporte de leads Zmart CR — {len(rows)} nuevos"
    gws("+send", "--to", args.to, "--subject", subj, "--html", "--body", html)
    print(f"email enviado a {args.to}")
    wm = load_watermark()
    wm["last_internal_ms"] = max(newest_ms, wm["last_internal_ms"])
    save_watermark(wm)
    print("watermark actualizado")


if __name__ == "__main__":
    main()
