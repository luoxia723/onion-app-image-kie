"""Test lanes follow the active entry points, not the age of a test file."""
import socket
import urllib.parse
import urllib.request
from pathlib import Path
import pytest

HISTORY_CASES={
    'test_both_new_and_frozen_asset_rules_are_accepted',
    'test_format_is_fingerprinted_without_changing_historical_config',
    'test_missing_new_story_fails_without_changing_frozen_legacy_configs',
    'test_contract_version_is_optional_for_frozen_prompts_and_part_of_new_fingerprints',
    'test_source_logo_background_rule_remains_resumable_for_the_previous_version',
}


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.core)
        name=item.originalname or item.name.split('[')[0]
        if name in HISTORY_CASES or Path(item.path).name=='test_frozen_prompt_formats.py':item.add_marker(pytest.mark.history)
        if Path(item.path).name=='test_kie_transport.py':item.add_marker(pytest.mark.transport)


@pytest.fixture(autouse=True)
def prevent_external_test_network(monkeypatch):
    """Both test trees may use loopback servers; neither may reach a provider."""
    allowed={'127.0.0.1','localhost','::1'}
    original_open=urllib.request.urlopen
    original_connection=socket.create_connection
    def local_open(request,*args,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else str(request)
        if urllib.parse.urlsplit(url).hostname not in allowed:pytest.fail('Automatic tests may only use loopback HTTP endpoints')
        return original_open(request,*args,**kwargs)
    def local_connection(address,*args,**kwargs):
        if address[0] not in allowed:pytest.fail('Automatic tests may not connect to external providers')
        return original_connection(address,*args,**kwargs)
    monkeypatch.setattr(urllib.request,'urlopen',local_open)
    monkeypatch.setattr(socket,'create_connection',local_connection)
    import os
    bypass=os.environ.get('NO_PROXY',os.environ.get('no_proxy',''))
    bypass=','.join(filter(None,[bypass,'127.0.0.1','localhost','::1']))
    monkeypatch.setenv('NO_PROXY',bypass);monkeypatch.setenv('no_proxy',bypass)
