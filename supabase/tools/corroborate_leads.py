#!/usr/bin/env python3
"""Agente de corroboracion de leads (deterministico, sin LLM).

Toma los telefonos enriquecidos por NumVerify y emite un veredicto por lead:
  consistente  - numero valido, movil, con datos coherentes
  dudoso       - valido pero con senales debiles (fijo/VoIP, sin carrier,
                 ubicacion no coincide con el pueblo del lead)
  descartable  - numero invalido

Si el CSV de contactos trae columna `town`/`municipality`, compara la
ubicacion de la API contra el pueblo del lead (normalizando acentos).

Uso:
  python3 corroborate_leads.py --enriched enriched.csv --contacts contactos.csv \
      --out verificacion.csv --sql verificacion.sql

No hace llamadas a APIs: trabaja sobre el CSV ya enriquecido.
El SQL de salida contiene telefonos reales -> NO commitear (PII).
"""

import argparse
import csv
import re
import unicodedata

# Companias que operan en Puerto Rico (segun lo observado en la API)
PR_CARRIERS = {
    "t-mobile puerto rico llc",
    "liberty mobile puerto rico inc.",
    "puerto rico telephone company inc. (prtc)",
    "puerto rico telephone company",
    "claro puerto rico",
}

MOBILE_OK = {"mobile"}
WEAK_LINE_TYPES = {"landline", "voip", "non-fixed voip", "fixed voip",
                   "premium", "toll_free", "toll-free", "voicemail", ""}


def norm(s):
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s)


def corroborate(phone, enr, town):
    reasons = []
    valid = str(enr.get("valid", "")).lower() == "true"
    line_type = norm(enr.get("line_type", ""))
    carrier = norm(enr.get("carrier", ""))
    location = norm(enr.get("location", ""))

    if not valid:
        return "descartable", ["numero invalido segun NumVerify"]

    if line_type in WEAK_LINE_TYPES:
        if line_type in ("landline",):
            reasons.append("linea fija: no sirve para WhatsApp")
        elif "voip" in line_type:
            reasons.append("linea VoIP: posible numero virtual/desechable")
        else:
            reasons.append(f"tipo de linea no movil: {line_type or 'desconocido'}")
    elif line_type not in MOBILE_OK:
        reasons.append(f"tipo de linea inesperado: {line_type}")

    if not carrier:
        reasons.append("sin informacion de compania")
    elif carrier not in PR_CARRIERS:
        reasons.append(f"compania fuera de PR o desconocida: {enr.get('carrier')}")

    if town and location:
        if norm(town) != location and norm(town) not in location and location not in norm(town):
            reasons.append(f"ubicacion del numero ({enr.get('location')}) no coincide con pueblo del lead ({town})")

    if not valid:
        verdict = "descartable"
    elif reasons:
        verdict = "dudoso"
    else:
        verdict = "consistente"
        reasons.append("movil valido, compania de PR")
    return verdict, reasons


def sql_lit(v):
    if v is None or v == "":
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser(description="Corroborar leads contra datos de NumVerify")
    ap.add_argument("--enriched", required=True, help="CSV de enrich_phones.py")
    ap.add_argument("--contacts", default="", help="CSV de contactos con columnas phone[,full_name[,town|municipality]] (opcional)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sql", required=True)
    args = ap.parse_args()

    enriched = {r["phone"]: r for r in csv.DictReader(open(args.enriched, encoding="utf-8"))}
    contacts = {}
    if args.contacts:
        for r in csv.DictReader(open(args.contacts, encoding="utf-8")):
            p = re.sub(r"\D", "", r.get("phone", "") or "")
            if p:
                contacts[p] = {"name": r.get("full_name", ""),
                               "town": r.get("town", "") or r.get("municipality", "")}

    results = []
    for phone, enr in enriched.items():
        c = contacts.get(phone, {})
        verdict, reasons = corroborate(phone, enr, c.get("town", ""))
        results.append({"phone": phone, "full_name": c.get("name", ""),
                        "verdict": verdict, "reasons": " | ".join(reasons),
                        "carrier": enr.get("carrier", ""), "line_type": enr.get("line_type", ""),
                        "location": enr.get("location", "")})

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["phone", "full_name", "verdict", "reasons", "carrier", "line_type", "location"])
        for r in results:
            w.writerow([r["phone"], r["full_name"], r["verdict"], r["reasons"],
                        r["carrier"], r["line_type"], r["location"]])

    with open(args.sql, "w", encoding="utf-8") as f:
        f.write("-- Veredictos de corroboracion de leads. NO commitear (PII).\n\n")
        for r in results:
            f.write("insert into public.lead_verification (phone, verdict, reasons) values ("
                    + ", ".join([sql_lit(r["phone"]), sql_lit(r["verdict"]), sql_lit(r["reasons"])])
                    + ") on conflict (phone) do update set verdict=excluded.verdict, "
                    "reasons=excluded.reasons, checked_at=now();\n")

    from collections import Counter
    print("veredictos:", dict(Counter(r["verdict"] for r in results)))
    print(f"OK: {args.out}, {args.sql}")


if __name__ == "__main__":
    main()
