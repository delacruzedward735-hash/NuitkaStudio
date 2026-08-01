# SPDX-License-Identifier: MIT
"""Nuitka Studio: a modern CustomTkinter frontend for Nuitka builds."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image

try:
    import customtkinter as ctk
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing dependency",
        "CustomTkinter is not installed.\n\nRun install_and_run.bat first, or run:\n"
        "python -m pip install -r requirements.txt",
    )
    root.destroy()
    raise SystemExit(1)

from .command_builder import (
    BuildConfig,
    ConfigurationError,
    DataMapping,
    build_command,
    clean_lines,
    display_command,
    normalized_output_filename,
)
from .deb_package import DebianPackageConfig, DebianPackagingError, build_debian_package
from .windows_installer import (
    WindowsInstallerConfig,
    WindowsInstallerError,
    find_inno_setup_compiler,
    installer_output_filename,
    prepare_windows_installer,
)
from .cross_build import (
    CrossBuildError,
    detect_project_entry_script,
    generate_cross_build_workflow,
    path_is_inside_project,
    write_cross_build_workflow,
)
from .environment_check import check_python_environment, nuitka_install_command, parse_python_version
from .progress import detect_build_phase
from .naming import debian_package_id, executable_name, infer_application_name
from .runtime import (
    atomic_write_json,
    create_linux_desktop_launcher,
    detect_project_interpreter,
    find_built_executable,
    host_target_os,
    is_linux_elf_executable,
    is_private_environment_for_external_project,
    iter_batched_text_stream,
    mousewheel_scroll_units,
    open_folder,
    reveal_file,
    terminate_process_tree,
    windows_pe_subsystem,
    WINDOWS_CONSOLE_SUBSYSTEM,
    WINDOWS_GUI_SUBSYSTEM,
)


APP_NAME = "Nuitka Studio"
APP_VERSION = "3.9.3"
CREATOR_NAME = "John Edward Dela Cruz"
PORTFOLIO_URL = "https://myportfoliohub.online"
DONATION_DEFAULTS = {
    "kofi_url": "",
    "gcash_account_name": "",
    "gcash_number": "",
    "gcash_qr_image": "",
    "support_message": (
        "Your support helps maintain Nuitka Studio, improve Linux and Windows builds, "
        "and keep future releases free to use."
    ),
}
SETTINGS_SCHEMA = 9
MAX_LOG_CHARS = 300_000
MIN_FREE_BUILD_BYTES = 1_000_000_000

NAVY = "#071426"
NAVY_2 = "#0b1d33"
BLUE = "#2563eb"
BLUE_HOVER = "#1d4ed8"
SLATE = "#64748b"
GREEN = "#16a34a"
RED = "#dc2626"
AMBER = "#d97706"
WINDOWS_EXE_FORMAT = "Windows EXE (.exe)"
WINDOWS_SETUP_FORMAT = "Windows Setup Installer (.exe)"
LINUX_ELF_FORMAT = "Linux executable (ELF)"
LINUX_DEB_FORMAT = "Debian package (.deb)"


WINDOWS_APP_MUTEX = "PypyProject.NuitkaStudio.App"
_WINDOWS_MUTEX_HANDLES: list[int] = []


def set_windows_app_user_model_id() -> None:
    """Give Windows a stable taskbar identity before Tk creates the window."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PypyProject.NuitkaStudio.3")
    except (AttributeError, OSError):
        pass


def create_windows_app_mutexes() -> None:
    """Expose stable mutexes so Setup/Uninstall can detect a running app.

    The handles intentionally stay alive for the lifetime of the process. The
    session mutex works for normal desktop use; the Global mutex allows an
    elevated uninstaller to detect the application across Windows sessions
    when Windows permits creating it.
    """
    if os.name != "nt" or _WINDOWS_MUTEX_HANDLES:
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        for mutex_name in (WINDOWS_APP_MUTEX, rf"Global\{WINDOWS_APP_MUTEX}"):
            handle = create_mutex(None, False, mutex_name)
            if handle:
                _WINDOWS_MUTEX_HANDLES.append(int(handle))
    except (AttributeError, OSError, TypeError, ValueError):
        # A mutex failure must never prevent the application from starting.
        pass


def app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", str(Path.home())))
    else:
        root = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    base = root / "NuitkaStudio"
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_saved_appearance_mode() -> str:
    """Read the saved theme before constructing any widgets.

    Applying the theme after the interface exists forces CustomTkinter to
    redraw every widget and makes startup look like several windows are being
    reloaded. Reading this one value first keeps the first painted frame final.
    """
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            appearance = str(data.get("appearance_mode", "light")).lower()
            if appearance in {"light", "dark"}:
                return appearance
    except (OSError, ValueError, TypeError):
        pass
    return "light"


