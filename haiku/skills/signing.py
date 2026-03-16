import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

logger = logging.getLogger(__name__)

_EXCLUDE_FILES = {"SKILL.sigstore"}
_EXCLUDE_DIRS = {"__pycache__", "node_modules"}
_EXCLUDE_EXTENSIONS = {".pyc", ".pyo"}
_SIGSTORE_ISSUER_OID = "1.3.6.1.4.1.57264.1.1"


@dataclass(frozen=True)
class TrustedIdentity:
    identity: str
    issuer: str


def _import_sigstore() -> SimpleNamespace:
    """Import sigstore components, raising ImportError if not installed."""
    try:
        from sigstore.errors import VerificationError
        from sigstore.models import Bundle, ClientTrustConfig
        from sigstore.oidc import IdentityToken, Issuer, detect_credential
        from sigstore.sign import SigningContext, sigstore_hashes
        from sigstore.verify import Verifier
        from sigstore.verify.policy import AnyOf, Identity
    except ImportError:
        raise ImportError(
            "sigstore is required for signing and verification. "
            "Install with: pip install haiku.skills[signing]"
        ) from None

    return SimpleNamespace(
        Bundle=Bundle,
        ClientTrustConfig=ClientTrustConfig,
        IdentityToken=IdentityToken,
        Issuer=Issuer,
        detect_credential=detect_credential,
        SigningContext=SigningContext,
        Hashed=sigstore_hashes.Hashed,
        HashAlgorithm=sigstore_hashes.HashAlgorithm,
        Verifier=Verifier,
        VerificationError=VerificationError,
        Identity=Identity,
        AnyOf=AnyOf,
    )


def _collect_gitignore_patterns(skill_dir: Path):
    """Collect .gitignore patterns from skill_dir up to the repository root.

    Walks from ``skill_dir`` toward the filesystem root, collecting patterns
    from every ``.gitignore`` found. Stops when a ``.git`` directory is
    encountered (repo root) or the filesystem root is reached.

    Returns a compiled ``PathSpec``, or ``None`` if no ``.gitignore`` was found.

    Note: patterns from parent ``.gitignore`` files are applied relative to the
    skill directory, not to the directory where the ``.gitignore`` lives. This
    differs from git's scoping rules but is sufficient in practice since
    gitignore patterns are typically for generated artifacts (``node_modules/``,
    ``build/``, etc.) that match regardless of relative root.
    """
    patterns: list[str] = []
    current = skill_dir.resolve()

    while True:
        gitignore = current / ".gitignore"
        if gitignore.is_file():
            patterns.extend(gitignore.read_text().splitlines())

        if (current / ".git").is_dir():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    if not patterns:
        return None

    import pathspec

    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def _walk_skill_files(skill_dir: Path) -> list[Path]:
    """Walk a skill directory and return sorted relative paths to include in the hash.

    Applies two layers of filtering:

    1. **Always excluded**:
       - ``SKILL.sigstore`` (the signature bundle itself)
       - Hidden files and directories (names starting with ``'.'``)
       - ``__pycache__/`` and ``node_modules/`` directories
       - ``.pyc`` and ``.pyo`` files

    2. **Gitignore patterns** (when ``.gitignore`` files are found walking
       up from the skill directory to the repository root): any file
       matched by the combined patterns is excluded as well.
    """
    gitignore_spec = _collect_gitignore_patterns(skill_dir)

    files = []
    for file_path in sorted(skill_dir.rglob("*")):
        if not file_path.is_file():
            continue

        rel = file_path.relative_to(skill_dir)
        parts = rel.parts

        if any(p.startswith(".") for p in parts):
            continue
        if any(p in _EXCLUDE_DIRS for p in parts):
            continue
        if file_path.name in _EXCLUDE_FILES:
            continue
        if file_path.suffix in _EXCLUDE_EXTENSIONS:
            continue
        if gitignore_spec is not None and gitignore_spec.match_file(str(rel)):
            continue

        files.append(rel)
    return files


