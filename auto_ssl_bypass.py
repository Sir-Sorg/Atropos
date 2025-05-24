import lzma
import os
import subprocess
import sys
import time
import art
import frida
import requests
from termcolor import colored


def get_device_arch() -> str:
    """Get the Android device architecture."""
    try:
        result = subprocess.run(
            ["adb", "shell", "getprop", "ro.product.cpu.abi"],
            capture_output=True,
            text=True,
        )
        arch = result.stdout.strip()

        # Map Android architectures to Frida naming
        arch_map = {
            "arm64-v8a": "android-arm64",
            "armeabi-v7a": "android-arm",
            "x86": "android-x86",
            "x86_64": "android-x86_64",
        }
        print(
            colored(f"[✔] Device architecture: {arch}", "light_green", attrs=["bold"])
        )
        return arch_map.get(arch, arch)
    except subprocess.CalledProcessError:
        print(
            colored(
                "[-] Error: Unable to get device architecture. Is ADB connected?",
                "light_red",
                attrs=["bold"],
            )
        )
        sys.exit(1)


def check_adb_availability() -> bool:
    """Checks if the Android Debug Bridge (ADB) is available on the system."""
    try:
        subprocess.run(["adb", "version"], capture_output=True, text=True)
        return True
    except FileNotFoundError:
        print(
            colored(
                "[-] ADB not found. Please install ADB and add it to your PATH.",
                "light_red",
                attrs=["bold"],
            )
        )
        sys.exit(1)


def check_device_connection() -> None:
    """Check if an Android device is connected."""
    result = subprocess.run(["adb", "get-state"], capture_output=True, text=True)
    if "device" not in result.stdout:
        print(
            colored(
                "[-] Error: No device connected. Please connect an Android device.",
                "light_red",
                attrs=["bold"],
            )
        )
        sys.exit(1)
    print(
        colored(
            f"[✔] Device {_get_prop('ro.product.manufacturer').title()} {_get_prop('ro.product.device').title()} with Android {_get_prop('ro.build.version.release')} detected and connected",
            "light_green",
            attrs=["bold"],
        )
    )


