from __future__ import annotations

import logging
from pathlib import Path
import numpy as np
import tifffile as tf
from typing import TYPE_CHECKING

from ..info import __version__

if TYPE_CHECKING:
    from typing import Any
    from os import PathLike
    from numpy.typing import NDArray
    from .dataclasses import ImageChannel


logger = logging.getLogger(__name__)


def read_tiff(filepath: str | PathLike[str]) -> NDArray[Any]:
    with tf.TiffFile(filepath) as tiff:
        return tiff.asarray()


def get_combined_array_from_tiffs(
    *file_paths: str | PathLike[str],
) -> NDArray[Any]:
    logger.debug(
        "Combining tiffs from:\n%s",
        "\n\t".join(str(fp) for fp in file_paths),
    )
    return np.stack(tuple(tf.memmap(fp).squeeze() for fp in file_paths), -3)  # type: ignore


def write_tiff(
    output_path: str | PathLike[str],
    *channels: ImageChannel,
    pixel_size_microns: float | None = None,
    ome: bool = True,
    overwrite: bool = False,
) -> None:
    def get_channel_dict(channel: ImageChannel) -> None:
        channel_dict: dict[str, Any] = {}
        if channel.wavelengths.excitation_nm is not None:
            channel_dict["ExcitationWavelength"] = channel.wavelengths.excitation_nm
            channel_dict["ExcitationWavelengthUnits"] = "nm"
        if channel.wavelengths.emission_nm is not None:
            channel_dict["EmissionWavelength"] = channel.wavelengths.emission_nm
            channel_dict["EmissionWavelengthUnits"] = "nm"
        return channel_dict

    output_path = Path(output_path)

    logger.debug("Writing array to %s", output_path)

    if output_path.is_file():
        if overwrite:
            logger.warning("Overwriting file %s", output_path)
            output_path.unlink()
        else:
            raise FileExistsError(f"File {output_path} already exists")

    tiff_kwargs: dict[str, Any] = {
        "software": f"PySIMRecon {__version__}",
        "photometric": "MINISBLACK",
        "metadata": {},
    }

    if pixel_size_microns is not None:

        # TIFF tags:
        tiff_kwargs["resolution"] = (1e4 / pixel_size_microns, 1e4 / pixel_size_microns)
        tiff_kwargs["resolutionunit"] = (
            tf.RESUNIT.CENTIMETER
        )  # Use CENTIMETER for maximum compatibility

    if ome:
        if pixel_size_microns is not None:
            # OME PhysicalSize:
            tiff_kwargs["metadata"]["PhysicalSizeX"] = pixel_size_microns
            tiff_kwargs["metadata"]["PhysicalSizeY"] = pixel_size_microns
            tiff_kwargs["metadata"]["PhysicalSizeXUnit"] = "µm"
            tiff_kwargs["metadata"]["PhysicalSizeYUnit"] = "µm"

    with tf.TiffWriter(
        output_path,
        mode="x",  # New files only
        bigtiff=True,
        ome=ome,
        shaped=not ome,
    ) as tiff:
        for channel in channels:
            channel_kwargs = tiff_kwargs.copy()
            channel_kwargs["metadata"]["axes"] = (
                "YX" if channel.array.ndim == 2 else "ZYX"
            )
            if ome:
                channel_kwargs["metadata"]["Channel"] = get_channel_dict(channel)
            tiff.write(channel.array, **channel_kwargs)
