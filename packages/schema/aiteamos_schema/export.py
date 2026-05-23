from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .models import API_SCHEMA_MODELS, API_VERSION, KIND_TO_MODEL, RunAssistanceBundleRecord, RunAssistedIngestInput


REF_TEMPLATE = "#/$defs/{model}"
SCHEMA_ID = "https://aiteamos.dev/schemas/aiteamos.dev/v1alpha1/manifest.schema.json"
AITEAMOS_BUNDLE_SCHEMA_ID = "https://aiteamos.dev/schemas/aiteamos.dev/v1alpha1/aiteamos-bundle.schema.json"


def build_json_schema_bundle() -> dict[str, Any]:
    defs = _combined_defs()
    manifest_refs = [{"$ref": f"#/$defs/{model.__name__}"} for model in KIND_TO_MODEL.values()]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "AITEAMOS v1alpha1 Manifest",
        "description": "Generated from Pydantic manifest models. Do not edit by hand.",
        "x-aiteamos-api-version": API_VERSION,
        "x-aiteamos-api-models": sorted(API_SCHEMA_MODELS),
        "x-aiteamos-kinds": sorted(KIND_TO_MODEL),
        "oneOf": manifest_refs,
        "$defs": defs,
    }


def build_aiteamos_bundle_schema() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    for model in (RunAssistanceBundleRecord, RunAssistedIngestInput):
        schema = model.model_json_schema(ref_template=REF_TEMPLATE)
        nested = schema.pop("$defs", {})
        for name, value in nested.items():
            _add_def(defs, name, value)
        _add_def(defs, model.__name__, schema)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": AITEAMOS_BUNDLE_SCHEMA_ID,
        "title": "AITEAMOS Bundle v1",
        "description": "Generated from Pydantic RunAssistanceBundleRecord for IDE-assisted handoff and ingest.",
        "x-aiteamos-api-version": API_VERSION,
        "$ref": f"#/$defs/{RunAssistanceBundleRecord.__name__}",
        "$defs": dict(sorted(defs.items())),
    }


def build_openapi_schema() -> dict[str, Any]:
    schemas = {
        name: _rewrite_refs(schema, from_prefix="#/$defs/", to_prefix="#/components/schemas/")
        for name, schema in _combined_defs().items()
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "AITEAMOS Manifest Schemas",
            "version": API_VERSION,
            "description": "Generated from Pydantic manifest models. Do not edit by hand.",
        },
        "paths": {},
        "components": {
            "schemas": schemas,
        },
        "x-aiteamos-api-models": sorted(API_SCHEMA_MODELS),
        "x-aiteamos-kinds": sorted(KIND_TO_MODEL),
    }


def build_typescript_types() -> str:
    schema = build_json_schema_bundle()
    defs: dict[str, Any] = schema["$defs"]
    lines = [
        "/*",
        " * Generated from Pydantic JSON Schema emitted by packages/schema/aiteamos_schema.",
        " * Do not edit by hand. Run `aiteamos schema export`.",
        " */",
        "",
        "export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };",
        "",
    ]
    for name in sorted(defs):
        lines.append(f"export type {name} = {_schema_to_ts(defs[name], defs)};")
        lines.append("")
    manifest_union = " | ".join(model.__name__ for model in KIND_TO_MODEL.values())
    lines.append(f"export type AiteamosManifest = {manifest_union};")
    lines.append(f"export type AiteamosManifestKind = { _literal_union(sorted(KIND_TO_MODEL)) };")
    lines.append("")
    return "\n".join(lines)


def export_schema_files(
    *,
    json_schema_path: str | Path | None = None,
    openapi_path: str | Path | None = None,
    typescript_path: str | Path | None = None,
    aiteamos_bundle_schema_path: str | Path | None = None,
) -> list[Path]:
    written: list[Path] = []
    if json_schema_path is not None:
        path = Path(json_schema_path)
        _write_json(path, build_json_schema_bundle())
        written.append(path)
    if openapi_path is not None:
        path = Path(openapi_path)
        _write_json(path, build_openapi_schema())
        written.append(path)
    if typescript_path is not None:
        path = Path(typescript_path)
        _write_text(path, build_typescript_types())
        written.append(path)
    if aiteamos_bundle_schema_path is not None:
        path = Path(aiteamos_bundle_schema_path)
        _write_json(path, build_aiteamos_bundle_schema())
        written.append(path)
    return written


def _combined_defs() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    for model in list(KIND_TO_MODEL.values()) + list(API_SCHEMA_MODELS.values()):
        schema = model.model_json_schema(ref_template=REF_TEMPLATE)
        nested = schema.pop("$defs", {})
        for name, value in nested.items():
            _add_def(defs, name, value)
        _add_def(defs, model.__name__, schema)
    return dict(sorted(defs.items()))


def _add_def(defs: dict[str, Any], name: str, schema: dict[str, Any]) -> None:
    existing = defs.get(name)
    if existing is not None and existing != schema:
        raise ValueError(f"schema definition name collision: {name}")
    defs[name] = schema


def _rewrite_refs(value: Any, *, from_prefix: str, to_prefix: str) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str) and item.startswith(from_prefix):
                rewritten[key] = f"{to_prefix}{item[len(from_prefix):]}"
            else:
                rewritten[key] = _rewrite_refs(item, from_prefix=from_prefix, to_prefix=to_prefix)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_refs(item, from_prefix=from_prefix, to_prefix=to_prefix) for item in value]
    return value


def _schema_to_ts(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_to_type(str(schema["$ref"]))
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=True)
    if "enum" in schema:
        return _literal_union(schema["enum"])
    if "anyOf" in schema:
        return _union([_schema_to_ts(item, defs) for item in schema["anyOf"]])
    if "oneOf" in schema:
        return _union([_schema_to_ts(item, defs) for item in schema["oneOf"]])
    if "allOf" in schema:
        return " & ".join(_parenthesize(_schema_to_ts(item, defs)) for item in schema["allOf"]) or "unknown"

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return _union([_schema_to_ts({**schema, "type": item}, defs) for item in schema_type])
    if schema_type == "null":
        return "null"
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "array":
        return f"Array<{_schema_to_ts(schema.get('items') or {}, defs)}>"
    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        return _object_to_ts(schema, defs)
    return "unknown"


def _object_to_ts(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    properties: dict[str, Any] = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    additional = schema.get("additionalProperties", False)
    if not properties:
        if isinstance(additional, dict):
            return f"Record<string, {_schema_to_ts(additional, defs)}>"
        return "Record<string, unknown>" if additional else "Record<string, never>"

    lines = ["{"]
    for name, prop_schema in properties.items():
        marker = "" if name in required else "?"
        lines.append(f"  {json.dumps(name, ensure_ascii=True)}{marker}: {_schema_to_ts(prop_schema, defs)};")
    if isinstance(additional, dict):
        lines.append(f"  [key: string]: {_schema_to_ts(additional, defs)};")
    elif additional:
        lines.append("  [key: string]: unknown;")
    lines.append("}")
    return "\n".join(lines)


def _ref_to_type(ref: str) -> str:
    prefix = "#/$defs/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return "unknown"


def _union(items: list[str]) -> str:
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return " | ".join(_parenthesize(item) for item in unique) or "unknown"


def _literal_union(values: list[Any]) -> str:
    return " | ".join(json.dumps(value, ensure_ascii=True) for value in values) or "never"


def _parenthesize(value: str) -> str:
    if "\n" in value or " | " in value or " & " in value:
        return f"({value})"
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
