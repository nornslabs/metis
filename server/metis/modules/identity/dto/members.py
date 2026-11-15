"""Membership DTOs: roles and new members."""

from __future__ import annotations

from enum import StrEnum

from metis.helpers.dto import Email, FrozenModel


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class NewMember(FrozenModel):
    email: Email
    role: MemberRole