def hash_skill_directory(skill_dir: Path) -> bytes:
    """Compute a deterministic SHA-256 hash of a skill directory's contents.

    Files are selected by :func:`_walk_skill_files`, which applies built-in
    exclusions and respects ``.gitignore`` patterns when present.
    """
    hasher = hashlib.sha256()
    for rel in _walk_skill_files(skill_dir):
        hasher.update(str(rel).encode("utf-8"))
        hasher.update((skill_dir / rel).read_bytes())

    return hasher.digest()


def sign_skill(skill_dir: Path) -> None:
    """Sign a skill directory and write SKILL.sigstore bundle."""
    if not (skill_dir / "SKILL.md").exists():
        raise ValueError(f"No SKILL.md found in {skill_dir}")

    sigstore = _import_sigstore()

    credential = sigstore.detect_credential()
    if credential is not None:
        identity_token = sigstore.IdentityToken.from_jwt(credential)
    else:
        issuer = sigstore.Issuer("https://oauth2.sigstore.dev/auth")
        identity_token = issuer.identity_token()
    trust_config = sigstore.ClientTrustConfig.production()
    signing_ctx = sigstore.SigningContext.from_trust_config(trust_config)

    digest = hash_skill_directory(skill_dir)
    hashed = sigstore.Hashed(digest=digest, algorithm=sigstore.HashAlgorithm.SHA2_256)

    with signing_ctx.signer(identity_token) as signer:
        bundle = signer.sign_artifact(hashed)

    bundle_path = skill_dir / "SKILL.sigstore"
    bundle_path.write_text(bundle.to_json())
    logger.info("Signed skill at %s", skill_dir)


def get_bundle_signer(skill_dir: Path) -> TrustedIdentity | None:
    """Extract the signer identity from a skill's sigstore bundle.

    Returns None if no bundle exists or the bundle can't be parsed.
    """
    bundle_path = skill_dir / "SKILL.sigstore"
    if not bundle_path.exists():
        return None

    import base64
    import json

    from cryptography import x509
    from cryptography.x509 import ObjectIdentifier

    try:
        bundle_data = json.loads(bundle_path.read_text())
        cert_bytes = base64.b64decode(
            bundle_data["verificationMaterial"]["certificate"]["rawBytes"]
        )
        cert = x509.load_der_x509_certificate(cert_bytes)

        san = cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        identity = san.value[0].value  # type: ignore[index]

        issuer_oid = ObjectIdentifier(_SIGSTORE_ISSUER_OID)
        issuer_ext = cert.extensions.get_extension_for_oid(issuer_oid)
        issuer = issuer_ext.value.value.decode()  # type: ignore[union-attr]

        return TrustedIdentity(identity=identity, issuer=issuer)
    except Exception:
        logger.debug("Failed to extract signer from %s", bundle_path, exc_info=True)
        return None


def verify_skill(
    skill_dir: Path,
    trusted_identities: Sequence[TrustedIdentity],
) -> bool:
    """Verify a skill's sigstore bundle against trusted identities.

    Returns True if verification succeeds, False if no bundle exists
    or verification fails.
    """
    bundle_path = skill_dir / "SKILL.sigstore"
    if not bundle_path.exists():
        return False

    sigstore = _import_sigstore()

    bundle = sigstore.Bundle.from_json(bundle_path.read_text())
    verifier = sigstore.Verifier.production()

    digest = hash_skill_directory(skill_dir)
    hashed = sigstore.Hashed(digest=digest, algorithm=sigstore.HashAlgorithm.SHA2_256)

    policy = sigstore.AnyOf(
        children=[
            sigstore.Identity(identity=ti.identity, issuer=ti.issuer)
            for ti in trusted_identities
        ]
    )

    try:
        verifier.verify_artifact(hashed, bundle, policy)
        return True
    except sigstore.VerificationError:
        logger.debug("Signature verification failed for %s", skill_dir, exc_info=True)
        return False
