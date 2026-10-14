"""Unit tests for the sc_common module."""

import os
import subprocess  # noqa: S404
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sc_foundation.sc_common import SCCommon


def test_is_valid_hostname_valid_ipv4():
    """Test is_valid_hostname with valid IPv4 addresses."""
    assert SCCommon.is_valid_hostname("192.168.1.1") is True
    assert SCCommon.is_valid_hostname("10.0.0.1") is True
    assert SCCommon.is_valid_hostname("127.0.0.1") is True
    assert SCCommon.is_valid_hostname("255.255.255.255") is True


def test_is_valid_hostname_invalid_ipv4():
    """Test is_valid_hostname with invalid IPv4 addresses."""
    assert SCCommon.is_valid_hostname("256.1.1.1") is False
    assert SCCommon.is_valid_hostname("192.168.1") is False
    assert SCCommon.is_valid_hostname("192.168.1.1.1") is False
    assert SCCommon.is_valid_hostname("192.168.1.a") is False


def test_is_valid_hostname_valid_ipv6():
    """Test is_valid_hostname with valid IPv6 addresses."""
    assert SCCommon.is_valid_hostname("::1") is True
    assert SCCommon.is_valid_hostname("2001:db8::1") is True
    assert SCCommon.is_valid_hostname("fe80::1") is True


def test_is_valid_hostname_valid_dns():
    """Test is_valid_hostname with valid DNS hostnames."""
    assert SCCommon.is_valid_hostname("example.com") is True
    assert SCCommon.is_valid_hostname("subdomain.example.com") is True
    assert SCCommon.is_valid_hostname("test-host.example.org") is True
    assert SCCommon.is_valid_hostname("localhost") is True
    assert SCCommon.is_valid_hostname("example.com.") is True  # FQDN


def test_is_valid_hostname_invalid_dns():
    """Test is_valid_hostname with invalid DNS hostnames."""
    assert SCCommon.is_valid_hostname("-example.com") is False
    assert SCCommon.is_valid_hostname("example-.com") is False
    assert SCCommon.is_valid_hostname("example..com") is False
    assert SCCommon.is_valid_hostname("ex@mple.com") is False
    assert SCCommon.is_valid_hostname("a" * 64 + ".com") is False  # Label too long


def test_is_valid_hostname_invalid_input():
    """Test is_valid_hostname with invalid input types."""
    assert SCCommon.is_valid_hostname("") is False
    assert SCCommon.is_valid_hostname(None) is False  # type: ignore[arg-type]
    assert SCCommon.is_valid_hostname(123) is False  # type: ignore[arg-type]
    assert SCCommon.is_valid_hostname([]) is False  # type: ignore[arg-type]


