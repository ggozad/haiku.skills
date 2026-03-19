from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haiku.skills.signing import (
    TrustedIdentity,
    _collect_gitignore_patterns,
    _import_sigstore,
    get_bundle_signer,
    hash_skill_directory,
    sign_skill,
    verify_skill,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestTrustedIdentity:
    def test_creation(self):
        ti = TrustedIdentity(
            identity="user@example.com",
            issuer="https://accounts.google.com",
        )
        assert ti.identity == "user@example.com"
        assert ti.issuer == "https://accounts.google.com"

    def test_frozen(self):
        ti = TrustedIdentity(identity="a", issuer="b")
        with pytest.raises(AttributeError):
            ti.identity = "c"  # type: ignore[misc]


class TestImportSigstore:
    def test_imports_sigstore_components(self):
        ns = _import_sigstore()
        assert hasattr(ns, "Bundle")
        assert hasattr(ns, "ClientTrustConfig")
        assert hasattr(ns, "SigningContext")
        assert hasattr(ns, "Verifier")
        assert hasattr(ns, "VerificationError")
        assert hasattr(ns, "Identity")
        assert hasattr(ns, "AnyOf")
        assert hasattr(ns, "UnsafeNoOp")
        assert hasattr(ns, "Hashed")
        assert hasattr(ns, "detect_credential")
        assert hasattr(ns, "IdentityToken")

    def test_raises_helpful_error_when_missing(self, monkeypatch: pytest.MonkeyPatch):
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("sigstore"):
                raise ImportError("No module named 'sigstore'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="haiku.skills\\[signing\\]"):
            _import_sigstore()


class TestCollectGitignorePatterns:
    def test_returns_none_without_gitignore(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        assert _collect_gitignore_patterns(skill_dir) is None

    def test_reads_local_gitignore(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / ".gitignore").write_text("node_modules/\n*.log\n")

        spec = _collect_gitignore_patterns(skill_dir)
        assert spec is not None
        assert spec.match_file("node_modules/foo/index.js")
        assert spec.match_file("error.log")
        assert not spec.match_file("SKILL.md")

    def test_reads_parent_gitignore(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / ".gitignore").write_text("__pycache__/\n")

        skill_dir = repo / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)

        spec = _collect_gitignore_patterns(skill_dir)
        assert spec is not None
        assert spec.match_file("__pycache__/module.pyc")

    def test_combines_local_and_parent_patterns(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / ".gitignore").write_text("node_modules/\n")

        skill_dir = repo / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / ".gitignore").write_text("*.log\n")

        spec = _collect_gitignore_patterns(skill_dir)
        assert spec is not None
        assert spec.match_file("node_modules/pkg/index.js")
        assert spec.match_file("debug.log")
        assert not spec.match_file("SKILL.md")

    def test_stops_at_git_directory(self, tmp_path: Path):
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / ".gitignore").write_text("*.secret\n")

        repo = outer / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        skill_dir = repo / "skill"
        skill_dir.mkdir()

        spec = _collect_gitignore_patterns(skill_dir)
        # Should NOT pick up outer/.gitignore (past the .git boundary)
        assert spec is None or not spec.match_file("test.secret")

    def test_stops_at_filesystem_root(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        # No .gitignore anywhere — should return None without error
        assert _collect_gitignore_patterns(skill_dir) is None


class TestHashSkillDirectory:
    def test_deterministic(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\nBody.\n")
        (skill_dir / "script.py").write_text("print('hello')\n")

        h1 = hash_skill_directory(skill_dir)
        h2 = hash_skill_directory(skill_dir)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path: Path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / "SKILL.md").write_text("content-a")

        dir_b = tmp_path / "b"
        dir_b.mkdir()
        (dir_b / "SKILL.md").write_text("content-b")

        assert hash_skill_directory(dir_a) != hash_skill_directory(dir_b)

    def test_excludes_sigstore_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        (skill_dir / "SKILL.sigstore").write_text("bundle-data")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_excludes_pycache(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        cache_dir = skill_dir / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.cpython-313.pyc").write_bytes(b"\x00\x01")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_excludes_pyc_files(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        (skill_dir / "stale.pyc").write_bytes(b"\x00")
        (skill_dir / "stale.pyo").write_bytes(b"\x00")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_excludes_hidden_files(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        (skill_dir / ".hidden").write_text("secret")
        hidden_dir = skill_dir / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config").write_text("data")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_includes_subdirectories(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "run.py").write_text("print('run')")
        h_after = hash_skill_directory(skill_dir)

        assert h_before != h_after

    def test_path_order_matters(self, tmp_path: Path):
        """Files are sorted by relative path, so hash is independent of OS walk order."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "a.txt").write_text("same")
        (skill_dir / "b.txt").write_text("same")

        h = hash_skill_directory(skill_dir)

        # Recreate in different order
        skill_dir2 = tmp_path / "skill2"
        skill_dir2.mkdir()
        (skill_dir2 / "b.txt").write_text("same")
        (skill_dir2 / "a.txt").write_text("same")

        assert hash_skill_directory(skill_dir2) == h

    def test_returns_bytes(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        result = hash_skill_directory(skill_dir)
        assert isinstance(result, bytes)
        assert len(result) == 32  # SHA-256

    def test_excludes_node_modules(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        nm = skill_dir / "node_modules"
        nm.mkdir()
        pkg = nm / "some-pkg"
        pkg.mkdir()
        (pkg / "index.js").write_text("module.exports = {}")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_respects_gitignore(self, tmp_path: Path):
        """Files matching .gitignore patterns are excluded from hash."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / ".gitignore").write_text("*.log\nbuild/\n")

        h_before = hash_skill_directory(skill_dir)
        (skill_dir / "debug.log").write_text("log data")
        build = skill_dir / "build"
        build.mkdir()
        (build / "output.js").write_text("compiled")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_respects_parent_gitignore(self, tmp_path: Path):
        """Parent .gitignore patterns apply to skill subdirectories."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        (repo / ".gitignore").write_text("node_modules/\n")

        skill_dir = repo / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("content")

        h_before = hash_skill_directory(skill_dir)
        nm = skill_dir / "node_modules"
        nm.mkdir()
        (nm / "pkg" / "index.js").parent.mkdir(parents=True)
        (nm / "pkg" / "index.js").write_text("module.exports = {}")
        h_after = hash_skill_directory(skill_dir)

        assert h_before == h_after

    def test_non_ignored_files_included(self, tmp_path: Path):
        """Files not matching .gitignore are still included in hash."""
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / ".gitignore").write_text("*.log\n")

        h_before = hash_skill_directory(skill_dir)
        (skill_dir / "script.py").write_text("print('hi')")
        h_after = hash_skill_directory(skill_dir)

        assert h_before != h_after

    def test_real_fixture(self):
        h = hash_skill_directory(FIXTURES / "simple-skill")
        assert isinstance(h, bytes)
        assert len(h) == 32


class TestSignSkill:
    def test_raises_without_skill_md(self, tmp_path: Path):
        skill_dir = tmp_path / "not-a-skill"
        skill_dir.mkdir()
        with pytest.raises(ValueError, match="SKILL.md"):
            sign_skill(skill_dir)

    def test_raises_without_sigstore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore",
            MagicMock(
                side_effect=ImportError(
                    "sigstore is required for signing and verification. "
                    "Install with: pip install haiku.skills[signing]"
                )
            ),
        )
        with pytest.raises(ImportError, match="haiku.skills\\[signing\\]"):
            sign_skill(skill_dir)

    def test_signs_and_writes_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = '{"bundle": "data"}'

        mock_signer = MagicMock()
        mock_signer.sign_artifact.return_value = mock_bundle
        mock_signer.__enter__ = MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = MagicMock(return_value=False)

        mock_signing_ctx = MagicMock()
        mock_signing_ctx.signer.return_value = mock_signer

        mock_sigstore = MagicMock()
        mock_sigstore.SigningContext.from_trust_config.return_value = mock_signing_ctx
        mock_sigstore.IdentityToken.from_jwt.return_value = MagicMock()
        mock_sigstore.detect_credential.return_value = "fake-jwt-token"
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        sign_skill(skill_dir)

        bundle_path = skill_dir / "SKILL.sigstore"
        assert bundle_path.exists()
        assert bundle_path.read_text() == '{"bundle": "data"}'

    def test_falls_back_to_browser_oidc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = '{"bundle": "data"}'

        mock_signer = MagicMock()
        mock_signer.sign_artifact.return_value = mock_bundle
        mock_signer.__enter__ = MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = MagicMock(return_value=False)

        mock_signing_ctx = MagicMock()
        mock_signing_ctx.signer.return_value = mock_signer

        mock_issuer = MagicMock()
        mock_identity_token = MagicMock()
        mock_issuer.identity_token.return_value = mock_identity_token

        mock_sigstore = MagicMock()
        mock_sigstore.detect_credential.return_value = None
        mock_sigstore.Issuer.return_value = mock_issuer
        mock_sigstore.SigningContext.from_trust_config.return_value = mock_signing_ctx
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        sign_skill(skill_dir)

        mock_sigstore.Issuer.assert_called_once_with("https://oauth2.sigstore.dev/auth")
        mock_issuer.identity_token.assert_called_once()
        assert (skill_dir / "SKILL.sigstore").read_text() == '{"bundle": "data"}'

    def test_raises_when_oidc_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        mock_sigstore = MagicMock()
        mock_sigstore.detect_credential.return_value = None
        mock_sigstore.Issuer.return_value.identity_token.side_effect = Exception(
            "OIDC flow failed"
        )

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        with pytest.raises(Exception, match="OIDC flow failed"):
            sign_skill(skill_dir)


class TestBundleSigner:
    def test_returns_none_without_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        assert get_bundle_signer(skill_dir) is None

    def test_extracts_identity_from_bundle(self, tmp_path: Path):
        import base64
        import json
        from datetime import datetime, timedelta

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509 import NameOID, ObjectIdentifier

        # Build a minimal self-signed cert with SAN email and issuer OID
        key = ec.generate_private_key(ec.SECP256R1())
        issuer_oid = ObjectIdentifier("1.3.6.1.4.1.57264.1.1")
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")]))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC))
            .not_valid_after(datetime.now(UTC) + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.RFC822Name("test@example.com")]),
                critical=False,
            )
            .add_extension(
                x509.UnrecognizedExtension(issuer_oid, b"https://accounts.google.com"),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        cert_b64 = base64.b64encode(
            cert.public_bytes(serialization.Encoding.DER)
        ).decode()

        bundle = {
            "verificationMaterial": {"certificate": {"rawBytes": cert_b64}},
        }

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.sigstore").write_text(json.dumps(bundle))

        result = get_bundle_signer(skill_dir)
        assert result is not None
        assert result.identity == "test@example.com"
        assert result.issuer == "https://accounts.google.com"

    def test_returns_none_on_malformed_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.sigstore").write_text("not json")
        assert get_bundle_signer(skill_dir) is None

    def test_raises_without_cryptography(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import builtins

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("cryptography"):
                raise ImportError("No module named 'cryptography'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="haiku.skills\\[signing\\]"):
            get_bundle_signer(skill_dir)


class TestVerifySkill:
    def test_returns_false_without_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        assert verify_skill(skill_dir, identities) is False

    def test_returns_false_without_bundle_unsafe(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        assert verify_skill(skill_dir, unsafe=True) is False

    def test_raises_without_identities_or_unsafe(self, tmp_path: Path):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")

        with pytest.raises(ValueError, match="trusted_identities.*unsafe"):
            verify_skill(skill_dir)

    def test_verifies_integrity_only_with_unsafe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        mock_bundle = MagicMock()
        mock_verifier = MagicMock()
        mock_verifier.verify_artifact.return_value = None

        mock_sigstore = MagicMock()
        mock_sigstore.Bundle.from_json.return_value = mock_bundle
        mock_sigstore.Verifier.production.return_value = mock_verifier
        mock_sigstore.UnsafeNoOp = MagicMock()
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        assert verify_skill(skill_dir, unsafe=True) is True
        mock_sigstore.UnsafeNoOp.assert_called_once()
        mock_verifier.verify_artifact.assert_called_once()

    def test_raises_without_sigstore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore",
            MagicMock(
                side_effect=ImportError(
                    "sigstore is required for signing and verification. "
                    "Install with: pip install haiku.skills[signing]"
                )
            ),
        )
        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        with pytest.raises(ImportError, match="haiku.skills\\[signing\\]"):
            verify_skill(skill_dir, identities)

    def test_verifies_valid_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        mock_bundle = MagicMock()
        mock_verifier = MagicMock()
        mock_verifier.verify_artifact.return_value = None  # success = no exception

        mock_sigstore = MagicMock()
        mock_sigstore.Bundle.from_json.return_value = mock_bundle
        mock_sigstore.Verifier.production.return_value = mock_verifier
        mock_sigstore.Identity = MagicMock()
        mock_sigstore.AnyOf = MagicMock()
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        assert verify_skill(skill_dir, identities) is True

        mock_verifier.verify_artifact.assert_called_once()

    def test_returns_false_on_verification_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from sigstore.errors import VerificationError

        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        mock_verifier = MagicMock()
        mock_verifier.verify_artifact.side_effect = VerificationError(
            "verification failed"
        )

        mock_sigstore = MagicMock()
        mock_sigstore.Bundle.from_json.return_value = MagicMock()
        mock_sigstore.Verifier.production.return_value = mock_verifier
        mock_sigstore.VerificationError = VerificationError
        mock_sigstore.Identity = MagicMock()
        mock_sigstore.AnyOf = MagicMock()
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        assert verify_skill(skill_dir, identities) is False

    def test_tries_all_identities(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("content")
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        mock_verifier = MagicMock()
        mock_sigstore = MagicMock()
        mock_sigstore.Bundle.from_json.return_value = MagicMock()
        mock_sigstore.Verifier.production.return_value = mock_verifier
        mock_sigstore.Identity = MagicMock()
        mock_sigstore.AnyOf = MagicMock()
        mock_sigstore.Hashed = MagicMock()

        monkeypatch.setattr(
            "haiku.skills.signing._import_sigstore", lambda: mock_sigstore
        )

        identities = [
            TrustedIdentity(identity="a@b.com", issuer="https://issuer-a"),
            TrustedIdentity(identity="c@d.com", issuer="https://issuer-b"),
        ]
        verify_skill(skill_dir, identities)

        # AnyOf should be called with both Identity instances
        mock_sigstore.AnyOf.assert_called_once()
        mock_sigstore.Identity.assert_any_call(
            identity="a@b.com", issuer="https://issuer-a"
        )
        mock_sigstore.Identity.assert_any_call(
            identity="c@d.com", issuer="https://issuer-b"
        )
