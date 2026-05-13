import stat

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from mcp_proxy.oauth import FileTokenStorage


async def test_get_tokens_no_file(tmp_path):
    storage = FileTokenStorage(tmp_path / "nonexistent.json")
    assert await storage.get_tokens() is None


async def test_set_and_get_tokens(tmp_path):
    storage = FileTokenStorage(tmp_path / "tokens.json")
    token = OAuthToken(access_token="test-access", token_type="bearer")
    await storage.set_tokens(token)
    result = await storage.get_tokens()
    assert result is not None
    assert result.access_token == "test-access"
    assert result.token_type.lower() == "bearer"


async def test_get_client_info_no_file(tmp_path):
    storage = FileTokenStorage(tmp_path / "nonexistent.json")
    assert await storage.get_client_info() is None


async def test_set_and_get_client_info(tmp_path):
    storage = FileTokenStorage(tmp_path / "client.json")
    info = OAuthClientInformationFull(
        client_id="test-id",
        client_secret="test-secret",
        redirect_uris=["http://localhost/callback"],
    )
    await storage.set_client_info(info)
    result = await storage.get_client_info()
    assert result is not None
    assert result.client_id == "test-id"


async def test_tokens_and_client_info_coexist(tmp_path):
    storage = FileTokenStorage(tmp_path / "both.json")
    token = OAuthToken(access_token="tok", token_type="bearer")
    info = OAuthClientInformationFull(
        client_id="cid",
        redirect_uris=["http://localhost/callback"],
    )
    await storage.set_tokens(token)
    await storage.set_client_info(info)
    assert (await storage.get_tokens()).access_token == "tok"
    assert (await storage.get_client_info()).client_id == "cid"


async def test_set_tokens_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nested" / "tokens.json"
    storage = FileTokenStorage(path)
    await storage.set_tokens(OAuthToken(access_token="x", token_type="bearer"))
    assert path.exists()


async def test_file_permissions(tmp_path):
    path = tmp_path / "perms.json"
    storage = FileTokenStorage(path)
    await storage.set_tokens(OAuthToken(access_token="x", token_type="bearer"))
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600