def launch_scrcpy() -> None:
    """Launch scrcpy to mirror the Android device screen silently."""
    try:
        subprocess.Popen(
            ["scrcpy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        print(
            colored(
                "[✔] Launched mirror device screen",
                "light_green",
                attrs=["bold"],
            )
        )
    except FileNotFoundError:
        print(
            colored(
                "[-] scrcpy not found. Make sure it's installed and in your PATH.",
                "light_red",
                attrs=["bold"],
            )
        )
    except Exception as e:
        print(colored(f"[-] Failed to launch scrcpy: {e}", "light_red", attrs=["bold"]))


def check_existing_frida_server() -> bool:
    """Check if frida-server already exists on device."""
    try:
        result = subprocess.run(
            ["adb", "shell", "ls", "/data/local/tmp/frida-server"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(
                colored(
                    "[*] Frida server already exists on device, starting server...",
                    "light_grey",
                    attrs=["bold"],
                )
            )
        return result.returncode == 0
    except Exception:
        return False


def start_frida(filename=None) -> None:
    """Start Frida server on device. If filename is provided, push it first."""
    try:
        # Kill any existing Frida server process
        print(
            colored(
                "[*] Attempting to kill existing Frida server...",
                "light_grey",
                attrs=["bold"],
            )
        )
        subprocess.run(
            ["adb", "shell", 'su -c "pkill -9 frida-server"'],
            capture_output=True,
            shell=True,
        )
        time.sleep(1)

        # Push file if provided
        if filename:
            print(
                colored(
                    "[*] Pushing Frida server to device...",
                    "light_grey",
                    attrs=["bold"],
                )
            )
            result = subprocess.run(
                ["adb", "push", filename, "/data/local/tmp/frida-server"],
                capture_output=True,
                text=True,
            )
            if result.stderr and "pushed" in result.stderr:
                print(
                    colored(
                        f"[+] {result.stderr.strip()}", "light_green", attrs=["bold"]
                    )
                )

        print(colored("[*] Setting permissions...", "light_grey", attrs=["bold"]))
        subprocess.run(
            ["adb", "shell", 'su -c "chmod 755 /data/local/tmp/frida-server"'],
            capture_output=True,
            shell=True,
        )

        print(colored("[*] Running Frida server...", "light_grey", attrs=["bold"]))
        subprocess.run(
            ["adb", "shell", 'su -c "/data/local/tmp/frida-server -D"'],
            capture_output=True,
            shell=True,
        )
        print(
            colored(
                "[✔] Frida server is running! You can now use Frida for injection",
                "light_green",
                attrs=["bold"],
            )
        )

    except subprocess.CalledProcessError as e:
        print(colored(f"[-] Error: {e}", "light_red", attrs=["bold"]))
        sys.exit(1)


def download_frida_server(frida_version, arch) -> str:
    """Download Frida server for the specified architecture."""
    base_url = f"https://github.com/frida/frida/releases/download/{frida_version}"
    filename = f"frida-server-{frida_version}-{arch}"
    url = f"{base_url}/{filename}.xz"

    print(
        colored(
            f"[*] Downloading Frida server from: {url}", "light_grey", attrs=["bold"]
        )
    )

    try:
        response = requests.get(url)
        response.raise_for_status()
        print(
            colored(
                "[✔] Download successful, Decompressing...",
                "light_green",
                attrs=["bold"],
            )
        )

        # Save the compressed content to a temporary file
        with open(f"{filename}.xz", "wb") as f:
            f.write(response.content)

        # Decompress using lzma
        with lzma.open(f"{filename}.xz", "rb") as compressed:
            with open("frida-server", "wb") as decompressed:
                decompressed.write(compressed.read())

        # Clean up the .xz file
        os.remove(f"{filename}.xz")
        if os.path.exists(filename):
            os.remove(filename)

        return "frida-server"
    except Exception as e:
        print(
            colored(
                f"[-] Error downloading Frida server: {e}", "light_red", attrs=["bold"]
            )
        )
        sys.exit(1)


def _get_prop(prop_name) -> str:
    "Retrieve the value of a system property from an Android device using ADB."
    try:
        result = subprocess.check_output(["adb", "shell", "getprop", prop_name])
        return result.decode("utf-8").strip()
    except subprocess.CalledProcessError:
        return "Unknown"


def _validate_js_file(script_path: str) -> bool:
    """Validate the existence of the JavaScript file."""
    if not os.path.exists(script_path):
        print(
            colored(
                f"[-] JavaScript file not found: {script_path}",
                "light_red",
                attrs=["bold"],
            )
        )
        return False
    return True


def _load_js_code(script_path: str) -> str:
    """Load JavaScript code from a file."""
    try:
        if _validate_js_file(script_path):
            with open(script_path, "r") as f:
                return f.read()
        else:
            sys.exit(1)
    except Exception as e:
        print(colored(f"[-] Failed to read JS file: {e}", "light_red", attrs=["bold"]))
        sys.exit(1)


def start_frida_server() -> None:
    print(colored("[*] Starting Frida server setup...", "light_grey", attrs=["bold"]))

    check_adb_availability()
    check_device_connection()
    launch_scrcpy()
    device_arch = get_device_arch()
    print(colored("[*] Using Frida version: 16.5.9", "light_grey", attrs=["bold"]))

    if check_existing_frida_server():
        start_frida()
    else:
        filename = download_frida_server("16.5.9", device_arch)
        start_frida(filename=filename)
        # Clean up downloaded files
        if os.path.exists(filename):
            os.remove(filename)


def hook_proxygen_SSLVerification() -> None:
    """Hook SSL verification in the Facebook app using Frida."""
    script_path = "./MAIN_SSLPINING.js"
    js_code = _load_js_code(script_path)

    try:
        # Connect to the USB device
        device = frida.get_usb_device(timeout=5)
        print(
            colored("[*] Spawning com.facebook.katana...", "light_grey", attrs=["bold"])
        )

        # Spawn and attach to the Facebook app
        pid = device.spawn(["com.facebook.katana"])
        session = device.attach(pid)
        device.resume(pid)

        # Load the external JavaScript
        script = session.create_script(js_code)

        # Define message handler
        script.on(
            "message",
            lambda message, data: print(
                colored(f"[Frida] {message}", "light_grey", attrs=["bold"]),
            ),
        )
        script.load()

        print(
            colored(
                "[✔] Script loaded and running. Press Ctrl+C to stop.",
                "light_green",
                attrs=["bold"],
            )
        )
        sys.stdin.read()
    except frida.TransportError:
        print(
            colored(
                "[-] Failed to connect to the device. Ensure Frida server is running.",
                "light_red",
                attrs=["bold"],
            )
        )
        sys.exit(1)
    except Exception as e:
        print(colored(f"[-] Error: {e}", "light_red", attrs=["bold"]))
        sys.exit(1)


# -------------------- UI ---------------------


def create_logo():
    app_logo = art.text2art("\nAtropos", font="roman")
    print(colored("welcome to project", "light_blue", attrs=["bold"]))
    print(colored(app_logo, "light_blue", attrs=["bold"]), end="")


if __name__ == "__main__":
    create_logo()
    start_frida_server()
    hook_proxygen_SSLVerification()
