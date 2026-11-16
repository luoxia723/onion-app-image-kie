"""The public check command must select the promised lanes and stay offline."""
import importlib.util
from pathlib import Path
import shutil
import socket
import sys
import urllib.request

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('suite,expected',[
    ('core',{'test_current'}),('history',{'test_frozen'}),
    ('transport',{'test_transport'}),('all',{'test_current','test_frozen','test_transport'}),
])
def test_check_command_selects_actual_pytest_lanes(tmp_path,monkeypatch,capfd,suite,expected):
    for name in ('pytest.ini','conftest.py'):shutil.copyfile(ROOT/name,tmp_path/name)
    tests=tmp_path/'tests';tests.mkdir()
    (tests/'test_cases.py').write_text('import pytest\ndef test_current(): pass\n@pytest.mark.history\ndef test_frozen(): pass\n@pytest.mark.transport\ndef test_transport(): pass\n')
    spec=importlib.util.spec_from_file_location('check_command',ROOT/'scripts/check_workbench.py')
    command=importlib.util.module_from_spec(spec);spec.loader.exec_module(command)
    monkeypatch.setattr(command,'ROOT',tmp_path)
    monkeypatch.setattr(sys,'argv',['check_workbench','--suite',suite,'--collect'])
    assert command.main()==0
    lines=capfd.readouterr().out.splitlines()
    selected={line.rsplit('::',1)[-1] for line in lines if line.startswith('tests/test_cases.py::')}
    assert selected==expected


def test_outbound_calls_are_blocked_before_dns_or_socket_io():
    with pytest.raises(pytest.fail.Exception,match='loopback'):
        urllib.request.urlopen('https://example.invalid/not-a-real-endpoint')
    with pytest.raises(pytest.fail.Exception,match='external'):
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open('https://example.invalid/not-a-real-endpoint')
    with pytest.raises(pytest.fail.Exception,match='external'):
        socket.create_connection(('192.0.2.1',443))
    with socket.socket() as connection:
        with pytest.raises(pytest.fail.Exception,match='external'):
            connection.connect(('192.0.2.1',443))
        with pytest.raises(pytest.fail.Exception,match='external'):
            connection.connect_ex(('192.0.2.1',443))
