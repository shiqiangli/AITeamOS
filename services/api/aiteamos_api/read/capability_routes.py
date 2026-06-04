"""Capability registry routes."""

from __future__ import annotations

from fastapi import APIRouter

from .capability_service import CapabilityRegistryResponse, CapabilityRegistryStatus, capability_registry, capability_registry_status

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilityRegistryResponse)
async def get_capabilities() -> CapabilityRegistryResponse:
    return capability_registry()


@router.get("/status", response_model=CapabilityRegistryStatus)
async def get_capabilities_status() -> CapabilityRegistryStatus:
    return capability_registry_status()
