import time
import argparse
import numpy as np
import warnings
import yaml
import os
import openslide

from PIL import Image
from pathlib import Path
from functools import partial
from opm.patch_manager import PatchManager
from opm.utils import tissue_mask, alpha_channel_check, patch_size_check

Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore")

#
# 1) Custom header support
# 2) Replace , with :
# 3) Refactor config to yaml
# 4) Replace path multilation with os.path.join()



def generate_initial_mask(slide_path, scale):
    """
    Helper method to generate random coordinates within a slide
    :param slide_path: Path to slide (str)
    :param num_patches: Number of patches you want to generate
    :return: list of n (x,y) coordinates
    """
    # Open slide and get properties
    slide = openslide.open_slide(slide_path)
    slide_dims = slide.dimensions

    # Call thumbnail for effiency, calculate scale relative to whole slide
    slide_thumbnail = np.asarray(slide.get_thumbnail((slide_dims[0] // scale, slide_dims[1] // scale)))
    real_scale = (slide_dims[0] / slide_thumbnail.shape[1], slide_dims[1] / slide_thumbnail.shape[0])

    return tissue_mask(slide_thumbnail), real_scale


if __name__ == '__main__':
    start = time.time()
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input_path',
                        dest='input_path',
                        help="input path for the tissue",
                        required=True)
    parser.add_argument('-n', '--num_patches',
                        type=int,
                        dest='num_patches',
                        help="Number of patches to mine. Set to -1 to mine until saturation. ",
                        required=True)
    parser.add_argument('-c', '--config',
                        type=str,
                        dest='config',
                        help="config.yml for running OPM. ",
                        required=True)
    parser.add_argument('-lm', '--label_map_path',
                        dest='label_map_path',
                        help="input path for the label mask")
    parser.add_argument('-o', '--output_path',
                        dest='output_path', default=None,
                        help="output path for the patches")
    parser.add_argument('-ocsv', '--output_csv',
                        dest='output_csv', default=None,
                        help="output path for the csv.")
    parser.add_argument('-icsv', '--input_csv',
                        dest='input_csv', default=None,
                        help="CSV with x,y coordinates of patches to mine.")
    parser.add_argument('-t', '--threads',
                        dest='threads',
                        help="number of threads, by default will use all")

    args = parser.parse_args()
    if args.output_path is None:
        do_save_patches = False
        out_dir = ""
    else:
        if not os.path.exists(args.output_path):
            print("Output Directory does not exist, we are creating one for you.")
            Path(args.output_path).mkdir(parents=True, exist_ok=True)

        do_save_patches = True
        out_dir = os.path.abspath(args.output_path)
        if not out_dir.endswith("/"):
            out_dir += "/"
    # Path to openslide supported file (.svs, .tiff, etc.)
    slide_path = os.path.abspath(args.input_path)

    if not os.path.exists(slide_path):
        raise ValueError("Could not find the slide, could you recheck the path?")

    # Create new instance of slide manager
    manager = PatchManager(slide_path)
    cfg = yaml.load(open(args.config), Loader=yaml.FullLoader)

    if args.input_csv is None:
        # Generate an initial validity mask
        mask, scale = generate_initial_mask(args.input_path, cfg['scale'])
        manager.set_valid_mask(mask, scale)
        manager.set_label_map(args.label_map_path)

        # Reject patch if any pixels are transparent
        manager.add_patch_criteria(alpha_channel_check)
        # Reject patch if image dimensions are not equal to PATCH_SIZE
        patch_dims_check = partial(patch_size_check, patch_height=cfg['patch_size'][0], patch_width=cfg['patch_size'][1])
        manager.add_patch_criteria(patch_dims_check)
        # Save patches releases saves all patches stored in manager, dumps to specified output file
        manager.mine_patches(out_dir, output_csv=args.output_csv, config=cfg)
        print("Total time: {}".format(time.time() - start))
    else:
        manager.save_predefined_patches(out_dir, patch_coord_csv=args.input_csv, config=cfg)

