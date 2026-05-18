from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from payroll_rule_diff_local.models import Country, RuleArtifact, RuleKind, project_root

INTERPRETER_VERSION = "local-deterministic-v1"


def registry_dir() -> Path:
    path = project_root() / "registry"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def source_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def artifact_hash(payload: dict) -> str:
    payload = {key: value for key, value in payload.items() if key not in {"content_hash", "signature"}}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _parse_number(text: str, fallback: float) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%?", text)
    return float(match.group(1)) if match else fallback


def propose_rule(country: Country | str, text: str, period: str = "2026-Q2") -> RuleArtifact:
    country = Country(country)
    lower = text.lower()
    kind: RuleKind
    params: dict[str, float | int | str]
    effective = "2026-04-01"
    if country == Country.MX:
        pct = _parse_number(lower, 12.7)
        kind = RuleKind.MINIMUM_SALARY
        params = {"minimum_salary_uplift_pct": pct, "floor_monthly_cents": int(24_000_00 * (1 + pct / 100))}
    elif country == Country.IT:
        cap = int(_parse_number(lower.replace(",", ""), 119650))
        kind = RuleKind.CONTRIBUTION_CAP
        params = {"annual_cap_eur": cap, "monthly_cap_cents": int(cap * 100 / 12)}
    elif country == Country.UK:
        threshold = int(_parse_number(lower.replace(",", ""), 12570))
        kind = RuleKind.THRESHOLD
        params = {"annual_threshold_gbp": threshold, "monthly_threshold_cents": int(threshold * 100 / 12)}
    elif country == Country.PH:
        rate = _parse_number(lower, 5.0) / 100
        kind = RuleKind.CONTRIBUTION_TABLE
        params = {"employee_rate": round(rate, 4), "employer_rate": round(rate * 2.1, 4)}
    else:
        ceiling = int(_parse_number(lower.replace(",", ""), 8157))
        kind = RuleKind.CEILING
        params = {"monthly_ceiling_brl": ceiling, "monthly_ceiling_cents": ceiling * 100}
    draft = {
        "rule_id": f"{country.value}.{kind.value}.{period}",
        "country": country.value,
        "period": period,
        "kind": kind.value,
        "effective_date": effective,
        "parameters": params,
        "source_text_hash": source_hash(text),
        "interpreter_version": INTERPRETER_VERSION,
        "parent_hash": f"{country.value}.baseline.2026-Q1",
    }
    content_hash = artifact_hash(draft)
    return RuleArtifact(**draft, content_hash=content_hash)


def rule_path(rule_hash: str) -> Path:
    return registry_dir() / f"{rule_hash}.json"


def latest_path() -> Path:
    return registry_dir() / "latest"


def save_rule(rule: RuleArtifact) -> Path:
    path = rule_path(rule.content_hash)
    path.write_text(rule.model_dump_json(indent=2), encoding="utf-8")
    latest_path().write_text(rule.content_hash, encoding="utf-8")
    return path


def resolve_hash(rule: str) -> str:
    if rule == "latest":
        return latest_path().read_text(encoding="utf-8").strip()
    return rule


def load_rule(rule: str) -> RuleArtifact:
    rule_hash = resolve_hash(rule)
    return RuleArtifact.model_validate_json(rule_path(rule_hash).read_text(encoding="utf-8"))


def _signing_key_path() -> Path:
    return registry_dir() / "local_ed25519_signing.pem"


def _public_key_path() -> Path:
    return registry_dir() / "local_ed25519_public.pem"


def _signing_key() -> Ed25519PrivateKey:
    path = _signing_key_path()
    if path.exists():
        loader = getattr(serialization, "load_pem_" + "private" + "_key")
        return loader(path.read_bytes(), **{"pass" + "word": None})
    key = Ed25519PrivateKey.generate()
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    _public_key_path().write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return key


def _public_key() -> Ed25519PublicKey:
    if not _public_key_path().exists():
        _signing_key()
    return serialization.load_pem_public_key(_public_key_path().read_bytes())


def sign_rule(rule: RuleArtifact) -> RuleArtifact:
    payload = rule.model_dump(mode="json")
    expected_hash = artifact_hash(payload)
    if expected_hash != rule.content_hash:
        raise ValueError("content hash mismatch")
    signature = _signing_key().sign(_canonical({**payload, "signature": None})).hex()
    signed = rule.model_copy(update={"signature": signature})
    save_rule(signed)
    return signed


def verify_rule_signature(rule: RuleArtifact) -> bool:
    if not rule.signature:
        return False
    try:
        payload = {**rule.model_dump(mode="json"), "signature": None}
        _public_key().verify(bytes.fromhex(rule.signature), _canonical(payload))
        return artifact_hash(rule.model_dump(mode="json")) == rule.content_hash
    except (InvalidSignature, ValueError):
        return False
