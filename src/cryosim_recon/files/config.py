from __future__ import annotations
import logging
from pathlib import Path
from os.path import abspath
from configparser import RawConfigParser, NoOptionError
from typing import TYPE_CHECKING, Any

from ..settings import WavelengthSettings
from ..settings.formatting import OTF_FORMATTERS, RECON_FORMATTERS

if TYPE_CHECKING:
    from typing import Literal, override
    from os import PathLike
    from collections.abc import Generator

logger = logging.getLogger(__name__)

__CONFIGS_SECTION = "configs"
__DEFAULTS_KEY = "defaults"
__OTF_LOCATIONS_SECTION = "otfs"
__PARSER_KWARGS = {"inline_comment_prefixes": "#;"}
__DIRECTORY_KEY = "directory"
__RECON_CONFIG_SECTION = "recon config"
__OTF_CONFIG_SECTION = "otf config"


def read_config(input_config: str | PathLike[str]) -> RawConfigParser:
    config_parser = RawConfigParser(**__PARSER_KWARGS)  # type: ignore[call-overload]
    config_parser.read(input_config)
    return config_parser


def _parse_wavelength_key(key: str) -> int:
    key = key.strip().lower()
    if key.endswith("nm"):
        logger.debug("Trimming 'nm' from %s", key)
        # Handle nm endings but not other units
        key = key[:-2].strip()
    return int(key)


def _handle_paths_from_config(
    key: str | int, path_str: str, directory: str
) -> tuple[int | str, Path]:
    try:
        path = Path(path_str.strip())
        if (
            not path.is_absolute() and directory
        ):  # Ignore if directory is an empty string
            path = Path(directory) / path

        # If directory is not specified, an absolute path is required
        if not path.is_file():
            raise FileNotFoundError(f"No {key} file found for at {path}")
        # Ensure returned path is absolute
        return key, path.absolute()
    except Exception as e:
        logger.warning("%s file path error: %s", key, e)


@override
def _get_paths_from_section(
    section_name: str,
    config_parser: RawConfigParser,
    *,
    subkey: str,
    defaults_section: Literal[True],
) -> dict[int | str, dict[str, Path]]: ...


@override
def _get_paths_from_section(
    section_name: str,
    config_parser: RawConfigParser,
    *,
    subkey: None,
    defaults_section: Literal[True],
) -> dict[int | str, Path]: ...


@override
def _get_paths_from_section(
    section_name: str,
    config_parser: RawConfigParser,
    *,
    subkey: str,
    defaults_section: Literal[False],
) -> dict[int, dict[str, Path]]: ...


@override
def _get_paths_from_section(
    section_name: str,
    config_parser: RawConfigParser,
    *,
    subkey: None,
    defaults_section: Literal[False],
) -> dict[int, Path]: ...


def _get_paths_from_section(
    section_name: str,
    config_parser: RawConfigParser,
    *,
    defaults_section: bool = False,
) -> dict[int | str, Path | dict[str, Path]]:
    dictionary = {}
    directory = config_parser.get(section_name, __DIRECTORY_KEY, fallback="").strip()
    for key, path_str in config_parser.items(section_name):
        key = key.strip()
        if key == __DIRECTORY_KEY:
            # Ignore __DIRECTORY_KEY
            continue
        if not defaults_section or key != __DEFAULTS_KEY:
            try:
                key = _parse_wavelength_key(key)
            except Exception:
                logger.warning(
                    "'%s' is not a valid wavelength (must be an integer)", key
                )
                continue
        key, path = _handle_paths_from_config(key, path_str, directory)
        dictionary[key] = path
    return dictionary


def get_defaults_config_path(main_config: RawConfigParser) -> Path:
    directory = main_config.get(__CONFIGS_SECTION, __DIRECTORY_KEY, fallback="").strip()
    path_str = main_config.get(__CONFIGS_SECTION, __DEFAULTS_KEY).strip()
    return _handle_paths_from_config(__DEFAULTS_KEY, path_str, directory)


def get_wavelength_settings(
    main_config: RawConfigParser,
) -> Generator[WavelengthSettings, None, None]:
    configs_dict = _get_paths_from_section(
        __CONFIGS_SECTION,
        main_config,
        subkey=__CONFIGS_SECTION,
        defaults_section=False,
    )
    otfs_dict = _get_paths_from_section(
        __OTF_LOCATIONS_SECTION,
        main_config,
        subkey=__OTF_LOCATIONS_SECTION,
        defaults_section=False,
    )

    wavelengths = set(configs_dict.keys())
    wavelengths.update(otfs_dict.keys())

    for wavelength in wavelengths:
        if wavelength in configs_dict:
            wavelength_config = read_config(configs_dict[wavelength])
            # Get per-wavelength recon kwargs
            recon_kwargs = get_recon_kwargs(wavelength_config)
            # Get per-wavelength otf kwargs:
            otf_kwargs = get_otf_kwargs(wavelength_config)
        else:
            recon_kwargs = {}
            otf_kwargs = {}

        otf_path = otfs_dict.get(wavelength, None)

        yield WavelengthSettings(
            wavelength,
            otf=otf_path,
            reconstruction_config=recon_kwargs,
            otf_config=otf_kwargs,
        )


def create_wavelength_config(
    output_path: str | PathLike[str],
    otf_path: str | PathLike[str],
    **config_kwargs: Any,
) -> Path:
    # Add otf_file that is expected by ReconParams
    config_kwargs["otf_file"] = str(abspath(otf_path))
    # Convert to string so it can be written without a section, like sirecon expects
    text = ""
    for key, value in config_kwargs.items():
        if isinstance(value, (tuple, list)):
            # Comma separated values
            value = ",".join(str(i) for i in value)
        text += f"{key}={value}\n"

    with open(output_path, "w") as f:
        f.write(text)
    return Path(output_path)


def get_recon_kwargs(
    config_parser: RawConfigParser,
) -> dict[str, str]:
    return _config_section_to_dict(
        config_parser, section_name=__RECON_CONFIG_SECTION, settings_for="recon"
    )


def get_otf_kwargs(
    config_parser: RawConfigParser,
) -> dict[str, str]:
    return _config_section_to_dict(
        config_parser, section_name=__OTF_CONFIG_SECTION, settings_for="otf"
    )


def _config_section_to_dict(
    config_parser: RawConfigParser,
    section_name: str,
    settings_for: Literal["otf", "recon"],
):
    kwargs = {}
    if settings_for == "otf":
        formatters = OTF_FORMATTERS
    elif settings_for == "recon":
        formatters = RECON_FORMATTERS
    else:
        raise TypeError(
            '_config_section_to_dict argument "settings_for" only accepts "otf" or "recon"'
        )

    for key, value in config_parser.items(section_name):
        if value is None or key not in formatters:
            logger.debug("Option %s=%s is invalid and will be ignored", key, value)
            formatters
        setting_format = formatters.get(key)
        if setting_format is None:
            logger.warning("Invalid setting %s=%s will be ignored", key, value)
            continue
        if setting_format.count > 1:
            kwargs[key] = tuple(
                setting_format.conv(s.strip())
                for s in value.split(",", maxsplit=setting_format.count - 1)
                if s.strip()
            )
        else:
            kwargs[key] = setting_format.conv(value.strip())
    return kwargs
