"""CRUD de usuários internos (tabela app_usuarios) + hash de senha."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from services.supabase_client import supabase

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_senha(plain: str) -> str:
    """Armazena hash com scrypt (stdlib)."""
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt1${salt.hex()}${h.hex()}"


def verificar_senha(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    if hashed.startswith("$2"):
        try:
            import bcrypt

            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        except ImportError:
            return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3 or parts[0] != "scrypt1":
            return False
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
        got = hashlib.scrypt(
            plain.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        return secrets.compare_digest(got, expected)
    except (ValueError, OSError, TypeError):
        return False


def email_valido(email: str) -> bool:
    return bool(_EMAIL_RE.match(_norm_email(email)))


def contar_usuarios() -> int:
    r = supabase.table("app_usuarios").select("id", count="exact").execute()
    return int(r.count or 0)


def contar_admins_ativos() -> int:
    r = (
        supabase.table("app_usuarios")
        .select("id", count="exact")
        .eq("perfil", "admin")
        .eq("ativo", True)
        .execute()
    )
    return int(r.count or 0)


def listar_usuarios_resumo() -> list[dict[str, Any]]:
    r = (
        supabase.table("app_usuarios")
        .select("id, nome, email, perfil, ativo, created_at, updated_at")
        .order("created_at", desc=True)
        .execute()
    )
    return list(r.data or [])


def buscar_por_email(email: str) -> dict[str, Any] | None:
    em = _norm_email(email)
    if not em:
        return None
    r = (
        supabase.table("app_usuarios")
        .select("id, nome, email, senha_hash, perfil, ativo")
        .eq("email", em)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def buscar_por_id(uid: str) -> dict[str, Any] | None:
    r = (
        supabase.table("app_usuarios")
        .select("id, nome, email, perfil, ativo")
        .eq("id", uid)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def criar_usuario(
    nome: str,
    email: str,
    senha_plana: str,
    perfil: str,
) -> dict[str, Any]:
    """Senha é obrigatória no cadastro (mín. 6 caracteres)."""
    if perfil not in ("admin", "cadastro"):
        raise ValueError("Perfil inválido.")
    if not email_valido(email):
        raise ValueError("E-mail inválido.")
    sp = (senha_plana or "").strip()
    if len(sp) < 6:
        raise ValueError("Senha deve ter pelo menos 6 caracteres.")
    row = {
        "nome": (nome or "").strip(),
        "email": _norm_email(email),
        "senha_hash": hash_senha(sp),
        "perfil": perfil,
        "ativo": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    r = supabase.table("app_usuarios").insert(row).execute()
    data = r.data or []
    if not data:
        raise RuntimeError("Falha ao criar usuário.")
    return data[0]


def atualizar_usuario(
    uid: str,
    *,
    nome: str | None = None,
    email: str | None = None,
    perfil: str | None = None,
    ativo: bool | None = None,
    nova_senha_plana: str | None = None,
) -> None:
    patch: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if nome is not None:
        patch["nome"] = nome.strip()
    if email is not None:
        if not email_valido(email):
            raise ValueError("E-mail inválido.")
        patch["email"] = _norm_email(email)
    if perfil is not None:
        if perfil not in ("admin", "cadastro"):
            raise ValueError("Perfil inválido.")
        patch["perfil"] = perfil
    if ativo is not None:
        patch["ativo"] = ativo
    if nova_senha_plana is not None:
        s = nova_senha_plana.strip()
        if len(s) < 6:
            raise ValueError("Senha deve ter pelo menos 6 caracteres.")
        patch["senha_hash"] = hash_senha(s)
    if len(patch) <= 1:
        return
    supabase.table("app_usuarios").update(patch).eq("id", uid).execute()
