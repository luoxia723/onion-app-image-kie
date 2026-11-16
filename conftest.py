"""Test lanes follow the active entry points, not the age of a test file."""
import socket
import ipaddress
import urllib.parse
import urllib.request
import pytest

@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    for item in items:
        lanes=[name for name in ('core','history','transport') if item.get_closest_marker(name)]
        if len(lanes)>1:raise pytest.UsageError(f'{item.nodeid}: choose one primary test lane, got {lanes}')
        if not lanes:item.add_marker(pytest.mark.core)


def _loopback(host):
    if host=='localhost':return True
    try:return ipaddress.ip_address(host).is_loopback
    except (ValueError,TypeError):return False


@pytest.fixture(autouse=True)
def prevent_external_test_network(monkeypatch):
    """Both test trees may use loopback servers; neither may reach a provider."""
    original_open=urllib.request.urlopen
    original_connection=socket.create_connection
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_resolve=socket.getaddrinfo
    def local_open(request,*args,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else str(request)
        if not _loopback(urllib.parse.urlsplit(url).hostname):pytest.fail('Automatic tests may only use loopback HTTP endpoints')
        return original_open(request,*args,**kwargs)
    def local_connection(address,*args,**kwargs):
        if not _loopback(address[0]):pytest.fail('Automatic tests may not connect to external providers')
        return original_connection(address,*args,**kwargs)
    def local_connect(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6) and not _loopback(address[0]):
            pytest.fail('Automatic tests may not connect to external providers')
        return original_connect(sock,address)
    def local_connect_ex(sock,address):
        if sock.family in (socket.AF_INET,socket.AF_INET6) and not _loopback(address[0]):
            pytest.fail('Automatic tests may not connect to external providers')
        return original_connect_ex(sock,address)
    def local_resolve(host,*args,**kwargs):
        if host is not None and not _loopback(host):pytest.fail('Automatic tests may not resolve external provider hosts')
        return original_resolve(host,*args,**kwargs)
    monkeypatch.setattr(urllib.request,'urlopen',local_open)
    monkeypatch.setattr(socket,'create_connection',local_connection)
    monkeypatch.setattr(socket.socket,'connect',local_connect)
    monkeypatch.setattr(socket.socket,'connect_ex',local_connect_ex)
    monkeypatch.setattr(socket,'getaddrinfo',local_resolve)
    import os
    for key in ('KIE_API_KEY','KIE_BASE_URL','KIE_UPLOAD_BASE_URL','ONION_PLANNING_API_KEY',
                'ONION_PLANNING_BASE_URL','ONION_PLANNING_MODEL','ONION_IMAGE_MODEL','ONION_IMAGE_WORKSPACE','ONION_REAL_MODE'):
        monkeypatch.delenv(key,raising=False)
    bypass=os.environ.get('NO_PROXY',os.environ.get('no_proxy',''))
    bypass=','.join(filter(None,[bypass,'127.0.0.1','localhost','::1']))
    monkeypatch.setenv('NO_PROXY',bypass);monkeypatch.setenv('no_proxy',bypass)
