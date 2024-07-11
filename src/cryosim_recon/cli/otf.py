import logging
import sys

from ..main import sim_psf_to_otf
from .parsing import parse_otf_args


def sim_otf():
    namespace, otf_kwargs = parse_otf_args(*sys.argv[1:])
    logging.basicConfig(level=logging.DEBUG if namespace.verbose else logging.INFO)

    sim_psf_to_otf(
        namespace.config_path,
        *namespace.psf_paths,
        output_directory=namespace.output_directory,
        overwrite=namespace.overwrite,
        cleanup=namespace.cleanup,
        **otf_kwargs,
    )


if __name__ == "__main__":
    sim_otf()