@patch("sc_foundation.sc_common.subprocess.run")
@patch("sc_foundation.sc_common.platform.system")
def test_ping_host_success_linux(mock_platform, mock_run):
    """Test ping_host success on Linux."""
    mock_platform.return_value = "Linux"
    mock_run.return_value = MagicMock(returncode=0)

    result = SCCommon.ping_host("192.168.1.1")

    assert result is True
    mock_run.assert_called_once_with(
        ["ping", "-c", "1", "-W", "1", "192.168.1.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        check=False
    )


@patch("sc_foundation.sc_common.subprocess.run")
@patch("sc_foundation.sc_common.platform.system")
def test_ping_host_success_windows(mock_platform, mock_run):
    """Test ping_host success on Windows."""
    mock_platform.return_value = "Windows"
    mock_run.return_value = MagicMock(returncode=0)

    result = SCCommon.ping_host("192.168.1.1")

    assert result is True
    mock_run.assert_called_once_with(
        ["ping", "-n", "1", "-W", "1", "192.168.1.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        check=False
    )


@patch("sc_foundation.sc_common.subprocess.run")
@patch("sc_foundation.sc_common.platform.system")
def test_ping_host_failure(mock_platform, mock_run):
    """Test ping_host failure."""
    mock_platform.return_value = "Linux"
    mock_run.return_value = MagicMock(returncode=1)

    result = SCCommon.ping_host("192.168.1.1")

    assert result is False


def test_ping_host_invalid_ip():
    """Test ping_host with invalid IP address."""
    with pytest.raises(RuntimeError, match="Invalid IP address"):
        SCCommon.ping_host("192.168.3.4.5")


def test_ping_host_untrusted_input():
    """Test ping_host with untrusted input."""
    with pytest.raises(RuntimeError, match="Invalid IP address"):
        SCCommon.ping_host("192.168.1.1; rm -rf /")


def test_check_internet_connection():
    """Test check_internet_connection."""
    assert SCCommon.check_internet_connection() is True  # This will depend on your actual internet connection


def test_get_project_root():
    """Test get_project_root."""
    root = SCCommon.get_project_root()
    assert root is not None
    assert root.is_dir()
    assert (root / "src").is_dir() or (root / "README.md").is_file()  # Check for common project files

    # Test environment variable override
    special_dir = "/Users/nick/dev/sc-foundation"
    os.environ["SC_FOUNDATION_PROJECT_ROOT"] = special_dir
    root = SCCommon.get_project_root()
    assert root is not None
    assert root.is_dir()
    assert root == Path(special_dir)


def test_is_probable_path_absolute_path():
    """Test is_probable_path with absolute paths."""
    assert SCCommon.is_probable_path("/usr/bin/python") is True
    assert SCCommon.is_probable_path("C:\\Windows\\System32") is True
    assert SCCommon.is_probable_path(Path("/usr/bin/python")) is True


def test_is_probable_path_relative_path():
    """Test is_probable_path with relative paths."""
    assert SCCommon.is_probable_path("./config.yaml") is True
    assert SCCommon.is_probable_path("../data/file.txt") is True
    assert SCCommon.is_probable_path("folder/file.txt") is True


def test_is_probable_path_file_extension():
    """Test is_probable_path with file extensions."""
    assert SCCommon.is_probable_path("config.yaml") is True
    assert SCCommon.is_probable_path("data.json") is True
    assert SCCommon.is_probable_path("script.py") is True


def test_is_probable_path_not_path():
    """Test is_probable_path with non-path strings."""
    assert SCCommon.is_probable_path("justtext") is False
    assert SCCommon.is_probable_path("no-extension") is False


@patch("sc_foundation.sc_common.SCCommon.get_os")
@patch("sc_foundation.sc_common.os.pathconf")
def test_is_probable_path_too_long(mock_pathconf, mock_get_os):
    """Test is_probable_path with path too long."""
    mock_get_os.return_value = "linux"
    mock_pathconf.return_value = 100

    long_path = "a" * 150 + ".txt"
    assert SCCommon.is_probable_path(long_path) is False


@patch("sc_foundation.sc_common.Path.cwd")
def test_select_file_location_absolute_path(mock_cwd):  # noqa: ARG001
    """Test select_file_location with absolute path."""
    result = SCCommon.select_file_location("/etc/config.yaml")
    assert result == Path("/etc/config.yaml")


@patch("sc_foundation.sc_common.Path.cwd")
def test_select_file_location_relative_path(mock_cwd):
    """Test select_file_location with relative path."""
    mock_cwd.return_value = Path("/home/user")

    result = SCCommon.select_file_location("config/settings.yaml")
    assert str(result).find("/home/user/config/settings.yaml")


@patch("sc_foundation.sc_common.os.getpid")
def test_get_process_id(mock_getpid):
    """Test get_process_id."""
    mock_getpid.return_value = 12345
    assert SCCommon.get_process_id() == 12345
    mock_getpid.assert_called_once()


def test_get_process_id_integration():
    """Test get_process_id integration."""
    pid = SCCommon.get_process_id()
    assert isinstance(pid, int)
    assert pid > 0


# test_select_file_location_absolute_path()
# test_select_file_location_relative_path()
# test_get_project_root()


# --- get_geo_location ---

@patch("sc_foundation.sc_common.requests.get")
@patch("sc_foundation.sc_common.get_tz")
def test_get_geo_location_lat_lon_config(mock_get_tz, mock_requests_get):
    """Lat/lon provided directly in config; Nominatim lookup succeeds."""
    mock_get_tz.return_value = "Australia/Sydney"
    nominatim_response = MagicMock()
    nominatim_response.json.return_value = {
        "address": {
            "city": "Sydney",
            "state": "New South Wales",
            "country": "Australia",
        }
    }
    mock_requests_get.return_value = nominatim_response

    result = SCCommon.get_geo_location({
        "Latitude": -33.86,
        "Longitude": 151.21,
        "Timezone": "Australia/Sydney",
    })

    assert result["method"] == "config: lat-long"
    assert result["latitude"] == -33.86
    assert result["longitude"] == 151.21
    assert result["timezone"] == "Australia/Sydney"
    assert result["city"] == "Sydney"
    assert result["state"] == "New South Wales"
    assert result["country"] == "Australia"


@patch("sc_foundation.sc_common.requests.get")
@patch("sc_foundation.sc_common.get_tz")
def test_get_geo_location_google_maps_url(mock_get_tz, mock_requests_get):
    """Lat/lon extracted from a Google Maps URL."""
    mock_get_tz.return_value = "Europe/London"
    nominatim_response = MagicMock()
    nominatim_response.json.return_value = {
        "address": {
            "city": "London",
            "state": "England",
            "country": "United Kingdom",
        }
    }
    mock_requests_get.return_value = nominatim_response

    result = SCCommon.get_geo_location({
        "GoogleMapsURL": "https://www.google.com/maps/place/Buckingham+Palace/@51.4993124,-0.1353157,14.92z"
    })

    assert result["method"] == "config: google url"
    assert result["latitude"] == pytest.approx(51.4993124)
    assert result["longitude"] == pytest.approx(-0.1353157)
    assert result["city"] == "London"


@patch("sc_foundation.sc_common.requests.get")
@patch("sc_foundation.sc_common.get_tz")
def test_get_geo_location_nominatim_failure_is_silent(mock_get_tz, mock_requests_get):
    """Nominatim throwing an exception should not propagate; city/state/country keys absent."""
    mock_get_tz.return_value = "Australia/Sydney"
    mock_requests_get.side_effect = Exception("network error")

    result = SCCommon.get_geo_location({
        "Latitude": -33.86,
        "Longitude": 151.21,
        "Timezone": "Australia/Sydney",
    })

    assert result["method"] == "config: lat-long"
    assert result["latitude"] == -33.86
    assert "city" not in result
    assert "country" not in result


@patch("sc_foundation.sc_common.requests.get")
@patch("sc_foundation.sc_common.SCCommon.get_external_ip")
@patch("sc_foundation.sc_common.get_tz")
def test_get_geo_location_ip_based_fallback(mock_get_tz, mock_get_ip, mock_requests_get):
    """No config provided; falls back to IP-based geolocation."""
    mock_get_tz.return_value = "America/New_York"
    mock_get_ip.return_value = "8.8.8.8"

    ipinfo_response = MagicMock()
    ipinfo_response.json.return_value = {"loc": "40.7128,-74.0060"}

    nominatim_response = MagicMock()
    nominatim_response.json.return_value = {
        "address": {
            "city": "New York City",
            "state": "New York",
            "country": "United States",
        }
    }

    mock_requests_get.side_effect = [ipinfo_response, nominatim_response]

    result = SCCommon.get_geo_location()

    assert result["method"] == "ip-based geolocation"
    assert result["latitude"] == pytest.approx(40.7128)
    assert result["longitude"] == pytest.approx(-74.0060)
    assert result["city"] == "New York City"


@patch("sc_foundation.sc_common.requests.get")
@patch("sc_foundation.sc_common.SCCommon.get_external_ip")
def test_get_geo_location_default_fallback(mock_get_ip, mock_requests_get):
    """All external calls fail; falls back to 0,0 / UTC."""
    mock_get_ip.side_effect = Exception("no network")
    mock_requests_get.side_effect = Exception("no network")

    result = SCCommon.get_geo_location()

    assert result["method"] == "default"
    assert result["latitude"] == 0.0
    assert result["longitude"] == 0.0
    assert result["timezone"] == "UTC"


# --- get_deployment_info ---


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
def git_project(tmp_path, monkeypatch):
    """Create a git project with a bare remote, and point get_project_root at it.

    Returns:
        The project directory.
    """
    remote = tmp_path / "remote.git"
    project = tmp_path / "project"
    project.mkdir()
    _git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    (project / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.2.3"\ndescription = "A demo"\n')
    _git(project, "init", "-b", "main")
    _git(project, "config", "user.email", "test@example.com")
    _git(project, "config", "user.name", "Test")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "init")
    _git(project, "tag", "v1.2.3")
    _git(project, "remote", "add", "origin", str(remote))
    _git(project, "push", "-u", "origin", "main")
    monkeypatch.setenv("SC_FOUNDATION_PROJECT_ROOT", str(project))
    return project


@pytest.mark.usefixtures("git_project")
def test_get_deployment_info_up_to_date():
    """Test get_deployment_info for a clean, synced repo."""
    info = SCCommon.get_deployment_info()
    assert info["name"] == "demo"
    assert info["version"] == "1.2.3"
    assert info["description"] == "A demo"
    assert info["git_branch"] == "main"
    assert info["git_tag"] == "v1.2.3"
    assert info["git_remote"].endswith("remote.git")
    assert info["git_status"] == "Up to date"
    assert info["git_changes"] == 0


def test_get_deployment_info_ahead_and_changes(git_project):
    """Test get_deployment_info with a local commit and uncommitted changes."""
    (git_project / "a.txt").write_text("a")
    _git(git_project, "add", "a.txt")
    _git(git_project, "commit", "-m", "second")
    (git_project / "b.txt").write_text("b")  # untracked
    (git_project / "pyproject.toml").write_text('[project]\nname = "demo2"\n')  # unstaged
    info = SCCommon.get_deployment_info()
    assert info["git_status"] == "Ahead"
    assert info["git_changes"] == 2
    assert info["name"] == "demo2"
    assert info["version"] is None


def test_get_deployment_info_behind(git_project, tmp_path):
    """Test get_deployment_info when the remote has a newer commit."""
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(tmp_path / "remote.git"), str(other))
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "Test")
    (other / "c.txt").write_text("c")
    _git(other, "add", "c.txt")
    _git(other, "commit", "-m", "remote change")
    _git(other, "push")
    _git(git_project, "fetch")
    assert SCCommon.get_deployment_info()["git_status"] == "Behind"


def test_get_deployment_info_not_a_git_repo(tmp_path, monkeypatch):
    """Test get_deployment_info outside a git repository."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "nogit"\nversion = "0.1.0"\n')
    monkeypatch.setenv("SC_FOUNDATION_PROJECT_ROOT", str(tmp_path))
    with patch.object(SCCommon, "_run_git", return_value=None):
        info = SCCommon.get_deployment_info()
    assert info["name"] == "nogit"
    assert info["version"] == "0.1.0"
    assert info["git_branch"] is None
    assert info["git_status"] == "Unknown"
    assert info["git_changes"] is None
