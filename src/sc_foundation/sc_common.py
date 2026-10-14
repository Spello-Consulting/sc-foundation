"""Common functions and classes used by other classes in the sc_foundation package."""

import datetime as dt
import ipaddress
import os
import platform
import re
import subprocess  # noqa: S404
import tomllib
from pathlib import Path

import httpx
import requests
import validators
from tzfpy import get_tz

HTTP_TIMEOUT = 10
GIT_TIMEOUT = 10
UA = {"User-Agent": "failover-monitor/1.0"}
# Multiple IP-echo services, tried in order — protects against any one being down.
IP_ECHO_URLS = [
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
]


class SCCommon:
    """Common functions and classes used by other classes in the sc_foundation package."""

    @staticmethod
    def is_valid_hostname(target: str) -> bool:
        """Return whether target is a valid IPv4, IPv6, or DNS hostname.

        Args:
            target: The target string to validate.

        Returns:
            A boolean indicating validity.
        """
        result, _ = SCCommon.check_hostname_and_type(target)
        return result

    @staticmethod
    def check_hostname_and_type(target: str) -> tuple[bool, str | None]:
        """Return whether target is a valid IPv4, IPv6, or DNS hostname. Also returns the type.

        Args:
            target: The target string to validate.

        Returns:
            A tuple containing a boolean indicating validity and a string indicating the type ('ipv4', 'ipv6', or 'hostname').
        """
        # Make sure the target is a string
        if not isinstance(target, str):
            return False, None

        # Check strict IPv4
        try:
            ipaddress.IPv4Address(target)
        except ValueError:
            pass
        else:
            if target.count(".") == 3:
                return True, "ipv4"

        # Check strict IPv6
        try:
            ipaddress.IPv6Address(target)
        except ValueError:
            pass
        else:
            # If it is a valid IPv6 address, return True
            return True, "ipv6"

        # Reject if it looks like a malformed IP (like 192.168.1 or 256.1.1.1)
        if re.fullmatch(r"[0-9.]+", target):
            return False, None

        # Validate hostname using validators library
        if validators.domain(target) or validators.hostname(target, rfc_1034=True):
            return True, "hostname"

        return False, None

    @staticmethod
    def ping_host(ip_address: str, timeout: int = 1) -> bool:
        """Pings an IP address and returns True if the host is responding, False otherwise.

        Args:
            ip_address: The IP address to ping.
            timeout: Timeout in seconds for the ping response. Default is 1 second.

        Raises:
            RuntimeError: If the IP address is invalid or the ping system call fails.

        Returns:
            result (bool): True if the host responds, False otherwise.
        """
        # Determine the ping command based on the operating system
        param = "-n" if platform.system().lower() == "windows" else "-c"

        if not SCCommon.is_valid_hostname(ip_address):
            error_msg = f"Invalid IP address: {ip_address}"
            raise RuntimeError(error_msg)

        command = ["ping", param, "1", "-W", str(timeout), ip_address]

        try:
            # Run the ping command using subprocess for better security
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False, check=False)  # noqa: S603
            response_code = result.returncode
        except OSError as e:
            error_msg = f"Error pinging {ip_address}: {e}"
            raise RuntimeError(error_msg) from e
        else:
            # Return True if the ping was successful (exit code 0)
            return response_code == 0

    @staticmethod
    def check_internet_connection(urls=None, timeout: int = 3) -> bool:
        """Check if the system has an active internet connection by trying to open a connection to common websites.

        Args:
            urls (list): A list of URLs to check for internet connectivity. Defaults to common DNS servers and websites.
            timeout (int): The timeout in seconds for each request.

        Returns:
            True if the system is connected to the internet, False otherwise.
        """
        if urls is None:
            urls = [
                "https://1.1.1.1",         # Cloudflare DNS
                "https://8.8.8.8",         # Google DNS
                "https://www.google.com",
                "https://www.cloudflare.com"
            ]

        for url in urls:
            try:
                response = httpx.get(url, timeout=timeout, follow_redirects=True)
                if response.status_code < 400:
                    return True
            except httpx.RequestError:
                continue
        return False

    @staticmethod
    def get_os() -> str:
        """Return the name of the operating system.

        Returns:
            The name of the operating system in lowercase.
        """
        # Get the platform name and convert it to lowercase
        platform_name = platform.system().lower()

        if platform_name == "darwin":
            platform_name = "macos"

        return platform_name

    @staticmethod
    def is_probable_path(possible_path: str | Path) -> bool:
        """Check if the given string or Path object is likely to be a file path.

        This method checks if the string is an absolute path, contains a path separator, or has a file extension.

        Args:
            possible_path: The string to check.

        Returns:
            True if the string is likely a file path, False otherwise.
        """
        max_path = 260 if SCCommon.get_os() == "windows" else os.pathconf("/", "PC_PATH_MAX")

        path_obj = None
        if isinstance(possible_path, Path):
            path_str = str(possible_path)
            path_obj = possible_path
        else:
            path_str = possible_path

        if len(path_str) > max_path:
            # If the path is longer than the maximum allowed path length, it cannot be a valid path
            return False

        if path_obj is None:
            path_obj = Path(possible_path)

        # Check if it's absolute, or contains a path separator, or has a file extension
        if path_obj.is_absolute():
            return True

        if "/" in path_str or "\\" in path_str:
            return True

        # Check if the path has a file extension
        return bool(path_obj.suffix and path_obj.suffix.lower() is not None)

    @staticmethod
    def get_project_root(marker_files=("pyproject.toml", ".project_root", "uv.lock", ".git")) -> Path:
        """Return the root folder of the Python project.

        By default, this function looks for marker files like pyproject.toml, .project_root, uv.lock, or .git to
        identify the project root. It starts from the directory of this file and walks upwards until it finds one
        of the marker files. If it cannot find any of the marker files, it raises a RuntimeError.

        If the environment variable SC_FOUNDATION_PROJECT_ROOT is set, it will check if that path exists and is a directory,
        and return it as the project root if so. This allows users to override the automatic detection of the project
        root if needed (e.g., if they have an unusual project structure or want to use the foundation in a different project
        without copying this file).

        Args:
            marker_files (tuple): A tuple of file names that indicate the project root.

        Raises:
            RuntimeError: If the project root cannot be found.

        Returns:
            root_dir (Path): The root folder of the Python project as a Path object.
        """
        path = None
        env_path = os.environ.get("SC_FOUNDATION_PROJECT_ROOT")        # Issue 32
        if env_path:
            path = Path(env_path).resolve()
        if path and path.exists() and path.is_dir():
            return path

        # Default behaviour is to look for the project root based on the location of this file and the presence of marker files. This allows the foundation to be used in other projects without requiring users
        path = Path(__file__).resolve()

        # Walk upwards until we find a marker file
        for parent in [path, *list(path.parents)]:
            for marker in marker_files:
                if (parent / marker).exists():
                    return parent

        error_msg = f"Project root not found. Looked for markers: {marker_files}"
        if env_path:
            error_msg += f" (also checked SC_FOUNDATION_PROJECT_ROOT={env_path})"
        raise RuntimeError(error_msg)

    @staticmethod
    def select_file_location(file_name: str, create_folder: bool = False) -> Path | None:
        """Select the file location for the given file name. It resolves an absolute path for the file_name as follows.

        1. If file_name is an absolute path, return it as a Path object.
        2. If file_name is a relative path (contains parent directories), return the absolute path based on the current working directory.
        3. If file_name is just a file name, look for it in the current working directory first, then in the root directory.

        The root directly is defined as the directory containing the main script being executed (the module containing __main__).

        Raises:
            RuntimeError: If the project root cannot be determined.

        Args:
            file_name: The name of the file to locate. Can be just a file name, or a relative or absolute path.
            create_folder: If True, create the parent folder if it does not exist. Default is False.

        Returns:
            file_path (Path): The full path to the file as a Path object. None if the file_name does not appear to be a path.
        """
        return_file_path = None

        # Look at the file_name and see if it looks like a path
        if not SCCommon.is_probable_path(file_name):
            return None

        # Check to see if file_name is a full path or just a file name
        return_file_path = Path(file_name)

        # Check if file_name is an absolute path, return this even if it does not exist
        if return_file_path.is_absolute():
            SCCommon._create_folder_if_not_exists(return_file_path.parent) if create_folder else None
            return return_file_path

        # Check if file_name contains any parent directories (i.e., is a relative path)
        # If so, return this even if it does not exist
        if return_file_path.parent != Path("."):  # noqa: PTH201
            # It's a relative path
            return_file_path = (Path.cwd() / return_file_path).resolve()
            SCCommon._create_folder_if_not_exists(return_file_path.parent) if create_folder else None
            return return_file_path

        # Otherwise, assume it's just a file name and look for it in the current directory and the script directory
        current_dir = Path.cwd()
        return_file_path = current_dir / file_name
        if not return_file_path.exists():
            try:
                project_root_dir = SCCommon.get_project_root()
                return_file_path = project_root_dir / file_name
            except RuntimeError as e:
                error_msg = f"Cannot determine project root to locate file '{file_name}': {e}"
                raise RuntimeError(error_msg) from e

        if return_file_path:
            SCCommon._create_folder_if_not_exists(return_file_path.parent) if create_folder else None

        return return_file_path

    @staticmethod
    def select_folder_location(folder_path: str | None = None, create_folder: bool = False) -> Path | None:
        """Return an absolute folder path for the given (relative) folder path.

        If folder_path is None, return the project root folder.
        If folder_path is an absolute path, return it as a Path object.
        If folder_path is a relative path, return the absolute path based on the project root directory.

        Args:
            folder_path: The folder path to locate. Can be None, or a relative or absolute path.
            create_folder: If True, create the folder if it does not exist. Default is False.

        Raises:
            RuntimeError: If the project root cannot be determined or if folder creation fails.

        Returns:
            The full path to the folder as a Path object. None if folder_path is None and project root cannot be determined.
        """
        try:
            project_root = SCCommon.get_project_root()
        except RuntimeError as e:
            raise RuntimeError(e) from e

        if folder_path is None:
            return project_root

        selected_folder = Path(folder_path)

        # Check if folder_path is an absolute path, return this even if it does not exist
        if not selected_folder.is_absolute():
            selected_folder = (project_root / selected_folder).resolve()

        if create_folder:
            SCCommon._create_folder_if_not_exists(selected_folder)

        return selected_folder

    @staticmethod
    def get_process_id() -> int:
        """Return the process ID of the current process.

        Returns:
            The process ID of the current process.
        """
        return os.getpid()

    @staticmethod
    def get_external_ip() -> str:
        """
        Query multiple external IP-echo services in turn to get the public IP address of the machine.

        Returns:
            The external IP address as a string.

        Raises:
            RuntimeError: If all IP-echo services fail.
        """
        last_err = None
        for url in IP_ECHO_URLS:
            try:
                r = requests.get(url, headers=UA, timeout=HTTP_TIMEOUT)
                r.raise_for_status()
                ip = r.text.strip()
                if ip:
                    return ip
            except requests.RequestException as e:
                last_err = e
                continue
        error_msg = f"All IP-echo services failed. Last error: {last_err}"
        raise RuntimeError(error_msg)

    @staticmethod
    def _create_folder_if_not_exists(folder_path: Path) -> None:
        """Create the folder if it does not exist.

        Args:
            folder_path: The path of the folder to create.

        Raises:
            RuntimeError: If folder creation fails.
        """
        if not folder_path.exists():
            try:
                folder_path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                error_msg = f"Error creating folder '{folder_path}': {e}"
                raise RuntimeError(error_msg) from e

    @staticmethod
    def get_geo_location(location_config: dict | None = None, google_maps_url: str | None = None) -> dict:
        """Get the geographical location based on the provided configuration.

        Args:
            location_config: A dictionary containing location configuration. If None, defaults to an empty dictionary.
            google_maps_url: A Google Maps URL to extract the location from. If None, defaults to None.

        location_config is the YAML Location configuration dictionary. It can conatin the following keys (examples shown):
            - Latitude: 51.4993124
            - Longitude: -0.1353157
            - GoogleMapsURL: https://www.google.com/maps/place/Buckingham+Palace/@51.4993124,-0.1353157,14.92z

        The returned dictionary will contain the following keys:
            - method: The method used to determine the location (e.g., "config", "google_maps_url").
            - latitude: The latitude of the location.
            - longitude: The longitude of the location.
            - timezone: The timezone of the location (if available).
            - city, state and country if available from a lookup on openstreetmap.org.

        If location_config contains a lat/long pair, this will be used directly. If it contains a Google Maps URL,
        the lat/long will be extracted from the URL. If neither is provided, the function will attempt to determine
        the location using other means (e.g., IP-based geolocation).

        Returns:
            A dictionary containing the geographical location information.
        """
        if location_config is None:
            location_config = {}

        tz = lat = lon = method = None

        if location_config.get("Latitude") is not None and location_config.get("Longitude") is not None:
            lat = location_config["Latitude"]
            lon = location_config["Longitude"]
            tz = location_config.get("Timezone")
            method = "config: lat-long"

        elif location_config.get("GoogleMapsURL") is not None or google_maps_url is not None:
            url = location_config.get("GoogleMapsURL") or google_maps_url
            match = re.search(r"@?([-]?\d+\.\d+),([-]?\d+\.\d+)", url)  # pyright: ignore[reportArgumentType, reportCallIssue]
            if match:
                lat = float(match.group(1))
                lon = float(match.group(2))
                method = "config: google url"

        # Default to IP-based geolocation if no lat/long or Google Maps URL is provided. This will require an external service or library to determine the location based on the public IP address.
        if lat is None or lon is None:
            try:
                external_ip = SCCommon.get_external_ip()

                r = requests.get(f"https://ipinfo.io/{external_ip}/json", timeout=HTTP_TIMEOUT).json()  # omit IP to get your own
            except Exception:  # noqa: BLE001
                external_ip = None
            else:
                method = "ip-based geolocation"
                lat, lon = map(float, r["loc"].split(","))

        # Last resort: if we still don't have lat/lon, default to 0,0 and UTC timezone
        if lat is None or lon is None:
            tz = tz or "UTC"
            lat = 0.0
            lon = 0.0
            method = "default"

        # If we have lat/long but not tz, get the timezone using tzfpy. If tzfpy fails, default to the system timezone.
        if tz is None:
            tz_name = get_tz(lon, lat)
            tz = tz_name or str(dt.datetime.now().astimezone().tzinfo)

        return_dict = {
            "method": method,
            "latitude": lat,
            "longitude": lon,
            "timezone": tz,
        }

        # Lookup city, etc. using lat/lon if we have them and the method is not already "config: lat-long" or "config: google url"
        if lat is not None and lon is not None:
            try:
                r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers=UA, timeout=HTTP_TIMEOUT).json()
                if "address" in r:
                    address = r["address"]
                    return_dict["city"] = address.get("city") or address.get("town") or address.get("village") or address.get("hamlet")
                    return_dict["state"] = address.get("state")
                    return_dict["country"] = address.get("country")
            except Exception:  # noqa: BLE001, S110
                pass

        return return_dict

    @staticmethod
    def _run_git(project_root: Path, *args: str) -> str | None:
        """Run a git command in project_root.

        Args:
            project_root: The directory to run git in.
            *args: The git sub-command and its arguments.

        Returns:
            The stripped stdout, or None if git is unavailable or the command failed.
        """
        try:
            result = subprocess.run(  # noqa: S603
                ["git", *args],  # noqa: S607
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=GIT_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    @staticmethod
    def get_deployment_info() -> dict:
        """Return project and git deployment information for the project.

        The project root is located using get_project_root(). Project details are read from pyproject.toml in
        that folder. Git details are read from the git repository in that folder. Git status is based on the last
        fetch; no network access is performed.

        Returns:
            A dictionary with the following keys:
                - name, version, description: From the [project] table of pyproject.toml. None if unavailable.
                - git_branch: The current branch name (None if detached or not a git repo).
                - git_tag: The latest tag reachable from HEAD (None if there are no tags).
                - git_remote: The URL of the upstream remote (or origin if no upstream is set).
                - git_status: "Ahead", "Behind", "Up to date", "Diverged" or "Unknown" if it cannot be determined.
                - git_changes: Count of changed files, staged and unstaged (None if not a git repo).
        """
        project_root = SCCommon.get_project_root()

        info: dict = {
            "name": None,
            "version": None,
            "description": None,
            "git_branch": None,
            "git_tag": None,
            "git_remote": None,
            "git_status": "Unknown",
            "git_changes": None,
        }

        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.is_file():
            try:
                with pyproject_path.open("rb") as f:
                    project = tomllib.load(f).get("project", {})
            except (OSError, tomllib.TOMLDecodeError):
                project = {}
            for key in ("name", "version", "description"):
                info[key] = project.get(key)

        # Not a git repo (or git not installed)
        if SCCommon._run_git(project_root, "rev-parse", "--git-dir") is None:
            return info

        info["git_branch"] = SCCommon._run_git(project_root, "branch", "--show-current") or None
        info["git_tag"] = SCCommon._run_git(project_root, "describe", "--tags", "--abbrev=0")

        upstream = SCCommon._run_git(project_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        remote_name = upstream.split("/", 1)[0] if upstream else "origin"
        info["git_remote"] = SCCommon._run_git(project_root, "remote", "get-url", remote_name)

        if upstream:
            counts = SCCommon._run_git(project_root, "rev-list", "--left-right", "--count", "@{u}...HEAD")
            if counts:
                behind, ahead = (int(n) for n in counts.split())
                if ahead and behind:
                    info["git_status"] = "Diverged"
                elif ahead:
                    info["git_status"] = "Ahead"
                elif behind:
                    info["git_status"] = "Behind"
                else:
                    info["git_status"] = "Up to date"

        porcelain = SCCommon._run_git(project_root, "status", "--porcelain")
        if porcelain is not None:
            info["git_changes"] = len(porcelain.splitlines())

        return info