def settings_signature(data: dict) -> str:
    """Return a stable signature used to skip unnecessary disk writes."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def asset_path(filename: str) -> Path:
    """Resolve an asset in source, standalone, or onefile execution."""
    candidates = (
        Path(__file__).resolve().parents[1] / "assets" / filename,
        Path(sys.argv[0]).resolve().parent / "assets" / filename,
    )
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


def load_donation_config() -> dict[str, str]:
    """Load public donation details bundled with the application."""
    config = dict(DONATION_DEFAULTS)
    path = asset_path("donation_config.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return config
        for key in config:
            value = data.get(key)
            if isinstance(value, str):
                config[key] = value.strip()
    except (OSError, ValueError, TypeError):
        pass
    return config


def masked_gcash_number(number: str) -> str:
    """Return a public-safe GCash number while preserving copyable source data."""
    digits = "".join(character for character in number if character.isdigit())
    if len(digits) >= 10:
        return f"{digits[:4]} ••• •{digits[-3:]}"
    return "Not configured"


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("nuitka_studio")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(
            app_data_dir() / "nuitka-studio.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class NuitkaStudioApp(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        ctk.set_appearance_mode(load_saved_appearance_mode())
        ctk.set_default_color_theme("blue")
        super().__init__()
        # Keep the root hidden while the first page is assembled. This avoids
        # exposing intermediate layouts or theme redraws on slower computers.
        self.withdraw()

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1380x860")
        self.minsize(1120, 720)
        self.configure(fg_color=("#f6f8fc", "#070d18"))
        self.logger = configure_logging()
        self.target_os = host_target_os()
        self.report_callback_exception = self._handle_tk_exception
        self.logger.info("Starting %s %s", APP_NAME, APP_VERSION)
        self._window_icon: tk.PhotoImage | None = None
        self._nav_icons: dict[str, ctk.CTkImage] = {}
        self._brand_icon: ctk.CTkImage | None = None
        self._load_window_icon()
        self._load_navigation_icons()
        self.donation_config = load_donation_config()
        self.gcash_qr_image: ctk.CTkImage | None = None

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.data_mappings: list[DataMapping] = []
        self.history: list[dict[str, str]] = []
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.pages: dict[str, ctk.CTkFrame] = {}
        self._scrollable_frames: list[ctk.CTkScrollableFrame] = []
        self.active_page = "Build"
        self.python_ready = False
        self.nuitka_ready = False
        self.nuitka_checked = False
        self.nuitka_installed = False
        self.nuitka_issue = ""
        self._nuitka_install_running = False
        self.build_log = ""
        self.terminal_mode = "command"
        self._terminal_expanded = False
        self.build_started_at = 0.0
        self._refresh_after_id: str | None = None
        self._cross_preview_dirty = True
        self._last_cross_preview_text = ""
        self._last_cross_status_text = ""
        self._last_terminal_text = ""
        self._installer_compiler_cache: tuple[str, float, Path | None] | None = None
        self._setup_cache: dict[str, dict[str, object]] = {}
        self._setup_checks_running: set[str] = set()
        self._cancel_requested = False
        self._active_build: dict[str, str] | None = None
        self._last_output_dir: Path | None = None
        self._last_output_file: Path | None = None
        self._last_linux_launcher: Path | None = None
        self._packaged_output_file: Path | None = None
        self._packaged_binary_file: Path | None = None
        self._cross_workflow_path: Path | None = None
        self._build_progress_value = 0.0
        self._build_progress_ceiling = 0.08
        self._build_phase = "Preparing build"
        self._progress_tick_after_id: str | None = None
        self._progress_hide_after_id: str | None = None
        self._closing = False
        self._startup_complete = False
        self._last_saved_settings_signature = ""
        self._packages_lines: list[str] = []
        self._package_data_lines: list[str] = []
        self._extra_argument_lines: list[str] = []
        self._page_builders: dict[str, Callable[[], None]] = {}

        self._make_variables()
        self._build_shell()
        self._build_pages()
        self._install_scroll_routing()
        self._build_action_bar()
        self._load_settings()
        self._bind_refresh_traces()
        self._show_page("Build")
        self._refresh_all()

        self.after(120, self._drain_output)
        self.after(900, self._check_setup_silent)
        self.after_idle(self._finish_startup)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ state
    def _make_variables(self) -> None:
        default_output = executable_name("Application", self.target_os)
        self.python_var = tk.StringVar(value=sys.executable)
        self.script_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.application_name_var = tk.StringVar(value="Application")
        self.output_name_var = tk.StringVar(value=default_output)
        self._last_application_name = "Application"
        self._last_generated_output_name = default_output
        default_package_id = debian_package_id("Application")
        self.package_format_var = tk.StringVar(
            value=WINDOWS_EXE_FORMAT if self.target_os == "windows" else LINUX_ELF_FORMAT
        )
        self.package_id_var = tk.StringVar(value=default_package_id)
        self._last_generated_package_id = default_package_id
        self.package_maintainer_var = tk.StringVar(value=CREATOR_NAME)
        self.package_section_var = tk.StringVar(value="utils")
        self.icon_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="standalone")
        self.console_var = tk.StringVar(value="disable" if self.target_os == "windows" else "native")
        self.compiler_var = tk.StringVar(value="auto")
        self.tk_plugin_var = tk.BooleanVar(value=True)
        self.ctk_data_var = tk.BooleanVar(value=False)
        self.clean_var = tk.BooleanVar(value=True)
        self.assume_var = tk.BooleanVar(value=True)
        self.progress_var = tk.BooleanVar(value=False)
        self.jobs_var = tk.StringVar(value="-2")
        self.onefile_no_compression_var = tk.BooleanVar(value=True)

        self.company_var = tk.StringVar()
        self.product_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.file_version_var = tk.StringVar(value="1.0.0.0")
        self.product_version_var = tk.StringVar(value="1.0.0.0")
        self.copyright_var = tk.StringVar()

        self.installer_publisher_var = tk.StringVar(value=CREATOR_NAME)
        self.installer_website_var = tk.StringVar(value=PORTFOLIO_URL)
        self.installer_scope_var = tk.StringVar(value="All users (Program Files)")
        self.installer_compiler_var = tk.StringVar()
        self.installer_license_var = tk.StringVar()
        self.installer_desktop_shortcut_var = tk.BooleanVar(value=True)
        self.installer_start_menu_var = tk.BooleanVar(value=True)
        self.installer_launch_var = tk.BooleanVar(value=True)
        self.installer_status_var = tk.StringVar(value="Checking installer tools...")

        default_cross_python = f"{sys.version_info.major}.{sys.version_info.minor}"
        self.cross_project_root_var = tk.StringVar()
        self.cross_python_version_var = tk.StringVar(value=default_cross_python)
        self.cross_requirements_var = tk.StringVar(value="requirements.txt")
        self.cross_target_var = tk.StringVar(value="Windows + Linux")
        self.cross_windows_icon_var = tk.StringVar()
        self.cross_linux_icon_var = tk.StringVar()
        self.cross_build_on_push_var = tk.BooleanVar(value=False)
        self.cross_repo_url_var = tk.StringVar()
        self.cross_status_var = tk.StringVar(value="Select a project root to prepare native Windows and Linux builds.")

        self.status_var = tk.StringVar(value="Ready to configure")
        self.environment_var = tk.StringVar(value="Checking Python...")
        self.environment_state_var = tk.StringVar(value="Checking")
        self.summary_mode_var = tk.StringVar(value="Standalone")
        self.summary_compiler_var = tk.StringVar(value="Auto")
        self.summary_target_var = tk.StringVar(value=self.target_os.title())
        self.summary_format_var = tk.StringVar(value=self.package_format_var.get())
        self.summary_application_var = tk.StringVar(value="Application")
        self.summary_output_var = tk.StringVar(value=default_output)
        self.summary_jobs_var = tk.StringVar(value="All cores except 2")
        self.python_check_var = tk.StringVar(value="○ Python not checked")
        self.nuitka_check_var = tk.StringVar(value="○ Nuitka not checked")
        self.config_check_var = tk.StringVar(value="○ Complete project setup")
        self.terminal_title_var = tk.StringVar(value="Command preview")
        self.progress_detail_var = tk.StringVar(value="")

    def _bind_refresh_traces(self) -> None:
        variables = (
            self.python_var,
            self.script_var,
            self.output_dir_var,
            self.application_name_var,
            self.package_format_var,
            self.package_id_var,
            self.package_maintainer_var,
            self.package_section_var,
            self.output_name_var,
            self.icon_var,
            self.mode_var,
            self.console_var,
            self.compiler_var,
            self.tk_plugin_var,
            self.ctk_data_var,
            self.clean_var,
            self.assume_var,
            self.progress_var,
            self.jobs_var,
            self.onefile_no_compression_var,
            self.company_var,
            self.product_var,
            self.description_var,
            self.file_version_var,
            self.product_version_var,
            self.copyright_var,
            self.installer_publisher_var,
            self.installer_website_var,
            self.installer_scope_var,
            self.installer_compiler_var,
            self.installer_license_var,
            self.installer_desktop_shortcut_var,
            self.installer_start_menu_var,
            self.installer_launch_var,
            self.cross_project_root_var,
            self.cross_python_version_var,
            self.cross_requirements_var,
            self.cross_target_var,
            self.cross_windows_icon_var,
            self.cross_linux_icon_var,
            self.cross_build_on_push_var,
            self.cross_repo_url_var,
        )
        for variable in variables:
            variable.trace_add("write", lambda *_args: self._schedule_refresh())
        self.application_name_var.trace_add("write", self._application_name_changed)
        self.python_var.trace_add("write", self._python_path_changed)

    def _python_path_changed(self, *_args) -> None:
        """Never carry readiness state from one interpreter into another."""
        self.python_ready = False
        self.nuitka_ready = False
        self.nuitka_checked = False
        self.nuitka_installed = False
        self.nuitka_issue = ""

    def _application_name_changed(self, *_args) -> None:
        """Keep generated filename and product metadata aligned until customized."""
        name = self.application_name_var.get().strip()
        current_output = self.output_name_var.get().strip()
        if not current_output or current_output.casefold() == self._last_generated_output_name.casefold():
            self.output_name_var.set(executable_name(name, self.target_os))
        current_product = self.product_var.get().strip()
        if not current_product or current_product == self._last_application_name:
            self.product_var.set(name)
        generated_package_id = debian_package_id(name)
        current_package_id = self.package_id_var.get().strip()
        if not current_package_id or current_package_id == self._last_generated_package_id:
            self.package_id_var.set(generated_package_id)
        self._last_application_name = name
        self._last_generated_output_name = executable_name(name, self.target_os)
        self._last_generated_package_id = generated_package_id

    def _schedule_refresh(self, delay: int = 110) -> None:
        """Coalesce rapid changes and defer expensive cross-build rendering."""
        self._cross_preview_dirty = True
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except (ValueError, tk.TclError):
                pass
        self._refresh_after_id = self.after(delay, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_after_id = None
        self._refresh_all()
        if self.active_page == "Cross Build":
            self._refresh_cross_build_preview()

    def _load_window_icon(self) -> None:
        try:
            png_path = asset_path("nuitka-studio-icon-64.png")
            self._window_icon = tk.PhotoImage(file=str(png_path))
            with Image.open(png_path) as source:
                brand_image = source.copy()
            self._brand_icon = ctk.CTkImage(light_image=brand_image, dark_image=brand_image, size=(52, 52))
            self._apply_window_icon()
            # CTk applies its bundled icon about 200 ms after construction.
            # Reapply ours after that callback and once more after the shell is ready.
            self.after(300, self._apply_window_icon)
            self.after(1200, self._apply_window_icon)
        except (OSError, tk.TclError) as exc:
            self.logger.warning("Could not load application icon: %s", exc)

    def _apply_window_icon(self) -> None:
        if self._window_icon is None:
            return
        try:
            self.iconphoto(True, self._window_icon)
            if os.name == "nt":
                self.iconbitmap(str(asset_path("nuitka-studio.ico")))
        except (OSError, tk.TclError) as exc:
            self.logger.warning("Could not apply application icon: %s", exc)

    def _load_navigation_icons(self) -> None:
        filenames = {
            "Build": "nav-build.png",
            "Cross Build": "nav-cross-build.png",
            "Packages": "nav-packages.png",
            "Resources": "nav-resources.png",
            "App Identity": "nav-identity.png",
            "Installer": "nav-installer.png",
            "History": "nav-history.png",
            "Settings": "nav-settings.png",
            "How to Use": "nav-help.png",
            "Donate": "nav-donate.png",
        }
        for name, filename in filenames.items():
            try:
                with Image.open(asset_path(filename)) as source:
                    image = source.copy()
                self._nav_icons[name] = ctk.CTkImage(light_image=image, dark_image=image, size=(20, 20))
            except (OSError, tk.TclError) as exc:
                self.logger.warning("Could not load navigation icon %s: %s", filename, exc)

    # --------------------------------------------------------------- app shell
    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=226, corner_radius=0, fg_color=NAVY)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(11, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=18, pady=(24, 28), sticky="ew")
        if self._brand_icon is not None:
            ctk.CTkLabel(
                brand,
                text="",
                image=self._brand_icon,
                width=52,
                height=52,
                fg_color="transparent",
            ).pack(side="left")
        else:
            ctk.CTkLabel(
                brand,
                text="N",
                width=44,
                height=44,
                corner_radius=12,
                fg_color=BLUE,
                text_color="white",
                font=ctk.CTkFont(size=24, weight="bold"),
            ).pack(side="left")
        ctk.CTkLabel(
            brand,
            text="NUITKA\nSTUDIO",
            justify="left",
            text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=(12, 0))

        navigation = ("Build", "Cross Build", "Packages", "Resources", "App Identity", "Installer", "History", "Settings", "How to Use", "Donate")
        for row, name in enumerate(navigation, start=1):
            button = ctk.CTkButton(
                self.sidebar,
                text=name,
                image=self._nav_icons.get(name),
                compound="left",
                height=46,
                corner_radius=9,
                anchor="w",
                font=ctk.CTkFont(size=14),
                fg_color="transparent",
                hover_color="#112b49",
                text_color="#dbeafe",
                command=lambda page=name: self._show_page(page),
            )
            button.grid(row=row, column=0, padx=14, pady=3, sticky="ew")
            self.nav_buttons[name] = button

        version_box = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        version_box.grid(row=12, column=0, padx=24, pady=22, sticky="sw")
        ctk.CTkLabel(version_box, text=f"Studio {APP_VERSION}", text_color="#94a3b8", font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkLabel(version_box, text="● Ready", text_color="#4ade80", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(4, 0))

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color=("#f6f8fc", "#070d18"))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self.header = ctk.CTkFrame(self.content, height=112, corner_radius=0, fg_color="transparent")
        self.header.grid(row=0, column=0, padx=30, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)

        self.header_text = ctk.CTkFrame(self.header, fg_color="transparent")
        self.header_text.grid(row=0, column=0, pady=22, sticky="w")
        self.page_title = ctk.CTkLabel(self.header_text, text="Build application", font=ctk.CTkFont(size=27, weight="bold"), anchor="w")
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(
            self.header_text,
            text="Configure and compile your Python project",
            text_color=(SLATE, "#94a3b8"),
            font=ctk.CTkFont(size=14),
        )
        self.page_subtitle.pack(anchor="w", pady=(2, 0))

        env = ctk.CTkFrame(self.header, corner_radius=10, border_width=1, border_color=("#d7deea", "#25344a"), fg_color=("white", NAVY_2))
        env.grid(row=0, column=1, padx=(10, 8), pady=25)
        ctk.CTkLabel(env, text="Python", text_color=BLUE, font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(14, 8), pady=10)
        ctk.CTkLabel(env, textvariable=self.environment_var, font=ctk.CTkFont(size=12)).pack(side="left", pady=10)
        self.env_state_label = ctk.CTkLabel(env, textvariable=self.environment_state_var, text_color=GREEN, font=ctk.CTkFont(size=12, weight="bold"))
        self.env_state_label.pack(side="left", padx=(10, 14), pady=10)

        self.theme_button = ctk.CTkButton(
            self.header,
            text="☼",
            width=42,
            height=42,
            fg_color=("white", NAVY_2),
            hover_color=("#e8eef8", "#162a45"),
            text_color=(NAVY, "white"),
            border_width=1,
            border_color=("#d7deea", "#25344a"),
            command=self._toggle_theme,
        )
        self.theme_button.grid(row=0, column=2, padx=4)
        self.help_button = ctk.CTkButton(
            self.header,
            text="?",
            width=42,
            height=42,
            fg_color=("white", NAVY_2),
            hover_color=("#e8eef8", "#162a45"),
            text_color=(NAVY, "white"),
            border_width=1,
            border_color=("#d7deea", "#25344a"),
            command=lambda: self._show_page("How to Use"),
        )
        self.help_button.grid(row=0, column=3, padx=(4, 0))

        self.page_host = ctk.CTkFrame(self.content, corner_radius=0, fg_color="transparent")
        self.page_host.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="nsew")
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

    def _build_pages(self) -> None:
        """Register pages and build only the first visible page.

        Earlier releases created every card, textbox, image, and scrollable
        frame before the window appeared. Besides slowing startup, that allowed
        users to see intermediate page layouts on lower-end systems. Pages are
        now created once, on first navigation, then retained in memory.
        """
        self._page_builders = {
            "Build": self._build_build_page,
            "Cross Build": self._build_cross_build_page,
            "Packages": self._build_packages_page,
            "Resources": self._build_resources_page,
            "App Identity": self._build_identity_page,
            "Installer": self._build_installer_page,
            "History": self._build_history_page,
            "Settings": self._build_settings_page,
            "How to Use": self._build_help_page,
            "Donate": self._build_donate_page,
        }
        self._build_page_if_needed("Build")

    def _build_page_if_needed(self, name: str) -> ctk.CTkFrame:
        page = self.pages.get(name)
        if page is not None:
            return page
        builder = self._page_builders.get(name)
        if builder is None:
            raise KeyError(f"Unknown page: {name}")
        builder()
        return self.pages[name]

    def _new_page(self, name: str, *, scroll: bool = False) -> ctk.CTkFrame:
        if scroll:
            page = self._scrollable_frame(self.page_host, fg_color="transparent")
        else:
            page = ctk.CTkFrame(self.page_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        self.pages[name] = page
        return page

    def _finish_startup(self) -> None:
        """Reveal one fully laid-out window after the first idle cycle."""
        if self._closing or self._startup_complete:
            return
        try:
            self.update_idletasks()
            self.deiconify()
            self._startup_complete = True
        except tk.TclError:
            pass

    def _scrollable_frame(self, master, **kwargs) -> ctk.CTkScrollableFrame:
        """Create and register a scrollable frame for reliable wheel routing."""
        frame = ctk.CTkScrollableFrame(master, **kwargs)
        self._scrollable_frames.append(frame)
        return frame

    def _install_scroll_routing(self) -> None:
        """Route wheel and touchpad events to the scroll area under the pointer.

        CustomTkinter scrollable frames use a global wheel binding. When an app
        contains several of them, the last-created frame can replace the earlier
        bindings, which makes other pages appear non-scrollable. A single router
        fixes that behavior on Windows, macOS, Linux/X11, and Linux/Wayland.
        """
        self.bind_all("<MouseWheel>", self._route_mousewheel)
        self.bind_all("<Button-4>", self._route_mousewheel)
        self.bind_all("<Button-5>", self._route_mousewheel)

    def _scroll_candidates_for_widget(self, widget) -> list[ctk.CTkScrollableFrame]:
        candidates: list[ctk.CTkScrollableFrame] = []
        current = widget
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            for frame in reversed(self._scrollable_frames):
                related = (
                    frame,
                    getattr(frame, "_parent_canvas", None),
                    getattr(frame, "_parent_frame", None),
                    getattr(frame, "_scrollbar", None),
                )
                if any(current is item for item in related if item is not None) and frame not in candidates:
                    candidates.append(frame)
            current = getattr(current, "master", None)
        return candidates

    def _route_mousewheel(self, event):
        """Scroll the nearest usable CTkScrollableFrame without blocking text boxes."""
        widget = getattr(event, "widget", None)
        # CTkTextbox wraps a native tk.Text. Let its own class binding handle the
        # wheel so terminal and workflow previews remain independently scrollable.
        if isinstance(widget, (tk.Text, tk.Listbox)):
            return None

        units = mousewheel_scroll_units(
            sys.platform,
            delta=getattr(event, "delta", 0),
            button_number=getattr(event, "num", None),
        )
        if units == 0:
            return None

        candidates = self._scroll_candidates_for_widget(widget)
        if not candidates:
            try:
                pointer_widget = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
            except tk.TclError:
                pointer_widget = None
            candidates = self._scroll_candidates_for_widget(pointer_widget)

        for frame in candidates:
            canvas = getattr(frame, "_parent_canvas", None)
            if canvas is None:
                continue
            try:
                first, last = canvas.yview()
            except tk.TclError:
                continue
            if first <= 0.0 and last >= 1.0:
                continue
            if units < 0 and first <= 0.0:
                continue
            if units > 0 and last >= 1.0:
                continue
            try:
                canvas.yview_scroll(units, "units")
            except tk.TclError:
                continue
            return "break"
        return None

    # --------------------------------------------------------------- Build page
    def _build_build_page(self) -> None:
        page = self._new_page("Build")
        page.grid_columnconfigure(0, weight=3, uniform="build")
        page.grid_columnconfigure(1, weight=2, uniform="build")
        page.grid_rowconfigure(0, weight=1)

        left = self._scrollable_frame(page, fg_color="transparent")
        left.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkFrame(page, fg_color="transparent")
        right.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        project = self._card(left, "Project setup", "Choose the environment and files used for this build.", 0)
        self._path_row(project, 2, "Python interpreter", self.python_var, self._choose_python)
        self._path_row(project, 3, "Entry script", self.script_var, self._choose_script)
        self._path_row(project, 4, "Output location", self.output_dir_var, self._choose_output)
        self._entry_row(project, 5, "Application name", self.application_name_var, "Example: NexaConvert")
        output_example = "NexaConvert.exe" if self.target_os == "windows" else "NexaConvert"
        icon_label = "Windows icon" if self.target_os == "windows" else "Linux launcher icon"
        self._entry_row(project, 6, "Executable filename", self.output_name_var, output_example)
        self._path_row(project, 7, icon_label, self.icon_var, self._choose_icon, optional=True)

        config = self._card(left, "Build configuration", "Start with Standalone; use Onefile after your app is verified.", 1)
        modes = ctk.CTkSegmentedButton(
            config,
            values=["standalone", "onefile"],
            variable=self.mode_var,
            selected_color=BLUE,
            selected_hover_color=BLUE_HOVER,
            command=lambda _value: self._refresh_all(),
        )
        modes.grid(row=2, column=0, padx=20, pady=(2, 14), sticky="ew")

        select_grid = ctk.CTkFrame(config, fg_color="transparent")
        select_grid.grid(row=3, column=0, padx=20, sticky="ew")
        select_grid.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(select_grid, text="Console mode", anchor="w").grid(row=0, column=0, padx=(0, 16), pady=6, sticky="w")
        console_values = ["disable", "force", "attach", "hide"] if self.target_os == "windows" else ["native"]
        ctk.CTkOptionMenu(
            select_grid,
            values=console_values,
            variable=self.console_var,
            fg_color=("#e8eef8", "#15253b"),
            button_color=("#cbd5e1", "#25344a"),
            text_color=(NAVY, "white"),
            command=lambda _value: self._refresh_all(),
        ).grid(row=0, column=1, pady=6, sticky="ew")
        ctk.CTkLabel(select_grid, text="Compiler", anchor="w").grid(row=1, column=0, padx=(0, 16), pady=6, sticky="w")
        compiler_values = ["auto", "msvc", "mingw64"] if self.target_os == "windows" else ["auto", "gcc", "clang"]
        ctk.CTkOptionMenu(
            select_grid,
            values=compiler_values,
            variable=self.compiler_var,
            fg_color=("#e8eef8", "#15253b"),
            button_color=("#cbd5e1", "#25344a"),
            text_color=(NAVY, "white"),
            command=lambda _value: self._refresh_all(),
        ).grid(row=1, column=1, pady=6, sticky="ew")
        ctk.CTkLabel(select_grid, text="Output format", anchor="w").grid(row=2, column=0, padx=(0, 16), pady=6, sticky="w")
        format_values = [WINDOWS_EXE_FORMAT, WINDOWS_SETUP_FORMAT] if self.target_os == "windows" else [LINUX_ELF_FORMAT, LINUX_DEB_FORMAT]
        ctk.CTkOptionMenu(
            select_grid,
            values=format_values,
            variable=self.package_format_var,
            fg_color=("#e8eef8", "#15253b"),
            button_color=("#cbd5e1", "#25344a"),
            text_color=(NAVY, "white"),
            command=lambda _value: self._refresh_all(),
        ).grid(row=2, column=1, pady=6, sticky="ew")

        toggles = ctk.CTkFrame(config, fg_color="transparent")
        toggles.grid(row=4, column=0, padx=20, pady=(12, 18), sticky="ew")
        toggles.grid_columnconfigure(0, weight=1)
        for row, (text, variable) in enumerate(
            (
                ("Tkinter plugin", self.tk_plugin_var),
                ("CustomTkinter data", self.ctk_data_var),
                ("Clean temporary build files", self.clean_var),
            )
        ):
            ctk.CTkLabel(toggles, text=text, anchor="w").grid(row=row, column=0, pady=5, sticky="ew")
            ctk.CTkSwitch(toggles, text="", width=44, variable=variable, command=self._refresh_all).grid(row=row, column=1, pady=5)

        summary = self._card(right, "Build summary", "Review the important output settings.", 0)
        self.build_summary_card = summary
        summary_grid = ctk.CTkFrame(summary, fg_color="transparent")
        summary_grid.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
        summary_grid.grid_columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(
            (
                ("Target", self.summary_target_var),
                ("Format", self.summary_format_var),
                ("Mode", self.summary_mode_var),
                ("Compiler", self.summary_compiler_var),
                ("Application", self.summary_application_var),
                ("Output", self.summary_output_var),
                ("Jobs", self.summary_jobs_var),
            )
        ):
            ctk.CTkLabel(summary_grid, text=label, text_color=(SLATE, "#94a3b8"), anchor="w").grid(row=row, column=0, pady=4, sticky="w")
            ctk.CTkLabel(summary_grid, textvariable=variable, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=row, column=1, padx=(28, 0), pady=4, sticky="ew")

        line = ctk.CTkFrame(summary, height=1, fg_color=("#dbe2ec", "#25344a"))
        line.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        checklist = ctk.CTkFrame(summary, fg_color="transparent")
        checklist.grid(row=4, column=0, padx=20, pady=(0, 18), sticky="ew")
        self.python_check_label = ctk.CTkLabel(checklist, textvariable=self.python_check_var, anchor="w")
        self.python_check_label.pack(anchor="w", pady=3)
        self.nuitka_check_label = ctk.CTkLabel(checklist, textvariable=self.nuitka_check_var, anchor="w")
        self.nuitka_check_label.pack(anchor="w", pady=3)
        self.config_check_label = ctk.CTkLabel(checklist, textvariable=self.config_check_var, anchor="w")
        self.config_check_label.pack(anchor="w", pady=3)

        terminal = ctk.CTkFrame(right, corner_radius=13, fg_color="#071321")
        self.terminal_card = terminal
        terminal.grid(row=1, column=0, pady=(14, 0), sticky="nsew")
        terminal.grid_columnconfigure(0, weight=1)
        terminal.grid_rowconfigure(1, weight=1)
        terminal_head = ctk.CTkFrame(terminal, fg_color="transparent")
        terminal_head.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")
        ctk.CTkLabel(
            terminal_head,
            textvariable=self.terminal_title_var,
            text_color="white",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            terminal_head,
            text="Copy",
            width=58,
            height=28,
            fg_color="#142c47",
            hover_color="#1e4169",
            command=self._copy_terminal,
        ).pack(side="right", padx=(6, 0))
        self.terminal_expand_button = ctk.CTkButton(
            terminal_head,
            text="Expand",
            width=68,
            height=28,
            fg_color="#142c47",
            hover_color="#1e4169",
            command=self._toggle_terminal_expansion,
        )
        self.terminal_expand_button.pack(side="right", padx=(6, 0))
        self.log_toggle_button = ctk.CTkButton(
            terminal_head,
            text="Build log",
            width=74,
            height=28,
            fg_color="#142c47",
            hover_color="#1e4169",
            command=self._toggle_terminal,
        )
        self.log_toggle_button.pack(side="right")
        self.terminal_text = ctk.CTkTextbox(
            terminal,
            fg_color="#071321",
            text_color="#c4b5fd",
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="none",
            border_width=0,
        )
        self.terminal_text.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.terminal_text.configure(state="disabled")

    # --------------------------------------------------------- Cross Build page
    def _build_cross_build_page(self) -> None:
        page = self._new_page("Cross Build", scroll=True)

        notice = self._card(
            page,
            "Build for Windows and Linux",
            "Nuitka binaries are operating-system specific. Cross Build uses native GitHub-hosted Windows and Ubuntu runners instead of unreliable local cross-compilation.",
            0,
        )
        self._info_rows(
            notice,
            (
                ("1", "Configure the project here", "Keep the entry script, requirements, icons, packages, and resources inside one project root folder."),
                ("2", "Generate the workflow", "Studio creates .github/workflows/nuitka-studio-cross-build.yml inside the project."),
                ("3", "Push the project to GitHub", "Open the repository Actions tab, run the workflow, and download the Windows or Linux artifact."),
            ),
        )

        setup = self._card(page, "Cross-build configuration", "These settings are used only by the generated GitHub Actions workflow.", 1)
        self._path_row(setup, 2, "Project root", self.cross_project_root_var, self._choose_cross_project_root)
        self._path_row(setup, 3, "Entry script", self.script_var, self._choose_cross_entry_script)
        self._entry_row(setup, 4, "Python version", self.cross_python_version_var, "3.12")
        self._entry_row(setup, 5, "Requirements file", self.cross_requirements_var, "requirements.txt (optional)")
        self._entry_row(setup, 6, "GitHub repository", self.cross_repo_url_var, "https://github.com/owner/repository (optional)")

        target_row = ctk.CTkFrame(setup, fg_color="transparent")
        target_row.grid(row=7, column=0, padx=20, pady=5, sticky="ew")
        target_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(target_row, text="Build targets", width=132, anchor="w").grid(row=0, column=0, padx=(0, 10))
        ctk.CTkOptionMenu(
            target_row,
            values=["Windows + Linux", "Windows only", "Linux only"],
            variable=self.cross_target_var,
            fg_color=("#e8eef8", "#15253b"),
            button_color=("#cbd5e1", "#25344a"),
            text_color=(NAVY, "white"),
            command=lambda _value: self._schedule_refresh(0),
        ).grid(row=0, column=1, sticky="ew")

        self._path_row(setup, 8, "Windows icon", self.cross_windows_icon_var, self._choose_cross_windows_icon, optional=True)
        self._path_row(setup, 9, "Linux icon", self.cross_linux_icon_var, self._choose_cross_linux_icon, optional=True)

        push_row = ctk.CTkFrame(setup, fg_color="transparent")
        push_row.grid(row=10, column=0, padx=20, pady=(8, 4), sticky="ew")
        push_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(push_row, text="Also build automatically when main/master is pushed", anchor="w").grid(row=0, column=0, sticky="ew")
        ctk.CTkSwitch(push_row, text="", width=44, variable=self.cross_build_on_push_var, command=lambda: self._schedule_refresh(0)).grid(row=0, column=1)

        buttons = ctk.CTkFrame(setup, fg_color="transparent")
        buttons.grid(row=11, column=0, padx=20, pady=(10, 18), sticky="ew")
        ctk.CTkButton(buttons, text="Use current project", width=145, command=self._use_current_cross_project).pack(side="left")
        ctk.CTkButton(buttons, text="Generate workflow", width=145, command=self._generate_cross_workflow).pack(side="left", padx=8)
        ctk.CTkButton(buttons, text="Open workflow folder", width=155, fg_color="#475569", hover_color="#334155", command=self._open_cross_workflow_folder).pack(side="left")
        ctk.CTkButton(buttons, text="Open GitHub Actions", width=145, fg_color="#475569", hover_color="#334155", command=self._open_cross_actions).pack(side="left", padx=8)

        preview = self._card(page, "Workflow preview", "The workflow runs each build on its actual target operating system.", 2)
        ctk.CTkLabel(
            preview,
            textvariable=self.cross_status_var,
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
            justify="left",
            wraplength=920,
        ).grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
        self.cross_workflow_preview = ctk.CTkTextbox(preview, height=330, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.cross_workflow_preview.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
        self.cross_workflow_preview.configure(state="disabled")
        ctk.CTkButton(preview, text="Copy workflow", width=120, command=self._copy_cross_workflow).grid(row=4, column=0, padx=20, pady=(0, 18), sticky="w")

        limits = self._card(page, "Important limitations", "Cross Build is a native remote build, not a local Windows-to-Linux or Linux-to-Windows compiler switch.", 3)
        self._info_rows(
            limits,
            (
                ("!", "Your source must be in the repository", "External resources and icons cannot be uploaded by the workflow. Move them inside the selected project root."),
                ("!", "Test each artifact on its own OS", "A successful compiler run does not guarantee that every dynamic dependency or platform-specific feature works."),
                ("!", "Installer packaging is separate", "This workflow creates native Windows and Linux applications. Windows Setup and Debian package creation remain separate release steps."),
            ),
        )

    # ------------------------------------------------------------- other pages
    def _build_packages_page(self) -> None:
        page = self._new_page("Packages", scroll=True)
        card = self._card(page, "Package inclusion", "Nuitka detects normal imports automatically. Add only dynamic or missed imports here.", 0)
        fields = ctk.CTkFrame(card, fg_color="transparent")
        fields.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        fields.grid_columnconfigure(0, weight=1)
        fields.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fields, text="Include package", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkLabel(fields, text="Include package data", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self.packages_text = ctk.CTkTextbox(fields, height=240)
        self.packages_text.grid(row=1, column=0, padx=(0, 8), pady=(8, 0), sticky="ew")
        self.package_data_text = ctk.CTkTextbox(fields, height=240)
        self.package_data_text.grid(row=1, column=1, padx=(8, 0), pady=(8, 0), sticky="ew")
        if self._packages_lines:
            self.packages_text.insert("1.0", "\n".join(self._packages_lines))
        if self._package_data_lines:
            self.package_data_text.insert("1.0", "\n".join(self._package_data_lines))
        self.packages_text.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        self.package_data_text.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        ctk.CTkLabel(
            fields,
            text="Examples: pillow_heif, fitz, pdf2docx",
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
        ).grid(row=2, column=0, padx=(0, 8), pady=(7, 0), sticky="ew")
        ctk.CTkLabel(
            fields,
            text="Examples: customtkinter, tkinterdnd2",
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
        ).grid(row=2, column=1, padx=(8, 0), pady=(7, 0), sticky="ew")

        guide = self._card(page, "When should I add a package?", "Use explicit inclusion only when the build runs but reports a missing module or missing package resource.", 1)
        self._info_rows(
            guide,
            (
                ("1", "Build once without forcing packages", "This produces a cleaner and smaller application."),
                ("2", "Read the exact Nuitka warning", "Identify whether code, package data, or a DLL is missing."),
                ("3", "Add the smallest specific inclusion", "Avoid including your entire environment."),
            ),
        )

    def _build_resources_page(self) -> None:
        page = self._new_page("Resources")
        page.grid_rowconfigure(0, weight=1)
        card = self._card(page, "Application resources", "Include assets, templates, static files, configuration files, or other runtime data.", 0)
        card.grid_rowconfigure(3, weight=1)
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        ctk.CTkButton(actions, text="+ Add folder", width=112, command=self._add_data_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="+ Add file", width=100, command=self._add_data_file).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Remove selected", width=132, fg_color="#475569", hover_color="#334155", command=self._remove_data).pack(side="left")
        self.data_list = tk.Listbox(
            card,
            height=14,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            background="#0b1d33",
            foreground="#e2e8f0",
            selectbackground=BLUE,
            selectforeground="white",
            highlightbackground="#25344a",
            font=("Segoe UI", 10),
            selectmode=tk.EXTENDED,
        )
        self.data_list.grid(row=3, column=0, padx=20, pady=(0, 18), sticky="nsew")
        self.resource_empty_label = ctk.CTkLabel(
            card,
            text="No resources added yet.\nUse Add folder or Add file to include runtime assets.",
            justify="center",
            text_color="#94a3b8",
            fg_color="#0b1d33",
        )
        ctk.CTkLabel(
            card,
            text="Destination paths must be relative, such as assets or server/templates.",
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
        ).grid(row=4, column=0, padx=20, pady=(0, 18), sticky="ew")
        self._refresh_data_list(refresh=False)

    def _build_identity_page(self) -> None:
        page = self._new_page("App Identity", scroll=True)
        identity_description = (
            "These values appear under File Explorer → Properties → Details."
            if self.target_os == "windows"
            else "Application identity is used by Linux desktop launchers and Debian packages."
        )
        card = self._card(page, "Application identity", identity_description, 0)
        form = ctk.CTkFrame(card, fg_color="transparent")
        form.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)
        fields = (
            ("Company name", self.company_var, "Example: John Edward Dela Cruz"),
            ("Product name", self.product_var, "Example: NexaConvert"),
            ("File description", self.description_var, "Example: Universal file converter"),
            ("Copyright", self.copyright_var, "Example: © 2026 John Edward Dela Cruz"),
            ("File version", self.file_version_var, "Example: 1.0.0.0"),
            ("Product version", self.product_version_var, "Example: 1.0.0.0"),
        )
        for index, (label, variable, placeholder) in enumerate(fields):
            row, column = divmod(index, 2)
            field = ctk.CTkFrame(form, fg_color="transparent")
            field.grid(row=row, column=column, padx=8, pady=9, sticky="ew")
            field.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(field, text=label, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, pady=(0, 5), sticky="ew")
            ctk.CTkEntry(field, textvariable=variable, placeholder_text=placeholder).grid(row=1, column=0, sticky="ew")

        package_card = self._card(
            page,
            "Debian package identity",
            "Used when Linux output format is Debian package (.deb). Kali, Parrot, Debian, Ubuntu, and Mint use this format.",
            1,
        )
        package_form = ctk.CTkFrame(package_card, fg_color="transparent")
        package_form.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        package_form.grid_columnconfigure(0, weight=1)
        package_form.grid_columnconfigure(1, weight=1)
        package_fields = (
            ("Package ID", self.package_id_var, "Example: nexaconvert"),
            ("Maintainer", self.package_maintainer_var, "Example: John Edward Dela Cruz <you@example.com>"),
            ("Section", self.package_section_var, "Example: utils"),
        )
        for index, (label, variable, placeholder) in enumerate(package_fields):
            row, column = divmod(index, 2)
            field = ctk.CTkFrame(package_form, fg_color="transparent")
            field.grid(row=row, column=column, padx=8, pady=9, sticky="ew")
            field.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(field, text=label, font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, pady=(0, 5), sticky="ew")
            ctk.CTkEntry(field, textvariable=variable, placeholder_text=placeholder).grid(row=1, column=0, sticky="ew")

        icon_title = "Use a true multi-size Windows ICO file for the sharpest result." if self.target_os == "windows" else "Use a PNG or SVG image for the Linux desktop launcher."
        icon_card = self._card(page, "Icon requirement", icon_title, 2)
        ctk.CTkLabel(
            icon_card,
            text=(
                "Recommended embedded sizes: 16, 24, 32, 48, 64, 128, and 256 pixels. Renaming a PNG to .ico does not convert it."
                if self.target_os == "windows"
                else "Recommended Linux launcher size: a transparent 256×256 or 512×512 PNG, or a scalable SVG."
            ),
            wraplength=850,
            justify="left",
            anchor="w",
            text_color=(SLATE, "#cbd5e1"),
        ).grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")

    def _build_installer_page(self) -> None:
        page = self._new_page("Installer", scroll=True)

        platform_title = "Windows Setup is available on this computer" if self.target_os == "windows" else "Native installer availability"
        platform_description = (
            "Select Windows Setup Installer (.exe) under Build → Output format. Nuitka Studio compiles the application first, then packages it with Inno Setup."
            if self.target_os == "windows"
            else "On Linux, Debian package (.deb) is the native installer. A Windows Setup .exe must be created by running Nuitka Studio on Windows."
        )
        status_card = self._card(page, platform_title, platform_description, 0)
        status_body = ctk.CTkFrame(status_card, fg_color="transparent")
        status_body.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        status_body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            status_body,
            textvariable=self.installer_status_var,
            anchor="w",
            justify="left",
            wraplength=850,
            text_color=(SLATE, "#cbd5e1"),
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            status_body,
            text="Get Inno Setup",
            width=132,
            fg_color=BLUE,
            hover_color=BLUE_HOVER,
            command=lambda: webbrowser.open("https://jrsoftware.org/isdl.php"),
        ).grid(row=0, column=1, padx=(14, 0))

        setup_card = self._card(
            page,
            "Windows Setup settings",
            "These values are reused automatically when Windows Setup Installer (.exe) is selected.",
            1,
        )
        self._entry_row(setup_card, 2, "Publisher", self.installer_publisher_var, "Example: John Edward Dela Cruz")
        self._entry_row(setup_card, 3, "Website", self.installer_website_var, "https://example.com")
        self._path_row(setup_card, 4, "Inno compiler", self.installer_compiler_var, self._choose_installer_compiler, optional=True)
        self._path_row(setup_card, 5, "License file", self.installer_license_var, self._choose_installer_license, optional=True)

        scope_row = ctk.CTkFrame(setup_card, fg_color="transparent")
        scope_row.grid(row=6, column=0, padx=20, pady=5, sticky="ew")
        scope_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(scope_row, text="Install location", width=132, anchor="w").grid(row=0, column=0, padx=(0, 10))
        ctk.CTkOptionMenu(
            scope_row,
            values=["All users (Program Files)", "Current user (no admin)"],
            variable=self.installer_scope_var,
            fg_color=("#e8eef8", "#15253b"),
            button_color=("#cbd5e1", "#25344a"),
            text_color=(NAVY, "white"),
            command=lambda _value: self._refresh_all(),
        ).grid(row=0, column=1, sticky="ew")

        toggle_frame = ctk.CTkFrame(setup_card, fg_color="transparent")
        toggle_frame.grid(row=7, column=0, padx=20, pady=(12, 18), sticky="ew")
        toggle_frame.grid_columnconfigure(0, weight=1)
        installer_toggles = (
            ("Create Start Menu shortcut", self.installer_start_menu_var),
            ("Offer desktop shortcut", self.installer_desktop_shortcut_var),
            ("Offer launch after installation", self.installer_launch_var),
        )
        for row, (label, variable) in enumerate(installer_toggles):
            ctk.CTkLabel(toggle_frame, text=label, anchor="w").grid(row=row, column=0, pady=5, sticky="ew")
            ctk.CTkSwitch(toggle_frame, text="", width=44, variable=variable, command=self._refresh_all).grid(row=row, column=1, pady=5)

        flow_card = self._card(page, "Installer workflow", "Test the compiled application before distributing the setup file.", 2)
        self._info_rows(
            flow_card,
            (
                ("1", "Configure the project", "Choose the Python interpreter, entry script, output location, packages, and resources."),
                ("2", "Select the installer format", "On Windows, choose Build → Output format → Windows Setup Installer (.exe)."),
                ("3", "Compile and package", "Nuitka creates the native application; Inno Setup then creates the professional setup wizard and uninstaller."),
                ("4", "Test on another computer", "Verify installation, shortcuts, application data storage, uninstall behavior, and required external runtimes."),
            ),
        )

    def _build_history_page(self) -> None:
        page = self._new_page("History")
        page.grid_rowconfigure(0, weight=1)
        card = self._card(page, "Recent builds", "The latest 25 build results are stored locally on this computer.", 0)
        card.grid_rowconfigure(3, weight=1)
        toolbar = ctk.CTkFrame(card, fg_color="transparent")
        toolbar.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")
        ctk.CTkButton(toolbar, text="Clear history", width=108, fg_color="#475569", hover_color="#334155", command=self._clear_history).pack(side="right")
        self.history_frame = self._scrollable_frame(card, height=410, fg_color=("#f8fafc", "#0b1729"))
        self.history_frame.grid(row=3, column=0, padx=20, pady=(0, 18), sticky="nsew")
        self.history_frame.grid_columnconfigure(0, weight=1)

    def _build_settings_page(self) -> None:
        page = self._new_page("Settings", scroll=True)
        behavior = self._card(page, "Build behavior", "Defaults applied to every compilation.", 0)
        settings = ctk.CTkFrame(behavior, fg_color="transparent")
        settings.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        settings.grid_columnconfigure(0, weight=1)
        for row, (title, description, variable) in enumerate(
            (
                ("Allow compiler downloads", "Let Nuitka download its supported compiler or tools when required.", self.assume_var),
                ("Remove temporary output", "Delete generated C source and temporary build directories after success.", self.clean_var),
                ("Show compilation progress", "Display module-level progress in the live build output.", self.progress_var),
            )
        ):
            text = ctk.CTkFrame(settings, fg_color="transparent")
            text.grid(row=row, column=0, pady=8, sticky="ew")
            ctk.CTkLabel(text, text=title, font=ctk.CTkFont(weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(text, text=description, text_color=(SLATE, "#94a3b8"), anchor="w").pack(anchor="w")
            ctk.CTkSwitch(settings, text="", width=44, variable=variable, command=self._refresh_all).grid(row=row, column=1, padx=(20, 0))

        performance = self._card(page, "Performance", "Faster defaults for compilation and onefile packaging.", 1)
        performance_body = ctk.CTkFrame(performance, fg_color="transparent")
        performance_body.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        performance_body.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(performance_body, text="Compilation jobs", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, padx=(0, 20), pady=7, sticky="w")
        ctk.CTkOptionMenu(
            performance_body,
            values=["auto", "-2", "8", "4", "2", "1"],
            variable=self.jobs_var,
            command=lambda _value: self._schedule_refresh(0),
        ).grid(row=0, column=1, pady=7, sticky="ew")
        ctk.CTkLabel(
            performance_body,
            text="-2 uses all CPU cores except two, keeping the desktop responsive.",
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, pady=(0, 8), sticky="ew")
        ctk.CTkLabel(performance_body, text="Faster onefile packaging", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=2, column=0, padx=(0, 20), pady=7, sticky="w")
        ctk.CTkSwitch(
            performance_body,
            text="No compression (larger executable)",
            variable=self.onefile_no_compression_var,
            command=self._schedule_refresh,
        ).grid(row=2, column=1, pady=7, sticky="w")
        ctk.CTkButton(
            performance_body,
            text="Apply fast preset",
            width=130,
            command=self._apply_fast_preset,
        ).grid(row=3, column=0, columnspan=2, pady=(12, 0), sticky="w")

        advanced = self._card(page, "Advanced Nuitka arguments", "One complete argument per line. Use only options you understand.", 2)
        self.extra_text = ctk.CTkTextbox(advanced, height=150)
        self.extra_text.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
        if self._extra_argument_lines:
            self.extra_text.insert("1.0", "\n".join(self._extra_argument_lines))
        self.extra_text.bind("<KeyRelease>", lambda _event: self._schedule_refresh())
        ctk.CTkLabel(
            advanced,
            text="Example: --nofollow-import-to=tests",
            text_color=(SLATE, "#94a3b8"),
            anchor="w",
        ).grid(row=3, column=0, padx=20, pady=(0, 18), sticky="ew")

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=3, column=0, pady=12, sticky="ew")
        ctk.CTkButton(actions, text="Save settings", width=120, command=self._save_settings_with_feedback).pack(side="left")
        ctk.CTkButton(actions, text="Restore defaults", width=125, fg_color="#475569", hover_color="#334155", command=self._restore_defaults).pack(side="left", padx=8)
        ctk.CTkButton(
            actions,
            text="Open diagnostics",
            width=135,
            fg_color="#475569",
            hover_color="#334155",
            command=self._open_diagnostics,
        ).pack(side="left")

    def _build_help_page(self) -> None:
        page = self._new_page("How to Use", scroll=True)
        interpreter_hint = (
            "Choose your project's .venv\\Scripts\\python.exe, not a random Python installation."
            if self.target_os == "windows"
            else "Choose your project's .venv/bin/python, not a random Python installation."
        )
        icon_hint = "Use a real multi-size .ico file." if self.target_os == "windows" else "Use a PNG or SVG launcher icon."
        output_term = ".exe" if self.target_os == "windows" else "native Linux executable"
        start = self._card(page, "How to build your application", "Follow these steps in order for the most reliable result.", 0)
        self._info_rows(
            start,
            (
                ("1", "Select the project interpreter", interpreter_hint),
                ("2", "Choose the entry script", "Select the file you normally run to start the program, such as main.py or app.py."),
                ("3", "Choose output and icon", f"Select an output folder. The icon is optional. {icon_hint}"),
                ("4", "Add packages and resources", "Only add missed dynamic packages. Add assets, templates, and static folders under Resources."),
                ("5", "Build in Standalone mode first", f"Run the generated {output_term} from its .dist folder and test every important feature."),
                (
                    "6",
                    "Create the release",
                    "After Standalone works, choose Windows EXE or Windows Setup Installer. Setup output requires Inno Setup 6."
                    if self.target_os == "windows"
                    else "Choose Linux executable (ELF), or Debian package (.deb) for Kali, Parrot, Debian, Ubuntu, and Mint.",
                ),
            ),
        )

        compilers = self._card(page, "Which compiler should I choose?", "Auto is the safest default.", 1)
        compiler_rows = (
            (
                ("A", "Auto — recommended", "Nuitka chooses a compatible compiler available on your computer."),
                ("M", "MSVC", "Use Microsoft Visual Studio 2022 Build Tools. Choose this for Python 3.13 or newer on Windows."),
                ("G", "MinGW64", "Convenient for Python 3.12 and older. It is not supported with Python 3.13 or newer."),
            )
            if self.target_os == "windows"
            else (
                ("A", "Auto — recommended", "Nuitka uses a suitable compiler installed by your Linux distribution."),
                ("G", "GCC", "Use the standard GNU compiler toolchain available on most Linux distributions."),
                ("C", "Clang", "Use Clang when installed; it can help with some GCC-specific build problems."),
            )
        )
        self._info_rows(compilers, compiler_rows)

        problems = self._card(page, "Common problems", "Quick checks before changing many compiler options.", 2)
        self._info_rows(
            problems,
            (
                ("!", "Module not found", "Add only the named dynamic module under Packages, then rebuild."),
                ("!", "Images or templates are missing", "Add their folder under Resources and keep the destination path relative."),
                (
                    "!",
                    "The application closes immediately",
                    "Temporarily use Force console and rebuild to read the error."
                    if self.target_os == "windows"
                    else "Run the generated executable from a terminal to read the runtime error.",
                ),
                ("!", "Build is very large", "Remove unnecessary forced packages and avoid including the entire virtual environment."),
                ("!", "Unexpected interface error", "Open Settings → Open diagnostics and review nuitka-studio.log."),
            ),
        )

        action_row = 3
        if self.target_os == "windows":
            windows_setup = self._card(page, "Creating a Windows Setup installer", "Use this for a professional installation wizard and uninstaller.", 3)
            self._info_rows(
                windows_setup,
                (
                    ("1", "Install Inno Setup 6", "Studio detects ISCC.exe automatically, or you can select it under Installer."),
                    ("2", "Configure the installer", "Open Installer and set publisher, website, license, install scope, and shortcut options."),
                    ("3", "Choose Windows Setup Installer", "Select it under Build configuration → Output format, then click Build setup."),
                ),
            )
            action_row = 4
        elif self.target_os == "linux":
            debian = self._card(page, "Creating a Debian installer", "Use this for Kali, Parrot, Debian, Ubuntu, and Mint.", 3)
            self._info_rows(
                debian,
                (
                    ("1", "Choose Debian package (.deb)", "Select it under Build configuration → Output format."),
                    ("2", "Set package identity", "Open App Identity and confirm Package ID, Maintainer, version, description, and icon."),
                    ("3", "Build and install", "Studio creates package-id_version_arch.deb. Install it from the output folder with sudo apt install ./filename.deb."),
                ),
            )
            action_row = 4

        cross_platform = self._card(
            page,
            "Building for another operating system",
            "Use Cross Build when the target operating system is different from the computer running Nuitka Studio.",
            action_row,
        )
        self._info_rows(
            cross_platform,
            (
                ("1", "Open Cross Build", "Select the project root, Python version, targets, and platform-specific icons."),
                ("2", "Generate the GitHub workflow", "Commit the generated .github/workflows file together with the project source."),
                ("3", "Download native artifacts", "GitHub builds the EXE on Windows and the Linux application on Ubuntu."),
            ),
        )
        action_row += 1

        creator = self._card(
            page,
            "About the creator",
            f"{APP_NAME} is created and maintained by {CREATOR_NAME}.",
            action_row,
        )
        creator_body = ctk.CTkFrame(creator, fg_color="transparent")
        creator_body.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        creator_body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            creator_body,
            text="Explore more applications, websites, and completed projects on MyPortfolioHub.",
            wraplength=760,
            justify="left",
            anchor="w",
            text_color=(SLATE, "#cbd5e1"),
        ).grid(row=0, column=0, padx=(0, 14), sticky="ew")
        ctk.CTkButton(
            creator_body,
            text="Visit myportfoliohub.online",
            width=210,
            command=lambda: webbrowser.open(PORTFOLIO_URL),
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkButton(page, text="Start configuring a build", height=42, width=190, command=lambda: self._show_page("Build")).grid(
            row=action_row + 1, column=0, pady=(12, 28), sticky="w"
        )

    def _build_donate_page(self) -> None:
        page = self._new_page("Donate", scroll=True)
        config = self.donation_config
        kofi_url = config.get("kofi_url", "").strip()
        gcash_name = config.get("gcash_account_name", "").strip()
        gcash_number = config.get("gcash_number", "").strip()
        support_message = config.get("support_message", "").strip() or DONATION_DEFAULTS["support_message"]

        hero = self._card(
            page,
            "Support Nuitka Studio",
            "Donations are optional. The application remains free to use.",
            0,
        )
        hero_body = ctk.CTkFrame(hero, fg_color="transparent")
        hero_body.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")
        hero_body.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            hero_body,
            text=support_message,
            wraplength=900,
            justify="left",
            anchor="w",
            text_color=(SLATE, "#cbd5e1"),
            font=ctk.CTkFont(size=14),
        ).grid(row=0, column=0, padx=(0, 16), sticky="ew")
        ctk.CTkButton(
            hero_body,
            text="View creator portfolio",
            width=180,
            fg_color=("#e8eef8", "#15253b"),
            hover_color=("#dbe5f3", "#243a58"),
            text_color=(NAVY, "white"),
            command=lambda: webbrowser.open(PORTFOLIO_URL),
        ).grid(row=0, column=1, sticky="e")

        providers = ctk.CTkFrame(page, fg_color="transparent")
        providers.grid(row=1, column=0, pady=7, sticky="nsew")
        providers.grid_columnconfigure(0, weight=1, uniform="donation_provider")
        providers.grid_columnconfigure(1, weight=1, uniform="donation_provider")

        kofi = ctk.CTkFrame(
            providers,
            corner_radius=13,
            fg_color=("white", "#0d1828"),
            border_width=1,
            border_color=("#dce3ee", "#25344a"),
        )
        kofi.grid(row=0, column=0, padx=(0, 7), sticky="nsew")
        kofi.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            kofi,
            text="☕",
            width=54,
            height=54,
            corner_radius=14,
            fg_color=("#fff1e8", "#402417"),
            text_color=("#b45309", "#fdba74"),
            font=ctk.CTkFont(size=25, weight="bold"),
        ).grid(row=0, column=0, padx=22, pady=(22, 10), sticky="w")
        ctk.CTkLabel(kofi, text="Ko-fi", font=ctk.CTkFont(size=20, weight="bold"), anchor="w").grid(
            row=1, column=0, padx=22, sticky="ew"
        )
        ctk.CTkLabel(
            kofi,
            text="For international supporters using Ko-fi's available payment options.",
            wraplength=500,
            justify="left",
            anchor="w",
            text_color=(SLATE, "#94a3b8"),
        ).grid(row=2, column=0, padx=22, pady=(5, 14), sticky="ew")
        ctk.CTkLabel(
            kofi,
            text="Ready to accept support" if kofi_url else "Ko-fi link is not configured yet",
            anchor="w",
            text_color=(GREEN if kofi_url else AMBER),
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=3, column=0, padx=22, sticky="ew")
        ctk.CTkButton(
            kofi,
            text="Donate on Ko-fi" if kofi_url else "Ko-fi coming soon",
            height=42,
            state="normal" if kofi_url else "disabled",
            command=self._open_kofi,
        ).grid(row=4, column=0, padx=22, pady=(18, 22), sticky="ew")

        gcash = ctk.CTkFrame(
            providers,
            corner_radius=13,
            fg_color=("white", "#0d1828"),
            border_width=1,
            border_color=("#dce3ee", "#25344a"),
        )
        gcash.grid(row=0, column=1, padx=(7, 0), sticky="nsew")
        gcash.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            gcash,
            text="G",
            width=54,
            height=54,
            corner_radius=14,
            fg_color=("#e8f1ff", "#102c59"),
            text_color=("#145be7", "#93c5fd"),
            font=ctk.CTkFont(size=25, weight="bold"),
        ).grid(row=0, column=0, padx=22, pady=(22, 10), sticky="w")
        ctk.CTkLabel(gcash, text="GCash", font=ctk.CTkFont(size=20, weight="bold"), anchor="w").grid(
            row=1, column=0, padx=22, sticky="ew"
        )
        ctk.CTkLabel(
            gcash,
            text="For supporters in the Philippines. Scan the QR or copy the configured number.",
            wraplength=500,
            justify="left",
            anchor="w",
            text_color=(SLATE, "#94a3b8"),
        ).grid(row=2, column=0, padx=22, pady=(5, 14), sticky="ew")

        gcash_body = ctk.CTkFrame(gcash, fg_color="transparent")
        gcash_body.grid(row=3, column=0, padx=22, pady=(0, 16), sticky="ew")
        gcash_body.grid_columnconfigure(1, weight=1)
        qr_path = self._gcash_qr_path()
        if qr_path is not None:
            try:
                with Image.open(qr_path) as image:
                    qr_image = image.convert("RGB").copy()
                self.gcash_qr_image = ctk.CTkImage(
                    light_image=qr_image,
                    dark_image=qr_image,
                    size=(154, 154),
                )
                ctk.CTkLabel(
                    gcash_body,
                    text="",
                    image=self.gcash_qr_image,
                    width=166,
                    height=166,
                    corner_radius=12,
                    fg_color="white",
                ).grid(row=0, column=0, rowspan=4, padx=(0, 18), sticky="nw")
            except (OSError, ValueError):
                qr_path = None
        if qr_path is None:
            ctk.CTkLabel(
                gcash_body,
                text="GCash QR\nnot configured",
                width=166,
                height=166,
                corner_radius=12,
                fg_color=("#f1f5f9", "#142238"),
                text_color=(SLATE, "#94a3b8"),
                justify="center",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, rowspan=4, padx=(0, 18), sticky="nw")

        ctk.CTkLabel(gcash_body, text="Recipient", text_color=(SLATE, "#94a3b8"), anchor="w").grid(
            row=0, column=1, sticky="sw"
        )
        ctk.CTkLabel(
            gcash_body,
            text=gcash_name or "Not configured",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=1, column=1, pady=(1, 10), sticky="nw")
        ctk.CTkLabel(gcash_body, text="Number", text_color=(SLATE, "#94a3b8"), anchor="w").grid(
            row=2, column=1, sticky="sw"
        )
        ctk.CTkLabel(
            gcash_body,
            text=masked_gcash_number(gcash_number),
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=3, column=1, pady=(1, 0), sticky="nw")

        gcash_actions = ctk.CTkFrame(gcash, fg_color="transparent")
        gcash_actions.grid(row=4, column=0, padx=22, pady=(0, 22), sticky="ew")
        gcash_actions.grid_columnconfigure(0, weight=1)
        gcash_actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            gcash_actions,
            text="Copy GCash number",
            state="normal" if gcash_number else "disabled",
            command=self._copy_gcash_number,
        ).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(
            gcash_actions,
            text="Open QR image",
            state="normal" if qr_path is not None else "disabled",
            fg_color=("#e8eef8", "#15253b"),
            hover_color=("#dbe5f3", "#243a58"),
            text_color=(NAVY, "white"),
            command=self._open_gcash_qr,
        ).grid(row=0, column=1, padx=(5, 0), sticky="ew")

        safety = self._card(
            page,
            "Donate safely",
            "A few checks help ensure your payment reaches the intended recipient.",
            2,
        )
        self._info_rows(
            safety,
            (
                ("1", "Confirm the recipient", "Check the recipient name shown by GCash before sending any amount."),
                ("2", "Keep account credentials private", "Never share an OTP, MPIN, password, or recovery code with anyone."),
                ("3", "Donations are voluntary", "Nuitka Studio features are not locked behind a donation."),
            ),
        )

    def _gcash_qr_path(self) -> Path | None:
        filename = self.donation_config.get("gcash_qr_image", "").strip()
        if not filename:
            return None
        path = asset_path(filename)
        return path if path.is_file() else None

    def _open_kofi(self) -> None:
        url = self.donation_config.get("kofi_url", "").strip()
        if not url:
            messagebox.showinfo("Ko-fi", "The creator has not configured a Ko-fi page yet.")
            return
        if not url.lower().startswith(("https://", "http://")):
            messagebox.showerror("Ko-fi", "The configured Ko-fi link is invalid.")
            return
        webbrowser.open(url)

    def _copy_gcash_number(self) -> None:
        number = self.donation_config.get("gcash_number", "").strip()
        if not number:
            messagebox.showinfo("GCash", "The creator has not configured a GCash number yet.")
            return
        self.clipboard_clear()
        self.clipboard_append(number)
        self.status_var.set("GCash number copied")

    def _open_gcash_qr(self) -> None:
        path = self._gcash_qr_path()
        if path is None:
            messagebox.showinfo("GCash", "The creator has not configured a GCash QR image yet.")
            return
        try:
            webbrowser.open(path.resolve().as_uri())
        except (OSError, ValueError) as exc:
            self.logger.warning("Could not open GCash QR image: %s", exc)
            messagebox.showerror("GCash", f"The QR image could not be opened:\n\n{exc}")

    # ------------------------------------------------------------- action bar
    def _build_action_bar(self) -> None:
        self.action_bar = ctk.CTkFrame(
            self,
            height=94,
            corner_radius=0,
            fg_color=("white", "#0b1422"),
            border_width=1,
            border_color=("#dbe2ec", "#243147"),
        )
        self.action_bar.grid(row=1, column=1, sticky="ew")
        self.action_bar.grid_columnconfigure(0, weight=1)
        status = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        status.grid(row=0, column=0, padx=28, pady=(10, 7), sticky="w")
        self.status_dot = ctk.CTkLabel(
            status,
            text="✓",
            width=30,
            height=30,
            corner_radius=15,
            fg_color=GREEN,
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
        )
        self.status_dot.pack(side="left")
        ctk.CTkLabel(status, textvariable=self.status_var, font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=(10, 0))

        buttons = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        buttons.grid(row=0, column=1, padx=26, pady=(9, 6))
        self.check_button = ctk.CTkButton(
            buttons,
            text="Check setup",
            width=108,
            height=42,
            fg_color="#475569",
            hover_color="#334155",
            command=self._check_setup,
        )
        self.check_button.pack(side="left", padx=(0, 8))
        self.save_button = ctk.CTkButton(
            buttons,
            text="Save preset",
            width=112,
            height=42,
            fg_color=("white", "#15253b"),
            text_color=(NAVY, "white"),
            hover_color=("#e8eef8", "#243a58"),
            border_width=1,
            border_color=("#cbd5e1", "#334155"),
            command=self._save_settings_with_feedback,
        )
        self.save_button.pack(side="left", padx=(0, 8))
        self.open_output_button = ctk.CTkButton(
            buttons,
            text="Show built output",
            width=116,
            height=42,
            fg_color="#475569",
            hover_color="#334155",
            state="disabled",
            command=self._open_output_artifact,
        )
        self.open_output_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            buttons,
            text="Cancel",
            width=84,
            height=42,
            fg_color=RED,
            hover_color="#b91c1c",
            state="disabled",
            command=self._cancel_build,
        )
        self.cancel_button.pack(side="left", padx=(0, 8))
        self.build_button = ctk.CTkButton(
            buttons,
            text="▷  Build application",
            width=168,
            height=42,
            fg_color=BLUE,
            hover_color=BLUE_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_build,
        )
        self.build_button.pack(side="left")

        self.progress_row = ctk.CTkFrame(self.action_bar, fg_color="transparent")
        self.progress_row.grid(row=1, column=0, columnspan=2, padx=28, pady=(0, 9), sticky="ew")
        self.progress_row.grid_columnconfigure(0, weight=1)
        self.build_progress_bar = ctk.CTkProgressBar(
            self.progress_row,
            height=7,
            corner_radius=4,
            fg_color=("#dbe4f0", "#1e293b"),
            progress_color=BLUE,
            mode="determinate",
        )
        self.build_progress_bar.grid(row=0, column=0, padx=(0, 14), sticky="ew")
        self.build_progress_bar.set(0)
        ctk.CTkLabel(
            self.progress_row,
            textvariable=self.progress_detail_var,
            width=260,
            anchor="e",
            text_color=(SLATE, "#94a3b8"),
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=1, sticky="e")
        self.progress_row.grid_remove()

    # ------------------------------------------------------------- UI helpers
    def _card(self, master, title: str, subtitle: str, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            master,
            corner_radius=13,
            fg_color=("white", "#0d1828"),
            border_width=1,
            border_color=("#dce3ee", "#25344a"),
        )
        card.grid(row=row, column=0, pady=7, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16, weight="bold"), anchor="w").grid(
            row=0, column=0, padx=20, pady=(16, 0), sticky="ew"
        )
        ctk.CTkLabel(card, text=subtitle, text_color=(SLATE, "#94a3b8"), anchor="w", wraplength=820, justify="left").grid(
            row=1, column=0, padx=20, pady=(2, 12), sticky="ew"
        )
        return card

    def _path_row(self, master, row, label, variable, command, optional=False) -> None:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        suffix = " (optional)" if optional else ""
        ctk.CTkLabel(frame, text=label + suffix, width=132, anchor="w").grid(row=0, column=0, padx=(0, 10))
        ctk.CTkEntry(frame, textvariable=variable).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(
            frame,
            text="Browse",
            width=76,
            fg_color=("#e8eef8", "#15253b"),
            hover_color=("#dbe5f3", "#243a58"),
            text_color=(NAVY, "white"),
            command=command,
        ).grid(row=0, column=2, padx=(10, 0))

    def _entry_row(self, master, row, label, variable, placeholder="") -> None:
        frame = ctk.CTkFrame(master, fg_color="transparent")
        frame.grid(row=row, column=0, padx=20, pady=5, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, width=132, anchor="w").grid(row=0, column=0, padx=(0, 10))
        ctk.CTkEntry(frame, textvariable=variable, placeholder_text=placeholder).grid(row=0, column=1, sticky="ew")

    def _info_rows(self, card, rows) -> None:
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=2, column=0, padx=20, pady=(0, 18), sticky="ew")
        body.grid_columnconfigure(1, weight=1)
        for row, (badge, title, description) in enumerate(rows):
            ctk.CTkLabel(
                body,
                text=badge,
                width=30,
                height=30,
                corner_radius=15,
                fg_color=("#dbeafe", "#153661"),
                text_color=(BLUE, "#93c5fd"),
                font=ctk.CTkFont(weight="bold"),
            ).grid(row=row, column=0, padx=(0, 12), pady=7, sticky="n")
            text = ctk.CTkFrame(body, fg_color="transparent")
            text.grid(row=row, column=1, pady=7, sticky="ew")
            ctk.CTkLabel(text, text=title, font=ctk.CTkFont(weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(text, text=description, text_color=(SLATE, "#94a3b8"), wraplength=800, justify="left", anchor="w").pack(anchor="w")

    def _show_page(self, name: str) -> None:
        previous_name = self.active_page
        page = self._build_page_if_needed(name)
        # Hide only the previous page. Reconfiguring every existing page on
        # each navigation caused visible redraws and unnecessary Tk work.
        if previous_name != name:
            previous = self.pages.get(previous_name)
            if previous is not None:
                previous.grid_remove()
        page.grid(row=0, column=0, sticky="nsew")
        self.active_page = name
        titles = {
            "Build": ("Build application", "Configure and compile your Python project"),
            "Cross Build": ("Cross-platform builds", "Create native Windows and Linux builds through GitHub Actions"),
            "Packages": ("Packages", "Control dynamic imports and package data"),
            "Resources": ("Resources", "Bundle application assets and runtime files"),
            "App Identity": ("App identity", "Set application metadata and branding"),
            "Installer": ("Installer setup", "Configure Windows Setup packaging and native Linux releases"),
            "History": ("Build history", "Review recent compiler results"),
            "Settings": ("Settings", "Configure default Nuitka behavior"),
            "How to Use": ("How to use Nuitka Studio", f"A guided path from Python project to native {self.target_os.title()} application"),
            "Donate": ("Support development", "Donate securely through Ko-fi or GCash"),
        }
        title, subtitle = titles[name]
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        for page, button in self.nav_buttons.items():
            button.configure(fg_color=BLUE if page == name else "transparent", text_color="white" if page == name else "#dbeafe")
        if name == "History":
            self._refresh_history()
        elif name == "Cross Build":
            self._ensure_cross_project_consistency()
            self._refresh_cross_build_preview(force=True)
        elif name == "Installer":
            # Installer discovery is intentionally deferred until this page is
            # opened (or a Setup build is selected), keeping normal startup
            # and Windows EXE editing free from Program Files scans.
            self._refresh_all()
        if name == "Build":
            self.action_bar.grid()
        else:
            self.action_bar.grid_remove()

    # ------------------------------------------------------------ file dialogs
    def _choose_cross_project_root(self) -> None:
        initial = self.cross_project_root_var.get().strip() or (str(Path(self.script_var.get()).parent) if self.script_var.get().strip() else "")
        path = filedialog.askdirectory(title="Select project root", initialdir=initial or None)
        if path:
            self.cross_project_root_var.set(path)
            self._ensure_cross_project_consistency()

    def _choose_cross_entry_script(self) -> None:
        root_text = self.cross_project_root_var.get().strip()
        initial = root_text or (str(Path(self.script_var.get()).parent) if self.script_var.get().strip() else "")
        path = filedialog.askopenfilename(
            title="Select cross-build entry script",
            initialdir=initial or None,
            filetypes=[("Python scripts", "*.py *.pyw"), ("All files", "*.*")],
        )
        if not path:
            return
        selected = Path(path).expanduser().resolve()
        if root_text and not path_is_inside_project(str(selected), root_text):
            if not messagebox.askyesno(
                "Cross Build",
                "The selected script is outside the current project root.\n\n"
                "Use the script's folder as the new project root?",
            ):
                return
            self.cross_project_root_var.set(str(selected.parent))
            root_text = str(selected.parent)
        elif not root_text:
            self.cross_project_root_var.set(str(selected.parent))
            root_text = str(selected.parent)
        self._apply_entry_script(
            selected,
            project_root=Path(root_text),
            replace_project_paths=True,
            prompt_interpreter=False,
        )
        self.cross_status_var.set(f"Entry script selected: {selected.name}")
        self._cross_workflow_path = None
        self._schedule_refresh(0)

    def _ensure_cross_project_consistency(self) -> None:
        """Keep Cross Build from reusing paths from a previously selected app."""
        root_text = self.cross_project_root_var.get().strip()
        if not root_text:
            return
        root = Path(root_text).expanduser()
        try:
            root = root.resolve()
        except OSError:
            return
        if not root.is_dir():
            return

        current_script = self.script_var.get().strip()
        current_is_valid = bool(
            current_script
            and path_is_inside_project(current_script, str(root))
            and Path(current_script).expanduser().is_file()
        )
        if current_is_valid:
            return

        detected = detect_project_entry_script(root)
        if detected is None:
            if not current_is_valid:
                self.script_var.set("")
            self._clear_external_project_paths(root)
            self._cross_workflow_path = None
            self.cross_status_var.set(
                "No entry script was detected in this project. Select main.py, app.py, run.py, or another Python entry file."
            )
            self._schedule_refresh(0)
            return

        if not current_is_valid or Path(current_script).resolve() != detected.resolve():
            self._apply_entry_script(
                detected,
                project_root=root,
                replace_project_paths=True,
                prompt_interpreter=False,
            )
            self._cross_workflow_path = None
            self.cross_status_var.set(f"Project switched. Detected entry script: {detected.relative_to(root)}")
            self._schedule_refresh(0)

    def _clear_external_project_paths(self, root: Path) -> int:
        """Remove file selections that belong to the previously active project."""
        cleared = 0
        for variable in (
            self.icon_var,
            self.cross_windows_icon_var,
            self.cross_linux_icon_var,
            self.installer_license_var,
        ):
            value = variable.get().strip()
            if value and not path_is_inside_project(value, str(root)):
                variable.set("")
                cleared += 1
        kept_mappings = [
            mapping for mapping in self.data_mappings
            if path_is_inside_project(mapping.source, str(root))
        ]
        cleared += len(self.data_mappings) - len(kept_mappings)
        if len(kept_mappings) != len(self.data_mappings):
            self.data_mappings = kept_mappings
            self._refresh_data_list(refresh=False)
        return cleared

    def _apply_entry_script(
        self,
        path: Path,
        *,
        project_root: Path | None = None,
        replace_project_paths: bool = False,
        prompt_interpreter: bool = True,
    ) -> None:
        """Apply one entry script while keeping project-scoped paths coherent."""
        selected = path.expanduser().resolve()
        root = (project_root or selected.parent).expanduser().resolve()
        self.script_var.set(str(selected))
        if replace_project_paths or not self.cross_project_root_var.get().strip():
            self.cross_project_root_var.set(str(root))
        if replace_project_paths or not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(root / "dist"))
        inferred_name = infer_application_name(selected)
        if replace_project_paths:
            self.application_name_var.set(inferred_name)
            self.output_name_var.set(executable_name(inferred_name, self.target_os))
            self.product_var.set(inferred_name)
            self.package_id_var.set(debian_package_id(inferred_name))
        elif self.application_name_var.get().strip() in {"", "Application"}:
            self.application_name_var.set(inferred_name)
        if replace_project_paths:
            self._clear_external_project_paths(root)

        if not prompt_interpreter:
            return
        detected_python = detect_project_interpreter(selected)
        if detected_python is not None and str(detected_python).lower() != self.python_var.get().lower():
            if messagebox.askyesno(
                "Project environment detected",
                f"Nuitka Studio found this project interpreter:\n\n{detected_python}\n\nUse it for this build?",
            ):
                self.python_var.set(str(detected_python))
                self.python_ready = False
                self.nuitka_ready = False
                self.nuitka_checked = False
                self.nuitka_installed = False
                self.nuitka_issue = ""
                self._check_setup_silent()

    def _choose_cross_windows_icon(self) -> None:
        path = filedialog.askopenfilename(title="Select Windows cross-build icon", filetypes=[("Windows icon", "*.ico"), ("All files", "*.*")])
        if path:
            self.cross_windows_icon_var.set(path)

    def _choose_cross_linux_icon(self) -> None:
        path = filedialog.askopenfilename(title="Select Linux cross-build icon", filetypes=[("Linux icon", "*.png *.svg *.xpm"), ("All files", "*.*")])
        if path:
            self.cross_linux_icon_var.set(path)

    def _cross_targets(self) -> tuple[str, ...]:
        selected = self.cross_target_var.get()
        if selected == "Windows only":
            return ("windows",)
        if selected == "Linux only":
            return ("linux",)
        return ("windows", "linux")

    def _use_current_cross_project(self) -> None:
        script = self.script_var.get().strip()
        if not script:
            messagebox.showwarning("Cross Build", "Select the entry script on the Build page first.")
            return
        self.cross_project_root_var.set(str(Path(script).parent))
        icon = self.icon_var.get().strip()
        if icon.lower().endswith(".ico") and not self.cross_windows_icon_var.get().strip():
            self.cross_windows_icon_var.set(icon)
        elif icon.lower().endswith((".png", ".svg", ".xpm")) and not self.cross_linux_icon_var.get().strip():
            self.cross_linux_icon_var.set(icon)
        self._schedule_refresh(0)

    def _cross_workflow_text(self) -> str:
        return generate_cross_build_workflow(
            self._collect_config(),
            project_root=self.cross_project_root_var.get(),
            python_version=self.cross_python_version_var.get(),
            requirements_file=self.cross_requirements_var.get(),
            targets=self._cross_targets(),
            windows_icon=self.cross_windows_icon_var.get(),
            linux_icon=self.cross_linux_icon_var.get(),
            build_on_push=self.cross_build_on_push_var.get(),
        )

    def _refresh_cross_build_preview(self, *, force: bool = False) -> None:
        """Render the workflow only while its page is visible and data changed."""
        if not hasattr(self, "cross_workflow_preview"):
            return
        if not self._cross_preview_dirty:
            return
        if not force and self.active_page != "Cross Build":
            return
        try:
            workflow = self._cross_workflow_text()
            target_text = self.cross_target_var.get()
            status = f"Ready to generate {target_text.lower()} workflow."
        except (CrossBuildError, ConfigurationError, OSError, ValueError) as exc:
            workflow = f"Complete the cross-build configuration.\n\n{exc}"
            status = str(exc)
        self._cross_preview_dirty = False
        if status != self._last_cross_status_text:
            self.cross_status_var.set(status)
            self._last_cross_status_text = status
        if workflow == self._last_cross_preview_text:
            return
        self.cross_workflow_preview.configure(state="normal")
        self.cross_workflow_preview.delete("1.0", "end")
        self.cross_workflow_preview.insert("1.0", workflow)
        self.cross_workflow_preview.configure(state="disabled")
        self._last_cross_preview_text = workflow

    def _generate_cross_workflow(self) -> None:
        # A project root can be pasted directly into the field, bypassing the
        # Browse callback. Repair any stale entry script from the previous app
        # before validating or writing the workflow.
        self._ensure_cross_project_consistency()
        try:
            workflow = self._cross_workflow_text()
            path = write_cross_build_workflow(workflow, self.cross_project_root_var.get())
        except (CrossBuildError, ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror("Cross Build", str(exc))
            return
        self._cross_workflow_path = path
        self.cross_status_var.set(f"Workflow created: {path}")
        self._last_cross_status_text = self.cross_status_var.get()
        self._cross_preview_dirty = True
        self._refresh_cross_build_preview(force=True)
        self._save_settings()
        messagebox.showinfo(
            "Cross-build workflow created",
            f"Created:\n\n{path}\n\nCommit and push the project to GitHub, then run Nuitka Studio Cross Build under the repository Actions tab.",
        )

    def _open_cross_workflow_folder(self) -> None:
        root = self.cross_project_root_var.get().strip()
        path = self._cross_workflow_path or (Path(root) / ".github" / "workflows" / "nuitka-studio-cross-build.yml" if root else None)
        if path is None or not path.parent.is_dir():
            messagebox.showwarning("Cross Build", "Generate the workflow first.")
            return
        try:
            open_folder(path.parent)
        except OSError as exc:
            messagebox.showerror("Cross Build", str(exc))

    def _open_cross_actions(self) -> None:
        url = self.cross_repo_url_var.get().strip().rstrip("/")
        if url.lower().endswith(".git"):
            url = url[:-4]
        if not re.match(r"^https://github\.com/[^/]+/[^/]+$", url, re.IGNORECASE):
            messagebox.showwarning("GitHub repository", "Enter a repository URL such as https://github.com/owner/repository.")
            return
        webbrowser.open(f"{url}/actions")

    def _copy_cross_workflow(self) -> None:
        text = self.cross_workflow_preview.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Cross-build workflow copied")

    def _choose_installer_compiler(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Inno Setup compiler",
            filetypes=[("Inno Setup Compiler", "ISCC.exe"), ("Executable files", "*.exe"), ("All files", "*.*")],
        )
        if path:
            self.installer_compiler_var.set(path)

    def _choose_installer_license(self) -> None:
        path = filedialog.askopenfilename(
            title="Select installer license file",
            filetypes=[("License documents", "*.txt *.rtf"), ("Text files", "*.txt"), ("Rich text files", "*.rtf"), ("All files", "*.*")],
        )
        if path:
            self.installer_license_var.set(path)

    def _choose_python(self) -> None:
        filetypes = [("Python interpreter", "python.exe"), ("All files", "*.*")] if self.target_os == "windows" else [("All files", "*")]
        path = filedialog.askopenfilename(title="Select Python interpreter", filetypes=filetypes)
        if path:
            self.python_var.set(path)
            self.python_ready = False
            self.nuitka_ready = False
            self.nuitka_checked = False
            self.nuitka_installed = False
            self.nuitka_issue = ""
            self._check_setup_silent()

    def _choose_script(self) -> None:
        path = filedialog.askopenfilename(title="Select entry script", filetypes=[("Python scripts", "*.py *.pyw"), ("All files", "*.*")])
        if path:
            self._apply_entry_script(Path(path))

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self.output_dir_var.set(path)

    def _choose_icon(self) -> None:
        if self.target_os == "windows":
            title, filetypes = "Select Windows icon", [("Windows icon", "*.ico")]
        else:
            title, filetypes = "Select Linux launcher icon", [("Linux icons", "*.png *.svg *.xpm"), ("All files", "*")]
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if path:
            self.icon_var.set(path)

    def _add_data_folder(self) -> None:
        source = filedialog.askdirectory(title="Select data folder")
        if not source:
            return
        destination = self._ask_destination(Path(source).name)
        if destination:
            self._add_data_mapping(DataMapping(source, destination, "dir"))

    def _add_data_file(self) -> None:
        source = filedialog.askopenfilename(title="Select data file")
        if not source:
            return
        destination = self._ask_destination(Path(source).name)
        if destination:
            self._add_data_mapping(DataMapping(source, destination, "file"))

    def _add_data_mapping(self, mapping: DataMapping) -> None:
        if any(
            existing.source == mapping.source
            and existing.destination == mapping.destination
            and existing.kind == mapping.kind
            for existing in self.data_mappings
        ):
            messagebox.showinfo("Resource already added", "That source and destination mapping is already in the project.")
            return
        self.data_mappings.append(mapping)
        self._refresh_data_list()

    def _ask_destination(self, default: str) -> str | None:
        dialog = ctk.CTkInputDialog(title="Resource destination", text=f"Destination inside the app (default: {default}):")
        value = dialog.get_input()
        if value is None:
            return None
        return value.strip() or default

    def _remove_data(self) -> None:
        selected = set(self.data_list.curselection())
        self.data_mappings = [item for index, item in enumerate(self.data_mappings) if index not in selected]
        self._refresh_data_list()

    # ----------------------------------------------------------- configuration
    def _package_format_key(self) -> str:
        selected = self.package_format_var.get()
        if selected == LINUX_DEB_FORMAT:
            return "deb"
        if selected == LINUX_ELF_FORMAT:
            return "elf"
        if selected == WINDOWS_SETUP_FORMAT:
            return "setup"
        return "exe"

    def _text_lines_or_cached(self, attribute: str, cached: list[str]) -> list[str]:
        """Read a lazily-created textbox or its preloaded settings value."""
        widget = getattr(self, attribute, None)
        if widget is None:
            return list(cached)
        return clean_lines(widget.get("1.0", "end"))

    def _collect_config(self) -> BuildConfig:
        return BuildConfig(
            python_executable=self.python_var.get().strip(),
            entry_script=self.script_var.get().strip(),
            output_directory=self.output_dir_var.get().strip(),
            output_filename=self.output_name_var.get().strip(),
            application_name=self.application_name_var.get().strip(),
            target_os=self.target_os,
            package_format=self._package_format_key(),
            package_id=self.package_id_var.get().strip(),
            package_maintainer=self.package_maintainer_var.get().strip(),
            package_section=self.package_section_var.get().strip(),
            mode=self.mode_var.get(),
            console_mode=self.console_var.get(),
            icon_path=self.icon_var.get().strip(),
            compiler=self.compiler_var.get(),
            enable_tk_plugin=self.tk_plugin_var.get(),
            include_customtkinter_data=self.ctk_data_var.get(),
            assume_downloads=self.assume_var.get(),
            remove_output=self.clean_var.get(),
            show_progress=self.progress_var.get(),
            jobs=self.jobs_var.get(),
            onefile_no_compression=self.onefile_no_compression_var.get(),
            packages=self._text_lines_or_cached("packages_text", self._packages_lines),
            package_data=self._text_lines_or_cached("package_data_text", self._package_data_lines),
            data_mappings=list(self.data_mappings),
            extra_arguments=self._text_lines_or_cached("extra_text", self._extra_argument_lines),
            company_name=self.company_var.get(),
            product_name=self.product_var.get(),
            file_description=self.description_var.get(),
            file_version=self.file_version_var.get(),
            product_version=self.product_version_var.get(),
            copyright_text=self.copyright_var.get(),
            installer_publisher=self.installer_publisher_var.get(),
            installer_website=self.installer_website_var.get(),
            installer_scope=("all_users" if self.installer_scope_var.get().startswith("All users") else "current_user"),
            installer_compiler=self.installer_compiler_var.get().strip(),
            installer_license=self.installer_license_var.get().strip(),
            installer_desktop_shortcut=self.installer_desktop_shortcut_var.get(),
            installer_start_menu_shortcut=self.installer_start_menu_var.get(),
            installer_launch_after_install=self.installer_launch_var.get(),
        )

    def _cached_inno_compiler(self) -> Path | None:
        """Avoid repeatedly scanning Program Files while fields are being edited."""
        selected = self.installer_compiler_var.get().strip()
        now = time.monotonic()
        cached = self._installer_compiler_cache
        if cached is not None and cached[0] == selected and now - cached[1] < 20.0:
            return cached[2]
        compiler = find_inno_setup_compiler(selected or None)
        self._installer_compiler_cache = (selected, now, compiler)
        return compiler

    def _refresh_all(self) -> None:
        if not hasattr(self, "terminal_text"):
            return
        config = self._collect_config()
        package_format = self._package_format_key()
        self.summary_mode_var.set(self.mode_var.get().title())
        self.summary_target_var.set(f"{self.target_os.title()} (native)")
        self.summary_format_var.set(self.package_format_var.get())
        self.summary_compiler_var.set(self.compiler_var.get().upper() if self.compiler_var.get() == "msvc" else self.compiler_var.get().title())
        self.summary_application_var.set(self.application_name_var.get().strip() or "Application")
        output_name = normalized_output_filename(config)
        if package_format == "deb":
            version = self.product_version_var.get().strip() or self.file_version_var.get().strip() or "1.0.0.0"
            package_id = self.package_id_var.get().strip() or "application"
            self.summary_output_var.set(f"{package_id}_{version}_<arch>.deb")
        elif package_format == "setup":
            version = self.product_version_var.get().strip() or self.file_version_var.get().strip() or "1.0.0.0"
            self.summary_output_var.set(installer_output_filename(self.application_name_var.get().strip() or "Application", version))
        else:
            self.summary_output_var.set(output_name)

        if self.target_os == "windows":
            should_probe_installer = (
                package_format == "setup"
                or self.active_page == "Installer"
                or bool(self.installer_compiler_var.get().strip())
            )
            if should_probe_installer:
                compiler = self._cached_inno_compiler()
                if compiler is not None:
                    self.installer_status_var.set(f"Inno Setup ready: {compiler}")
                else:
                    self.installer_status_var.set("Inno Setup is not installed or ISCC.exe has not been selected. Windows EXE builds still work; Setup Installer builds require Inno Setup 6.")
            else:
                self.installer_status_var.set("Open Installer setup to check Inno Setup, or select Windows Setup Installer as the output format.")
        else:
            self.installer_status_var.set("Linux provides Debian package (.deb) as the native installer. To create a Windows Setup .exe, run this project in Nuitka Studio on Windows and install Inno Setup 6.")

        if hasattr(self, "build_button"):
            self.build_button.configure(text="▷  Build setup" if package_format == "setup" else "▷  Build application")
        self.summary_jobs_var.set("Auto" if self.jobs_var.get() == "auto" else ("All cores except 2" if self.jobs_var.get() == "-2" else self.jobs_var.get()))

        try:
            command = build_command(config, require_paths=False)
            command_text = display_command(command, self.target_os)
            config_valid = bool(self.application_name_var.get().strip() and self.script_var.get().strip() and self.output_dir_var.get().strip())
        except (ConfigurationError, ValueError) as exc:
            command_text = f"Complete the project configuration.\n\n{exc}"
            config_valid = False

        if self.terminal_mode == "command":
            self._set_terminal_text(command_text)
        self.python_check_var.set("✓ Python detected" if self.python_ready else "○ Python not checked")
        if self.nuitka_ready:
            nuitka_text = "✓ Nuitka ready"
        elif self.nuitka_checked and self.nuitka_installed:
            nuitka_text = "× Nuitka installation needs repair"
        elif self.nuitka_checked:
            nuitka_text = "× Nuitka missing from selected environment"
        else:
            nuitka_text = "○ Nuitka not checked"
        self.nuitka_check_var.set(nuitka_text)
        self.config_check_var.set("✓ Configuration valid" if config_valid else "○ Complete project setup")
        self.python_check_label.configure(text_color=GREEN if self.python_ready else SLATE)
        self.nuitka_check_label.configure(
            text_color=GREEN if self.nuitka_ready else (RED if self.nuitka_checked else SLATE)
        )
        self.config_check_label.configure(text_color=GREEN if config_valid else SLATE)

        if self._active_build is None:
            if self.python_ready and self.nuitka_ready and config_valid:
                self.status_var.set("Ready to compile")
                self.status_dot.configure(fg_color=GREEN, text="✓")
            elif self.python_ready and self.nuitka_checked and not self.nuitka_ready:
                self.status_var.set("Nuitka setup needs attention")
                self.status_dot.configure(fg_color=RED, text="×")
            else:
                self.status_var.set("Setup needs attention")
                self.status_dot.configure(fg_color=AMBER, text="!")

    def _refresh_data_list(self, *, refresh: bool = True) -> None:
        if not hasattr(self, "data_list"):
            if refresh:
                self._refresh_all()
            return
        self.data_list.delete(0, tk.END)
        if not self.data_mappings:
            self.resource_empty_label.place(relx=0.5, rely=0.55, anchor="center")
        else:
            self.resource_empty_label.place_forget()
            for item in self.data_mappings:
                self.data_list.insert(tk.END, f"[{item.kind.upper()}]  {item.source}   →   {item.destination}")
        if refresh:
            self._refresh_all()

    # -------------------------------------------------------------- setup check
    def _check_setup(self) -> None:
        python = self.python_var.get().strip()
        if not Path(python).is_file():
            messagebox.showerror("Setup check", "Select a valid Python interpreter first.")
            return
        if python in self._setup_checks_running:
            self.status_var.set("Setup check already running...")
            return
        self.status_var.set("Checking Python and Nuitka...")
        self.check_button.configure(state="disabled")
        self._setup_checks_running.add(python)
        threading.Thread(target=self._check_setup_worker, args=(python, True), daemon=True).start()

    def _check_setup_silent(self) -> None:
        python = self.python_var.get().strip()
        cached = self._setup_cache.get(python)
        cache_is_fresh = bool(
            cached
            and cached.get("nuitka")
            and time.monotonic() - float(cached.get("checked_at", 0.0)) < 300
        )
        if cache_is_fresh and cached is not None:
            cached = dict(self._setup_cache[python])
            cached["notify"] = False
            self._handle_setup_result(cached)
        elif Path(python).is_file() and python not in self._setup_checks_running:
            self._setup_checks_running.add(python)
            threading.Thread(target=self._check_setup_worker, args=(python, False), daemon=True).start()

    def _check_setup_worker(self, python: str, notify: bool) -> None:
        try:
            result = check_python_environment(python)
            result.update(
                {
                    "python_path": python,
                    "notify": notify,
                    "checked_at": time.monotonic(),
                }
            )
            self.output_queue.put(("setup", result))
        except Exception as exc:
            self.logger.warning("Setup check failed for %s: %s", python, exc)
            self.output_queue.put(("setup_error", {"python_path": python, "message": str(exc), "notify": notify}))

    def _handle_setup_result(self, data: dict) -> None:
        python_path = str(data.get("python_path", self.python_var.get()))
        self._setup_checks_running.discard(python_path)
        self._setup_cache[python_path] = dict(data)
        if python_path != self.python_var.get().strip():
            return
        self.python_ready = bool(data["python"])
        self.nuitka_ready = bool(data["nuitka"])
        self.nuitka_checked = True
        self.nuitka_installed = bool(data.get("nuitka_installed"))
        self.nuitka_issue = str(data.get("nuitka_issue", ""))
        version = str(data["version"]).replace("Python ", "")
        self.environment_var.set(version or "Unknown")
        self.environment_state_var.set("Active" if self.python_ready else "Unavailable")
        self.env_state_label.configure(text_color=GREEN if self.python_ready else RED)
        self.check_button.configure(state="normal")
        self._refresh_all()
        if data["notify"]:
            if self.python_ready and self.nuitka_ready:
                messagebox.showinfo("Setup ready", f"Python {version}\nNuitka {data['nuitka_version']}")
            else:
                command = display_command(nuitka_install_command(python_path), self.target_os)
                issue = self.nuitka_issue or "Nuitka is not ready in the selected environment."
                install_now = messagebox.askyesno(
                    "Nuitka setup required",
                    f"Selected interpreter:\n{python_path}\n\n{issue}\n\n"
                    f"Install or repair Nuitka in this exact environment now?\n\n{command}",
                )
                if install_now:
                    self._install_nuitka(python_path)

    def _install_nuitka(self, python: str) -> None:
        if self._nuitka_install_running:
            return
        self._nuitka_install_running = True
        self.status_var.set("Installing Nuitka in the selected environment...")
        self.check_button.configure(state="disabled")
        threading.Thread(target=self._install_nuitka_worker, args=(python,), daemon=True).start()

    def _install_nuitka_worker(self, python: str) -> None:
        try:
            result = subprocess.run(
                nuitka_install_command(python),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            self.output_queue.put(
                (
                    "nuitka_install",
                    {
                        "python_path": python,
                        "success": result.returncode == 0,
                        "output": output.strip(),
                    },
                )
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.output_queue.put(
                (
                    "nuitka_install",
                    {"python_path": python, "success": False, "output": str(exc)},
                )
            )

    # ------------------------------------------------------------------- build
    def _start_build(self) -> None:
        if self._active_build is not None:
            return
        if not self.python_ready or not self.nuitka_ready:
            messagebox.showwarning(
                "Setup is not ready",
                "The selected Python environment has not passed the setup check. Click Check setup, then try again.",
            )
            return
        try:
            config = self._collect_config()
            command = build_command(config)
            Path(config.output_directory).mkdir(parents=True, exist_ok=True)
        except (ConfigurationError, OSError, ValueError) as exc:
            messagebox.showerror("Build configuration", str(exc))
            return

        if self._uses_studio_environment_for_external_project(config) and not messagebox.askyesno(
            "Check the Python environment",
            "The selected interpreter appears to be Nuitka Studio's private environment, but the entry script belongs to another project. "
            "That project's dependencies may be missing.\n\nContinue anyway?",
        ):
            return

        if not self._preflight_output_directory(Path(config.output_directory)):
            return

        selected_version = self._selected_python_version(config.python_executable)
        if selected_version == (0, 0):
            messagebox.showerror("Python check failed", "The selected interpreter could not report its Python version.")
            return
        if self.target_os == "windows" and config.compiler == "mingw64" and selected_version >= (3, 13):
            messagebox.showerror("Compiler incompatibility", "Python 3.13 or newer cannot use MinGW64 with Nuitka. Select Auto or MSVC.")
            return
        if config.package_format == "deb" and shutil.which("dpkg-deb") is None:
            messagebox.showerror(
                "Debian packaging tool missing",
                "dpkg-deb is required to create a .deb package. Install the dpkg package with your Linux package manager, then try again.",
            )
            return

        resolved_installer_compiler = ""
        if config.package_format == "setup":
            compiler_path = find_inno_setup_compiler(config.installer_compiler or None)
            if compiler_path is None:
                messagebox.showerror(
                    "Inno Setup is required",
                    "Windows Setup Installer needs Inno Setup 6. Install it, or open Installer and select ISCC.exe, then try again.",
                )
                return
            resolved_installer_compiler = str(compiler_path)

        self._save_settings()
        output_name = normalized_output_filename(config)
        self._active_build = {
            "name": config.application_name,
            "mode": config.mode.title(),
            "mode_value": config.mode,
            "console_mode": config.console_mode,
            "target_os": config.target_os,
            "package_format": config.package_format,
            "package_id": config.package_id,
            "package_maintainer": config.package_maintainer,
            "package_section": config.package_section,
            "package_version": config.product_version or config.file_version or "1.0.0.0",
            "package_description": config.file_description or config.application_name,
            "installer_publisher": config.installer_publisher or config.company_name or CREATOR_NAME,
            "installer_website": config.installer_website,
            "installer_scope": config.installer_scope,
            "installer_compiler": resolved_installer_compiler,
            "installer_license": config.installer_license,
            "installer_desktop_shortcut": str(config.installer_desktop_shortcut),
            "installer_start_menu_shortcut": str(config.installer_start_menu_shortcut),
            "installer_launch_after_install": str(config.installer_launch_after_install),
            "entry_script": config.entry_script,
            "icon_path": config.icon_path,
            "output": output_name,
            "output_dir": config.output_directory,
            "started_at": str(time.time()),
        }
        self._cancel_requested = False
        self._packaged_output_file = None
        self._packaged_binary_file = None
        self.open_output_button.configure(state="disabled")
        self.build_log = "=== Build started ===\n" + display_command(command, self.target_os) + "\n\n"
        self.terminal_mode = "log"
        self.terminal_title_var.set("Live build output")
        self.log_toggle_button.configure(text="Command")
        self._set_terminal_text(self.build_log)
        self._set_terminal_expanded(True)
        self.status_var.set("Building application...")
        self.status_dot.configure(fg_color=BLUE, text="•")
        self.build_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.check_button.configure(state="disabled")
        self.build_started_at = time.monotonic()
        self._start_build_progress()
        self.logger.info("Build started: mode=%s output=%s", config.mode, output_name)
        threading.Thread(
            target=self._build_worker,
            args=(command, str(Path(config.entry_script).parent), dict(self._active_build)),
            daemon=True,
        ).start()

    @staticmethod
    def _uses_studio_environment_for_external_project(config: BuildConfig) -> bool:
        return is_private_environment_for_external_project(
            Path(config.python_executable),
            Path(sys.executable),
            Path(sys.prefix),
            Path(config.entry_script),
        )

    def _preflight_output_directory(self, output_directory: Path) -> bool:
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".nuitka-studio-", dir=output_directory):
                pass
            free_bytes = shutil.disk_usage(output_directory).free
        except OSError as exc:
            self.logger.warning("Output preflight failed for %s: %s", output_directory, exc)
            messagebox.showerror("Output folder", f"The output folder is not writable:\n\n{exc}")
            return False

        if free_bytes < MIN_FREE_BUILD_BYTES:
            free_mb = free_bytes // 1_000_000
            return messagebox.askyesno(
                "Low disk space",
                f"Only about {free_mb} MB is free in the output location. Nuitka builds can require substantial temporary space. Continue anyway?",
            )
        return True

    def _start_build_progress(self) -> None:
        for after_id in (self._progress_tick_after_id, self._progress_hide_after_id):
            if after_id is not None:
                try:
                    self.after_cancel(after_id)
                except (ValueError, tk.TclError):
                    pass
        self._progress_tick_after_id = None
        self._progress_hide_after_id = None
        self._build_progress_value = 0.02
        self._build_progress_ceiling = 0.08
        self._build_phase = "Preparing build"
        self.build_progress_bar.configure(progress_color=BLUE)
        self.build_progress_bar.set(self._build_progress_value)
        self.progress_detail_var.set("Preparing build • 00:00 elapsed")
        self.progress_row.grid()
        self._tick_build_progress()

    def _tick_build_progress(self) -> None:
        self._progress_tick_after_id = None
        if self._active_build is None:
            return
        if self._build_progress_value < self._build_progress_ceiling:
            self._build_progress_value = min(
                self._build_progress_ceiling,
                self._build_progress_value + 0.0015,
            )
            self.build_progress_bar.set(self._build_progress_value)
        elapsed = max(0, int(time.monotonic() - self.build_started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.progress_detail_var.set(f"{self._build_phase} • {minutes:02d}:{seconds:02d} elapsed")
        self._progress_tick_after_id = self.after(250, self._tick_build_progress)

    def _update_progress_from_output(self, output: str) -> None:
        if self._active_build is None:
            return
        phase = detect_build_phase(output, self._build_progress_value)
        if phase is None:
            return
        if phase.label == self._build_phase and phase.ceiling <= self._build_progress_ceiling:
            return
        self._build_progress_value = max(self._build_progress_value, phase.start)
        self._build_progress_ceiling = phase.ceiling
        self._build_phase = phase.label
        self.build_progress_bar.set(self._build_progress_value)

    def _finish_build_progress(self, result: str, elapsed: int) -> None:
        if self._progress_tick_after_id is not None:
            try:
                self.after_cancel(self._progress_tick_after_id)
            except (ValueError, tk.TclError):
                pass
            self._progress_tick_after_id = None
        minutes, seconds = divmod(elapsed, 60)
        if result == "Successful":
            self._build_progress_value = 1.0
            self.build_progress_bar.configure(progress_color=GREEN)
            detail = f"Build completed • {minutes:02d}:{seconds:02d}"
        elif result == "Cancelled":
            self.build_progress_bar.configure(progress_color=AMBER)
            detail = f"Build cancelled • {minutes:02d}:{seconds:02d}"
        else:
            self.build_progress_bar.configure(progress_color=RED)
            detail = f"Build failed • {minutes:02d}:{seconds:02d}"
        self.build_progress_bar.set(self._build_progress_value)
        self.progress_detail_var.set(detail)
        self._progress_hide_after_id = self.after(3000, self._hide_build_progress)

    def _hide_build_progress(self) -> None:
        self._progress_hide_after_id = None
        if self._active_build is None:
            self.progress_row.grid_remove()

    def _selected_python_version(self, python: str) -> tuple[int, int]:
        """Read the version from the completed setup probe without blocking Tk."""
        cached = self._setup_cache.get(python, {})
        version = parse_python_version(cached.get("version_info") or cached.get("version"))
        if version[:2] != (0, 0):
            return version[0], version[1]
        fallback = parse_python_version(self.environment_var.get())
        return fallback[0], fallback[1]

    def _stream_process_output(self, process: subprocess.Popen[str]) -> None:
        """Batch verbose output while preserving prompt updates for quiet builds."""
        assert process.stdout is not None
        for batch in iter_batched_text_stream(process.stdout):
            self.output_queue.put(("log", batch))

    def _build_worker(self, command: list[str], cwd: str, snapshot: dict[str, str]) -> None:
        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process_environment = os.environ.copy()
            process_environment.setdefault("PYTHONUTF8", "1")
            process_environment.setdefault("PYTHONUNBUFFERED", "1")
            process_environment.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=process_environment,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            self.process = process
            if self._cancel_requested:
                terminate_process_tree(process)
            self._stream_process_output(process)
            code = process.wait()
            package_format = snapshot.get("package_format")
            if code == 0 and not self._cancel_requested and package_format == "deb":
                self.output_queue.put(("log", "\n=== Creating Debian package ===\n"))
                self.output_queue.put(("package_started", "deb"))
                artifact = find_built_executable(
                    Path(snapshot["output_dir"]),
                    snapshot["output"],
                    Path(snapshot["entry_script"]),
                    snapshot["mode_value"],
                    target_os="linux",
                    built_after=float(snapshot["started_at"]),
                )
                if artifact is None or not is_linux_elf_executable(artifact):
                    raise DebianPackagingError("The new Linux ELF executable could not be verified before packaging.")
                package = build_debian_package(
                    DebianPackageConfig(
                        executable=artifact,
                        output_directory=Path(snapshot["output_dir"]),
                        package_id=snapshot["package_id"],
                        application_name=snapshot["name"],
                        version=snapshot["package_version"],
                        maintainer=snapshot["package_maintainer"],
                        description=snapshot["package_description"],
                        section=snapshot["package_section"],
                        icon_path=Path(snapshot["icon_path"]) if snapshot.get("icon_path") else None,
                        mode=snapshot["mode_value"],
                    )
                )
                self.output_queue.put(("log", f"Created Debian package: {package}\n"))
                self.output_queue.put(("package_complete", {"package": str(package), "binary": str(artifact)}))
            elif code == 0 and not self._cancel_requested and package_format == "setup":
                self.output_queue.put(("log", "\n=== Creating Windows Setup installer ===\n"))
                self.output_queue.put(("package_started", "setup"))
                artifact = find_built_executable(
                    Path(snapshot["output_dir"]),
                    snapshot["output"],
                    Path(snapshot["entry_script"]),
                    snapshot["mode_value"],
                    target_os="windows",
                    built_after=float(snapshot["started_at"]),
                )
                if artifact is None or windows_pe_subsystem(artifact) is None:
                    raise WindowsInstallerError("The newly compiled Windows executable could not be verified before installer packaging.")
                prepared = prepare_windows_installer(
                    WindowsInstallerConfig(
                        executable=artifact,
                        output_directory=Path(snapshot["output_dir"]),
                        application_name=snapshot["name"],
                        version=snapshot["package_version"],
                        publisher=snapshot["installer_publisher"],
                        website=snapshot.get("installer_website", ""),
                        icon_path=Path(snapshot["icon_path"]) if snapshot.get("icon_path") else None,
                        license_path=Path(snapshot["installer_license"]) if snapshot.get("installer_license") else None,
                        mode=snapshot["mode_value"],
                        install_scope=snapshot.get("installer_scope", "all_users"),
                        desktop_shortcut=snapshot.get("installer_desktop_shortcut") == "True",
                        start_menu_shortcut=snapshot.get("installer_start_menu_shortcut") == "True",
                        launch_after_install=snapshot.get("installer_launch_after_install") == "True",
                        compiler_path=Path(snapshot["installer_compiler"]),
                    )
                )
                try:
                    if prepared.output_path.exists():
                        prepared.output_path.unlink()
                    self.output_queue.put(("log", f"Inno Setup script: {prepared.script_path}\n"))
                    installer_process = subprocess.Popen(
                        prepared.command,
                        cwd=str(prepared.temporary_directory),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        env=process_environment,
                        creationflags=creationflags,
                        start_new_session=os.name != "nt",
                    )
                    self.process = installer_process
                    if self._cancel_requested:
                        terminate_process_tree(installer_process)
                    self._stream_process_output(installer_process)
                    code = installer_process.wait()
                    if code == 0 and not self._cancel_requested:
                        if not prepared.output_path.is_file():
                            raise WindowsInstallerError("Inno Setup reported success, but the setup file was not found.")
                        self.output_queue.put(("log", f"Created Windows Setup installer: {prepared.output_path}\n"))
                        self.output_queue.put(("package_complete", {"package": str(prepared.output_path), "binary": str(artifact)}))
                finally:
                    prepared.cleanup()
            self.output_queue.put(("done", code))
        except (OSError, DebianPackagingError, WindowsInstallerError) as exc:
            self.logger.exception("Build or packaging failed")
            self.output_queue.put(("log", f"\nBuild or packaging failed: {exc}\n"))
            self.output_queue.put(("done", -2))

    def _cancel_build(self) -> None:
        if not messagebox.askyesno("Cancel build", "Stop the current Nuitka build and its compiler processes?"):
            return
        self._cancel_requested = True
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Cancelling build...")
        self._build_phase = "Stopping compiler processes"
        self._build_progress_ceiling = self._build_progress_value
        process = self.process
        if process is not None:
            threading.Thread(target=terminate_process_tree, args=(process,), daemon=True).start()

    def _finish_build(self, code: int) -> None:
        elapsed = max(0, round(time.monotonic() - self.build_started_at))
        cancelled = self._cancel_requested
        success = code == 0 and not cancelled
        result = "Cancelled" if cancelled else ("Successful" if success else "Failed")
        self.build_log += f"\n=== Build {result.lower()} (exit code {code}) ===\n"
        self._set_terminal_text(self.build_log)
        snapshot = self._active_build or {
            "name": self.application_name_var.get().strip() or "Application",
            "mode": self.mode_var.get().title(),
            "mode_value": self.mode_var.get(),
            "console_mode": self.console_var.get(),
            "target_os": self.target_os,
            "package_format": self._package_format_key(),
            "entry_script": self.script_var.get(),
            "icon_path": self.icon_var.get(),
            "output": self.summary_output_var.get(),
            "output_dir": self.output_dir_var.get(),
            "started_at": "0",
        }
        history_output = (
            self._packaged_output_file.name
            if snapshot.get("package_format") in {"deb", "setup"} and self._packaged_output_file is not None
            else snapshot["output"]
        )
        self.history.insert(
            0,
            {
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": result,
                "name": snapshot["name"],
                "mode": snapshot["mode"],
                "target": snapshot["target_os"].title(),
                "output": history_output,
                "duration": f"{elapsed}s",
            },
        )
        self.history = self.history[:25]
        self.process = None
        self._active_build = None
        self._cancel_requested = False
        self.build_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.check_button.configure(state="normal")
        if success:
            artifact = self._packaged_binary_file if snapshot.get("package_format") in {"deb", "setup"} else None
            if artifact is None:
                artifact = find_built_executable(
                    Path(snapshot["output_dir"]),
                    snapshot["output"],
                    Path(snapshot["entry_script"]),
                    snapshot["mode_value"],
                    target_os=snapshot["target_os"],
                    built_after=float(snapshot["started_at"]),
                )
            if snapshot.get("package_format") in {"deb", "setup"}:
                self._last_output_file = self._packaged_output_file
            else:
                self._last_output_file = artifact
            self._last_output_dir = self._last_output_file.parent if self._last_output_file is not None else Path(snapshot["output_dir"])
            subsystem = windows_pe_subsystem(artifact) if artifact is not None and snapshot["target_os"] == "windows" else None
            linux_verified = artifact is not None and snapshot["target_os"] == "linux" and is_linux_elf_executable(artifact)
            if snapshot.get("package_format") == "setup" and self._packaged_output_file is not None:
                self._last_linux_launcher = None
                self.status_var.set("Build completed • Windows Setup installer created")
            elif linux_verified and snapshot.get("package_format") == "deb" and self._packaged_output_file is not None:
                self._last_linux_launcher = None
                self.status_var.set("Build completed • Debian package created")
            elif linux_verified:
                try:
                    self._last_linux_launcher = create_linux_desktop_launcher(
                        artifact,
                        snapshot["name"],
                        Path(snapshot["icon_path"]) if snapshot["icon_path"] else None,
                    )
                except OSError as exc:
                    self._last_linux_launcher = None
                    self.logger.warning("Could not create Linux desktop launcher: %s", exc)
                self.status_var.set("Build completed • Linux ELF verified")
            elif snapshot["console_mode"] == "disable" and subsystem == WINDOWS_GUI_SUBSYSTEM:
                self.status_var.set("Build completed • GUI/no-console verified")
            elif snapshot["console_mode"] == "disable" and subsystem == WINDOWS_CONSOLE_SUBSYSTEM:
                self.status_var.set("Build completed • console verification failed")
            else:
                self.status_var.set("Build completed successfully")
            self.status_dot.configure(fg_color=GREEN, text="✓")
            self.open_output_button.configure(state="normal")
        elif cancelled:
            self.status_var.set("Build cancelled")
            self.status_dot.configure(fg_color=AMBER, text="!")
        else:
            self.status_var.set(f"Build failed (exit code {code})")
            self.status_dot.configure(fg_color=RED, text="×")
        self._save_settings()
        self._finish_build_progress(result, elapsed)
        self.logger.info("Build finished: status=%s exit_code=%s duration=%ss", result, code, elapsed)
        if success:
            if self._last_output_file is None:
                messagebox.showwarning(
                    "Build complete",
                    "Nuitka reported success, but Studio could not identify a newly created executable. Open the output folder and verify the newest .dist folder.",
                )
            elif snapshot.get("package_format") == "setup" and self._packaged_output_file is not None:
                messagebox.showinfo(
                    "Build complete — Windows Setup created",
                    f"The Windows application was compiled, verified, and packaged successfully:\n\n{self._packaged_output_file}\n\nTest this installer on another Windows computer before distribution.",
                )
            elif snapshot.get("package_format") == "deb" and self._packaged_output_file is not None:
                messagebox.showinfo(
                    "Build complete — Debian package created",
                    f"The Linux application was compiled, verified, and packaged successfully:\n\n{self._packaged_output_file}\n\nInstall it with:\nsudo apt install ./{self._packaged_output_file.name}",
                )
            elif snapshot["target_os"] == "linux" and is_linux_elf_executable(self._last_output_file):
                messagebox.showinfo(
                    "Build complete — Linux verified",
                    f"The exact new file was verified as an executable Linux ELF binary:\n\n{self._last_output_file}",
                )
            elif snapshot["console_mode"] == "disable" and windows_pe_subsystem(self._last_output_file) == WINDOWS_CONSOLE_SUBSYSTEM:
                messagebox.showwarning(
                    "Console verification failed",
                    f"The new file is a Windows console executable even though Disable was selected:\n\n{self._last_output_file}\n\nReview the build log for an overridden console option.",
                )
            elif snapshot["console_mode"] == "disable" and windows_pe_subsystem(self._last_output_file) == WINDOWS_GUI_SUBSYSTEM:
                messagebox.showinfo(
                    "Build complete — no console verified",
                    f"The exact new EXE was verified as a Windows GUI application:\n\n{self._last_output_file}\n\nIf a terminal appears only while converting a file, an external tool launched by your application is creating it.",
                )
            else:
                messagebox.showinfo("Build complete", f"Your application compiled successfully:\n\n{self._last_output_file}")
        elif not cancelled:
            messagebox.showerror("Build failed", "Review the live build output for the exact Nuitka error. The How to Use page includes common fixes.")

    # --------------------------------------------------------------- terminal
    def _set_terminal_text(self, text: str) -> None:
        if text == self._last_terminal_text:
            return
        self.terminal_text.configure(state="normal")
        self.terminal_text.delete("1.0", "end")
        self.terminal_text.insert("1.0", text)
        self.terminal_text.see("end")
        self.terminal_text.configure(state="disabled")
        self._last_terminal_text = text

    def _append_log(self, text: str) -> None:
        self._update_progress_from_output(text)
        self.build_log += text
        truncated = False
        if len(self.build_log) > MAX_LOG_CHARS:
            self.build_log = "[Older compiler output was trimmed to keep the interface responsive.]\n\n" + self.build_log[-MAX_LOG_CHARS:]
            truncated = True
        if self.terminal_mode == "log":
            if truncated:
                self._set_terminal_text(self.build_log)
            else:
                self.terminal_text.configure(state="normal")
                self.terminal_text.insert("end", text)
                self.terminal_text.see("end")
                self.terminal_text.configure(state="disabled")
                self._last_terminal_text = self.build_log

    def _toggle_terminal(self) -> None:
        if self.terminal_mode == "command":
            self.terminal_mode = "log"
            self.terminal_title_var.set("Build output")
            self.log_toggle_button.configure(text="Command")
            self._set_terminal_text(self.build_log or "No build output yet. Start a build to see the live compiler log.")
        else:
            self.terminal_mode = "command"
            self.terminal_title_var.set("Command preview")
            self.log_toggle_button.configure(text="Build log")
            self._refresh_all()

    def _toggle_terminal_expansion(self) -> None:
        self._set_terminal_expanded(not self._terminal_expanded)

    def _set_terminal_expanded(self, expanded: bool) -> None:
        """Give the live log the full right column when detailed output matters."""
        self._terminal_expanded = expanded
        if expanded:
            self.build_summary_card.grid_remove()
            self.terminal_card.grid_configure(row=0, rowspan=2, pady=0)
            self.terminal_expand_button.configure(text="Show summary")
        else:
            self.terminal_card.grid_configure(row=1, rowspan=1, pady=(14, 0))
            self.build_summary_card.grid()
            self.terminal_expand_button.configure(text="Expand")

    def _copy_terminal(self) -> None:
        text = self.terminal_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied to clipboard")

    # --------------------------------------------------------------- history
    def _refresh_history(self) -> None:
        for child in self.history_frame.winfo_children():
            child.destroy()
        if not self.history:
            ctk.CTkLabel(
                self.history_frame,
                text="No builds yet. Your completed builds will appear here.",
                text_color=(SLATE, "#94a3b8"),
            ).grid(row=0, column=0, padx=20, pady=40)
            return
        for row, item in enumerate(self.history):
            entry = ctk.CTkFrame(self.history_frame, fg_color=("white", "#101f33"), corner_radius=10)
            entry.grid(row=row, column=0, padx=8, pady=5, sticky="ew")
            entry.grid_columnconfigure(2, weight=1)
            status = item.get("status")
            color = GREEN if status == "Successful" else (AMBER if status == "Cancelled" else RED)
            symbol = "✓" if status == "Successful" else ("!" if status == "Cancelled" else "×")
            ctk.CTkLabel(entry, text=symbol, width=30, text_color=color, font=ctk.CTkFont(size=17, weight="bold")).grid(row=0, column=0, padx=(12, 4), pady=12)
            output = item.get("output", executable_name("Application", self.target_os))
            app_name = item.get("name") or Path(output).stem
            ctk.CTkLabel(entry, text=f"{app_name}  •  {output}", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=1, padx=6, sticky="w")
            target = item.get("target", "Windows")
            ctk.CTkLabel(entry, text=f"{target}  •  {item.get('mode', '')}  •  {item.get('duration', '')}", text_color=(SLATE, "#94a3b8"), anchor="w").grid(row=0, column=2, padx=10, sticky="w")
            ctk.CTkLabel(entry, text=item.get("date", ""), text_color=(SLATE, "#94a3b8")).grid(row=0, column=3, padx=14)

    def _clear_history(self) -> None:
        if self.history and messagebox.askyesno("Clear history", "Remove all locally stored build history?"):
            self.history.clear()
            self._refresh_history()
            self._save_settings()

    # -------------------------------------------------------------- persistence
    def _settings_dict(self) -> dict:
        config = self._collect_config()
        data = config.__dict__.copy()
        data["data_mappings"] = [item.__dict__ for item in config.data_mappings]
        data["history"] = self.history
        data["settings_schema"] = SETTINGS_SCHEMA
        data["appearance_mode"] = ctk.get_appearance_mode().lower()
        data["cross_project_root"] = self.cross_project_root_var.get()
        data["cross_python_version"] = self.cross_python_version_var.get()
        data["cross_requirements_file"] = self.cross_requirements_var.get()
        data["cross_target"] = self.cross_target_var.get()
        data["cross_windows_icon"] = self.cross_windows_icon_var.get()
        data["cross_linux_icon"] = self.cross_linux_icon_var.get()
        data["cross_build_on_push"] = self.cross_build_on_push_var.get()
        data["cross_repository_url"] = self.cross_repo_url_var.get()
        return data

    def _save_settings(self) -> bool:
        try:
            data = self._settings_dict()
            signature = settings_signature(data)
            if signature == self._last_saved_settings_signature:
                return True
            atomic_write_json(settings_path(), data)
            self._last_saved_settings_signature = signature
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.logger.warning("Could not save settings: %s", exc)
            return False

    def _save_settings_with_feedback(self) -> None:
        if self._save_settings():
            self.status_var.set("Preset saved")
            messagebox.showinfo("Preset saved", "Your project configuration and preferences were saved locally.")
        else:
            messagebox.showerror("Save failed", "The preset could not be saved. Open diagnostics for the local error log.")

    def _apply_fast_preset(self) -> None:
        self.jobs_var.set("-2")
        self.progress_var.set(False)
        self.onefile_no_compression_var.set(True)
        self.status_var.set("Fast build preset applied")
        self._schedule_refresh(0)

    def _load_settings(self) -> None:
        path = settings_path()
        if not path.is_file():
            self._refresh_data_list(refresh=False)
            self._last_saved_settings_signature = settings_signature(self._settings_dict())
            return
        needs_persist = False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Settings root must be an object")
            old_schema = int(data.get("settings_schema", 1))
            appearance = str(data.get("appearance_mode", "light")).lower()
            if appearance in {"light", "dark"} and appearance != ctk.get_appearance_mode().lower():
                ctk.set_appearance_mode(appearance)
            variable_map = {
                "python_executable": self.python_var,
                "entry_script": self.script_var,
                "output_directory": self.output_dir_var,
                "application_name": self.application_name_var,
                "package_id": self.package_id_var,
                "package_maintainer": self.package_maintainer_var,
                "package_section": self.package_section_var,
                "output_filename": self.output_name_var,
                "icon_path": self.icon_var,
                "mode": self.mode_var,
                "console_mode": self.console_var,
                "compiler": self.compiler_var,
                "enable_tk_plugin": self.tk_plugin_var,
                "include_customtkinter_data": self.ctk_data_var,
                "assume_downloads": self.assume_var,
                "remove_output": self.clean_var,
                "show_progress": self.progress_var,
                "jobs": self.jobs_var,
                "onefile_no_compression": self.onefile_no_compression_var,
                "company_name": self.company_var,
                "product_name": self.product_var,
                "file_description": self.description_var,
                "file_version": self.file_version_var,
                "product_version": self.product_version_var,
                "copyright_text": self.copyright_var,
                "installer_publisher": self.installer_publisher_var,
                "installer_website": self.installer_website_var,
                "installer_compiler": self.installer_compiler_var,
                "installer_license": self.installer_license_var,
                "installer_desktop_shortcut": self.installer_desktop_shortcut_var,
                "installer_start_menu_shortcut": self.installer_start_menu_var,
                "installer_launch_after_install": self.installer_launch_var,
                "cross_project_root": self.cross_project_root_var,
                "cross_python_version": self.cross_python_version_var,
                "cross_requirements_file": self.cross_requirements_var,
                "cross_target": self.cross_target_var,
                "cross_windows_icon": self.cross_windows_icon_var,
                "cross_linux_icon": self.cross_linux_icon_var,
                "cross_build_on_push": self.cross_build_on_push_var,
                "cross_repository_url": self.cross_repo_url_var,
            }
            for key, variable in variable_map.items():
                if key in data:
                    variable.set(data[key])
            saved_format = str(data.get("package_format", "exe" if self.target_os == "windows" else "elf"))
            if self.target_os == "windows":
                self.package_format_var.set(WINDOWS_SETUP_FORMAT if saved_format == "setup" else WINDOWS_EXE_FORMAT)
            else:
                self.package_format_var.set(LINUX_DEB_FORMAT if saved_format == "deb" else LINUX_ELF_FORMAT)
            saved_scope = str(data.get("installer_scope", "all_users"))
            self.installer_scope_var.set("Current user (no admin)" if saved_scope == "current_user" else "All users (Program Files)")
            saved_target = str(data.get("target_os", "windows"))
            if saved_target != self.target_os:
                needs_persist = True
                self.python_var.set(sys.executable)
                self.output_name_var.set(executable_name(self.application_name_var.get(), self.target_os))
                self.icon_var.set("")
                self.console_var.set("disable" if self.target_os == "windows" else "native")
                self.compiler_var.set("auto")
                self.package_format_var.set(WINDOWS_EXE_FORMAT if self.target_os == "windows" else LINUX_ELF_FORMAT)
            if old_schema < 5:
                previous_output = self.output_name_var.get().strip() or "Application.exe"
                previous_product = self.product_var.get().strip()
                self.application_name_var.set(previous_product or Path(previous_output).stem or "Application")
            if old_schema < SETTINGS_SCHEMA:
                needs_persist = True
                # v2.0 emitted a large progress stream that could starve the
                # Tk event loop. Migrate existing users to the faster default.
                self.progress_var.set(False)
                self.jobs_var.set("-2")
                self.onefile_no_compression_var.set(True)
            self._packages_lines = clean_lines(data.get("packages", []))
            self._package_data_lines = clean_lines(data.get("package_data", []))
            self._extra_argument_lines = clean_lines(data.get("extra_arguments", []))
            self.data_mappings = [DataMapping(**item) for item in data.get("data_mappings", [])]
            self.history = list(data.get("history", []))[:25]
            self._last_application_name = self.application_name_var.get().strip()
            self._last_generated_output_name = executable_name(self._last_application_name, self.target_os)
            self._last_generated_package_id = debian_package_id(self._last_application_name)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            needs_persist = True
            self.status_var.set("Saved settings could not be loaded")
            self.logger.warning("Settings file is invalid: %s", exc)
            backup = path.with_name(f"settings.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
            try:
                os.replace(path, backup)
                self.logger.info("Moved invalid settings to %s", backup)
            except OSError as backup_error:
                self.logger.warning("Could not preserve invalid settings: %s", backup_error)
        self._refresh_data_list(refresh=False)
        if not needs_persist:
            self._last_saved_settings_signature = settings_signature(self._settings_dict())

    def _restore_defaults(self) -> None:
        if not messagebox.askyesno("Restore defaults", "Reset build options and metadata? Project paths and history will be kept."):
            return
        self.mode_var.set("standalone")
        self.console_var.set("disable" if self.target_os == "windows" else "native")
        self.compiler_var.set("auto")
        self.package_format_var.set(WINDOWS_EXE_FORMAT if self.target_os == "windows" else LINUX_ELF_FORMAT)
        self.package_id_var.set(debian_package_id(self.application_name_var.get()))
        self.package_maintainer_var.set(CREATOR_NAME)
        self.package_section_var.set("utils")
        self.tk_plugin_var.set(True)
        self.ctk_data_var.set(False)
        self.clean_var.set(True)
        self.assume_var.set(True)
        self.progress_var.set(False)
        self.jobs_var.set("-2")
        self.onefile_no_compression_var.set(True)
        self.company_var.set("")
        self.product_var.set("")
        self.description_var.set("")
        self.copyright_var.set("")
        self.installer_publisher_var.set(CREATOR_NAME)
        self.installer_website_var.set(PORTFOLIO_URL)
        self.installer_scope_var.set("All users (Program Files)")
        self.installer_compiler_var.set("")
        self.installer_license_var.set("")
        self.installer_desktop_shortcut_var.set(True)
        self.installer_start_menu_var.set(True)
        self.installer_launch_var.set(True)
        self.cross_python_version_var.set(f"{sys.version_info.major}.{sys.version_info.minor}")
        self.cross_requirements_var.set("requirements.txt")
        self.cross_target_var.set("Windows + Linux")
        self.cross_windows_icon_var.set("")
        self.cross_linux_icon_var.set("")
        self.cross_build_on_push_var.set(False)
        self.cross_repo_url_var.set("")
        self.file_version_var.set("1.0.0.0")
        self.product_version_var.set("1.0.0.0")
        self.extra_text.delete("1.0", "end")
        self._refresh_all()
        self._save_settings()

    def _open_output_artifact(self) -> None:
        file_path = self._last_output_file
        directory = self._last_output_dir
        if file_path is None and (directory is None or not directory.is_dir()):
            messagebox.showwarning("Output folder", "No completed build output folder is available yet.")
            return
        try:
            if file_path is not None and file_path.is_file():
                reveal_file(file_path)
            elif directory is not None:
                open_folder(directory)
        except OSError as exc:
            self.logger.warning("Could not reveal build output: %s", exc)
            messagebox.showerror("Output folder", f"The system could not open the output folder:\n\n{exc}")

    def _open_diagnostics(self) -> None:
        try:
            open_folder(app_data_dir())
        except OSError as exc:
            self.logger.warning("Could not open diagnostics folder: %s", exc)
            messagebox.showerror("Diagnostics", f"Could not open the diagnostics folder:\n\n{app_data_dir()}\n\n{exc}")

    def _handle_tk_exception(self, exception_type, exception, traceback_object) -> None:
        self.logger.error(
            "Unhandled interface error",
            exc_info=(exception_type, exception, traceback_object),
        )
        messagebox.showerror(
            "Unexpected error",
            "Nuitka Studio encountered an unexpected interface error. Your settings were preserved. Open Settings → Open diagnostics for details.",
        )

    # -------------------------------------------------------------- event loop
    def _drain_output(self) -> None:
        """Process bounded, batched output without starving Tk's event loop."""
        log_parts: list[str] = []
        events: list[tuple[str, object]] = []
        started = time.perf_counter()
        processed = 0

        while processed < 120 and time.perf_counter() - started < 0.006:
            try:
                kind, value = self.output_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            if kind == "log":
                log_parts.append(str(value))
            else:
                events.append((kind, value))

        if log_parts:
            self._append_log("".join(log_parts))

        for kind, value in events:
            if kind == "done":
                self._finish_build(int(value))
            elif kind == "package_started":
                self._build_phase = "Creating Windows Setup installer" if value == "setup" else "Creating Debian package"
                self._build_progress_value = max(self._build_progress_value, 0.94)
                self._build_progress_ceiling = 0.99
                self.build_progress_bar.set(self._build_progress_value)
            elif kind == "package_complete":
                package_data = value  # type: ignore[assignment]
                self._packaged_output_file = Path(str(package_data["package"]))
                self._packaged_binary_file = Path(str(package_data["binary"]))
            elif kind == "nuitka_install":
                install_data = value  # type: ignore[assignment]
                self._nuitka_install_running = False
                python_path = str(install_data.get("python_path", ""))
                if install_data.get("success"):
                    self._setup_cache.pop(python_path, None)
                    if python_path == self.python_var.get().strip():
                        self.status_var.set("Nuitka installed • verifying setup...")
                        self.check_button.configure(state="normal")
                        self._check_setup()
                    else:
                        self.check_button.configure(state="normal")
                else:
                    self.check_button.configure(state="normal")
                    output = str(install_data.get("output", "")).strip()
                    details = output[-3000:] if output else "The installer did not return an error message."
                    self.status_var.set("Nuitka installation failed")
                    messagebox.showerror(
                        "Nuitka installation failed",
                        f"Could not install Nuitka in:\n{python_path}\n\n{details}",
                    )
            elif kind == "setup":
                self._handle_setup_result(value)  # type: ignore[arg-type]
            elif kind == "setup_error":
                data = value  # type: ignore[assignment]
                self._setup_checks_running.discard(str(data.get("python_path", "")))
                self.python_ready = False
                self.nuitka_ready = False
                self.nuitka_checked = True
                self.nuitka_installed = False
                self.nuitka_issue = str(data.get("message", "Setup check failed."))
                self.check_button.configure(state="normal")
                self._refresh_all()
                if data.get("notify"):
                    messagebox.showerror("Setup check", f"The setup check failed:\n\n{data.get('message')}")

        self.after(30 if not self.output_queue.empty() else 120, self._drain_output)

    def _toggle_theme(self) -> None:
        current = ctk.get_appearance_mode()
        ctk.set_appearance_mode("dark" if current == "Light" else "light")
        self._save_settings()

    def _on_close(self) -> None:
        if self._closing:
            return
        if self._active_build is not None and not messagebox.askyesno("Exit", "A build is running. Exit and stop it?"):
            return
        self._closing = True
        # Remove the window immediately, then finish cleanup without making
        # the user wait for process-tree termination or a settings fsync.
        try:
            self.withdraw()
            self.update_idletasks()
        except tk.TclError:
            pass
        if self._active_build is not None:
            self._cancel_requested = True
        process = self.process
        if process is not None and process.poll() is None:
            threading.Thread(
                target=terminate_process_tree,
                args=(process, 1.25),
                name="nuitka-studio-shutdown",
                daemon=False,
            ).start()
        self.process = None
        self._save_settings()
        self.logger.info("Application closed")
        self.destroy()


def main() -> None:
    set_windows_app_user_model_id()
    create_windows_app_mutexes()
    app = NuitkaStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
